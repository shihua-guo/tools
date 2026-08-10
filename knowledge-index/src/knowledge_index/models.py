from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Document:
    source_type: str
    source_root: str
    source_file: str
    relative_path: str
    category: str
    conversation: str
    ordinal: int
    text: str
    sender_name: str | None = None
    sender_id: str | None = None
    timestamp: str | None = None
    audio_start: float | None = None
    audio_end: float | None = None

    @property
    def unique_key(self) -> str:
        location = self.timestamp or (
            f"{self.audio_start:.3f}"
            if self.audio_start is not None
            else str(self.ordinal)
        )
        return "\x1f".join(
            (
                self.source_type,
                self.source_root,
                self.relative_path,
                location,
                str(self.ordinal),
            )
        )
