#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

export VIDEO_ROOT="${VIDEO_ROOT:-$PWD/videos}"
export OUTPUT_ROOT="${OUTPUT_ROOT:-$PWD/backend/output}"
export TASK_DB_PATH="${TASK_DB_PATH:-$PWD/backend/tasks.db}"
export QWEN_API_KEY="${QWEN_API_KEY:-}"

python backend/main.py
