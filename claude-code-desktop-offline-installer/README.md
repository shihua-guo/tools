# Claude Code Desktop 离线安装包 (Offline Installer)

> **版本**：v2.31226.1 (内置 Claude Desktop v2.31226.1 + Claude Code v2.1.286)  
> **适用环境**：纯内网 / 无外网隔离环境 / 国内直连受限网络（Air-gapped / Intranet / Enterprise Sandbox）  
> **支持平台**：Windows 10 / 11 / Windows Server 2019+ (x64)

---

## 目录
1. [核心背景与解决痛点](#一核心背景与解决痛点)
2. [核心特性](#二核心特性)
3. [安装包目录结构](#三安装包目录结构)
4. [Windows 一键离线安装指南](#四windows-一键离线安装指南)
5. [自检验证与健康检查](#五自检验证与健康检查)
6. [内网大模型服务与代理接入 (LLM Gateway)](#六内网大模型服务与代理接入-llm-gateway)
7. [常见问题与排查指南 (FAQ)](#七常见问题与排查指南-faq)

---

## 一、核心背景与解决痛点

在使用 Claude 官方桌面端及 Code 标签页时，内网或网络受限环境通常面临两大痛点：

1. **官方 7MB 在线引导器卡死 / 报 `unexpected EOF`**：  
   从官网下载的 `ClaudeSetup.exe` 仅是在线引导器，运行时需向 `downloads.claude.ai`（GCS）再次拉取 ~294MB 的 MSIX 安装包。在国内或受限网络下极易下载中断或直接卡死。  
   👉 **本离线包提供 100% 完整官方签名的自包含 `Claude-win-x64.msix`，无需任何二次网络请求。**

2. **Code 标签页报 `Host Claude Code binary not available`**：  
   Claude Desktop 首次打开 "Code" 标签页时，需要从 Anthropic 服务器向本地下载 `claude.exe`。因 DNS 或防火墙拦截，该步骤必然失败，导致无法启动桌面版代码交互。  
   👉 **本离线包内置官方独立版 `claude.exe` 二进制，自动部署至用户数据目录并在相应版本下打上 `.verified` 验证锁，实现即开即用！**

---

## 二、核心特性

1. **100% 离线自闭环**：
   - 彻底摆脱对外网 CDN、GCS、npm 镜像或在线握手的依赖。
   - 所有二进制（Claude Desktop MSIX、Claude Code CLI）均包含在离线包内。
2. **官方签名与哈希校验**：
   - 内置 Anthropic 官方签名的 `Claude-win-x64.msix`，随附官方 `SHA256SUMS.txt` 与 `release-manifest.json`，确保软件无重打包、无修改、安全可靠。
3. **自动化安装与智能降级**：
   - 管理员权限下自动优先采用 `Add-AppxProvisionedPackage` 机器级安装（多用户可用并正确注册 Cowork 虚拟化服务）；普通用户权限下平滑回退至 `Add-AppxPackage` 用户级安装。
4. **全自动桌面集成**：
   - 动态识别 Claude Desktop 的真实 `PackageFamilyName` 与系统 `AUMID`，自动生成桌面与开始菜单快捷方式。
5. **企业私有网关与 MDM 策略支持**：
   - 支持通过参数或交互界面一键配置企业私有大模型端点（OneAPI / NewAPI / Tokeness / 自建网关），自动写入 Windows 注册表 MDM 策略 (`HKCU\SOFTWARE\Policies\Claude`) 与 CLI 端配置。

---

## 三、安装包目录结构

```text
claude-code-desktop-offline-installer/
├── bin/
│   └── windows-x64/
│       └── claude.exe                    # 预编译独立版 Claude Code CLI (v2.1.286)
├── packages/
│   └── Claude-win-x64.msix               # 官方自包含 MSIX 离线安装包 (v2.31226.1, 294MB)
├── scripts/
│   └── download-packages.ps1             # 离线资源同步/更新辅助脚本
├── install.ps1                           # Windows 一键自动化离线安装与配置脚本
├── verify.ps1                            # Windows 离线安装健康检查脚本
├── release-manifest.json                 # 官方哈希与版本元数据清单
├── SHA256SUMS.txt                        # SHA256 完整性校验文件
└── README.md                             # 本使用指南文档
```

---

## 四、Windows 一键离线安装指南

### 1. 解压安装包
将 `claude-code-desktop-offline-installer.zip` 复制到目标内网机器并解压至任意目录（例如 `D:\claude-code-desktop-offline-installer`）。

### 2. 运行一键安装
以 PowerShell 打开解压后的目录，执行：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\install.ps1
```

> **提示**：建议使用管理员权限运行 PowerShell，以获得机器级预置注册和完整的系统功能支持。

### 3. 可选命令行参数

| 参数 | 说明 | 示例 |
| :--- | :--- | :--- |
| `-Silent` | 静默安装模式，无控制台交互提示 | `.\install.ps1 -Silent` |
| `-Force` | 强制重新安装并覆盖已存在的文件 | `.\install.ps1 -Force` |
| `-SkipClaudeCode` | 仅安装桌面应用，跳过 Code 标签页离线注入 | `.\install.ps1 -SkipClaudeCode` |
| `-SkipApi` | 跳过聚合 API / 第三方网关配置提示 | `.\install.ps1 -SkipApi` |
| `-ApiBaseUrl <url>` | 指定大模型网关 Base URL | `-ApiBaseUrl https://n.tokeness.dev` |
| `-ApiKey <key>` | 指定大模型网关 API Key (sk-xxxxxx) | `-ApiKey sk-xxxxxxxx` |
| `-ApiModels <models>` | 指定允许的模型列表 (逗号分隔) | `-ApiModels claude-opus-5,claude-sonnet-5` |

---

## 五、自检验证与健康检查

安装完成后，在当前目录执行健康检查脚本：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\verify.ps1
```

检查项目包括：
1. **[1/5] Claude Desktop 应用安装状态**：检测 Appx 包版本、PackageFamilyName 与安装目录。
2. **[2/5] Claude Code CLI 全局环境**：检测全局 `claude --version` 命令。
3. **[3/5] Code 标签页集成组件**：检测 `Claude-3p` 用户数据目录下的版本子目录、`claude.exe` 及 `.verified` 验证锁。
4. **[4/5] 系统快捷方式**：检测桌面 `Claude Desktop.lnk` 是否有效指向 AUMID。
5. **[5/5] API 策略配置**：检测注册表 MDM 策略与 CLI `settings.json`。

所有项目输出 `[PASS]` 即表示离线安装完全成功！

---

## 六、内网大模型服务与代理接入 (LLM Gateway)

若在纯内网环境下使用自建大模型中转或企业私有 API 网关（如 OneAPI / NewAPI / Tokeness / vLLM）：

安装程序会自动将配置写入 Windows 注册表 MDM 策略（Claude Desktop 官方认可方式）：
- 注册表路径：`HKCU\SOFTWARE\Policies\Claude`（或机器策略 `HKLM\SOFTWARE\Policies\Claude`）
  - `inferenceProvider` (REG_SZ): `"gateway"`
  - `inferenceGatewayBaseUrl` (REG_SZ): 企业网关地址（如 `http://192.168.1.100:8000/v1`）
  - `inferenceGatewayApiKey` (REG_SZ): 访问密钥
  - `inferenceGatewayAuthScheme` (REG_SZ): `"bearer"`
  - `inferenceModels` (REG_SZ): 允许的模型 JSON 数组，如 `["claude-opus-5","claude-sonnet-5"]`

> **注意**：修改注册表策略后，需**完全退出并重启** Claude Desktop（包含系统托盘右键退出）方可生效。

---

## 七、常见问题与排查指南 (FAQ)

### Q1: 安装时提示应用侧载或策略受限？
- Windows 10/11 消费版默认允许安装已签名 MSIX。如果系统在企业域控下受限，请在系统设置中启用：
  `设置 -> 开发者选项 -> 允许从任意源安装应用 (侧载应用)`。

### Q2: 首次点击 Code 标签页依然提示组件下载中？
- 请先完全关闭 Claude Desktop（确认托盘图标退出）。
- 运行 `.\verify.ps1` 确认第 3 项检查显示 `[PASS]`（即各个版本目录下的 `claude.exe` 与 `.verified` 文件均已就位）。
- 重新启动 Claude Desktop 即可立即识别本地已有二进制。

### Q3: 如何完全卸载？
- 在 Windows 开始菜单找到 Claude，右键选择“卸载”即可移除 MSIX。
- 如需清理用户注入缓存：
  ```powershell
  Remove-Item -Recurse -Force "$env:LOCALAPPDATA\Packages\*Claude*\LocalCache\Local\Claude-3p" -ErrorAction SilentlyContinue
  Remove-Item -Path "HKCU:\SOFTWARE\Policies\Claude" -Recurse -ErrorAction SilentlyContinue
  ```
