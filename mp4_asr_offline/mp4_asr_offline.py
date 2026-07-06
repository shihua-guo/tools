from __future__ import annotations

import argparse
import json
import logging.handlers
import math
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ASR_FRONTEND = "qwen3_asr_encoder_frontend.fp16.onnx"
ASR_BACKEND = "qwen3_asr_encoder_backend.fp16.onnx"
ASR_LLM = "qwen3_asr_llm.q4_k.gguf"
ALIGNER_FRONTEND = "qwen3_aligner_encoder_frontend.int4.onnx"
ALIGNER_BACKEND = "qwen3_aligner_encoder_backend.int4.onnx"
ALIGNER_LLM = "qwen3_aligner_llm.q4_k.gguf"
DLL_HANDLES: list[Any] = []
DEFAULT_CHUNK_SIZE = 30.0
MAX_CHUNK_SIZE = 40.0


@dataclass
class AppConfig:
    inputs: list[Path] = field(default_factory=list)
    output_dir: Path | None = None
    capswriter_dir: Path | None = None
    model_dir: Path | None = None
    recursive: bool = True
    overwrite: bool = False
    language: str = "Chinese"
    use_dml: bool = False
    vulkan: bool = False
    chunk_size: float = DEFAULT_CHUNK_SIZE
    mp3_bitrate: str = "192k"


class ConfigError(RuntimeError):
    pass


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value[0:1] in {"'", '"'} and value[-1:] == value[0]:
        return value[1:-1]
    low = value.lower()
    if low in {"true", "yes", "on"}:
        return True
    if low in {"false", "no", "off"}:
        return False
    if low in {"null", "none", "~"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part.strip()) for part in inner.split(",")]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def load_simple_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"配置文件不存在: {path}")

    data: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            if current_list_key is None:
                raise ConfigError(f"YAML 列表项没有对应字段: {raw}")
            if not isinstance(data.get(current_list_key), list):
                data[current_list_key] = []
            data[current_list_key].append(parse_scalar(stripped[2:]))
            continue
        if ":" not in stripped:
            raise ConfigError(f"无法解析配置行: {raw}")
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            data[key] = None
            current_list_key = key
        else:
            data[key] = parse_scalar(value)
            current_list_key = None
    return data


def as_path(value: Any) -> Path | None:
    if value is None or value == "":
        return None
    if isinstance(value, list) and not value:
        return None
    return Path(str(value)).expanduser()


def config_from_dict(data: dict[str, Any]) -> AppConfig:
    cfg = AppConfig()
    inputs = data.get("inputs", [])
    if isinstance(inputs, (str, Path)):
        inputs = [inputs]
    cfg.inputs = [Path(str(item)).expanduser() for item in inputs if str(item).strip()]
    cfg.output_dir = as_path(data.get("output_dir"))
    cfg.capswriter_dir = as_path(data.get("capswriter_dir"))
    cfg.model_dir = as_path(data.get("model_dir"))

    for key in ("recursive", "overwrite", "use_dml", "vulkan"):
        if key in data and data[key] is not None:
            setattr(cfg, key, bool(data[key]))
    if data.get("language"):
        cfg.language = str(data["language"])
    if data.get("chunk_size"):
        cfg.chunk_size = float(data["chunk_size"])
    if data.get("mp3_bitrate"):
        cfg.mp3_bitrate = str(data["mp3_bitrate"])
    return cfg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="离线 MP4 转 MP3 并用 CapsWriter Qwen3-ASR 转写文字")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--input", action="append", dest="inputs", help="MP4 来源目录，可重复传入")
    parser.add_argument("--output", dest="output_dir", help="统一输出目录")
    parser.add_argument("--capswriter-dir", help="CapsWriter-Offline 根目录")
    parser.add_argument("--model-dir", help="Qwen3-ASR-1.7B 模型目录")
    parser.add_argument("--overwrite", action="store_true", help="重新生成已有输出")
    parser.add_argument("--no-recursive", action="store_true", help="不递归扫描输入目录")
    parser.add_argument("--language", help="转写语言，默认 Chinese")
    parser.add_argument("--use-dml", action="store_true", help="启用 DirectML")
    parser.add_argument("--vulkan", action="store_true", help="启用 Vulkan")
    parser.add_argument("--chunk-size", type=float, help="ASR 分段秒数")
    parser.add_argument("--dry-run", action="store_true", help="只扫描和校验配置，不转换")
    return parser.parse_args()


