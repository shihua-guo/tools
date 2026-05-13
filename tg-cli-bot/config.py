import os
from typing import Set
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

def get_allowed_users() -> Set[int]:
    raw = os.getenv("ALLOWED_USER_IDS", "")
    users = set()
    for item in raw.split(","):
        item = item.strip()
        if item.isdigit():
            users.add(int(item))
    return users

ALLOWED_USER_IDS = get_allowed_users()

CLAUDE_BIN = os.getenv("CLAUDE_BIN", "claude")
CODEX_BIN = os.getenv("CODEX_BIN", "codex")

WORK_DIR = os.getenv("WORK_DIR", ".")
if WORK_DIR == ".":
    WORK_DIR = os.getcwd()

STATE_DIR = os.path.join(WORK_DIR, ".tg-bot-state")
if not os.path.exists(STATE_DIR):
    os.makedirs(STATE_DIR, exist_ok=True)
