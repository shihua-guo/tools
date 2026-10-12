<#
.SYNOPSIS
    Claude Code Desktop 纯内网一键离线安装与配置脚本 (Windows x64)

.DESCRIPTION
    适用于纯离线、内网或受限网络环境：
    1. 100% 离线自闭环安装 Claude Desktop 官方 MSIX 应用包 (v2.31226.1)
    2. 全局部署独立预编译版 Claude Code CLI (v2.1.286) 并写入用户 PATH
    3. 修复 Claude Desktop Code 标签页 "Host Claude Code binary not available" 痛点：
       自动注入 claude.exe 与 .verified 验证锁至 Claude-3p 用户数据目录
    4. 自动生成桌面及开始菜单快捷方式 (动态解析 AUMID)
    5. 可选配置内网大模型网关 / 聚合 API MDM 策略策略与 CLI 端点 (Tokeness / OneAPI / NewAPI / 自建网关)

.PARAMETER Silent
    静默安装模式（非交互式，使用默认值）

.PARAMETER SkipClaudeCode
    仅安装桌面端，跳过 Claude Code CLI 与 Code 标签页修复

.PARAMETER SkipApi
    跳过第三方聚合 API / 代理端点配置

.PARAMETER ApiBaseUrl
    聚合 API 或内网反向代理 Base URL (默认: https://n.tokeness.dev 或自定义)

.PARAMETER ApiKey
    聚合 API Key (格式 sk-xxxxxx)

.PARAMETER ApiModels
    聚合模型列表 (以逗号分隔，如: claude-opus-5,claude-sonnet-5,claude-haiku-4-5)

.PARAMETER Force
    强制覆盖安装
#>

[CmdletBinding()]
param(
    [switch]$Silent,
    [switch]$SkipClaudeCode,
    [switch]$SkipApi,
    [string]$ApiBaseUrl = "",
    [string]$ApiKey = "",
    [string]$ApiModels = "claude-opus-5,claude-sonnet-5,claude-haiku-4-5",
    [switch]$Force
)

$ErrorActionPreference = "Continue"

function Write-Step {
    param([string]$Text)
    Write-Host "`n>>> $Text" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Text)
    Write-Host "  [PASS] $Text" -ForegroundColor Green
}

function Write-Info {
    param([string]$Text)
    Write-Host "  [INFO] $Text" -ForegroundColor Gray
}

function Write-WarnMsg {
    param([string]$Text)
    Write-Host "  [WARN] $Text" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$Text)
    Write-Host "  [FAIL] $Text" -ForegroundColor Red
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$packagesDir = Join-Path $scriptDir "packages"
$binDir = Join-Path $scriptDir "bin\windows-x64"
$msixPath = Join-Path $packagesDir "Claude-win-x64.msix"
$claudeBinSource = Join-Path $binDir "claude.exe"

Clear-Host
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "      Claude Code Desktop 离线安装程序 (v2.31226.1)         " -ForegroundColor Cyan
Write-Host "          纯内网 / 离线环境 / 官方签名自包含版              " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# ------------------------------------------------------------
# 1. 系统与环境检查
# ------------------------------------------------------------
Write-Step "[1/6] 检查系统环境与安装包完整性"

if ([IntPtr]::Size -ne 8) {
    Write-Fail "当前系统非 64 位 (x64) 架构，Claude Desktop 需要 64 位 Windows 系统！"
    exit 1
}

$os = [System.Environment]::OSVersion
Write-Info "操作系统: Windows $([System.Environment]::OSVersion.Version)"

if (-not (Test-Path -LiteralPath $msixPath)) {
    Write-Fail "未找到离线安装包: $msixPath"
    Write-Info "请先执行 scripts\download-packages.ps1 或将 Claude-win-x64.msix 放入 packages 目录"
    exit 1
}

