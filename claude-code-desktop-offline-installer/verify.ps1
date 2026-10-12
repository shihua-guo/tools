<#
.SYNOPSIS
    Claude Code Desktop 离线安装健康检查与验证脚本 (verify.ps1)
#>

$ErrorActionPreference = "Continue"

function Write-Step {
    param([string]$Text)
    Write-Host "`n>>> $Text" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Text)
    Write-Host "  [PASS] $Text" -ForegroundColor Green
}

function Write-WarnMsg {
    param([string]$Text)
    Write-Host "  [WARN] $Text" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$Text)
    Write-Host "  [FAIL] $Text" -ForegroundColor Red
}

$allPass = $true

Clear-Host
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "       Claude Code Desktop 离线安装自检验证程序             " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. 检查 Claude Desktop MSIX 应用包
Write-Step "[1/5] 检查 Claude Desktop 应用安装状态"
$appx = Get-AppxPackage -Name "*Claude*" -ErrorAction SilentlyContinue | Select-Object -First 1

if ($appx) {
    Write-Success "应用包已安装: $($appx.Name)"
    Write-Host "         版本号: $($appx.Version)" -ForegroundColor Gray
    Write-Host "         PackageFamilyName: $($appx.PackageFamilyName)" -ForegroundColor Gray
    Write-Host "         安装位置: $($appx.InstallLocation)" -ForegroundColor Gray
} else {
    Write-Fail "未检测到 Claude Desktop 应用包，请执行 .\install.ps1 进行安装！"
    $allPass = $false
}

# 2. 检查全局 Claude Code CLI
Write-Step "[2/5] 检查 Claude Code CLI 全局环境"
$cliPath = (Get-Command claude -ErrorAction SilentlyContinue).Source

if ($cliPath) {
    try {
        $verOut = & $cliPath --version 2>&1
        Write-Success "CLI 命令正常: $cliPath ($verOut)"
    } catch {
        Write-WarnMsg "CLI 存在但运行报错: $_"
    }
} else {
    $fallbackCli = Join-Path $env:USERPROFILE ".local\bin\claude.exe"
    if (Test-Path -LiteralPath $fallbackCli) {
        Write-WarnMsg "找到 $fallbackCli 但当前终端 PATH 尚未包含该目录（重新打开终端即可生效）"
    } else {
        Write-Fail "未找到全局 claude 命令！"
        $allPass = $false
    }
}

# 3. 检查 Claude-3p 数据目录与 .verified 锁
Write-Step "[3/5] 检查 Code 标签页集成组件 (Claude-3p 离线修复状态)"
if ($appx) {
    $userDataDir = Join-Path $env:LOCALAPPDATA "Packages\$($appx.PackageFamilyName)\LocalCache\Local\Claude-3p"
    $ccBase = Join-Path $userDataDir "claude-code"

    if (Test-Path -LiteralPath $ccBase) {
        $subDirs = Get-ChildItem -Path $ccBase -Directory -ErrorAction SilentlyContinue
        if ($subDirs.Count -gt 0) {
            $validCount = 0
            foreach ($dir in $subDirs) {
                $hasExe = Test-Path (Join-Path $dir.FullName "claude.exe")
                $hasVerified = Test-Path (Join-Path $dir.FullName ".verified")
                if ($hasExe -and $hasVerified) {
                    Write-Success "版本目录 [$($dir.Name)]: claude.exe 与 .verified 锁均已就位"
                    $validCount++
                } else {
                    Write-WarnMsg "版本目录 [$($dir.Name)]: 缺少组件 (exe=$hasExe, verified=$hasVerified)"
                }
            }
            if ($validCount -eq 0) {
                Write-Fail "未找到完整的 Claude Code 注入版本目录"
                $allPass = $false
            }
        } else {
            Write-Fail "未在 $ccBase 找到任何版本子目录"
            $allPass = $false
        }
    } else {
        Write-Fail "未找到数据目录: $ccBase"
        $allPass = $false
    }
} else {
    Write-Fail "跳过 Claude-3p 检查 (应用包未安装)"
    $allPass = $false
}

# 4. 检查桌面快捷方式
Write-Step "[4/5] 检查系统快捷方式"
$desktopLnk = Join-Path ([System.Environment]::GetFolderPath("Desktop")) "Claude Desktop.lnk"
if (Test-Path -LiteralPath $desktopLnk) {
    Write-Success "桌面快捷方式存在: $desktopLnk"
} else {
    Write-WarnMsg "桌面快捷方式未找到: $desktopLnk"
}

# 5. 检查 API 策略与配置
Write-Step "[5/5] 检查 API / 代理策略配置"
$regPolicy = Get-ItemProperty -Path "HKCU:\SOFTWARE\Policies\Claude" -ErrorAction SilentlyContinue
if ($regPolicy -and $regPolicy.inferenceGatewayBaseUrl) {
    Write-Success "已配置注册表 MDM 策略 (Gateway Base URL: $($regPolicy.inferenceGatewayBaseUrl))"
} else {
    Write-Host "  [INFO] 未配置第三方注册表策略（使用官方原生登录）" -ForegroundColor Gray
}

$cliConf = Join-Path $env:USERPROFILE ".claude\settings.json"
if (Test-Path -LiteralPath $cliConf) {
    Write-Success "CLI 配置文件存在: $cliConf"
} else {
    Write-Host "  [INFO] 未生成 CLI 独立 settings.json（使用默认配置）" -ForegroundColor Gray
}

# 总结
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
if ($allPass) {
    Write-Host "    [ALL PASS] Claude Code Desktop 离线环境全部就绪！       " -ForegroundColor Green
} else {
    Write-Host "    [ATTENTION] 存在未通过的检查项，请参考上述提示排查。    " -ForegroundColor Yellow
}
Write-Host "============================================================" -ForegroundColor Cyan
