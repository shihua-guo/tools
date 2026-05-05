from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone

from issue_bridge.config import AppConfig
from issue_bridge.models import IssueComment, IssueSnapshot


CONFIRM_RE = re.compile(r"\bCONFIRM\s+([A-Za-z0-9_-]{6,})\b")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def is_ai_comment(body: str, prefixes: list[str]) -> bool:
    stripped = (body or "").lstrip()
    return any(stripped.startswith(prefix) for prefix in prefixes)


def relevant_comments(snapshot: IssueSnapshot, cfg: AppConfig) -> list[IssueComment]:
    return [
        comment
        for comment in snapshot.comments
        if comment.author_login == cfg.tracked_user and not is_ai_comment(comment.body, cfg.ai_prefixes)
    ]


def has_relevant_input(snapshot: IssueSnapshot, cfg: AppConfig) -> bool:
    if snapshot.author_login == cfg.tracked_user:
        return True
    return bool(relevant_comments(snapshot, cfg))


def compute_marker(snapshot: IssueSnapshot, cfg: AppConfig) -> str:
    comments = relevant_comments(snapshot, cfg)
    if comments:
        return comments[-1].created_at
    if snapshot.author_login == cfg.tracked_user:
        return snapshot.created_at
    return ""


def latest_relevant_comment(snapshot: IssueSnapshot, cfg: AppConfig) -> IssueComment | None:
    comments = relevant_comments(snapshot, cfg)
    return comments[-1] if comments else None


def new_relevant_comments_since(
    snapshot: IssueSnapshot,
    cfg: AppConfig,
    last_comment_created_at: str,
) -> list[IssueComment]:
    if not last_comment_created_at:
        return relevant_comments(snapshot, cfg)
    return [
        comment
        for comment in relevant_comments(snapshot, cfg)
        if comment.created_at > last_comment_created_at
    ]


def issue_session_id(repo: str, number: int) -> str:
    token = secrets.token_hex(8)
    return str(f"{repo}#{number}:{token}")


def make_confirmation_token() -> str:
    return secrets.token_urlsafe(8).replace("-", "").replace("_", "")


def extract_confirm_token(body: str) -> str:
    match = CONFIRM_RE.search(body or "")
    return match.group(1) if match else ""


def sanitize_session_name(issue_key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", issue_key).strip("-")[:80] or "issue-bridge"
