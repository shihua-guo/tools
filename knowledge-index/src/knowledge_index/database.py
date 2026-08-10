from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .models import Document
from .parsers import iter_source_documents
from .text_features import (
    char_bigram_tokens,
    full_pinyin_tokens,
    index_fields,
    pinyin_initial_tokens,
    word_tokens,
)

SCHEMA = """
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    unique_key TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    source_root TEXT NOT NULL,
    source_file TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    category TEXT NOT NULL,
    conversation TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    sender_name TEXT,
    sender_id TEXT,
    timestamp TEXT,
    audio_start REAL,
    audio_end REAL,
    text TEXT NOT NULL
);

CREATE INDEX documents_source_ordinal
ON documents(source_file, ordinal);

CREATE INDEX documents_source_type
ON documents(source_type);

CREATE VIRTUAL TABLE document_fts USING fts5(
    words,
    char_bigrams,
    pinyin_full,
    pinyin_initials,
    content='',
    tokenize='unicode61 remove_diacritics 2'
);
"""


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _insert_document(connection: sqlite3.Connection, document: Document) -> bool:
    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO documents (
            unique_key, source_type, source_root, source_file, relative_path,
            category, conversation, ordinal, sender_name, sender_id, timestamp,
            audio_start, audio_end, text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document.unique_key,
            document.source_type,
            document.source_root,
            document.source_file,
            document.relative_path,
            document.category,
            document.conversation,
            document.ordinal,
            document.sender_name,
            document.sender_id,
            document.timestamp,
            document.audio_start,
            document.audio_end,
            document.text,
        ),
    )
    if cursor.rowcount == 0:
        return False
    document_id = int(cursor.lastrowid)
    searchable_text = " ".join(
        value
        for value in (
            document.category,
            document.conversation,
            document.sender_name,
            document.sender_id,
            document.text,
        )
        if value
    )
    connection.execute(
        "INSERT INTO document_fts(rowid, words, char_bigrams, pinyin_full, pinyin_initials) "
        "VALUES (?, ?, ?, ?, ?)",
        (document_id, *index_fields(searchable_text)),
    )
    return True


def build_database(sources: Iterable[Path], database: Path) -> dict[str, int]:
    source_paths = [source.expanduser().resolve() for source in sources]
    missing = [str(source) for source in source_paths if not source.exists()]
    if missing:
        raise FileNotFoundError("找不到数据路径：" + "；".join(missing))

    database = database.expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{database.name}.", suffix=".tmp", dir=database.parent
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    counts: defaultdict[str, int] = defaultdict(int)

    try:
        connection = _connect(temporary_path)
        try:
            connection.executescript(SCHEMA)
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("INSERT INTO metadata VALUES ('schema_version', '1')")
            connection.execute(
                "INSERT INTO metadata VALUES ('sources', ?)",
                (
                    json.dumps(
                        [str(source) for source in source_paths], ensure_ascii=False
                    ),
                ),
            )
            with connection:
                for source in source_paths:
                    for document in iter_source_documents(source):
                        if _insert_document(connection, document):
                            counts[document.source_type] += 1
            connection.execute(
                "INSERT INTO document_fts(document_fts) VALUES ('optimize')"
            )
            connection.commit()
        finally:
            connection.close()
        os.replace(temporary_path, database)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise

    counts["total"] = sum(counts.values())
    return dict(counts)


def _quoted_token(token: str) -> str:
    return '"' + token.replace('"', '""') + '"'


def _or_query(column: str, tokens: tuple[str, ...], *, limit: int = 32) -> str | None:
    unique = tuple(dict.fromkeys(token for token in tokens if token))[:limit]
    if not unique:
        return None
    return f"{column} : (" + " OR ".join(_quoted_token(token) for token in unique) + ")"


def _phrase_query(
    column: str, tokens: tuple[str, ...], *, limit: int = 24
) -> str | None:
    tokens = tuple(token for token in tokens if token)[:limit]
    if not tokens:
        return None
    return f"{column} : " + _quoted_token(" ".join(tokens))


