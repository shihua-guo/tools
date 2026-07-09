# OpenAI Codex CLI 账号切换器 (Codex Switcher)

这是一个跨平台（Windows / Linux）的 Python 脚本，专门用于 OpenAI Codex CLI 工具的多账号和聊天记录管理。

由于 OpenAI Codex CLI 将配置和聊天记录存储在本地的 `~/.codex` 目录中，直接退出或覆盖 Token 会导致之前的聊天历史被抹除。本工具通过**文件夹级隔离与整包替换**机制，让每个账号都能独立保留完整的聊天记录。

## 📁 核心原理

1. 您的所有不同账号数据将被存放并封存在 `~/.codex_profiles` 文件夹下。
2. 工具会智能地将您指定的账号配置从 `~/.codex_profiles/账号名` 替换回真正的系统工作目录 `~/.codex` 中，实现无缝切换。

## 🚀 快速上手 (交互式菜单)

我已经为您配置好了快捷启动模式。在您的 Windows 系统下：

1. 打开这个工具所在的文件夹 `C:\Users\shihu\Documents\workspace\tools\codex-switcher\`。
2. 里面有一个 **`com.bat`** 文件，您可以直接**双击运行它**，或者在任意命令行中输入 `com`（需要您将该文件夹加入环境变量 PATH）。
3. 运行后，您将看到一个直观的**交互式菜单**：

```text
=== OpenAI Codex 多账号无缝切换工具 ===
1. 切换账号 (Switch)
2. 保存当前账号 (Save)
3. 查看账号列表 (List)
4. 退出 (Exit)
请输入选项 (1-4): 
```
您只需要根据提示输入数字，例如输入 `1`，然后工具会提示您输入要切换的账号名称。所有的切换、保存逻辑都会自动安全地为您执行！

---

## 💻 进阶技巧 (命令行极速模式)

除了上面的交互式菜单，这个工具依然保留了“极速命令模式”。如果您希望一行命令搞定，不看菜单，可以直接带上参数：

### Windows 下直接执行
```bat
# 极速保存当前进度
com save personal_account

# 极速切走
com switch work_account
```

### Linux (通过 alias)
在您的 `~/.bashrc` 或 `~/.zshrc` 中添加：
```bash
alias com="python3 ~/workspace/tools/codex-switcher/codex_switcher.py"
```
保存并 `source ~/.bashrc` 后，您可以直接输入 `com` 呼出交互式菜单，或者输入 `com switch 账号名` 极速切换。
