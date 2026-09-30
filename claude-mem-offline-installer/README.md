# Claude-Mem 离线安装包 (Offline Installer)

> **版本**：v13.28.0  
> **适用环境**：纯内网 / 无外网隔离环境（Air-gapped / Intranet / Enterprise Sandbox）  
> **支持平台**：Windows (x64) / Linux (x64, glibc >= 2.28) / macOS (需预装 bun)

---

## 目录
1. [核心特性](#一核心特性)
2. [环境要求](#二环境要求)
3. [安装包目录结构](#三安装包目录结构)
4. [Windows 一键离线安装指南](#四windows-一键离线安装指南)
5. [Linux 一键离线安装指南](#五linux-一键离线安装指南)
6. [内网大模型服务接入配置 (LLM Provider)](#六内网大模型服务接入配置-llm-provider)
7. [常用运维与管理命令](#七常用运维与管理命令)
8. [常见问题与诊断排查 (FAQ)](#八常见问题与诊断排查-faq)

---

## 一、核心特性

1. **100% 离线自闭环**：
   - 彻底剥离官方在线安装脚本中的 `curl bun.sh`、`npm install`、`git clone` 和在线浏览器 OAuth 流程。
   - 内置预装完整的 37+ 个核心依赖（包括 Tree-sitter 全语言 AST 语法解析库、Better-Auth 认证组件、Zod 数据校验器等）。
2. **预置双架构核心运行时**：
   - 包含官方独立二进制：**Bun v1.4.2** 与 **uv v0.12.21**（支持 Windows-x64 与 Linux-x64），无需在内网配置复杂的 node/bun 打包环境。
3. **针对内网环境深度调优**：
   - **内置纯本地 SQLite FTS5 全文搜索**：默认禁用在线 Chroma/Python 依赖 (`CLAUDE_MEM_DISABLE_VECTOR_SEARCH: true`)，纯 C/SQLite 本地高性能运行。
   - **关闭外网遥测与统计**：默认关闭 PostHog 数据上报 (`CLAUDE_MEM_TELEMETRY: false`)。
   - **关闭在线自动更新与检测**：防止内网环境下后台轮询 GitHub 出现超时阻塞。
   - **预置版本防重装标记**：写入 `.install-version` 标记，防止 Claude Code 在会话启动时重复触发联网下载。
4. **一键安装与自检脚本**：
   - 提供 Windows PowerShell (`install.ps1`) 与 Linux Shell (`install.sh`) 自动化配置脚本。
   - 提供健康自检脚本 (`verify.ps1` / `verify.sh`)，即时验证各运行时、插件注册表与后台 Worker 状态。

---

## 二、环境要求

| 组件 | 要求 | 说明 |
| :--- | :--- | :--- |
| **操作系统** | Windows 10/11 / Windows Server (x64) 或 Linux x64 (glibc >= 2.28) | 需 64 位 x86_64 架构 |
| **Node.js** | `>= 20.12.0` | 内网运行 Claude Code 所必需的 Node 运行时 |
| **Claude Code** | 已就绪 | Claude Code CLI 已安装在机器环境中 |
| **Bun** | **已预置** | 本离线包已内置，安装脚本会自动部署至 `~/.bun/bin/` |
| **uv / uvx** | **已预置** | 本离线包已内置，安装脚本会自动部署至 `~/.bun/bin/` |

---

## 三、安装包目录结构

```text
claude-mem-offline-installer/
├── bin/
│   ├── windows-x64/          # Windows 运行时 (bun.exe, uv.exe, uvx.exe)
│   └── linux-x64/            # Linux 运行时 (bun, uv, uvx)
├── marketplace/              # Claude Code 插件市场离线注册目录
│   ├── .claude-plugin/       # 市场元数据定义
│   └── node_modules/         # 市场运行时前置依赖
├── plugin/                   # Claude-Mem 核心插件目录
│   ├── node_modules/         # 完整预装的离线依赖包 (含 tree-sitter 等)
│   ├── scripts/              # 核心服务 (worker-service.cjs, bun-runner.js 等)
│   ├── modes/                # 记忆模式预设
│   └── sqlite/               # 数据库 schema 与迁移脚本
├── packages/                 # 官方 npm 离线归档包 (claude-mem-13.28.0.tgz)
├── templates/                # 内网推荐 settings.json 配置模板
├── install.ps1               # Windows 一键自动化离线安装脚本
├── install.sh                # Linux / macOS 一键自动化离线安装脚本
├── verify.ps1                # Windows 离线安装自检脚本
├── verify.sh                 # Linux 离线安装自检脚本
└── README.md                 # 本手册文档
```

---

## 四、Windows 一键离线安装指南

### 1. 复制与解压
将 `claude-mem-offline-installer.zip` 拷贝至内网机器并解压至任意目录（如 `D:\claude-mem-offline-installer`）。

### 2. 执行一键安装
以当前用户权限打开 **PowerShell**，进入解压目录并执行：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\install.ps1
```

> **可选参数**：
> - `-Provider <provider>`：设置默认 LLM 提供商（可选 `claude`, `host`, `openai`, 默认为 `claude`）。
> - `-KeepAutoMemory`：保留 Claude Code 内置的 auto-memory（默认会自动禁用以防记忆冲突）。
> - `-SkipWorkerStart`：安装后不立即启动后台守护进程。

**安装脚本自动执行以下操作**：
1. 部署 `bun.exe`、`uv.exe`、`uvx.exe` 到 `%USERPROFILE%\.bun\bin\` 并注册系统用户 PATH 环境变量。
2. 创建全局命令快捷包装脚本 `claude-mem.cmd`。
3. 部署插件市场目录至 `%USERPROFILE%\.claude\plugins\marketplaces\thedotmack`。
4. 部署完整插件依赖缓存至 `%USERPROFILE%\.claude\plugins\cache\claude-mem@thedotmack\13.28.0`。
5. 注册 Claude 插件索引（`known_marketplaces.json`、`installed_plugins.json`、`settings.json`）。
6. 初始化内网专用配置文件 `%USERPROFILE%\.claude-mem\settings.json`（开启 SQLite FTS5，关闭遥测与更新）。
7. 启动并验证 Claude-Mem 后台 Worker 服务。

### 3. 运行自检
安装完成后，执行验证脚本：
```powershell
powershell.exe -ExecutionPolicy Bypass -File .\verify.ps1
```
当所有检查项输出 `[PASS]` 时，即代表离线部署完全成功。

---

## 五、Linux 一键离线安装指南

### 1. 复制与解压
将 `claude-mem-offline-installer.tar.gz` 拷贝至内网 Linux 机器，解压：

```bash
tar -xzf claude-mem-offline-installer.tar.gz
cd claude-mem-offline-installer
```

### 2. 执行一键安装
赋予执行权限并运行：

```bash
chmod +x install.sh verify.sh
./install.sh
```

> **可选环境变量参数**：
> - `PROVIDER=openai ./install.sh`（指定内网 LLM 提供商）。
> - `KEEP_AUTO_MEMORY=1 ./install.sh`（保留内置 memory）。
> - `SKIP_WORKER_START=1 ./install.sh`（跳过安装后立即启动）。

### 3. 刷新环境变量与自检
```bash
# 刷新当前终端 PATH (将 ~/.bun/bin 引入环境)
source ~/.bashrc

# 执行自检脚本
./verify.sh
```

---

## 六、内网大模型服务接入配置 (LLM Provider)

Claude-Mem 在会话结束或产生关键操作时，会自动提炼关键事实（Observations）与总结（Summaries）。这需要模型能力支持。

配置文件位于：
- **Windows**: `%USERPROFILE%\.claude-mem\settings.json`
- **Linux/macOS**: `~/.claude-mem/settings.json`

根据内网网络与模型环境，推荐以下两种模式：

### 模式 A：宿主复用模式 (推荐)
直接复用当前 Claude Code 的授权（适合内网中已通过中转代理正常运行 Claude Code 的场景）：
```json
{
  "CLAUDE_MEM_MODEL_PROVIDER": "claude",
  "CLAUDE_MEM_DISABLE_VECTOR_SEARCH": true,
  "CLAUDE_MEM_TELEMETRY": false,
  "CLAUDE_MEM_AUTO_UPDATE": false
}
```

### 模式 B：内网自定义 OpenAI 兼容接口模式
适用于内网搭建了 **OneAPI**、**NewAPI**、**vLLM**、**Ollama** 或企业私有大模型网关：
```json
{
  "CLAUDE_MEM_MODEL_PROVIDER": "openai",
  "CLAUDE_MEM_OPENAI_BASE_URL": "http://192.168.1.100:8000/v1",
  "CLAUDE_MEM_OPENAI_API_KEY": "sk-your-intranet-api-key",
  "CLAUDE_MEM_CUSTOM_MODEL": "qwen2.5-coder-32b-instruct",
  "CLAUDE_MEM_DISABLE_VECTOR_SEARCH": true,
  "CLAUDE_MEM_TELEMETRY": false,
  "CLAUDE_MEM_AUTO_UPDATE": false
}
```

---

## 七、常用运维与管理命令

全局命令已自动安装为 `claude-mem`，可在任意终端路径运行：

```bash
# 查看 Claude-Mem Worker 运行状态与内存数据统计
claude-mem status

# 启动 Claude-Mem 守护进程
claude-mem start

# 停止 Claude-Mem 守护进程
claude-mem stop

# 重启 Claude-Mem 守护进程
claude-mem restart

# 运行依赖项诊断检查
claude-mem doctor
```

### 离线数据存储位置
- **核心 SQLite 数据库**：
  - Windows: `%USERPROFILE%\.claude-mem\claude-mem.db`
  - Linux: `~/.claude-mem/claude-mem.db`
- **运行日志目录**：
  - Windows: `%USERPROFILE%\.claude-mem\logs\`
  - Linux: `~/.claude-mem/logs/`
- **本地 Web 监控查看器 (Viewer)**：
  - 启动后浏览器访问：`http://127.0.0.1:37777/`

---

## 八、常见问题与诊断排查 (FAQ)

### Q1: `claude-mem status` 显示 `Dependencies: degraded (uvx unavailable for vector search)` 是正常的吗？
**完全正常**。  
官方默认的向量检索尝试通过 `uvx` 从外网 PyPI 自动拉取 Chroma 服务，在纯内网环境下会报错。本离线包配置了 `CLAUDE_MEM_DISABLE_VECTOR_SEARCH: true`，系统已自动平滑降级使用内置的 **SQLite FTS5 原生全文检索**。所有持久化跨会话记忆、关键词搜索和记忆注入均 100% 正常工作，无需联网。

### Q2: 为什么终端提示 `bun: command not found` 或不是内部命令？
安装程序已将 `~/.bun/bin` 添加到用户 PATH。如果当前打开的终端尚未刷新环境：
- **Windows**：重新打开一个新的 PowerShell 终端窗口。
- **Linux**：执行 `source ~/.bashrc` 或 `source ~/.zshrc`。

### Q3: 内网环境下运行 Claude Code 时，Claude-Mem 是如何被自动唤起的？
在 Claude Code 会话生命周期中：
1. 启动会话时，Claude Code 会读取 `~/.claude/plugins/marketplaces/thedotmack/plugin/hooks/hooks.json`。
2. 触发 `SessionStart` 钩子，调用 `scripts/bun-runner.js` 启动后台 Worker 守护进程并注入当前项目上下文。
3. 交互过程中，触发 `PostToolUse` 钩子自动采集操作事实。
4. 会话结束时，触发 `Stop` / `SessionEnd` 钩子提炼长效记忆存入 SQLite。
整个过程对使用者完全透明。

### Q4: 如何彻底卸载或重装？
如需清理：
1. 停止服务：`claude-mem stop`
2. 删除插件与数据目录：
   - Windows:
     ```powershell
     Remove-Item -Recurse -Force "$HOME\.claude-mem"
     Remove-Item -Recurse -Force "$HOME\.claude\plugins\marketplaces\thedotmack"
     Remove-Item -Recurse -Force "$HOME\.claude\plugins\cache\claude-mem@thedotmack"
     ```
   - Linux:
     ```bash
     rm -rf ~/.claude-mem ~/.claude/plugins/marketplaces/thedotmack ~/.claude/plugins/cache/claude-mem@thedotmack
     ```