def _search_channel(
    connection: sqlite3.Connection,
    query: str,
    candidate_limit: int,
    source_type: str | None,
) -> list[int]:
    if source_type is None:
        rows = connection.execute(
            """
            SELECT rowid
            FROM document_fts
            WHERE document_fts MATCH ?
            ORDER BY bm25(document_fts)
            LIMIT ?
            """,
            (query, candidate_limit),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT document_fts.rowid
            FROM document_fts
            JOIN documents ON documents.id = document_fts.rowid
            WHERE document_fts MATCH ? AND documents.source_type = ?
            ORDER BY bm25(document_fts)
            LIMIT ?
            """,
            (query, source_type, candidate_limit),
        ).fetchall()
    return [int(row["rowid"]) for row in rows]


def search_database(
    database: Path,
    query: str,
    *,
    limit: int = 10,
    context: int = 1,
    source_type: str | None = None,
) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    database = database.expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(f"找不到索引数据库：{database}")

    channels = (
        ("hanzi", 10.0, _or_query("words", word_tokens(query))),
        ("bigram", 5.0, _or_query("char_bigrams", char_bigram_tokens(query))),
        ("pinyin", 2.0, _phrase_query("pinyin_full", full_pinyin_tokens(query))),
        ("initials", 1.0, _or_query("pinyin_initials", pinyin_initial_tokens(query))),
    )
    scores: defaultdict[int, float] = defaultdict(float)
    matched_by: defaultdict[int, list[str]] = defaultdict(list)
    candidate_limit = max(limit * 10, 50)

    connection = _connect(database)
    try:
        for channel_name, weight, channel_query in channels:
            if channel_query is None:
                continue
            for rank, document_id in enumerate(
                _search_channel(
                    connection, channel_query, candidate_limit, source_type
                ),
                start=1,
            ):
                scores[document_id] += weight / (60 + rank)
                matched_by[document_id].append(channel_name)

        ranked_ids = sorted(
            scores, key=lambda document_id: (-scores[document_id], document_id)
        )[:limit]
        results: list[dict[str, Any]] = []
        for document_id in ranked_ids:
            row = connection.execute(
                "SELECT * FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
            if row is None:
                continue
            item = dict(row)
            item["score"] = scores[document_id]
            item["matched_by"] = matched_by[document_id]
            item["context_before"] = []
            item["context_after"] = []
            if context > 0:
                nearby = connection.execute(
                    """
                    SELECT id, ordinal, sender_name, sender_id, timestamp,
                           audio_start, audio_end, text
                    FROM documents
                    WHERE source_file = ? AND ordinal BETWEEN ? AND ? AND id != ?
                    ORDER BY ordinal
                    """,
                    (
                        row["source_file"],
                        row["ordinal"] - context,
                        row["ordinal"] + context,
                        document_id,
                    ),
                ).fetchall()
                item["context_before"] = [
                    dict(value) for value in nearby if value["ordinal"] < row["ordinal"]
                ]
                item["context_after"] = [
                    dict(value) for value in nearby if value["ordinal"] > row["ordinal"]
                ]
            results.append(item)
        return results
    finally:
        connection.close()


def database_stats(database: Path) -> dict[str, Any]:
    database = database.expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(f"找不到索引数据库：{database}")
    connection = _connect(database)
    try:
        type_counts = {
            row["source_type"]: row["count"]
            for row in connection.execute(
                "SELECT source_type, COUNT(*) AS count FROM documents GROUP BY source_type"
            )
        }
        sources_row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'sources'"
        ).fetchone()
        return {
            "database": str(database),
            "database_bytes": database.stat().st_size,
            "total": sum(type_counts.values()),
            "by_type": type_counts,
            "sources": json.loads(sources_row["value"]) if sources_row else [],
        }
    finally:
        connection.close()
