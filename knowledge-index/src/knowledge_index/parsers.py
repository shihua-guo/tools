from __future__ import annotations

import html
import re
from collections.abc import Iterator
from pathlib import Path

from .models import Document

_CHAT_HEADER_RE = re.compile(
    r"^(.+)\(([^()\t]+)\)[\t ]+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*$"
)
_SRT_TIME_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{3})"
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _source_metadata(path: Path, root: Path) -> tuple[str, str, str, str]:
    resolved_path = path.resolve()
    resolved_root = root.resolve() if root.is_dir() else root.resolve().parent
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError:
        relative = Path(path.name)
    category = relative.parts[0] if len(relative.parts) > 1 else ""
    return str(resolved_root), str(resolved_path), relative.as_posix(), category


def parse_chat(path: Path, root: Path) -> tuple[bool, Iterator[Document]]:
    content = read_text(path)
    lines = content.splitlines()
    recognized = any(_CHAT_HEADER_RE.match(line.strip("\ufeff")) for line in lines)
    if not recognized:
        return False, iter(())

    source_root, source_file, relative_path, category = _source_metadata(path, root)

    def generate() -> Iterator[Document]:
        header: re.Match[str] | None = None
        body: list[str] = []
        ordinal = 0

        def make_document() -> Document | None:
            nonlocal ordinal
            if header is None:
                return None
            text = "\n".join(body).strip()
            if not text:
                return None
            document = Document(
                source_type="chat",
                source_root=source_root,
                source_file=source_file,
                relative_path=relative_path,
                category=category,
                conversation=path.stem,
                ordinal=ordinal,
                sender_name=header.group(1).strip(),
                sender_id=header.group(2).strip(),
                timestamp=header.group(3),
                text=text,
            )
            ordinal += 1
            return document

        for raw_line in lines:
            match = _CHAT_HEADER_RE.match(raw_line.strip("\ufeff"))
            if match:
                document = make_document()
                if document is not None:
                    yield document
                header = match
                body = []
            elif header is not None:
                body.append(raw_line)

        document = make_document()
        if document is not None:
            yield document

    return True, generate()


def _parse_srt_timestamp(value: str) -> float:
    hours, minutes, seconds = value.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _srt_cues(content: str) -> Iterator[tuple[float, float, str]]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    for block in re.split(r"\n\s*\n", normalized.strip()):
        lines = block.splitlines()
        time_index = next(
            (index for index, line in enumerate(lines) if _SRT_TIME_RE.search(line)),
            None,
        )
        if time_index is None:
            continue
        match = _SRT_TIME_RE.search(lines[time_index])
        assert match is not None
        text = " ".join(
            line.strip() for line in lines[time_index + 1 :] if line.strip()
        )
        text = html.unescape(_HTML_TAG_RE.sub("", text)).strip()
        if text:
            yield (
                _parse_srt_timestamp(match.group("start")),
                _parse_srt_timestamp(match.group("end")),
                text,
            )


def parse_srt(
    path: Path,
    root: Path,
    *,
    max_seconds: float = 60.0,
    max_cues: int = 8,
    max_gap: float = 15.0,
) -> Iterator[Document]:
    source_root, source_file, relative_path, category = _source_metadata(path, root)
    cues = _srt_cues(read_text(path))
    group: list[tuple[float, float, str]] = []
    ordinal = 0

    def make_document(items: list[tuple[float, float, str]], index: int) -> Document:
        return Document(
            source_type="meeting",
            source_root=source_root,
            source_file=source_file,
            relative_path=relative_path,
            category=category,
            conversation=path.stem,
            ordinal=index,
            audio_start=items[0][0],
            audio_end=items[-1][1],
            text=" ".join(item[2] for item in items),
        )

    for cue in cues:
        should_split = bool(group) and (
            len(group) >= max_cues
            or cue[1] - group[0][0] > max_seconds
            or cue[0] - group[-1][1] > max_gap
        )
        if should_split:
            yield make_document(group, ordinal)
            ordinal += 1
            group = []
        group.append(cue)

    if group:
        yield make_document(group, ordinal)


def parse_plain_text(
    path: Path, root: Path, *, max_chars: int = 800
) -> Iterator[Document]:
    source_root, source_file, relative_path, category = _source_metadata(path, root)
    content = read_text(path).strip()
    if not content:
        return

    paragraphs = [
        part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()
    ]
    group: list[str] = []
    group_size = 0
    ordinal = 0

    def make_document(parts: list[str], index: int) -> Document:
        return Document(
            source_type="text",
            source_root=source_root,
            source_file=source_file,
            relative_path=relative_path,
            category=category,
            conversation=path.stem,
            ordinal=index,
            text="\n\n".join(parts),
        )

    for paragraph in paragraphs:
        if group and group_size + len(paragraph) > max_chars:
            yield make_document(group, ordinal)
            ordinal += 1
            group = []
            group_size = 0
        if len(paragraph) <= max_chars:
            group.append(paragraph)
            group_size += len(paragraph)
            continue
        if group:
            yield make_document(group, ordinal)
            ordinal += 1
            group = []
            group_size = 0
        for offset in range(0, len(paragraph), max_chars):
            yield make_document([paragraph[offset : offset + max_chars]], ordinal)
            ordinal += 1

    if group:
        yield make_document(group, ordinal)


def iter_source_documents(source: Path) -> Iterator[Document]:
    source = source.resolve()
    root = source if source.is_dir() else source.parent
    paths = (
        [source]
        if source.is_file()
        else sorted(path for path in source.rglob("*") if path.is_file())
    )
    srt_paths = [path for path in paths if path.suffix.lower() == ".srt"]
    txt_paths = [path for path in paths if path.suffix.lower() == ".txt"]
    successful_srt: set[tuple[str, str]] = set()

    for path in srt_paths:
        documents = list(parse_srt(path, root))
        if documents:
            successful_srt.add((str(path.parent.resolve()).lower(), path.stem.lower()))
            yield from documents

    for path in txt_paths:
        recognized, documents = parse_chat(path, root)
        if recognized:
            yield from documents
            continue
        sibling_key = (str(path.parent.resolve()).lower(), path.stem.lower())
        if sibling_key not in successful_srt:
            yield from parse_plain_text(path, root)
