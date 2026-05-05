from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    pass


@dataclass
class ClaudeConfig:
    bin: str
    timeout_seconds: int
    permission_mode: str
    model: str
    max_turns: int


@dataclass
class AppConfig:
    host: str
    port: int
    shared_secret: str
    tracked_user: str
    ai_prefixes: list[str]
    repos: list[str]
    repo_paths: dict[str, str]
    state_dir: str
    log_dir: str
    per_issue_cooldown_seconds: int
    claude: ClaudeConfig


def _require_str(raw: dict, key: str) -> str:
    value = raw.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ConfigError(f"Missing required string config: {key}")


def _require_int(raw: dict, key: str) -> int:
    value = raw.get(key)
    if isinstance(value, int):
        return value
    raise ConfigError(f"Missing required integer config: {key}")


def _require_list(raw: dict, key: str) -> list[str]:
    value = raw.get(key)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        cleaned = [item.strip() for item in value if item.strip()]
        if cleaned:
            return cleaned
    raise ConfigError(f"Missing required string list config: {key}")


def _require_dict(raw: dict, key: str) -> dict:
    value = raw.get(key)
    if isinstance(value, dict):
        return value
    raise ConfigError(f"Missing required object config: {key}")


def load_config(path: str | os.PathLike[str]) -> AppConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    claude_raw = _require_dict(raw, "claude")
    cfg = AppConfig(
        host=_require_str(raw, "host"),
        port=_require_int(raw, "port"),
        shared_secret=_require_str(raw, "shared_secret"),
        tracked_user=_require_str(raw, "tracked_user"),
        ai_prefixes=_require_list(raw, "ai_prefixes"),
        repos=_require_list(raw, "repos"),
        repo_paths={str(key): str(value) for key, value in _require_dict(raw, "repo_paths").items()},
        state_dir=_require_str(raw, "state_dir"),
        log_dir=_require_str(raw, "log_dir"),
        per_issue_cooldown_seconds=_require_int(raw, "per_issue_cooldown_seconds"),
        claude=ClaudeConfig(
            bin=_require_str(claude_raw, "bin"),
            timeout_seconds=_require_int(claude_raw, "timeout_seconds"),
            permission_mode=_require_str(claude_raw, "permission_mode"),
            model=str(claude_raw.get("model", "")).strip(),
            max_turns=int(claude_raw.get("max_turns", 12)),
        ),
    )
    if not cfg.shared_secret or cfg.shared_secret == "change-me":
        raise ConfigError("shared_secret must be changed from the example value")
    for repo in cfg.repos:
        if repo not in cfg.repo_paths:
            raise ConfigError(f"Missing repo_paths entry for configured repo: {repo}")
    return cfg