def merge_cli(cfg: AppConfig, args: argparse.Namespace) -> AppConfig:
    if args.inputs:
        cfg.inputs = [Path(item).expanduser() for item in args.inputs]
    if args.output_dir:
        cfg.output_dir = Path(args.output_dir).expanduser()
    if args.capswriter_dir:
        cfg.capswriter_dir = Path(args.capswriter_dir).expanduser()
    if args.model_dir:
        cfg.model_dir = Path(args.model_dir).expanduser()
    if args.overwrite:
        cfg.overwrite = True
    if args.no_recursive:
        cfg.recursive = False
    if args.language:
        cfg.language = args.language
    if args.use_dml:
        cfg.use_dml = True
    if args.vulkan:
        cfg.vulkan = True
    if args.chunk_size:
        cfg.chunk_size = args.chunk_size
    return cfg


def resolve_config(cfg: AppConfig) -> AppConfig:
    if not cfg.inputs:
        raise ConfigError("请在配置文件 inputs 或命令行 --input 中指定至少一个视频目录")
    if cfg.output_dir is None:
        raise ConfigError("请在配置文件 output_dir 或命令行 --output 中指定输出目录")
    if cfg.capswriter_dir is None:
        raise ConfigError("请指定 capswriter_dir 或 --capswriter-dir")
    cfg.inputs = [p.resolve() for p in cfg.inputs]
    cfg.output_dir = cfg.output_dir.resolve()
    cfg.capswriter_dir = cfg.capswriter_dir.resolve()
    if cfg.model_dir is None:
        cfg.model_dir = cfg.capswriter_dir / "models" / "Qwen3-ASR" / "Qwen3-ASR-1.7B"
    cfg.model_dir = cfg.model_dir.resolve()
    if cfg.chunk_size <= 0:
        raise ConfigError("chunk_size 必须大于 0")
    if cfg.chunk_size > MAX_CHUNK_SIZE:
        raise ConfigError(
            f"chunk_size 不能超过 {MAX_CHUNK_SIZE:g} 秒。Qwen3-ASR 的 llama.cpp 后端在更长分段下容易触发 "
            "GGML_ASSERT(n_tokens_all <= cparams.n_batch)，请改为 30 或 40。"
        )
    if cfg.language.lower() != "chinese":
        raise ConfigError("当前工具仅支持中文普通话识别，请将 language 设置为 Chinese")
    return cfg


def validate_config(cfg: AppConfig) -> None:
    missing_inputs = [str(p) for p in cfg.inputs if not p.exists() or not (p.is_dir() or p.is_file())]
    if missing_inputs:
        raise ConfigError("输入路径不存在: " + "; ".join(missing_inputs))
    if not cfg.capswriter_dir.exists():
        raise ConfigError(f"CapsWriter-Offline 目录不存在: {cfg.capswriter_dir}")
    if not (cfg.capswriter_dir / "internal").exists():
        raise ConfigError(f"CapsWriter-Offline 缺少 internal 目录: {cfg.capswriter_dir}")
    if not (cfg.capswriter_dir / "util").exists():
        raise ConfigError(f"CapsWriter-Offline 缺少 util 目录: {cfg.capswriter_dir}")
    for filename in (ASR_FRONTEND, ASR_BACKEND, ASR_LLM, ALIGNER_FRONTEND, ALIGNER_BACKEND, ALIGNER_LLM):
        if not (cfg.model_dir / filename).exists():
            raise ConfigError(f"模型目录缺少 {filename}: {cfg.model_dir}")
    for exe in ("ffmpeg.exe", "ffprobe.exe"):
        if not (app_dir() / exe).exists() and shutil.which(exe) is None:
            raise ConfigError(f"未找到 {exe}。请将它放在程序目录: {app_dir()}")


