#!/usr/bin/env bash
# ==============================================================================
# Claude-Mem 离线安装脚本 (Linux / macOS)
# 适用于无外网连接的内网 Linux / macOS 环境。
# 自动部署独立 Bun 运行时、Claude-Mem 完整插件、配置 Claude Code 注册信息并启动后台服务。
# ==============================================================================

set -euo pipefail

VERSION="13.28.0"
IDE="claude-code"
PROVIDER="claude"
WORKER_PORT="37777"
SKIP_WORKER_START=false
KEEP_AUTO_MEMORY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ide)
      IDE="$2"
      shift 2
      ;;
    --provider)
      PROVIDER="$2"
      shift 2
      ;;
    --port)
      WORKER_PORT="$2"
      shift 2
      ;;
    --skip-worker-start)
      SKIP_WORKER_START=true
      shift
      ;;
    --keep-auto-memory)
      KEEP_AUTO_MEMORY=true
      shift
      ;;
    -h|--help)
      echo "用法: ./install.sh [选项]"
      echo "选项:"
      echo "  --ide <claude-code|cursor|codex|antigravity|all>   目标 IDE (默认: claude-code)"
      echo "  --provider <claude|host|openai|gemini|openrouter>  AI 记忆总结后端 (默认: claude)"
      echo "  --port <37777>                                     Worker 端口 (默认: 37777)"
      echo "  --skip-worker-start                                安装后不自动启动后台服务"
      echo "  --keep-auto-memory                                 不禁用 Claude Code 原生记忆"
      exit 0
      ;;
    *)
      echo "未知参数: $1"
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_HOME="${HOME}"
CLAUDE_DIR="${USER_HOME}/.claude"
CLAUDE_MEM_DIR="${USER_HOME}/.claude-mem"
BUN_BIN_DIR="${USER_HOME}/.bun/bin"
MARKETPLACE_DIR="${CLAUDE_DIR}/plugins/marketplaces/thedotmack"
PLUGIN_CACHE_DIR="${CLAUDE_DIR}/plugins/cache/claude-mem@thedotmack/${VERSION}"

echo -e "\033[32m==========================================================\033[0m"
echo -e "\033[32m      Claude-Mem v${VERSION} 离线安装程序 (Linux / macOS)     \033[0m"
echo -e "\033[32m==========================================================\033[0m"

# 1. 配置独立运行时
echo -e "\n\033[36m[+] 1/6 配置独立运行时 (Bun / uv)...\033[0m"
mkdir -p "${BUN_BIN_DIR}"

ARCH="$(uname -m)"
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"

if [[ -f "${SCRIPT_DIR}/bin/linux-x64/bun" && "${ARCH}" == "x86_64" && "${OS}" == "linux" ]]; then
  cp -f "${SCRIPT_DIR}/bin/linux-x64/bun" "${BUN_BIN_DIR}/bun"
  chmod +x "${BUN_BIN_DIR}/bun"
  if [[ -f "${SCRIPT_DIR}/bin/linux-x64/uv" ]]; then
    cp -f "${SCRIPT_DIR}/bin/linux-x64/uv" "${BUN_BIN_DIR}/uv"
    cp -f "${SCRIPT_DIR}/bin/linux-x64/uvx" "${BUN_BIN_DIR}/uvx"
    chmod +x "${BUN_BIN_DIR}/uv" "${BUN_BIN_DIR}/uvx"
  fi
  echo -e "  \033[32m[OK] 已部署预置 Bun/uv 运行时至: ${BUN_BIN_DIR}/bun\033[0m"
elif command -v bun >/dev/null 2>&1; then
  echo -e "  \033[32m[OK] 系统已存在可用 Bun: $(command -v bun) ($(bun --version))\033[0m"
else
  echo -e "  \033[33m[WARN] 未检测到内置架构匹配的 Bun 二进制，请确保系统 PATH 中已存在 bun (>=1.1.31)\033[0m"
fi

BUN_EXEC="${BUN_BIN_DIR}/bun"
if [[ ! -x "${BUN_EXEC}" ]]; then
  BUN_EXEC="$(command -v bun || echo "bun")"
fi

# 写入 PATH 环境变量到 shell profile
for rc in "${USER_HOME}/.bashrc" "${USER_HOME}/.zshrc"; do
  if [[ -f "${rc}" ]]; then
    if ! grep -q '\.bun/bin' "${rc}"; then
      echo 'export PATH="$HOME/.bun/bin:$PATH"' >> "${rc}"
      echo -e "  \033[32m[OK] 已将 ~/.bun/bin 加入 ${rc}\033[0m"
    fi
  fi
