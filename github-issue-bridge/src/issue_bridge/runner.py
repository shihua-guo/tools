from __future__ import annotations

import json
import subprocess
import uuid

from issue_bridge.config import AppConfig
from issue_bridge.logic import sanitize_session_name
from issue_bridge.models import IssueState, IssueSnapshot, RunnerOutput
from issue_bridge.prompt import build_followup_prompt, build_initial_prompt, output_schema_json


class ClaudeRunner:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg

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
        cmd.append(prompt)

        proc = subprocess.run(
            cmd,
            cwd=local_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=self.cfg.claude.timeout_seconds,
        )
        stderr_text = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return RunnerOutput(
                result_type="failed",
                reply_markdown=(
                    f"Claude execution failed with exit code {proc.returncode}.\n\n"
                    f"```text\n{stderr_text or proc.stdout.strip() or '<empty>'}\n```"
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
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return RunnerOutput(
                result_type="failed",
                reply_markdown=(
                    "Claude returned output that was not valid JSON.\n\n"
                    f"```text\n{proc.stdout.strip()[:4000] or '<empty>'}\n```"
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

        return RunnerOutput(
            result_type=str(payload.get("result_type", "failed")),
            reply_markdown=str(payload.get("reply_markdown", "")),
            needs_confirmation=bool(payload.get("needs_confirmation", False)),
            summary=str(payload.get("summary", "")),
            session_name=str(payload.get("session_name", session_name)),
            session_id=session_id,
            touched_paths=[str(item) for item in payload.get("touched_paths", [])],
            cooldown_seconds=int(payload.get("cooldown_seconds", self.cfg.per_issue_cooldown_seconds)),
            exit_code=0,
            stderr_text=stderr_text,
        )