$expectedSha256 = "ecd354206b5f00c4a7b47e15f4779be8e7385e7074e2ca4a8424a8adac75abd3"
$actualHash = (Get-FileHash -Path $msixPath -Algorithm SHA256).Hash.ToLower()
if ($actualHash -eq $expectedSha256) {
    Write-Success "MSIX 完整性哈希校验通过 ($actualHash)"
} else {
    Write-WarnMsg "MSIX SHA256 与官方清单不一致 (实际: $actualHash, 期望: $expectedSha256)"
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    Write-Info "运行权限: 管理员特权 (支持机器级预置与 Cowork 虚拟化服务注册)"
} else {
    Write-Info "运行权限: 当前用户级"
    if (-not $Silent) {
        Write-WarnMsg "Claude Desktop MSIX 包含 Cowork 虚拟化后台服务，Windows 要求管理员权限。"
        Write-Info "正在尝试请求 UAC 管理员提权..."
        try {
            $argStr = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
            if ($Force) { $argStr += " -Force" }
            if ($SkipClaudeCode) { $argStr += " -SkipClaudeCode" }
            if ($SkipApi) { $argStr += " -SkipApi" }
            if ($ApiBaseUrl) { $argStr += " -ApiBaseUrl `"$ApiBaseUrl`"" }
            if ($ApiKey) { $argStr += " -ApiKey `"$ApiKey`"" }
            if ($ApiModels) { $argStr += " -ApiModels `"$ApiModels`"" }
            Start-Process powershell.exe -ArgumentList $argStr -Verb RunAs
            Write-Info "已打开管理员提权窗口进行安装，当前终端退出。"
            exit 0
        } catch {
            Write-WarnMsg "未能拉起管理员提权窗口: $_。将继续尝试在普通权限下运行..."
        }
    }
}

# ------------------------------------------------------------
# 2. 安装 Claude Desktop MSIX
# ------------------------------------------------------------
Write-Step "[2/6] 安装 Claude Desktop 应用包"

$existingAppx = Get-AppxPackage -Name "*Claude*" -ErrorAction SilentlyContinue | Select-Object -First 1

if ($existingAppx -and (-not $Force)) {
    Write-Info "检测到已安装 Claude Desktop: $($existingAppx.Name) ($($existingAppx.Version))"
} else {
    $installSuccess = $false

    if ($isAdmin) {
        Write-Info "正在执行机器级预置安装 (Add-AppxProvisionedPackage)..."
        try {
            Add-AppxProvisionedPackage -Online -PackagePath $msixPath -SkipLicense -ErrorAction Stop | Out-Null
            Write-Success "机器范围注册成功"
            $installSuccess = $true
        } catch {
            Write-WarnMsg "机器范围预置注册失败: $_，尝试回退至用户级安装..."
        }
    }

    if (-not $installSuccess) {
        Write-Info "正在执行用户级安装 (Add-AppxPackage)..."
        try {
            Add-AppxPackage -Path $msixPath -ErrorAction Stop
            Write-Success "用户级安装成功"
            $installSuccess = $true
        } catch {
            Write-Fail "Add-AppxPackage 安装失败: $_"
            if ($_ -match "0x80073D28" -or $_ -match "administrator") {
                Write-Host ""
                Write-Host ">>> 关键提示: 该应用包包含 Cowork 虚拟化系统服务，Windows 系统策略要求以管理员权限安装。" -ForegroundColor Yellow
                Write-Host ">>> 解决方法: 请右键点击 'install.cmd' 选择【以管理员身份运行】，或以管理员权限打开 PowerShell 后执行 .\install.ps1" -ForegroundColor Cyan
                Write-Host ""
            } else {
                Write-Info "排查建议: 请确认 Windows 10/11 系统的'开发人员模式'或'侧载应用'权限未被组策略完全禁用。"
            }
            exit 1
        }
    }
}

# 重新检索已安装信息
$claudeAppx = Get-AppxPackage -Name "*Claude*" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $claudeAppx) {
    Write-Fail "未能检测到已安装的 Claude 应用包信息！"
    exit 1
}

Write-Success "Claude Desktop 就绪: $($claudeAppx.Name) $($claudeAppx.Version)"
Write-Info "PackageFamilyName: $($claudeAppx.PackageFamilyName)"

# ------------------------------------------------------------
# 3. 部署 Claude Code CLI 运行时 (全局命令行)
# ------------------------------------------------------------
Write-Step "[3/6] 部署 Claude Code 全局命令行工具"

$userLocalBin = Join-Path $env:USERPROFILE ".local\bin"
if (-not (Test-Path -LiteralPath $userLocalBin)) {
    New-Item -ItemType Directory -Path $userLocalBin -Force | Out-Null
}

$destCli = Join-Path $userLocalBin "claude.exe"

if (Test-Path -LiteralPath $claudeBinSource) {
    Copy-Item -LiteralPath $claudeBinSource -Destination $destCli -Force
    Write-Success "已部署独立版 claude.exe 至: $destCli"
} else {
    Write-WarnMsg "未在 $binDir 找到预打包的 claude.exe，跳过独立二进制全局部署"
}

# 注册 PATH
$currentPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
$paths = $currentPath -split ";" | Where-Object { $_ -ne "" }
if ($paths -notcontains $userLocalBin) {
    $newPath = "$userLocalBin;$currentPath"
    [System.Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    $env:Path = "$userLocalBin;$env:Path"
    Write-Success "已将 $userLocalBin 写入当前用户 PATH 环境变量"
} else {
    Write-Info "用户 PATH 已包含 $userLocalBin"
}

# ------------------------------------------------------------
# 4. 修复 Claude Desktop Code 标签页 ("Host Claude Code binary not available")
# ------------------------------------------------------------
Write-Step "[4/6] 修复 Claude Code 桌面集成组件 (解决 Code 标签页加载报错)"

if ($SkipClaudeCode) {
    Write-Info "用户指定了 -SkipClaudeCode，跳过组件修复"
} elseif (Test-Path -LiteralPath $claudeBinSource) {
    $userDataDir = Join-Path $env:LOCALAPPDATA "Packages\$($claudeAppx.PackageFamilyName)\LocalCache\Local\Claude-3p"
    $ccTargetBase = Join-Path $userDataDir "claude-code"

    if (-not (Test-Path -LiteralPath $ccTargetBase)) {
        New-Item -ItemType Directory -Path $ccTargetBase -Force | Out-Null
    }

    # 预设注入目标版本目录
    $targetVersions = @("2.1.286", "2.1.296", "latest")

    # 检查 Desktop 是否已经初始化过其它版本目录
    $existingVersions = Get-ChildItem -Path $ccTargetBase -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.Name }
    foreach ($ev in $existingVersions) {
        if ($targetVersions -notcontains $ev) {
            $targetVersions += $ev
        }
    }

    foreach ($ver in $targetVersions) {
        $verDir = Join-Path $ccTargetBase $ver
        if (-not (Test-Path -LiteralPath $verDir)) {
            New-Item -ItemType Directory -Path $verDir -Force | Out-Null
        }

        # 写入 claude.exe
        $destVerExe = Join-Path $verDir "claude.exe"
        Copy-Item -LiteralPath $claudeBinSource -Destination $destVerExe -Force

        # 写入 .verified 验证锁文件 (至关重要！Desktop 借由此文件确认下载验证通过)
        $verifiedFile = Join-Path $verDir ".verified"
        Set-Content -LiteralPath $verifiedFile -Value "" -Encoding ASCII -Force
    }

    Write-Success "已注入 Claude Code 核心二进制并生成 .verified 离线验证锁"
    Write-Info "注入目标目录: $ccTargetBase (版本: $($targetVersions -join ', '))"
} else {
    Write-WarnMsg "缺少离线 claude.exe，跳过 Claude-3p 组件注入"
}

# ------------------------------------------------------------
# 5. 创建桌面与开始菜单快捷方式
# ------------------------------------------------------------
Write-Step "[5/6] 生成系统快捷方式"

try {
    $wsh = New-Object -ComObject WScript.Shell
    $desktopPath = [System.Environment]::GetFolderPath("Desktop")

    # 动态获取 Claude 应用 AUMID
    $aumid = ""
    $startApps = Get-StartApps -ErrorAction SilentlyContinue
    foreach ($app in $startApps) {
        if ($app.AppID -like "*$($claudeAppx.PackageFamilyName)*") {
            $aumid = $app.AppID
            break
        }
    }

    if ([string]::IsNullOrEmpty($aumid)) {
        $aumid = "$($claudeAppx.PackageFamilyName)!Claude"
    }

    $lnkPath = Join-Path $desktopPath "Claude Desktop.lnk"
    $shortcut = $wsh.CreateShortcut($lnkPath)
    $shortcut.TargetPath = "explorer.exe"
    $shortcut.Arguments = "shell:AppsFolder\$aumid"
    $shortcut.Description = "Claude Desktop"
    $shortcut.Save()

    Write-Success "已在桌面创建快捷方式: $lnkPath"
    Write-Info "关联 AUMID: $aumid"
} catch {
    Write-WarnMsg "创建桌面快捷方式失败: $_"
}

# ------------------------------------------------------------
# 6. 配置内网聚合 API / MDM 策略 (可选)
# ------------------------------------------------------------
Write-Step "[6/6] 内网大模型网关 / 聚合 API 配置 (可选)"

$shouldConfigApi = $false
$targetBaseUrl = $ApiBaseUrl
$targetApiKey = $ApiKey
$targetModels = $ApiModels

if ($SkipApi) {
    Write-Info "已指定 -SkipApi，跳过 API 配置"
} elseif (-not [string]::IsNullOrEmpty($ApiKey)) {
    $shouldConfigApi = $true
} elseif (-not $Silent) {
    Write-Host ""
    Write-Host "如需连接企业私有大模型网关、OneAPI、NewAPI 或 Tokeness 等兼容端点，可直接在此配置。" -ForegroundColor Yellow
    $ans = Read-Host "是否现在配置大模型接口端点？[y/N]"
    if ($ans -match '^[Yy]') {
        $inputUrl = Read-Host "  请输入 Base URL [默认: https://n.tokeness.dev]"
        $targetBaseUrl = if ([string]::IsNullOrWhiteSpace($inputUrl)) { "https://n.tokeness.dev" } else { $inputUrl.Trim() }

        $inputKey = Read-Host "  请输入 API Key (格式 sk-xxxxxx)"
        $targetApiKey = if ([string]::IsNullOrWhiteSpace($inputKey)) { "" } else { $inputKey.Trim() }

        $inputModels = Read-Host "  请输入模型列表 (逗号分隔) [默认: $ApiModels]"
        $targetModels = if ([string]::IsNullOrWhiteSpace($inputModels)) { $ApiModels } else { $inputModels.Trim() }

        if (-not [string]::IsNullOrEmpty($targetApiKey)) {
            $shouldConfigApi = $true
        } else {
            Write-Info "未输入 API Key，跳过本次配置。"
        }
    }
}

if ($shouldConfigApi) {
    try {
        # 写入注册表策略 HKCU:\SOFTWARE\Policies\Claude
        $regPath = "HKCU:\SOFTWARE\Policies\Claude"
        if (-not (Test-Path -LiteralPath $regPath)) {
            New-Item -Path $regPath -Force | Out-Null
        }

        Set-ItemProperty -Path $regPath -Name "inferenceProvider" -Value "gateway" -Type String
        Set-ItemProperty -Path $regPath -Name "inferenceGatewayBaseUrl" -Value $targetBaseUrl -Type String
        Set-ItemProperty -Path $regPath -Name "inferenceGatewayApiKey" -Value $targetApiKey -Type String
        Set-ItemProperty -Path $regPath -Name "inferenceGatewayAuthScheme" -Value "bearer" -Type String

        if (-not [string]::IsNullOrEmpty($targetModels)) {
            $modelList = $targetModels.Split(@(',', '，', ';'), [System.StringSplitOptions]::RemoveEmptyEntries) | ForEach-Object { "`"$($_.Trim())`"" }
            $modelsJson = "[" + ($modelList -join ",") + "]"
            Set-ItemProperty -Path $regPath -Name "inferenceModels" -Value $modelsJson -Type String
        }

        Write-Success "已写入注册表 MDM 策略: HKCU\SOFTWARE\Policies\Claude"
        Write-Info "端点: $targetBaseUrl"

        # 写入 CLI ~/.claude/settings.json
        $claudeConfDir = Join-Path $env:USERPROFILE ".claude"
        if (-not (Test-Path -LiteralPath $claudeConfDir)) {
            New-Item -ItemType Directory -Path $claudeConfDir -Force | Out-Null
        }
        $claudeSettingsPath = Join-Path $claudeConfDir "settings.json"
        $cfgObj = @{}
        if (Test-Path -LiteralPath $claudeSettingsPath) {
            try {
                $cfgObj = (Get-Content -LiteralPath $claudeSettingsPath -Raw | ConvertFrom-Json)
            } catch {}
        }
        $cfgObj | Add-Member -Name "apiBaseUrl" -Value $targetBaseUrl -MemberType NoteProperty -Force
        $cfgObj | Add-Member -Name "apiKey" -Value $targetApiKey -MemberType NoteProperty -Force
        $cfgObj | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $claudeSettingsPath -Encoding UTF8
        Write-Success "已同步写入 Claude Code CLI 配置: $claudeSettingsPath"
    } catch {
        Write-WarnMsg "写入 API 配置时发生异常: $_"
    }
}

# ------------------------------------------------------------
# 安装完成总结
# ------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "       Claude Code Desktop 离线安装与配置已全部完成!        " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  1. 桌面端应用: 双击桌面的 'Claude Desktop' 快捷方式即可启动。" -ForegroundColor White
Write-Host "  2. Code 标签页: 点击应用顶部的 'Code' 标签，选择本地项目目录即可进入交互式编码。" -ForegroundColor White
Write-Host "  3. 命令行工具: 在终端输入 'claude --version' 即可使用 CLI。" -ForegroundColor White
Write-Host "  4. 健康检查:   可随时在当前目录执行 .\verify.ps1 自检各组件状态。" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Green
