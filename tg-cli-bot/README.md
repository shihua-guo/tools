# TG-CLI-BOT

一个独立的 Telegram 机器人，用于在 Linux 服务器上通过 Telegram 调用 Claude Code 和 Codex CLI。它会按 Telegram chat 记录 Claude Session ID / Codex Thread ID，支持连续对话，也可以通过 `/reset` 手动重置上下文。

## 当前部署

- 服务器：`root@192.168.2.200`
- 部署目录：`/root/tg-cli-bot`
- 工作目录：`/root`
- 运行方式：`systemd`
- 服务名：`tg-cli-bot.service`
- Telegram Bot：`https://t.me/alan9uoBot`
- 导航页：`http://192.168.2.200/`

## 使用方法

在 Telegram 中打开 bot 后发送：

```text
/start
```

常用命令：

```text
/claude 请只回复 OK
/codex 请只回复 OK
/reset
```

- `/claude <prompt>`：调用 Claude Code。
- `/codex <prompt>`：调用 Codex CLI。
- `/reset`：清空当前 Telegram chat 对应的 Claude/Codex 会话记录。

默认 `WORK_DIR=/root`，所以不写绝对路径时，CLI 会在 `/root` 下执行。

## 配置

复制示例配置：

```bash
cp .env.example .env
chmod 600 .env
```

编辑 `.env`：

```bash
TELEGRAM_BOT_TOKEN="your_bot_token_here"
ALLOWED_USER_IDS="123456789"
CLAUDE_BIN="/root/.nvm/versions/node/v22.22.2/bin/claude"
CODEX_BIN="/root/.nvm/versions/node/v22.22.2/bin/codex"
WORK_DIR="/root"
```

`ALLOWED_USER_IDS` 必须配置为允许使用 bot 的 Telegram User ID，多个 ID 用英文逗号分隔。

## 本地运行

服务器需要先准备好：

- Python 3.9+
- 可直接运行的 `claude`
- 可直接运行的 `codex`

安装依赖：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install python-telegram-bot python-dotenv
```

启动：

```bash
python bot.py
```

手动运行只适合调试。生产环境建议使用 systemd。

## systemd 部署

示例服务文件：`/etc/systemd/system/tg-cli-bot.service`

```ini
[Unit]
Description=Telegram CLI Bot for Claude and Codex
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/root/tg-cli-bot
Environment=HOME=/root
Environment=PATH=/root/.nvm/versions/node/v22.22.2/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
EnvironmentFile=/root/tg-cli-bot/.env
ExecStart=/root/tg-cli-bot/.venv/bin/python /root/tg-cli-bot/bot.py
Restart=always
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

启用并启动：

```bash
systemctl daemon-reload
systemctl enable --now tg-cli-bot.service
```

维护命令：

```bash
systemctl status tg-cli-bot.service
journalctl -u tg-cli-bot.service -f
systemctl restart tg-cli-bot.service
```

## 排查

如果 Telegram 中一直停在“正在运行 Claude，请稍候...”，先看服务日志：

```bash
journalctl -u tg-cli-bot.service -n 120 --no-pager
```

如果看到 `PermissionError: [Errno 13] Permission denied: .../bin/claude`，通常是 Claude Code npm 安装不完整或 `bin/claude` 指向了占位文件。可尝试：

```bash
npm install -g @anthropic-ai/claude-code --include=optional
claude --version
systemctl restart tg-cli-bot.service
```

确认 CLI 本身可用：

```bash
claude --version
codex --version
cd /root
claude -p --verbose --output-format stream-json --permission-mode acceptEdits "请只回复 OK"
```

## 安全提示

这个 bot 可以通过 Telegram 触发服务器上的 Claude/Codex 执行任务，权限很高：

- 不要提交 `.env`。
- 必须设置 `ALLOWED_USER_IDS`。
- `TELEGRAM_BOT_TOKEN` 泄露后应立即在 BotFather 重置。
- 尽量把 `WORK_DIR` 指向明确的工作目录。