SUPPORTED_INPUT_EXTS = {".mp4", ".mp3"}


def scan_media(inputs: list[Path], recursive: bool) -> list[Path]:
    files: list[Path] = []
    for root in inputs:
        if root.is_file():
            if root.suffix.lower() in SUPPORTED_INPUT_EXTS:
                files.append(root)
            continue
        pattern = "**/*" if recursive else "*"
        files.extend(p for p in root.glob(pattern) if p.suffix.lower() in SUPPORTED_INPUT_EXTS)
    return sorted({p.resolve() for p in files if p.is_file()}, key=lambda p: str(p).lower())


def tool_path(name: str) -> str:
    local = app_dir() / name
    if local.exists():
        return str(local)
    found = shutil.which(name)
    if found:
        return found
    raise ConfigError(f"未找到 {name}")


def progress_path(cfg: AppConfig) -> Path:
    return cfg.output_dir / "progress.jsonl"


def append_progress(cfg: AppConfig, record: dict[str, Any]) -> None:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        **record,
    }
    with progress_path(cfg).open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def output_paths(cfg: AppConfig, video: Path) -> tuple[Path, Path, Path]:
    stem = video.stem
    return cfg.output_dir / f"{stem}.mp3", cfg.output_dir / f"{stem}.txt", cfg.output_dir / f"{stem}.srt"


