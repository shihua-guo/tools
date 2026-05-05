from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class IssueComment:
    id: str
    author_login: str
    body: str
    created_at: str
    url: str = ""

    @classmethod
    def from_dict(cls, raw: dict) -> "IssueComment":
        return cls(
            id=str(raw.get("id", "")),
            author_login=str(raw.get("author_login", "")),
            body=str(raw.get("body", "")),
            created_at=str(raw.get("created_at", "")),
            url=str(raw.get("url", "")),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IssueSnapshot:
    issue_key: str
    repo: str
    number: int
    url: str
    title: str
    body: str
    author_login: str
    labels: list[str]
    state: str
    created_at: str
    updated_at: str
    comments: list[IssueComment] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict) -> "IssueSnapshot":
        comments = [IssueComment.from_dict(item) for item in raw.get("comments", [])]
        return cls(
            issue_key=str(raw.get("issue_key", "")),
            repo=str(raw.get("repo", "")),
            number=int(raw.get("number", 0)),
            url=str(raw.get("url", "")),
            title=str(raw.get("title", "")),
            body=str(raw.get("body", "")),
            author_login=str(raw.get("author_login", "")),
            labels=[str(item) for item in raw.get("labels", [])],
            state=str(raw.get("state", "")),
            created_at=str(raw.get("created_at", "")),
            updated_at=str(raw.get("updated_at", "")),
            comments=comments,
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["comments"] = [item.to_dict() for item in self.comments]
        return data


@dataclass
class IssueState:
    issue_key: str
    last_seen_marker: str = ""
    last_processed_marker: str = ""
    last_human_comment_id: str = ""
    last_human_comment_created_at: str = ""
    claude_session_id: str = ""
    status: str = "idle"
    queued_marker: str = ""
    pending_outbox_id: str = ""
    pending_confirmation_token: str = ""
    last_run_started_at: str = ""
    last_run_finished_at: str = ""
    cooldown_until: str = ""
    last_error: str = ""
    last_post_target_state: str = "idle"

    @classmethod
    def from_dict(cls, raw: dict, issue_key: str) -> "IssueState":
        return cls(
            issue_key=issue_key,
            last_seen_marker=str(raw.get("last_seen_marker", "")),
            last_processed_marker=str(raw.get("last_processed_marker", "")),
            last_human_comment_id=str(raw.get("last_human_comment_id", "")),
            last_human_comment_created_at=str(raw.get("last_human_comment_created_at", "")),
            claude_session_id=str(raw.get("claude_session_id", "")),
            status=str(raw.get("status", "idle")),
            queued_marker=str(raw.get("queued_marker", "")),
            pending_outbox_id=str(raw.get("pending_outbox_id", "")),
            pending_confirmation_token=str(raw.get("pending_confirmation_token", "")),
            last_run_started_at=str(raw.get("last_run_started_at", "")),
            last_run_finished_at=str(raw.get("last_run_finished_at", "")),
            cooldown_until=str(raw.get("cooldown_until", "")),
            last_error=str(raw.get("last_error", "")),
            last_post_target_state=str(raw.get("last_post_target_state", "idle")),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OutboxItem:
    outbox_id: str
    issue_key: str
    repo: str
    number: int
    issue_url: str
    comment_body: str
    comment_marker: str
    created_at: str
    next_state: str
    failure_count: int = 0

    @classmethod
    def from_dict(cls, raw: dict) -> "OutboxItem":
        return cls(
            outbox_id=str(raw.get("outbox_id", "")),
            issue_key=str(raw.get("issue_key", "")),
            repo=str(raw.get("repo", "")),
            number=int(raw.get("number", 0)),
            issue_url=str(raw.get("issue_url", "")),
            comment_body=str(raw.get("comment_body", "")),
            comment_marker=str(raw.get("comment_marker", "")),
            created_at=str(raw.get("created_at", "")),
            next_state=str(raw.get("next_state", "idle")),
            failure_count=int(raw.get("failure_count", 0)),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RunnerOutput:
    result_type: str
    reply_markdown: str
    needs_confirmation: bool
    summary: str
    session_name: str
    session_id: str
    touched_paths: list[str]
    cooldown_seconds: int
    exit_code: int = 0
    stderr_text: str = ""


@dataclass
class SyncResult:
    accepted_issue_keys: list[str] = field(default_factory=list)
    queued_issue_keys: list[str] = field(default_factory=list)
    ignored_issue_keys: list[str] = field(default_factory=list)
