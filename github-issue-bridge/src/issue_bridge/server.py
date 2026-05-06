from __future__ import annotations

import json
import logging
import queue
import threading
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from issue_bridge.config import AppConfig
from issue_bridge.logic import (
    compute_marker,
    extract_confirm_token,
    has_relevant_input,
    latest_relevant_comment,
    make_confirmation_token,
    new_relevant_comments_since,
    now_iso,
)
from issue_bridge.models import IssueSnapshot, IssueState, OutboxItem, SyncResult
from issue_bridge.runner import ClaudeRunner
from issue_bridge.store import StateStore


EMPTY_RUNNER_REPLY = "处理失败，但执行器没有返回具体错误内容。请查看本地 issue bridge 日志并补充更具体的 issue 描述后重试。"


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


class BridgeService:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        state_dir = Path(cfg.state_dir)
        log_dir = Path(cfg.log_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = log_dir / "issue-bridge.log"
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            handlers=[
                logging.FileHandler(self.log_file, encoding="utf-8"),
                logging.StreamHandler(),
            ],
        )
        self.store = StateStore(state_dir / "state.json")
        self.runner = ClaudeRunner(cfg)
        self.task_queue: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._recover_interrupted_work()
        self.worker = threading.Thread(target=self._worker_loop, name="issue-bridge-worker", daemon=True)
        self.worker.start()

    def shutdown(self) -> None:
        self._stop.set()
        self.task_queue.put("__stop__")
        self.worker.join(timeout=2)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "version": "1",
            "server_time": now_iso(),
        }

    def _refresh_cooldown(self, state: IssueState) -> IssueState:
        if state.status != "cooldown":
            return state
        deadline = _parse_iso(state.cooldown_until)
        now = datetime.now(timezone.utc)
        if deadline is not None and now >= deadline:
            state.status = "idle"
            state.cooldown_until = ""
            self.store.save_issue_state(state)
        return state

    def _cooldown_until(self, seconds: int) -> str:
        cooldown_deadline = datetime.now(timezone.utc).timestamp() + max(seconds, self.cfg.per_issue_cooldown_seconds)
        return datetime.fromtimestamp(cooldown_deadline, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    def _recover_interrupted_work(self) -> None:
        for state in self.store.list_issue_states():
            if state.status not in {"queued", "running"}:
                continue
            previous_status = state.status
            state.status = "idle"
            state.queued_marker = ""
            state.last_error = f"daemon restarted while issue was {previous_status}"
            self.store.save_issue_state(state)
            logging.info("recovered interrupted issue %s from status=%s", state.issue_key, previous_status)

    def _comment_content_without_metadata(self, body: str) -> str:
        content = (body or "").strip()
        if content.startswith("[AI]"):
            content = content[len("[AI]"):].strip()
        return content.split("<details>", 1)[0].strip()

    def _has_meaningful_comment_body(self, body: str) -> bool:
        return bool(self._comment_content_without_metadata(body))

    def _format_outbox_comment(self, body: str, comment_marker: str, token: str) -> str:
        comment_body = body.strip() or EMPTY_RUNNER_REPLY
        if not comment_body.startswith("[AI]"):
            comment_body = f"[AI]\n{comment_body}"
        if token:
            comment_body = (
                f"{comment_body}\n\n"
                "如确认覆盖当前本地未提交改动并继续，请直接回复：\n\n"
                f"CONFIRM {token}\n"
            )
        return (
            f"{comment_body}\n\n"
            "<details>\n"
            "<summary>Bridge metadata</summary>\n\n"
            f"`{comment_marker}`\n"
            "</details>"
        )

    def _enqueue_if_needed(self, snapshot: IssueSnapshot, state: IssueState, marker: str, result: SyncResult) -> None:
        if not marker:
            return
        if marker == state.last_processed_marker or marker == state.queued_marker:
            return
        if state.status in {"running", "awaiting_post"}:
            return
        state.status = "queued"
        state.queued_marker = marker
        self.store.save_issue_state(state)
        self.task_queue.put(snapshot.issue_key)
        result.queued_issue_keys.append(snapshot.issue_key)

    def sync_issues(self, raw_issues: list[dict]) -> SyncResult:
        result = SyncResult()
        logging.info("sync received issues=%s", len(raw_issues))
        for raw in raw_issues:
            snapshot = IssueSnapshot.from_dict(raw)
            if not snapshot.issue_key:
                snapshot.issue_key = f"{snapshot.repo}#{snapshot.number}"
            if snapshot.repo not in self.cfg.repos or snapshot.state.lower() != "open":
                logging.info(
                    "issue ignored %s reason=repo_or_state repo=%s state=%s",
                    snapshot.issue_key,
                    snapshot.repo,
                    snapshot.state,
                )
                result.ignored_issue_keys.append(snapshot.issue_key)
                continue
            if not has_relevant_input(snapshot, self.cfg):
                logging.info(
                    "issue ignored %s reason=no_tracked_user_input author=%s comments=%s",
                    snapshot.issue_key,
                    snapshot.author_login,
                    len(snapshot.comments),
                )
                result.ignored_issue_keys.append(snapshot.issue_key)
                continue
            marker = compute_marker(snapshot, self.cfg)
            if not marker:
                logging.info("issue ignored %s reason=empty_marker", snapshot.issue_key)
                result.ignored_issue_keys.append(snapshot.issue_key)
                continue
            self.store.save_snapshot(snapshot)
            state = self._refresh_cooldown(self.store.get_issue_state(snapshot.issue_key))
            state.last_seen_marker = marker
            latest_comment = latest_relevant_comment(snapshot, self.cfg)
            if state.pending_confirmation_token and latest_comment:
                token = extract_confirm_token(latest_comment.body)
                if token == state.pending_confirmation_token:
                    state.pending_confirmation_token = ""
            self.store.save_issue_state(state)
            result.accepted_issue_keys.append(snapshot.issue_key)
            self._enqueue_if_needed(snapshot, state, marker, result)
        logging.info(
            "sync result accepted=%s queued=%s ignored=%s",
            result.accepted_issue_keys,
            result.queued_issue_keys,
            result.ignored_issue_keys,
        )
        return result

    def list_outbox(self, limit: int) -> list[dict]:
        items = self.store.list_outbox(limit)
        return [item.to_dict() for item in items]

    def ack_outbox(
        self,
        outbox_id: str,
        status: str,
        github_comment_url: str,
        failure_reason: str,
    ) -> None:
        item = self.store.get_outbox(outbox_id)
        if item is None:
            return
        issue_state = self.store.get_issue_state(item.issue_key)
        if status in {"posted", "already_exists"}:
            issue_state.pending_outbox_id = ""
            issue_state.status = item.next_state
            issue_state.last_error = ""
            self.store.save_issue_state(issue_state)
            self.store.remove_outbox(outbox_id)
            snapshot = self.store.get_snapshot(item.issue_key)
            if snapshot is not None:
                marker = compute_marker(snapshot, self.cfg)
                refreshed = self._refresh_cooldown(self.store.get_issue_state(item.issue_key))
                if marker and marker != refreshed.last_processed_marker and refreshed.status not in {"running", "awaiting_post"}:
                    dummy = SyncResult()
                    self._enqueue_if_needed(snapshot, refreshed, marker, dummy)
            return

        item.failure_count += 1
        if not self._has_meaningful_comment_body(item.comment_body):
            item.comment_body = self._format_outbox_comment("", item.comment_marker, "")
            issue_state.pending_outbox_id = item.outbox_id
            issue_state.status = "awaiting_post"
            issue_state.last_error = "repaired empty outbox comment body after post failure"
            self.store.save_issue_state(issue_state)
            self.store.save_outbox(item)
            return

        issue_state.last_error = failure_reason or f"comment post failed for {github_comment_url or item.issue_url}"
        self.store.save_issue_state(issue_state)
        self.store.save_outbox(item)

    def _make_outbox_item(self, snapshot: IssueSnapshot, body: str, next_state: str, token: str) -> OutboxItem:
        outbox_id = f"obx_{uuid.uuid4().hex[:12]}"
        comment_marker = f"issue-bridge:{outbox_id}"
        comment_body = self._format_outbox_comment(body, comment_marker, token)
        return OutboxItem(
            outbox_id=outbox_id,
            issue_key=snapshot.issue_key,
            repo=snapshot.repo,
            number=snapshot.number,
            issue_url=snapshot.url,
            comment_body=comment_body,
            comment_marker=comment_marker,
            created_at=now_iso(),
            next_state=next_state,
        )

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            issue_key = self.task_queue.get()
            if issue_key == "__stop__":
                return
            try:
                self._process_issue(issue_key)
            except Exception as exc:  # pragma: no cover - best-effort daemon safety
                logging.exception("worker failed for %s: %s", issue_key, exc)
                self._mark_worker_failure(issue_key, exc)
            finally:
                self.task_queue.task_done()

    def _mark_worker_failure(self, issue_key: str, exc: Exception) -> None:
        try:
            state = self.store.get_issue_state(issue_key)
            state.status = "cooldown"
            state.queued_marker = ""
            state.last_run_finished_at = now_iso()
            state.cooldown_until = self._cooldown_until(self.cfg.per_issue_cooldown_seconds)
            state.last_error = str(exc) or exc.__class__.__name__
            self.store.save_issue_state(state)
        except Exception as save_exc:  # pragma: no cover - best-effort daemon safety
            logging.exception("failed to persist worker failure for %s: %s", issue_key, save_exc)

    def _process_issue(self, issue_key: str) -> None:
        snapshot = self.store.get_snapshot(issue_key)
        if snapshot is None:
            return
        state = self._refresh_cooldown(self.store.get_issue_state(issue_key))
        marker = compute_marker(snapshot, self.cfg)
        if not marker or marker == state.last_processed_marker:
            return
        state.status = "running"
        state.last_run_started_at = now_iso()
        state.queued_marker = ""
        self.store.save_issue_state(state)

        new_comments = new_relevant_comments_since(snapshot, self.cfg, state.last_human_comment_created_at)
        output = self.runner.run(snapshot, state, new_comments)

        latest_comment = latest_relevant_comment(snapshot, self.cfg)
        state.last_run_finished_at = now_iso()
        if output.session_id:
            state.claude_session_id = output.session_id
        state.last_processed_marker = marker
        if latest_comment is not None:
            state.last_human_comment_id = latest_comment.id
            state.last_human_comment_created_at = latest_comment.created_at

        next_state = "awaiting_user" if output.result_type == "needs_user_reply" or output.needs_confirmation else "idle"
        token = ""
        if output.needs_confirmation:
            token = make_confirmation_token()
            state.pending_confirmation_token = token

        if output.result_type == "failed":
            next_state = "cooldown"
            state.cooldown_until = self._cooldown_until(output.cooldown_seconds)
            state.last_error = output.stderr_text or output.summary or "runner failed"
        else:
            state.cooldown_until = ""
            state.last_error = ""

        outbox = self._make_outbox_item(snapshot, output.reply_markdown, next_state, token)
        state.pending_outbox_id = outbox.outbox_id
        state.status = "awaiting_post"
        state.last_post_target_state = next_state
        self.store.save_outbox(outbox)
        self.store.save_issue_state(state)
        logging.info("issue processed %s -> %s", issue_key, next_state)


class RequestHandler(BaseHTTPRequestHandler):
    server: "BridgeHTTPServer"

    def log_message(self, fmt: str, *args) -> None:
        logging.info("%s - %s", self.address_string(), fmt % args)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.startswith("/v1/health"):
            self._send_json(HTTPStatus.OK, self.server.service.health())
            return
        if self.path.startswith("/v1/outbox"):
            limit = 20
            if "limit=" in self.path:
                try:
                    limit = int(self.path.split("limit=", 1)[1].split("&", 1)[0])
                except ValueError:
                    limit = 20
            self._send_json(HTTPStatus.OK, {"version": "1", "items": self.server.service.list_outbox(limit)})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        try:
            payload = self._read_json()
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid json"})
            return
        if payload.get("secret") != self.server.service.cfg.shared_secret:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "invalid secret"})
            return

        if self.path == "/v1/issues/sync":
            result = self.server.service.sync_issues(payload.get("issues", []))
            self._send_json(
                HTTPStatus.OK,
                {
                    "version": "1",
                    "accepted_issue_keys": result.accepted_issue_keys,
                    "queued_issue_keys": result.queued_issue_keys,
                    "ignored_issue_keys": result.ignored_issue_keys,
                    "outbox_pending_count": len(self.server.service.list_outbox(1000)),
                },
            )
            return

        if self.path == "/v1/outbox/ack":
            self.server.service.ack_outbox(
                outbox_id=str(payload.get("outbox_id", "")),
                status=str(payload.get("status", "")),
                github_comment_url=str(payload.get("github_comment_url", "")),
                failure_reason=str(payload.get("failure_reason", "")),
            )
            self._send_json(HTTPStatus.OK, {"version": "1", "status": "ok"})
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})


class BridgeHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address, handler, service: BridgeService):
        super().__init__(server_address, handler)
        self.service = service


def serve(cfg: AppConfig) -> None:
    service = BridgeService(cfg)
    httpd = BridgeHTTPServer((cfg.host, cfg.port), RequestHandler, service)
    logging.info("listening on http://%s:%s", cfg.host, cfg.port)
    try:
        httpd.serve_forever()
    finally:
        service.shutdown()
        httpd.server_close()
