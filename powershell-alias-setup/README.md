# PowerShell Alias Setup

## 概述

为 `claude --allow-dangerously-skip-permissions --resume` 创建简写命令 `claudee`，并配置 PowerShell 7 的右键菜单。

## 一、命令别名

### 实现方式

通过 PowerShell Profile 添加自定义函数，使 `claudee` 成为完整命令的别名。

### 涉及文件

| 文件 | 用途 |
|------|------|
| `C:\Users\shihu\OneDrive\文档\PowerShell\Microsoft.PowerShell_profile.ps1` | PowerShell 启动时自动加载的配置文件 |

### Profile 内容

```powershell
function claudee { claude --allow-dangerously-skip-permissions --resume @args }
```

- `function claudee` — 定义名为 `claudee` 的函数
- `claude --allow-dangerously-skip-permissions --resume` — 实际执行的命令
- `@args` — 透传所有额外参数

### 使用方法

```powershell
# 等价于 claude --allow-dangerously-skip-permissions --resume
claudee

# 带额外参数
claudee --model claude-opus-4-7
```

### 生效方式

1. **当前会话生效**：运行 `. $PROFILE`
2. **永久生效**：重启 PowerShell 窗口即可，Profile 会自动加载

---

## 二、右键菜单配置

### 检查结果

- PowerShell 7 已安装：`C:\Program Files\PowerShell\7\pwsh.exe`（版本 7.5.5）
- 右键菜单缺失：只有 PowerShell 5 的菜单项，没有 PowerShell 7 的

### 添加菜单

以管理员身份运行：

```powershell
.\add-context-menu.ps1
```

添加后，**Shift + 右键** 在文件夹空白处会显示：

- **在此处打开 PowerShell 7**
- **以管理员身份打开 PowerShell 7**

### 移除菜单

以管理员身份运行：

```powershell
.\remove-context-menu.ps1
```

---

## 三、创建过程

### 命令别名

1. 确认 Profile 路径：`$PROFILE` → `C:\Users\shihu\OneDrive\文档\PowerShell\Microsoft.PowerShell_profile.ps1`
2. 创建 Profile 目录（如不存在）
3. 写入函数定义到 Profile 文件
4. 执行 `. $PROFILE` 使当前会话生效

### 右键菜单

1. 检查 PowerShell 7 安装状态：`pwsh --version` → 7.5.5
2. 检查注册表 `HKLM:\SOFTWARE\Classes\Directory\Background\shell` — 无 pwsh 条目
3. 创建 `add-context-menu.ps1` 脚本写入注册表
4. 创建 `remove-context-menu.ps1` 脚本用于移除
5. 需要管理员权限运行（HKLM 写入需要提权）
