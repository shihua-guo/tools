#!/usr/bin/env bash
# ==============================================================================
# Claude-Mem 离线安装自检验证脚本 (Linux / macOS)
# ==============================================================================

WORKER_PORT="${1:-37777}"
VERSION="13.28.0"

USER_HOME="${HOME}"
BUN_BIN="${USER_HOME}/.bun/bin/bun"
MARKETPLACE_DIR="${USER_HOME}/.claude/plugins/marketplaces/thedotmack"
PLUGIN_CACHE_DIR="${USER_HOME}/.claude/plugins/cache/claude-mem@thedotmack/${VERSION}"
CLAUDE_SETTINGS="${USER_HOME}/.claude/settings.json"
INSTALLED_PLUGINS="${USER_HOME}/.claude/plugins/installed_plugins.json"
KNOWN_MARKETPLACES="${USER_HOME}/.claude/plugins/known_marketplaces.json"
MEM_SETTINGS="${USER_HOME}/.claude-mem/settings.json"

echo -e "\033[36m==========================================================\033[0m"
echo -e "\033[36m         Claude-Mem Offline Diagnostics (Linux / macOS)   \033[0m"
echo -e "\033[36m==========================================================\033[0m"

function check_item() {
  local name="$1"
  local status="$2"
  local detail="$3"
  if [ "$status" -eq 0 ]; then
    echo -e "  \033[32m[PASS]\033[0m ${name}"
    [ -n "$detail" ] && echo -e "         \033[90m${detail}\033[0m"
  else
    echo -e "  \033[31m[FAIL]\033[0m ${name}"
    [ -n "$detail" ] && echo -e "         \033[33m${detail}\033[0m"
  fi
}

# 1. Bun
if [ -x "${BUN_BIN}" ]; then
  BUN_VER="$("${BUN_BIN}" --version 2>/dev/null || echo "error")"
  check_item "Bun Runtime" 0 "Path: ${BUN_BIN} (v${BUN_VER})"
elif command -v bun >/dev/null 2>&1; then
  check_item "Bun Runtime" 0 "System PATH Bun ($(bun --version))"
else
  check_item "Bun Runtime" 1 "Bun not found at ~/.bun/bin/bun or system PATH"
fi

# 2. Files
if [ -f "${MARKETPLACE_DIR}/plugin/scripts/worker-service.cjs" ]; then
  check_item "Marketplace Files" 0 "Path: ${MARKETPLACE_DIR}"
else
  check_item "Marketplace Files" 1 "Missing ${MARKETPLACE_DIR}"
fi

if [ -f "${PLUGIN_CACHE_DIR}/scripts/worker-service.cjs" ]; then
  check_item "Plugin Cache Files" 0 "Path: ${PLUGIN_CACHE_DIR}"
else
  check_item "Plugin Cache Files" 1 "Missing ${PLUGIN_CACHE_DIR}"
fi

if [ -d "${PLUGIN_CACHE_DIR}/node_modules/zod" ]; then
  check_item "Plugin Offline Dependencies" 0 "Zod / Tree-sitter node_modules present"
else
  check_item "Plugin Offline Dependencies" 1 "Missing node_modules in plugin cache"
fi

# 3. Registration
if [ -f "${KNOWN_MARKETPLACES}" ] && grep -q "thedotmack" "${KNOWN_MARKETPLACES}"; then
  check_item "Claude Known Marketplace Registration" 0 "${KNOWN_MARKETPLACES}"
else
  check_item "Claude Known Marketplace Registration" 1 "${KNOWN_MARKETPLACES}"
fi

if [ -f "${INSTALLED_PLUGINS}" ] && grep -q "claude-mem@thedotmack" "${INSTALLED_PLUGINS}"; then
  check_item "Claude Installed Plugin Registration" 0 "${INSTALLED_PLUGINS}"
else
  check_item "Claude Installed Plugin Registration" 1 "${INSTALLED_PLUGINS}"
fi

if [ -f "${CLAUDE_SETTINGS}" ] && grep -q "claude-mem@thedotmack" "${CLAUDE_SETTINGS}"; then
  check_item "Claude Settings Plugin Enabled" 0 "${CLAUDE_SETTINGS}"
else
  check_item "Claude Settings Plugin Enabled" 1 "${CLAUDE_SETTINGS}"
fi

# 4. Intranet settings
if [ -f "${MEM_SETTINGS}" ] && grep -q "CLAUDE_MEM_DISABLE_VECTOR_SEARCH" "${MEM_SETTINGS}"; then
  check_item "Intranet Settings (SQLite FTS5 / No Telemetry)" 0 "${MEM_SETTINGS}"
else
  check_item "Intranet Settings (SQLite FTS5 / No Telemetry)" 1 "${MEM_SETTINGS}"
fi

# 5. Worker health check
HEALTH_URL="http://127.0.0.1:${WORKER_PORT}/api/health"
if command -v curl >/dev/null 2>&1; then
  HEALTH_RESP="$(curl -s --connect-timeout 2 "${HEALTH_URL}" || echo "")"
  if echo "${HEALTH_RESP}" | grep -q '"status":"ok"'; then
    check_item "Worker Daemon Status" 0 "Running on port ${WORKER_PORT}"
  else
    check_item "Worker Daemon Status" 1 "Not responding on port ${WORKER_PORT} (run 'claude-mem start' or launch Claude Code)"
  fi
fi

echo -e "\033[36m==========================================================\033[0m\n"
