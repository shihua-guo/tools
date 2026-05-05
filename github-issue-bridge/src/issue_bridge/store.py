from __future__ import annotations

import json
import threading
from pathlib import Path

from issue_bridge.models import IssueSnapshot, IssueState, OutboxItem


class StateStore:
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self._lock = threading.RLock()
        self._payload = {
            "issue_states": {},
            "snapshots": {},
            "outbox": {},
        }
        self._load()

    def _load(self) -> None:
        if not self.state_file.exists():
            return
        with self.state_file.open("r", encoding="utf-8") as fh:
            self._payload = json.load(fh)

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self._payload, fh, ensure_ascii=False, indent=2)
        tmp.replace(self.state_file)

    def get_issue_state(self, issue_key: str) -> IssueState:
        with self._lock:
            raw = self._payload["issue_states"].get(issue_key, {})
            state = IssueState.from_dict(raw, issue_key)
            return state

    def save_issue_state(self, state: IssueState) -> None:
        with self._lock:
            self._payload["issue_states"][state.issue_key] = state.to_dict()
            self._save()

    def get_snapshot(self, issue_key: str) -> IssueSnapshot | None:
        with self._lock:
            raw = self._payload["snapshots"].get(issue_key)
            return IssueSnapshot.from_dict(raw) if raw else None

    def save_snapshot(self, snapshot: IssueSnapshot) -> None:
        with self._lock:
            self._payload["snapshots"][snapshot.issue_key] = snapshot.to_dict()
            self._save()

    def list_outbox(self, limit: int) -> list[OutboxItem]:
        with self._lock:
            items = [OutboxItem.from_dict(raw) for raw in self._payload["outbox"].values()]
            items.sort(key=lambda item: (item.created_at, item.outbox_id))
            return items[:limit]

    def get_outbox(self, outbox_id: str) -> OutboxItem | None:
        with self._lock:
            raw = self._payload["outbox"].get(outbox_id)
            return OutboxItem.from_dict(raw) if raw else None

    def save_outbox(self, item: OutboxItem) -> None:
        with self._lock:
            self._payload["outbox"][item.outbox_id] = item.to_dict()
            self._save()

    def remove_outbox(self, outbox_id: str) -> None:
        with self._lock:
            self._payload["outbox"].pop(outbox_id, None)
            self._save()
