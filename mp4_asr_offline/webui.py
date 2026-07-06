from __future__ import annotations

import json
import locale
import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


APP_TITLE = "MP4 ASR Offline WebUI"
DEFAULT_PORT = 8765
DEFAULT_CHUNK_SIZE = "30"


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def cli_command(config_path: Path) -> list[str]:
    base_dir = app_dir()
    candidates = [
        base_dir / "mp4_asr_offline.exe",
        base_dir / "mp4_asr_offline" / "mp4_asr_offline.exe",
    ]
    for exe in candidates:
        if exe.exists():
            return [str(exe), "--config", str(config_path)]
    return [sys.executable, str(base_dir / "mp4_asr_offline.py"), "--config", str(config_path)]


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def decode_output_line(line: bytes) -> str:
    for encoding in ("utf-8", locale.getpreferredencoding(False), "gbk"):
        try:
            return line.decode(encoding)
        except UnicodeDecodeError:
            continue
    return line.decode("utf-8", errors="replace")


def parse_simple_yaml(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key: str | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith("- ") and current_key:
            data.setdefault(current_key, []).append(stripped[2:].strip())
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key, value = key.strip(), value.strip()
        if not value:
            data[key] = []
            current_key = key
        else:
            low = value.lower()
            if low in {"true", "false"}:
                data[key] = low == "true"
            else:
                data[key] = value
            current_key = None
    return data


def default_config() -> dict[str, Any]:
    cfg = parse_simple_yaml(read_text_if_exists(app_dir() / "config.yaml"))
    return {
        "inputs": "\n".join(cfg.get("inputs") or []),
        "output_dir": cfg.get("output_dir") or "",
        "capswriter_dir": cfg.get("capswriter_dir") or "",
        "model_dir": "" if isinstance(cfg.get("model_dir"), list) else (cfg.get("model_dir") or ""),
        "recursive": cfg.get("recursive", True),
        "overwrite": cfg.get("overwrite", False),
        "use_dml": cfg.get("use_dml", False),
        "vulkan": cfg.get("vulkan", False),
        "chunk_size": cfg.get("chunk_size", DEFAULT_CHUNK_SIZE),
        "mp3_bitrate": cfg.get("mp3_bitrate", "192k"),
    }


def yaml_from_payload(payload: dict[str, Any]) -> str:
    inputs = [line.strip() for line in str(payload.get("inputs", "")).splitlines() if line.strip()]
    lines = ["inputs:"]
    lines.extend(f"  - {item}" for item in inputs)
    lines.extend(
        [
            f"output_dir: {payload.get('output_dir', '')}",
            f"capswriter_dir: {payload.get('capswriter_dir', '')}",
            f"model_dir: {payload.get('model_dir', '')}",
            f"recursive: {str(bool(payload.get('recursive', True))).lower()}",
            f"overwrite: {str(bool(payload.get('overwrite', False))).lower()}",
            "language: Chinese",
            f"use_dml: {str(bool(payload.get('use_dml', False))).lower()}",
            f"vulkan: {str(bool(payload.get('vulkan', False))).lower()}",
            f"chunk_size: {payload.get('chunk_size') or DEFAULT_CHUNK_SIZE}",
            f"mp3_bitrate: {payload.get('mp3_bitrate') or '192k'}",
            "",
        ]
    )
    return "\n".join(lines)


class JobState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.process: subprocess.Popen[bytes] | None = None
        self.config_path: Path | None = None
        self.output_dir: Path | None = None
        self.progress_path: Path | None = None
        self.progress_offset = 0
        self.logs: list[str] = []
        self.records: list[dict[str, Any]] = []
        self.started_at: float | None = None
        self.returncode: int | None = None
        self.error: str | None = None

    def is_running(self) -> bool:
        with self.lock:
            return self.process is not None and self.process.poll() is None

    def append_log(self, line: str) -> None:
        with self.lock:
            self.logs.append(line.rstrip("\n"))
            self.logs = self.logs[-500:]

    def start(self, payload: dict[str, Any]) -> None:
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise RuntimeError("已有任务正在运行")

            output_dir = Path(str(payload.get("output_dir") or "")).expanduser()
            if not output_dir:
                raise RuntimeError("请填写输出目录")
            output_dir.mkdir(parents=True, exist_ok=True)

            state_dir = app_dir() / "webui_state"
            state_dir.mkdir(parents=True, exist_ok=True)
            self.config_path = state_dir / f"run_{time.strftime('%Y%m%d_%H%M%S')}.yaml"
            self.config_path.write_text(yaml_from_payload(payload), encoding="utf-8")
            self.output_dir = output_dir.resolve()
            self.progress_path = self.output_dir / "progress.jsonl"
            self.progress_offset = self.progress_path.stat().st_size if self.progress_path.exists() else 0
            self.logs = []
            self.records = []
            self.returncode = None
            self.error = None
            self.started_at = time.time()

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            command = cli_command(self.config_path)
            self.logs.append("> " + " ".join(command))
            self.process = subprocess.Popen(
                command,
                cwd=str(app_dir()),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
            )
            threading.Thread(target=self._read_stdout, daemon=True).start()

    def stop(self) -> None:
        with self.lock:
            proc = self.process
        if proc is not None and proc.poll() is None:
            try:
                proc.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
            except Exception:
                proc.terminate()

    def _read_stdout(self) -> None:
        proc = self.process
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            self.append_log(decode_output_line(line))
        code = proc.wait()
        with self.lock:
            self.returncode = code
            self.logs.append(f"> process exited with code {code}")

    def _read_progress(self) -> None:
        with self.lock:
            path = self.progress_path
            offset = self.progress_offset
        if path is None or not path.exists():
            return
        try:
            with path.open("rb") as f:
                f.seek(offset)
                data = f.read()
                new_offset = f.tell()
        except OSError as exc:
            with self.lock:
                self.error = str(exc)
            return
        if not data:
            return
        text = data.decode("utf-8", errors="replace")
        new_records: list[dict[str, Any]] = []
        for line in text.splitlines():
            try:
                new_records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        with self.lock:
            self.progress_offset = new_offset
            self.records.extend(new_records)
            self.records = self.records[-2000:]

    def snapshot(self) -> dict[str, Any]:
        self._read_progress()
        with self.lock:
            latest: dict[str, dict[str, Any]] = {}
            for rec in self.records:
                key = rec.get("input") or rec.get("mp3") or str(len(latest))
                latest[str(key)] = rec

            total = len([rec for rec in latest.values() if rec.get("status") != "queued"]) or len(latest)
            done_states = {"done", "skipped", "failed"}
            finished = sum(1 for rec in latest.values() if rec.get("status") in done_states)
            active_percent = 0.0
            active = None
            for rec in reversed(self.records):
                if rec.get("status") not in done_states:
                    active = rec
                    active_percent = float(rec.get("percent") or 0)
                    break
            overall = 0
            if total:
                overall = int(min(100, ((finished + active_percent / 100.0) / total) * 100))

            proc = self.process
            running = proc is not None and proc.poll() is None
            return {
                "running": running,
                "returncode": self.returncode,
                "started_at": self.started_at,
                "elapsed_sec": round(time.time() - self.started_at, 1) if self.started_at else 0,
                "output_dir": str(self.output_dir or ""),
                "progress_path": str(self.progress_path or ""),
                "overall_percent": overall,
                "total_files": total,
                "finished_files": finished,
                "active": active,
                "latest": list(latest.values())[-200:],
                "logs": self.logs[-300:],
                "error": self.error,
            }


JOB = JobState()


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MP4 ASR Offline</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d9dee7;
      --text: #1d2430;
      --muted: #637083;
      --accent: #1f7a6b;
      --accent-2: #315f9f;
      --danger: #b42318;
      --shadow: 0 1px 3px rgba(18, 25, 38, .08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      letter-spacing: 0;
    }
    header {
      padding: 18px 24px;
      background: #ffffff;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    h1 { margin: 0; font-size: 20px; font-weight: 650; }
    main {
      padding: 20px 24px 28px;
      display: grid;
      grid-template-columns: minmax(360px, 520px) minmax(480px, 1fr);
      gap: 18px;
      align-items: start;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .section-head {
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      font-weight: 650;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }
    .content { padding: 16px; }
    label { display: block; font-size: 13px; color: var(--muted); margin: 0 0 6px; }
    input, textarea, select {
      width: 100%;
      border: 1px solid #c8d0dc;
      border-radius: 6px;
      padding: 9px 10px;
      font: inherit;
      font-size: 14px;
      background: #fff;
      color: var(--text);
    }
    textarea { min-height: 96px; resize: vertical; line-height: 1.45; }
    .field { margin-bottom: 14px; }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .check-row { display: flex; gap: 16px; flex-wrap: wrap; margin: 8px 0 16px; }
    .check-row label { display: inline-flex; align-items: center; gap: 7px; margin: 0; color: var(--text); }
    input[type="checkbox"] { width: 16px; height: 16px; }
    .actions { display: flex; gap: 10px; align-items: center; }
    button {
      border: 1px solid transparent;
      border-radius: 6px;
      padding: 9px 14px;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
      background: #eef2f6;
      color: var(--text);
    }
    button.primary { background: var(--accent); color: white; }
    button.danger { background: #fff2f0; color: var(--danger); border-color: #f2b8b5; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    .status-bar {
      height: 12px;
      background: #e8edf3;
      border-radius: 999px;
      overflow: hidden;
      border: 1px solid #dae1eb;
    }
    .status-fill {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      transition: width .25s ease;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin: 14px 0;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      min-height: 62px;
    }
    .metric b { display: block; font-size: 18px; margin-top: 4px; }
    .muted { color: var(--muted); font-size: 13px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { border-bottom: 1px solid #e6ebf2; padding: 8px 6px; text-align: left; vertical-align: top; }
    th { color: var(--muted); font-weight: 650; background: #fafbfc; position: sticky; top: 0; }
    .table-wrap { max-height: 260px; overflow: auto; border: 1px solid var(--line); border-radius: 8px; }
    pre {
      margin: 0;
      background: #101820;
      color: #d7e3f1;
      padding: 12px;
      border-radius: 8px;
      max-height: 300px;
      overflow: auto;
      font-size: 12px;
      line-height: 1.45;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .path { max-width: 360px; word-break: break-all; }
    .badge {
      display: inline-block;
      padding: 2px 7px;
      border-radius: 999px;
      background: #edf4ff;
      color: #27548a;
      font-size: 12px;
      font-weight: 650;
    }
    @media (max-width: 980px) {
      main { grid-template-columns: 1fr; padding: 14px; }
      header { padding: 14px; align-items: flex-start; flex-direction: column; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <header>
    <h1>MP4 ASR Offline</h1>
    <span class="muted">中文普通话 · MP4/MP3 · 本地离线 · 进度可视化</span>
  </header>
  <main>
    <section>
      <div class="section-head">任务参数 <span class="badge">Chinese</span></div>
      <div class="content">
        <div class="field">
          <label for="inputs">视频或音频文件/目录，每行一个（支持 .mp4/.mp3）</label>
          <textarea id="inputs" spellcheck="false"></textarea>
        </div>
        <div class="field">
          <label for="output_dir">输出目录</label>
          <input id="output_dir" spellcheck="false" />
        </div>
        <div class="field">
          <label for="capswriter_dir">CapsWriter-Offline 根目录</label>
          <input id="capswriter_dir" spellcheck="false" />
        </div>
        <div class="field">
          <label for="model_dir">Qwen3-ASR 模型目录，可留空</label>
          <input id="model_dir" spellcheck="false" />
        </div>
        <div class="grid-2">
          <div class="field">
            <label for="chunk_size">分段秒数</label>
            <input id="chunk_size" type="number" min="10" step="5" />
          </div>
          <div class="field">
            <label for="mp3_bitrate">MP3 码率</label>
            <select id="mp3_bitrate">
              <option>128k</option>
              <option selected>192k</option>
              <option>256k</option>
              <option>320k</option>
            </select>
          </div>
        </div>
        <div class="check-row">
          <label><input id="recursive" type="checkbox" /> 递归扫描</label>
          <label><input id="overwrite" type="checkbox" /> 覆盖已有结果</label>
          <label><input id="use_dml" type="checkbox" /> DirectML</label>
          <label><input id="vulkan" type="checkbox" /> Vulkan</label>
        </div>
        <div class="actions">
          <button class="primary" id="startBtn">启动任务</button>
          <button class="danger" id="stopBtn">停止</button>
          <span id="message" class="muted"></span>
        </div>
      </div>
    </section>

    <section>
      <div class="section-head">运行进度 <span id="runState" class="badge">idle</span></div>
      <div class="content">
        <div class="status-bar"><div id="bar" class="status-fill"></div></div>
        <div class="metrics">
          <div class="metric"><span class="muted">总进度</span><b id="overall">0%</b></div>
          <div class="metric"><span class="muted">文件</span><b id="files">0/0</b></div>
          <div class="metric"><span class="muted">耗时</span><b id="elapsed">0s</b></div>
          <div class="metric"><span class="muted">阶段</span><b id="phase">-</b></div>
        </div>
        <div class="field">
          <label>当前文件</label>
          <div id="activeFile" class="muted path">-</div>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>状态</th><th>百分比</th><th>文件</th><th>错误</th></tr></thead>
            <tbody id="records"></tbody>
          </table>
        </div>
        <div class="field" style="margin-top:14px">
          <label>控制台日志</label>
          <pre id="logs"></pre>
        </div>
      </div>
    </section>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);

    function payload() {
      return {
        inputs: $("inputs").value,
        output_dir: $("output_dir").value,
        capswriter_dir: $("capswriter_dir").value,
        model_dir: $("model_dir").value,
        recursive: $("recursive").checked,
        overwrite: $("overwrite").checked,
        use_dml: $("use_dml").checked,
        vulkan: $("vulkan").checked,
        chunk_size: $("chunk_size").value,
        mp3_bitrate: $("mp3_bitrate").value
      };
    }

    async function loadDefaults() {
      const res = await fetch("/api/defaults");
      const cfg = await res.json();
      for (const key of ["inputs","output_dir","capswriter_dir","model_dir","chunk_size","mp3_bitrate"]) {
        if ($(key)) $(key).value = cfg[key] || "";
      }
      for (const key of ["recursive","overwrite","use_dml","vulkan"]) {
        $(key).checked = !!cfg[key];
      }
    }

    async function startJob() {
      $("message").textContent = "";
      const res = await fetch("/api/start", {method:"POST", body: JSON.stringify(payload())});
      const data = await res.json();
      $("message").textContent = data.ok ? "任务已启动" : data.error;
      poll();
    }

    async function stopJob() {
      await fetch("/api/stop", {method:"POST"});
      $("message").textContent = "已请求停止";
    }

    function filename(path) {
      if (!path) return "-";
      return path.split(/[\\/]/).pop();
    }

    async function poll() {
      const res = await fetch("/api/status");
      const s = await res.json();
      $("runState").textContent = s.running ? "running" : (s.returncode === null ? "idle" : "exit " + s.returncode);
      $("overall").textContent = `${s.overall_percent || 0}%`;
      $("bar").style.width = `${s.overall_percent || 0}%`;
      $("files").textContent = `${s.finished_files || 0}/${s.total_files || 0}`;
      $("elapsed").textContent = `${s.elapsed_sec || 0}s`;
      const active = s.active || {};
      $("phase").textContent = active.status || "-";
      $("activeFile").textContent = active.input || "-";
      $("logs").textContent = (s.logs || []).join("\n");
      $("logs").scrollTop = $("logs").scrollHeight;
      const rows = (s.latest || []).slice().reverse().map(rec => `
        <tr>
          <td><span class="badge">${rec.status || ""}</span></td>
          <td>${rec.percent ?? ""}${rec.chunk ? ` · ${rec.chunk}/${rec.chunks}` : ""}</td>
          <td class="path">${filename(rec.input)}</td>
          <td class="path">${rec.error || ""}</td>
        </tr>`).join("");
      $("records").innerHTML = rows || `<tr><td colspan="4" class="muted">暂无进度</td></tr>`;
      $("startBtn").disabled = !!s.running;
      $("stopBtn").disabled = !s.running;
    }

    $("startBtn").addEventListener("click", startJob);
    $("stopBtn").addEventListener("click", stopJob);
    loadDefaults().then(poll);
    setInterval(poll, 1500);
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "MP4ASRWebUI/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/defaults":
            self.send_json(default_config())
        elif path == "/api/status":
            self.send_json(JOB.snapshot())
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_json({"ok": False, "error": "请求 JSON 无法解析"}, 400)
            return
        if path == "/api/start":
            try:
                JOB.start(payload)
                self.send_json({"ok": True})
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, 400)
        elif path == "/api/stop":
            JOB.stop()
            self.send_json({"ok": True})
        else:
            self.send_error(404)


def main() -> int:
    port = int(os.environ.get("MP4_ASR_WEBUI_PORT") or DEFAULT_PORT)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"{APP_TITLE} running at {url}")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWebUI stopped")
    finally:
        JOB.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