done
export PATH="${BUN_BIN_DIR}:${PATH}"

# 创建全局命令 wrapper: claude-mem
cat << 'EOF' > "${BUN_BIN_DIR}/claude-mem"
#!/usr/bin/env bash
BUN_BIN="$HOME/.bun/bin/bun"
if [ ! -x "$BUN_BIN" ]; then
  BUN_BIN="$(command -v bun || echo "bun")"
fi
exec "$BUN_BIN" "$HOME/.claude/plugins/marketplaces/thedotmack/plugin/scripts/worker-service.cjs" "$@"
EOF
chmod +x "${BUN_BIN_DIR}/claude-mem"
echo -e "  \033[32m[OK] 全局命令创建完成: claude-mem\033[0m"

# 2. 部署 Marketplace
echo -e "\n\033[36m[+] 2/6 部署插件市场目录 (Marketplace)...\033[0m"
rm -rf "${MARKETPLACE_DIR}"
mkdir -p "${MARKETPLACE_DIR}"
cp -a "${SCRIPT_DIR}/marketplace/." "${MARKETPLACE_DIR}/"
mkdir -p "${MARKETPLACE_DIR}/plugin"
cp -a "${SCRIPT_DIR}/plugin/." "${MARKETPLACE_DIR}/plugin/"
echo -e "  \033[32m[OK] 市场目录部署至: ${MARKETPLACE_DIR}\033[0m"

# 3. 部署 Plugin Cache
echo -e "\n\033[36m[+] 3/6 部署插件缓存目录 (Plugin Cache)...\033[0m"
rm -rf "${PLUGIN_CACHE_DIR}"
mkdir -p "${PLUGIN_CACHE_DIR}"
cp -a "${SCRIPT_DIR}/plugin/." "${PLUGIN_CACHE_DIR}/"
echo -e "  \033[32m[OK] 插件缓存部署至: ${PLUGIN_CACHE_DIR}\033[0m"

# 4. 配置 Claude Code 插件注册信息
echo -e "\n\033[36m[+] 4/6 配置插件注册与设置...\033[0m"
mkdir -p "${CLAUDE_DIR}/plugins"

NOW="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# 4.1 known_marketplaces.json
KNOWN_MKTS_PATH="${CLAUDE_DIR}/plugins/known_marketplaces.json"
cat << EOF > "${KNOWN_MKTS_PATH}"
{
  "thedotmack": {
    "source": {
      "source": "github",
      "repo": "thedotmack/claude-mem"
    },
    "installLocation": "${MARKETPLACE_DIR}",
    "lastUpdated": "${NOW}",
    "autoUpdate": false
  }
}
EOF
echo -e "  \033[32m[OK] 已更新: ${KNOWN_MKTS_PATH}\033[0m"

# 4.2 installed_plugins.json
INSTALLED_PLUGINS_PATH="${CLAUDE_DIR}/plugins/installed_plugins.json"
cat << EOF > "${INSTALLED_PLUGINS_PATH}"
{
  "version": 2,
  "plugins": {
    "claude-mem@thedotmack": [
      {
        "scope": "user",
        "installPath": "${PLUGIN_CACHE_DIR}",
        "version": "${VERSION}",
        "installedAt": "${NOW}",
        "lastUpdated": "${NOW}"
      }
    ]
  }
}
EOF
echo -e "  \033[32m[OK] 已更新: ${INSTALLED_PLUGINS_PATH}\033[0m"

# 4.3 settings.json (Claude Code settings)
CLAUDE_SETTINGS_PATH="${CLAUDE_DIR}/settings.json"
if [[ -f "${CLAUDE_SETTINGS_PATH}" ]]; then
  # 使用 node 或 jq 或临时 python 合并，这里用简单的内联 Node/Bun
  "${BUN_EXEC}" -e "
    const fs = require('fs');
    let s = {};
    try { s = JSON.parse(fs.readFileSync('${CLAUDE_SETTINGS_PATH}', 'utf8')); } catch {}
    s.enabledPlugins = s.enabledPlugins || {};
    s.enabledPlugins['claude-mem@thedotmack'] = true;
    if ('${KEEP_AUTO_MEMORY}' !== 'true') {
      s.env = s.env || {};
      s.env['CLAUDE_CODE_DISABLE_AUTO_MEMORY'] = '1';
    }
    fs.writeFileSync('${CLAUDE_SETTINGS_PATH}', JSON.stringify(s, null, 2));
  " 2>/dev/null || true