def get_duration(path: Path) -> float:
    cmd = [
        tool_path("ffprobe.exe"),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        return 0.0
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def parse_ffmpeg_time(line: str) -> float | None:
    match = re.search(r"out_time_ms=(\d+)", line)
    if match:
        return int(match.group(1)) / 1_000_000
    match = re.search(r"out_time=([0-9:.]+)", line)
    if not match:
        return None
    parts = match.group(1).split(":")
    if len(parts) != 3:
        return None
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def prepare_mp3(cfg: AppConfig, video: Path, mp3_path: Path) -> None:
    if video.suffix.lower() == ".mp3":
        if video.resolve() != mp3_path.resolve() and (cfg.overwrite or not mp3_path.exists()):
            shutil.copy2(video, mp3_path)
        append_progress(cfg, file_record(video, cfg, "audio_done", percent=100))
        return

    if mp3_path.exists() and not cfg.overwrite:
        append_progress(cfg, file_record(video, cfg, "audio_done", percent=100))
        return

    duration = get_duration(video)
    cmd = [
        tool_path("ffmpeg.exe"),
        "-y" if cfg.overwrite else "-n",
        "-i",
        str(video),
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        cfg.mp3_bitrate,
        "-progress",
        "pipe:1",
        "-nostats",
        str(mp3_path),
    ]
    append_progress(cfg, file_record(video, cfg, "extracting_audio", percent=0))
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")
    last_percent = -1
    assert process.stdout is not None
    for line in process.stdout:
        seconds = parse_ffmpeg_time(line)
        if seconds is None or duration <= 0:
            continue
        percent = max(0, min(99, int(seconds * 100 / duration)))
        if percent >= last_percent + 5:
            last_percent = percent
            print(f"  音频提取: {percent}%")
            append_progress(cfg, file_record(video, cfg, "extracting_audio", percent=percent))
    process.communicate()
    if process.returncode != 0:
        raise RuntimeError("ffmpeg 转换失败")
    append_progress(cfg, file_record(video, cfg, "audio_done", percent=100))


def setup_capswriter_runtime(cfg: AppConfig) -> None:
    capswriter = str(cfg.capswriter_dir)
    internal = str(cfg.capswriter_dir / "internal")
    os.environ["PATH"] = str(app_dir()) + os.pathsep + internal + os.pathsep + os.environ.get("PATH", "")
    for item in (capswriter, internal):
        if item not in sys.path:
            sys.path.insert(0, item)
    for module_name in ("numpy",):
        module = sys.modules.get(module_name)
        if module is not None and not hasattr(module, "float32"):
            del sys.modules[module_name]
    if hasattr(os, "add_dll_directory"):
        DLL_HANDLES.append(os.add_dll_directory(internal))
        llama_bin = cfg.capswriter_dir / "util" / "llama" / "bin"
        if llama_bin.exists():
            DLL_HANDLES.append(os.add_dll_directory(str(llama_bin)))


def load_audio_array(audio_file: Path):
    from util.qwen_asr_gguf.inference.utils import load_audio

    return load_audio(str(audio_file), sample_rate=16000)


def create_qwen_engine(cfg: AppConfig):
    module = sys.modules.get("numpy")
    if module is not None and not hasattr(module, "float32"):
        del sys.modules["numpy"]
    from util.qwen_asr_gguf import create_asr_engine

    return create_asr_engine(
        model_dir=str(cfg.model_dir),
        encoder_frontend_fn=ASR_FRONTEND,
        encoder_backend_fn=ASR_BACKEND,
        llm_fn=ASR_LLM,
        use_dml=cfg.use_dml,
        vulkan_enable=cfg.vulkan,
        verbose=False,
        n_ctx=2048,
        chunk_size=cfg.chunk_size,
        pad_to=int(cfg.chunk_size),
        enable_aligner=True,
    )


def group_items_to_subtitles(items: list[Any], max_chars: int = 35, max_gap: float = 0.5, min_duration: float = 0.8) -> list[dict[str, Any]]:
    subtitles: list[dict[str, Any]] = []
    if not items:
        return subtitles
    current_text = ""
    current_start = items[0].start_time
    current_end = items[0].end_time
    punctuation = set("。！？，；：.!? ,;:")
    for i, item in enumerate(items):
        text, start, end = item.text, item.start_time, item.end_time
        should_break = False
        if i > 0 and (start - items[i - 1].end_time) > max_gap:
            should_break = True
        if len(current_text + text) > max_chars:
            should_break = True
        if i > 0 and any(p in items[i - 1].text for p in punctuation):
            should_break = True
        if should_break and current_text:
            if (current_end - current_start) < min_duration:
                current_end = current_start + min_duration
            subtitles.append({"start": current_start, "end": current_end, "text": current_text.strip()})
            current_text, current_start, current_end = text, start, end
        else:
            current_text += text
            current_end = end
    if current_text:
        if (current_end - current_start) < min_duration:
            current_end = current_start + min_duration
        subtitles.append({"start": current_start, "end": current_end, "text": current_text.strip()})
    return subtitles


def format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(path: Path, items: list[Any]) -> None:
    subtitles = group_items_to_subtitles(items)
    with path.open("w", encoding="utf-8") as f:
        for idx, sub in enumerate(subtitles, 1):
            f.write(f"{idx}\n{format_timestamp(sub['start'])} --> {format_timestamp(sub['end'])}\n{sub['text']}\n\n")


def transcribe_mp3(cfg: AppConfig, engine: Any, video: Path, mp3_path: Path, txt_path: Path, srt_path: Path) -> None:
    if txt_path.exists() and srt_path.exists() and not cfg.overwrite:
        append_progress(cfg, file_record(video, cfg, "done", percent=100))
        return

    append_progress(cfg, file_record(video, cfg, "transcribing", percent=0, chunk=0, chunks=0))
    print("  加载音频...")
    audio = load_audio_array(mp3_path)
    sample_rate = 16000
    samples_per_chunk = int(cfg.chunk_size * sample_rate)
    total_chunks = max(1, math.ceil(len(audio) / samples_per_chunk))
    all_text: list[str] = []
    all_items: list[Any] = []

    for index in range(total_chunks):
        start = index * samples_per_chunk
        end = min((index + 1) * samples_per_chunk, len(audio))
        chunk_audio = audio[start:end]
        offset_sec = start / sample_rate
        percent = int(index * 100 / total_chunks)
        print(f"  转写: {index + 1}/{total_chunks}")
        append_progress(cfg, file_record(video, cfg, "transcribing", percent=percent, chunk=index + 1, chunks=total_chunks))
        context = "".join(all_text)[-300:]
        result = engine.engine.asr(
            audio=chunk_audio,
            context=context,
            language=cfg.language,
            chunk_size_sec=cfg.chunk_size,
            memory_chunks=1,
        )
        all_text.append(result.text)
        if result.alignment:
            for item in result.alignment.items:
                item = type(item)(
                    text=item.text,
                    start_time=item.start_time + offset_sec,
                    end_time=item.end_time + offset_sec,
                )
                all_items.append(item)

    text = "".join(all_text).strip()
    txt_path.write_text(text + "\n", encoding="utf-8")
    if all_items:
        write_srt(srt_path, all_items)
    else:
        srt_path.write_text(f"1\n00:00:00,000 --> 00:00:01,000\n{text}\n", encoding="utf-8")
    append_progress(cfg, file_record(video, cfg, "done", percent=100, chunk=total_chunks, chunks=total_chunks))


def file_record(video: Path, cfg: AppConfig, status: str, **extra: Any) -> dict[str, Any]:
    mp3_path, txt_path, srt_path = output_paths(cfg, video)
    return {
        "input": str(video),
        "mp3": str(mp3_path),
        "txt": str(txt_path),
        "srt": str(srt_path),
        "status": status,
        **extra,
    }


def process_files(cfg: AppConfig, files: list[Path]) -> int:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    setup_capswriter_runtime(cfg)
    engine = None
    failures = 0

    try:
        for idx, video in enumerate(files, 1):
            started = time.time()
            mp3_path, txt_path, srt_path = output_paths(cfg, video)
            print(f"\n[{idx}/{len(files)}] {video}")
            append_progress(cfg, file_record(video, cfg, "queued", percent=0))
            if mp3_path.exists() and txt_path.exists() and srt_path.exists() and not cfg.overwrite:
                print("  已存在完整输出，跳过")
                append_progress(cfg, file_record(video, cfg, "skipped", percent=100, elapsed_sec=0))
                continue
            try:
                prepare_mp3(cfg, video, mp3_path)
                if engine is None:
                    print("  加载 Qwen3-ASR 模型...")
                    engine = create_qwen_engine(cfg)
                transcribe_mp3(cfg, engine, video, mp3_path, txt_path, srt_path)
                append_progress(cfg, file_record(video, cfg, "done", percent=100, elapsed_sec=round(time.time() - started, 3)))
            except Exception as exc:
                failures += 1
                error_detail = traceback.format_exc()
                print(f"  失败: {exc}")
                print(error_detail)
                append_progress(cfg, file_record(video, cfg, "failed", error=str(exc), traceback=error_detail, elapsed_sec=round(time.time() - started, 3)))
    finally:
        if engine is not None and hasattr(engine, "cleanup"):
            engine.cleanup()
    return failures


def main() -> int:
    try:
        args = parse_args()
        config_file = Path(args.config).expanduser()
        data = load_simple_yaml(config_file) if config_file.exists() else {}
        cfg = merge_cli(config_from_dict(data), args)
        cfg = resolve_config(cfg)
        validate_config(cfg)
        files = scan_media(cfg.inputs, cfg.recursive)
        print(f"扫描到媒体文件: {len(files)}")
        print(f"输出目录: {cfg.output_dir}")
        if args.dry_run:
            for item in files:
                print(item)
            return 0
        if not files:
            return 0
        failures = process_files(cfg, files)
        print(f"\n完成。失败: {failures}，进度文件: {progress_path(cfg)}")
        return 1 if failures else 0
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
