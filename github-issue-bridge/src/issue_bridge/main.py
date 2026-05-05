from __future__ import annotations

import argparse
import sys
from pathlib import Path

from issue_bridge.config import ConfigError, load_config
from issue_bridge.server import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the GitHub Issue Bridge local daemon.")
    parser.add_argument(
        "--config",
        default="issue-bridge.json",
        help="Path to issue-bridge.json",
    )
    args = parser.parse_args(argv)
    try:
        cfg = load_config(Path(args.config))
    except (OSError, ConfigError) as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    serve(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
