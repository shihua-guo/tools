# Linux Claude Code 配置切换工具

这个目录保存了在 `root@192.168.2.200` 上实现的命令行版 `cc-switch`。它用于切换 Claude Code 的 `~/.claude/settings.json` 里的 `env` 配置，效果类似本机的 CC switch。

## 文件

- `cc-switch`: Python 命令行脚本。
- `install-linux.sh`: Linux 安装脚本，会安装到 `/usr/local/bin/cc-switch`，并把当前远端配置导入为 `current-remote`。
- `README.md`: 本说明。

## 当前远端状态

远端已经安装：

```bash
/usr/local/bin/cc-switch
```

远端当前 profile：

```bash
cc-switch list
# * current-remote
```

当前远端配置来源：

```bash
/root/.claude/settings.json
```

切换时会自动备份旧配置到：

```bash
/root/.claude/backups/settings.cc-switch-*.json
```

## 安装或重装

把本目录复制到 Linux 后执行：

```bash
chmod +x install-linux.sh cc-switch
sudo ./install-linux.sh
```

如果是 `root` 用户，也可以直接：

```bash
./install-linux.sh
```

## 常用命令

查看 profile：

```bash
cc-switch list
```

查看当前切换名和生效环境变量：

```bash
cc-switch current
```

查看正在写入 Claude Code 的 env：

```bash
cc-switch active
```

查看某个 profile：

```bash
cc-switch show current-remote
```

切换 profile：

```bash
cc-switch use current-remote
```

删除 profile：

```bash
cc-switch remove profile-name
```

## 添加新配置

推荐使用 `--token-stdin`，避免 token 进入 shell history。注意：`--token-stdin` 后面不要再跟 token。

例如添加 DashScope：

```bash
cc-switch add dashscope \
  --base-url https://dashscope.aliyuncs.com/apps/anthropic \
  --model qwen-flash-2025-07-28 \
  --token-stdin
```

粘贴 token 后按 `Ctrl-D` 结束输入，然后切换：

```bash
cc-switch use dashscope
claude
```

也可以用管道传入：

```bash
printf '%s' 'sk-xxx' | cc-switch add dashscope \
  --base-url https://dashscope.aliyuncs.com/apps/anthropic \
  --model qwen-flash-2025-07-28 \
  --token-stdin
```

如果不介意 token 出现在 shell history，也可以直接使用：

```bash
cc-switch add dashscope \
  --base-url https://dashscope.aliyuncs.com/apps/anthropic \
  --model qwen-flash-2025-07-28 \
  --token sk-xxx
```

归档版脚本兼容误写成 `--token-stdin sk-xxx` 的情况，但仍建议使用交互粘贴或管道。

## 目录结构

脚本会使用这些目录：

```bash
~/.claude/settings.json
~/.claude/cc-switch/current
~/.claude/cc-switch/profiles/*.json
~/.claude/backups/settings.cc-switch-*.json
```

## 注意

- 切换只影响之后新启动的 `claude` 进程。
- 已经运行中的 `claude` 需要退出后重新启动。
- 输出会把 `TOKEN`、`KEY`、`SECRET`、`AUTH` 相关变量显示为 `[redacted]`。
- 不要把真实 token 提交到仓库或同步目录里。
