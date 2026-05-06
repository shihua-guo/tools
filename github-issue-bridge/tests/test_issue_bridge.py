from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from issue_bridge.config import AppConfig, ClaudeConfig
from issue_bridge.logic import matches_required_title_prefix
from issue_bridge.models import IssueComment, IssueSnapshot, IssueState
from issue_bridge.prompt import build_followup_prompt, build_initial_prompt
from issue_bridge.runner import ClaudeRunner


def make_config(*, required_title_prefixes: list[str] | None = None) -> AppConfig:
    return AppConfig(
        host="127.0.0.1",
        port=8765,
        shared_secret="secret",
        tracked_user="shihua-guo",
        ai_prefixes=["[AI]"],
        required_title_prefixes=required_title_prefixes or ["[hw]"],
        repos=["shihua-guo/tools"],
        repo_paths={"shihua-guo/tools": "/tmp/tools"},
        state_dir="/tmp/state",
        log_dir="/tmp/log",
        per_issue_cooldown_seconds=60,
        claude=ClaudeConfig(
            bin="claude",
            timeout_seconds=30,
            permission_mode="default",
            model="",
            max_turns=8,
        ),
    )


def make_snapshot(*, title: str = "[hw] bridge issue", body: str = "issue body") -> IssueSnapshot:
    return IssueSnapshot(
        issue_key="shihua-guo/tools#7",
        repo="shihua-guo/tools",
        number=7,
        url="https://github.com/shihua-guo/tools/issues/7",
        title=title,
        body=body,
        author_login="shihua-guo",
        labels=[],
        state="open",
        created_at="2026-05-06T09:00:00Z",
        updated_at="2026-05-06T09:00:00Z",
        comments=[
            IssueComment(
                id="c1",
                author_login="shihua-guo",
                body="first user comment",
                created_at="2026-05-06T09:01:00Z",
            ),
            IssueComment(
                id="c2",
                author_login="bridge-bot",
                body="[AI]\nassistant comment",
                created_at="2026-05-06T09:02:00Z",
            ),
        ],
    )


class TitlePrefixTests(unittest.TestCase):
    def test_title_prefix_is_case_sensitive_and_must_be_leading(self) -> None:
        cfg = make_config(required_title_prefixes=["[hw]"])

        self.assertTrue(matches_required_title_prefix(make_snapshot(title="[hw] valid"), cfg))
        self.assertFalse(matches_required_title_prefix(make_snapshot(title="[HW] wrong case"), cfg))
        self.assertFalse(matches_required_title_prefix(make_snapshot(title=" [hw] leading space"), cfg))
        self.assertFalse(matches_required_title_prefix(make_snapshot(title="prefix [hw] later"), cfg))


class PromptTests(unittest.TestCase):
    def test_initial_prompt_contains_issue_payload(self) -> None:
        cfg = make_config()
        snapshot = make_snapshot(body="full issue body")

        prompt = build_initial_prompt(snapshot, cfg, "/work/tools")

        self.assertIn("You are handling exactly one GitHub issue through a local issue bridge.", prompt)
        self.assertIn("IssueTitle:\n[hw] bridge issue", prompt)
        self.assertIn("IssueBody:\nfull issue body", prompt)
        self.assertIn("TrackedUserCommentsAlreadyPresent:", prompt)
        self.assertIn("first user comment", prompt)
        self.assertNotIn("assistant comment", prompt)

    def test_followup_prompt_contains_issue_payload_and_new_comments(self) -> None:
        cfg = make_config()
        snapshot = make_snapshot(body="body for followup")
        new_comments = [
            IssueComment(
                id="c3",
                author_login="shihua-guo",
                body="follow-up request",
                created_at="2026-05-06T09:03:00Z",
            )
        ]

        prompt = build_followup_prompt(snapshot, cfg, "/work/tools", new_comments)

        self.assertIn("Continue the existing GitHub issue session for the same issue key.", prompt)
        self.assertIn("IssueBody:\nbody for followup", prompt)
        self.assertIn("NewUserComments:", prompt)
        self.assertIn("follow-up request", prompt)


class RunnerTests(unittest.TestCase):
    @patch("issue_bridge.runner.subprocess.run")
    @patch("issue_bridge.runner.build_initial_prompt", return_value="PROMPT FROM BUILDER")
    def test_runner_pipes_prompt_via_stdin(self, mock_prompt, mock_run) -> None:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = json.dumps(
            {
                "session_id": "session-123",
                "structured_output": {
                    "result_type": "done",
                    "reply_markdown": "ok",
                    "needs_confirmation": False,
                    "summary": "done",
                    "session_name": "session-name",
                    "touched_paths": [],
                    "cooldown_seconds": 60,
                },
            }
        )
        mock_run.return_value.stderr = ""

        cfg = make_config()
        runner = ClaudeRunner(cfg)
        snapshot = make_snapshot()
        state = IssueState(issue_key=snapshot.issue_key)

        output = runner.run(snapshot, state, [])

        self.assertEqual(output.result_type, "done")
        self.assertEqual(output.reply_markdown, "ok")
        mock_prompt.assert_called_once()
        cmd = mock_run.call_args.args[0]
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["input"], "PROMPT FROM BUILDER")
        self.assertNotIn("PROMPT FROM BUILDER", cmd)


if __name__ == "__main__":
    unittest.main()
