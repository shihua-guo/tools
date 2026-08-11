from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .database import build_database, database_stats, search_database

INTERACTIVE_MENU = """\
请选择操作：
  1. 建立或重建索引
  2. 搜索全部来源
  3. 只搜索聊天记录
  4. 只搜索会议字幕
  5. 多关键词全部命中（AND）
  6. 查看索引统计
  0. 退出
"""


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


def _clean_path_input(value: str) -> Path:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return Path(value)


def _prompt_sources() -> list[Path]:
    print("请输入数据目录，每行一个；直接回车结束。")
    sources: list[Path] = []
    while True:
        value = input(f"数据目录 {len(sources) + 1}: ").strip()
        if not value:
            return sources
        sources.append(_clean_path_input(value))


def _prompt_and_source_type() -> str | None:
    print("限定来源：[1] 全部  [2] 聊天  [3] 会议  [4] 普通文本")
    choices = {"": None, "1": None, "2": "chat", "3": "meeting", "4": "text"}
    while True:
        choice = input("请选择 [1]: ").strip()
        if choice in choices:
            return choices[choice]
        print("无效选项，请输入 1～4。")


def _run_interactive(database: Path, *, limit: int, context: int) -> int:
    print("本地知识检索")
    print(f"当前数据库：{database.expanduser().resolve()}")
    while True:
        print()
        print(INTERACTIVE_MENU, end="")
        try:
            choice = input("请选择 [0-6]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            return 0

        try:
            if choice == "0":
                print("已退出。")
                return 0
            if choice == "1":
                sources = _prompt_sources()
                if not sources:
                    print("已取消：至少需要一个数据目录。")
                    continue
                counts = build_database(sources, database)
                print(f"索引已建立：{database.expanduser().resolve()}")
                print(
                    "文档数："
                    + "，".join(
                        f"{key}={value}" for key, value in sorted(counts.items())
                    )
                )
                continue
            if choice in {"2", "3", "4", "5"}:
                query = input("搜索内容: ").strip()
                if not query:
                    print("已取消：搜索内容不能为空。")
                    continue
                source_type = {"3": "chat", "4": "meeting"}.get(choice)
                match_all = choice == "5"
                if match_all:
                    source_type = _prompt_and_source_type()
                results = search_database(
                    database,
                    query,
                    limit=limit,
                    context=context,
                    source_type=source_type,
                    match_all=match_all,
                )
                _print_results(results)
                continue
            if choice == "6":
                print(
                    json.dumps(database_stats(database), ensure_ascii=False, indent=2)
                )
                continue
            print("无效选项，请输入 0～6。")
        except (OSError, sqlite3.Error) as error:
            print(f"错误：{error}", file=sys.stderr)
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="knowledge-search", description="本地聊天记录与会议字幕检索"
    )
    subparsers = parser.add_subparsers(dest="command")

    interactive = subparsers.add_parser("interactive", help="打开预设操作菜单")
    interactive.add_argument(
        "--db", type=Path, default=Path("knowledge.db"), help="索引数据库"
    )
    interactive.add_argument("--limit", type=int, default=10, help="最多返回多少条结果")
    interactive.add_argument(
        "--context", type=int, default=1, help="显示前后多少个片段"
    )

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
    search.add_argument(
        "--type",
        dest="source_type",
        choices=("chat", "meeting", "text"),
        help="只搜索指定来源类型",
    )
    search.add_argument(
        "--and",
        dest="match_all",
        action="store_true",
        help="要求每个空格分隔的关键词都命中",
    )
    search.add_argument("--json", action="store_true", help="输出 JSON")

    stats = subparsers.add_parser("stats", help="显示索引统计")
    stats.add_argument(
        "--db", type=Path, default=Path("knowledge.db"), help="索引数据库"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        argv = ["interactive"]
    args = parser.parse_args(argv)
    try:
        if args.command == "interactive":
            if args.limit < 1 or args.context < 0:
                parser.error("--limit 必须大于 0，--context 不能小于 0")
            return _run_interactive(args.db, limit=args.limit, context=args.context)
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
                args.db,
                args.query,
                limit=args.limit,
                context=args.context,
                source_type=args.source_type,
                match_all=args.match_all,
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
