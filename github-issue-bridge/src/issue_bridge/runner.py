from __future__ import annotations

import json
import logging
import subprocess
import uuid
from typing import Any

from issue_bridge.config import AppConfig
from issue_bridge.logic import sanitize_session_name
from issue_bridge.models import IssueState, IssueSnapshot, RunnerOutput
from issue_bridge.prompt import build_followup_prompt, build_initial_prompt, output_schema_json


logger = logging.getLogger(__name__)


class ClaudeRunner:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg

    def _extract_structured_payload(self, raw_payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if isinstance(raw_payload.get("structured_output"), dict):
            return raw_payload["structured_output"], ""

        if "result_type" in raw_payload:
            return raw_payload, ""

        result_text = raw_payload.get("result")
        if isinstance(result_text, str) and result_text.strip():
            try:
                parsed = json.loads(result_text)
            except json.JSONDecodeError:
                return None, result_text.strip()
            if isinstance(parsed, dict):
                return parsed, ""
            return None, result_text.strip()

        return None, ""

    def run(self, snapshot: IssueSnapshot, state: IssueState, new_comments) -> RunnerOutput:
        local_path = self.cfg.repo_paths.get(snapshot.repo, "")
        if not local_path:
            return RunnerOutput(
                result_type="failed",
                reply_markdown=f"Local path is not configured for `{snapshot.repo}`.",
                needs_confirmation=False,
                summary="Missing repo path",
                session_name=sanitize_session_name(snapshot.issue_key),
                session_id=state.claude_session_id,
                touched_paths=[],
                cooldown_seconds=self.cfg.per_issue_cooldown_seconds,
                exit_code=1,
                stderr_text="missing repo path",
            )

        session_id = state.claude_session_id or str(uuid.uuid4())
        session_name = sanitize_session_name(snapshot.issue_key)
        prompt = (
            build_initial_prompt(snapshot, self.cfg, local_path)
            if not state.claude_session_id
            else build_followup_prompt(snapshot, self.cfg, local_path, new_comments)
        )
        logger.info(
            "claude run issue=%s resume=%s bin=%s cwd=%s prompt_chars=%s title=%r body=%r new_comments=%s",
            snapshot.issue_key,
            bool(state.claude_session_id),
            self.cfg.claude.bin,
            local_path,
            len(prompt),
            snapshot.title,
            snapshot.body,
            len(new_comments),
        )

        cmd = [
            self.cfg.claude.bin,
            "-p",
            "--output-format",
            "json",
            "--json-schema",
            output_schema_json(),
            "--permission-mode",
            self.cfg.claude.permission_mode,
            "--max-turns",
            str(self.cfg.claude.max_turns),
        ]
        if self.cfg.claude.model:
            cmd.extend(["--model", self.cfg.claude.model])
        if state.claude_session_id:
            cmd.extend(["--resume", session_id])
        else:
            cmd.extend(["--session-id", session_id, "--name", session_name])

        proc = subprocess.run(
            cmd,
            cwd=local_path,
            input=prompt,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.cfg.claude.timeout_seconds,
        )
        stderr_text = (proc.stderr or "").strip()
        stdout_text = (proc.stdout or "").strip()
        logger.info(
            "claude finished issue=%s exit_code=%s stdout_chars=%s stderr_chars=%s session_id=%s",
            snapshot.issue_key,
            proc.returncode,
            len(stdout_text),
            len(stderr_text),
            session_id,
        )
        if proc.returncode != 0:
            return RunnerOutput(
                result_type="failed",
                reply_markdown=(
                    f"Claude execution failed with exit code {proc.returncode}.\n\n"
                    f"```text\n{stderr_text or stdout_text or '<empty>'}\n```"
                ),
                needs_confirmation=False,
                summary="Claude execution failed",
                session_name=session_name,
                session_id=session_id,
                touched_paths=[],
                cooldown_seconds=self.cfg.per_issue_cooldown_seconds,
                exit_code=proc.returncode,
                stderr_text=stderr_text,
            )

        try:
            raw_payload = json.loads(stdout_text)
        except (json.JSONDecodeError, TypeError):
            return RunnerOutput(
                result_type="failed",
                reply_markdown=(
                    "Claude returned output that was not valid JSON.\n\n"
                    f"```text\n{stdout_text[:4000] or '<empty>'}\n```"
                ),
                needs_confirmation=False,
                summary="Invalid Claude JSON output",
                session_name=session_name,
                session_id=session_id,
                touched_paths=[],
                cooldown_seconds=self.cfg.per_issue_cooldown_seconds,
                exit_code=1,
                stderr_text=stderr_text,
            )

        if not isinstance(raw_payload, dict):
            return RunnerOutput(
                result_type="failed",
                reply_markdown=(
                    "Claude returned JSON, but it was not an object.\n\n"
                    f"```text\n{stdout_text[:4000] or '<empty>'}\n```"
                ),
                needs_confirmation=False,
                summary="Unexpected Claude JSON output",
                session_name=session_name,
                session_id=session_id,
                touched_paths=[],
                cooldown_seconds=self.cfg.per_issue_cooldown_seconds,
                exit_code=1,
                stderr_text=stderr_text,
            )

        payload, unstructured_result = self._extract_structured_payload(raw_payload)
        if payload is None:
            reply_markdown = (
                "Claude completed, but did not return the required structured output."
            )
            if unstructured_result:
                reply_markdown = f"{reply_markdown}\n\n```text\n{unstructured_result[:4000]}\n```"
            return RunnerOutput(
                result_type="failed",
                reply_markdown=reply_markdown,
                needs_confirmation=False,
                summary="Missing structured Claude output",
                session_name=session_name,
                session_id=str(raw_payload.get("session_id", session_id)),
                touched_paths=[],
                cooldown_seconds=self.cfg.per_issue_cooldown_seconds,
                exit_code=1,
                stderr_text=stderr_text,
            )

        result_type = str(payload.get("result_type", "failed"))
        reply_markdown = str(payload.get("reply_markdown", ""))
        summary = str(payload.get("summary", ""))
        if not reply_markdown and result_type == "failed":
            reply_markdown = summary or "Claude returned a failed result without a reply body."

        return RunnerOutput(
            result_type=result_type,
            reply_markdown=reply_markdown,
            needs_confirmation=bool(payload.get("needs_confirmation", False)),
            summary=summary,
            session_name=str(payload.get("session_name", session_name)),
            session_id=str(raw_payload.get("session_id", session_id)),
            touched_paths=[str(item) for item in payload.get("touched_paths", [])],
            cooldown_seconds=int(payload.get("cooldown_seconds", self.cfg.per_issue_cooldown_seconds)),
            exit_code=0,
            stderr_text=stderr_text,
        )
