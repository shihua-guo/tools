#!/usr/bin/env bash
set -euo pipefail

target="${1:-/usr/local/bin/cc-switch}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install -m 0755 "$script_dir/cc-switch" "$target"
echo "installed $target"

if [ -f "$HOME/.claude/settings.json" ]; then
  "$target" import current-remote "$HOME/.claude/settings.json"
  "$target" use current-remote
else
  echo "no $HOME/.claude/settings.json found; add a profile with cc-switch add"
fi
