from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .database import build_database, database_stats, search_database


def _format_seconds(value: float | None) -> str:
    if value is None:
        return ""
    milliseconds = round(value * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def _message_label(item: dict[str, Any]) -> str:
    sender = item.get("sender_name") or ""
    sender_id = item.get("sender_id") or ""
    timestamp = item.get("timestamp") or ""
    if sender_id:
        sender = f"{sender}({sender_id})"
    if sender or timestamp:
        return " ".join(value for value in (sender, timestamp) if value)
    start = _format_seconds(item.get("audio_start"))
    end = _format_seconds(item.get("audio_end"))
    return f"{start} --> {end}" if start else ""


def _print_context(items: list[dict[str, Any]], prefix: str) -> None:
    for item in items:
        label = _message_label(item)
        text = item["text"].replace("\n", " ")
        print(f"  {prefix} {label}: {text}".rstrip())


def _print_results(results: list[dict[str, Any]]) -> None:
    if not results:
        print("没有找到匹配内容。")
        return
    for index, result in enumerate(results, start=1):
        channels = ",".join(result["matched_by"])
        print(
            f"[{index}] {result['source_type']}  score={result['score']:.4f}  "
            f"匹配={channels}"
        )
        print(f"  来源: {result['source_file']}")
        label = _message_label(result)
        if label:
            print(f"  位置: {label}")
        _print_context(result["context_before"], "前文")
        print("  正文: " + result["text"].replace("\n", " "))
        _print_context(result["context_after"], "后文")
        print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="knowledge-search", description="本地聊天记录与会议字幕检索"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="扫描数据目录并重建索引")
    build.add_argument("sources", nargs="+", type=Path, help="聊天记录或会议字幕目录")
    build.add_argument(
        "--db", type=Path, default=Path("knowledge.db"), help="索引数据库"
    )

    search = subparsers.add_parser("search", help="搜索索引")
    search.add_argument("query", help="搜索文字、拼音或缩写")
    search.add_argument(
        "--db", type=Path, default=Path("knowledge.db"), help="索引数据库"
    )
    search.add_argument("--limit", type=int, default=10, help="最多返回多少条结果")
    search.add_argument("--context", type=int, default=1, help="显示前后多少个片段")
    search.add_argument("--json", action="store_true", help="输出 JSON")

    stats = subparsers.add_parser("stats", help="显示索引统计")
    stats.add_argument(
        "--db", type=Path, default=Path("knowledge.db"), help="索引数据库"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            counts = build_database(args.sources, args.db)
            print(f"索引已建立：{args.db.resolve()}")
            print(
                "文档数："
                + "，".join(f"{key}={value}" for key, value in sorted(counts.items()))
            )
            return 0
        if args.command == "search":
            if args.limit < 1 or args.context < 0:
                parser.error("--limit 必须大于 0，--context 不能小于 0")
            results = search_database(
                args.db, args.query, limit=args.limit, context=args.context
            )
            if args.json:
                print(json.dumps(results, ensure_ascii=False, indent=2))
            else:
                _print_results(results)
            return 0
        if args.command == "stats":
            print(json.dumps(database_stats(args.db), ensure_ascii=False, indent=2))
            return 0
    except (OSError, sqlite3.Error) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