else
  cat << EOF > "${CLAUDE_SETTINGS_PATH}"
{
  "enabledPlugins": {
    "claude-mem@thedotmack": true
  },
  "env": {
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"
  }
}
EOF
fi
echo -e "  \033[32m[OK] 已更新: ${CLAUDE_SETTINGS_PATH}\033[0m"

# 5. 配置 Claude-Mem 内网参数
echo -e "\n\033[36m[+] 5/6 配置 Claude-Mem 内网参数 (~/.claude-mem/settings.json)...\033[0m"
mkdir -p "${CLAUDE_MEM_DIR}"
MEM_SETTINGS_PATH="${CLAUDE_MEM_DIR}/settings.json"
cat << EOF > "${MEM_SETTINGS_PATH}"
{
  "CLAUDE_MEM_DISABLE_VECTOR_SEARCH": true,
  "CLAUDE_MEM_TELEMETRY": false,
  "CLAUDE_MEM_AUTO_UPDATE": false,
  "CLAUDE_MEM_PROVIDER": "${PROVIDER}",
  "CLAUDE_MEM_WORKER_PORT": "${WORKER_PORT}"
}
EOF
echo -e "  \033[32m[OK] 已优化内网配置: 启用 SQLite FTS5 本地检索, 禁用遥测与外网更新\033[0m"

# 6. 可选 IDE 集成
if [[ "${IDE}" == "cursor" || "${IDE}" == "all" ]]; then
  echo -e "\n\033[36m配置 Cursor 集成...\033[0m"
  mkdir -p "${USER_HOME}/.cursor"
  cat << EOF > "${USER_HOME}/.cursor/mcp.json"
{
  "mcpServers": {
    "claude-mem": {
      "command": "${BUN_EXEC}",
      "args": ["${PLUGIN_CACHE_DIR}/scripts/mcp-server.cjs"]
    }
  }
}
EOF
  echo -e "  \033[32m[OK] Cursor MCP 配置已写入: ~/.cursor/mcp.json\033[0m"
fi

if [[ "${IDE}" == "antigravity" || "${IDE}" == "all" ]]; then
  echo -e "\n\033[36m配置 Antigravity CLI 集成...\033[0m"
  mkdir -p "${USER_HOME}/.gemini/config"
  cat << EOF > "${USER_HOME}/.gemini/config/mcp_config.json"
{
  "mcpServers": {
    "claude-mem": {
      "command": "${BUN_EXEC}",
      "args": ["${PLUGIN_CACHE_DIR}/scripts/mcp-server.cjs"]
    }
  }
}
EOF
  echo -e "  \033[32m[OK] Antigravity MCP 配置已写入: ~/.gemini/config/mcp_config.json\033[0m"
fi

# 7. 启动并测试后台服务
if [[ "${SKIP_WORKER_START}" != "true" ]]; then
  echo -e "\n\033[36m[+] 6/6 启动并验证 Claude-Mem 后台 Worker 服务...\033[0m"
  WORKER_SCRIPT="${MARKETPLACE_DIR}/plugin/scripts/worker-service.cjs"
  
  "${BUN_EXEC}" "${WORKER_SCRIPT}" stop >/dev/null 2>&1 || true
  sleep 1
  "${BUN_EXEC}" "${WORKER_SCRIPT}" start >/dev/null 2>&1 || true
  sleep 2

  HEALTH_URL="http://127.0.0.1:${WORKER_PORT}/api/health"
  if command -v curl >/dev/null 2>&1; then
    HEALTH_RESP="$(curl -s --connect-timeout 3 "${HEALTH_URL}" || echo "")"
    if echo "${HEALTH_RESP}" | grep -q '"status":"ok"'; then
      echo -e "  \033[32m[OK] Worker 服务运行正常! (Port: ${WORKER_PORT})\033[0m"
    else
      echo -e "  \033[33m[WARN] Worker 正在后台初始化中，可稍后运行 'claude-mem status' 检查。\033[0m"
    fi
  fi
fi

echo -e "\n\033[32m==========================================================\033[0m"
echo -e "\033[32m           Claude-Mem 离线安装全部顺利完成!               \033[0m"
echo -e "\033[32m==========================================================\033[0m"
echo -e "直接启动 Claude Code 即可自动利用持久化记忆！"
echo -e "常用管理命令:"
echo -e "  claude-mem status   - 查看记忆服务状态与统计"
echo -e "  claude-mem start    - 启动记忆服务"
echo -e "  claude-mem stop     - 停止记忆服务"
echo -e "  claude-mem doctor   - 运行诊断检查\n"
