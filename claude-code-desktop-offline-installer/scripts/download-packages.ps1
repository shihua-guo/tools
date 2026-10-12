<#
.SYNOPSIS
    Claude Code Desktop 离线包资源自动下载 / 镜像同步脚本
.DESCRIPTION
    从官方或高速镜像同步下载 Claude Desktop 完整自包含 MSIX 与 Claude Code 二进制。
#>
[CmdletBinding()]
param(
    [switch]$Force,
    [ValidateSet("mirror", "official")]
    [string]$Source = "mirror"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
$packagesDir = Join-Path $rootDir "packages"
$binDir = Join-Path $rootDir "bin\windows-x64"

if (-not (Test-Path $packagesDir)) { New-Item -ItemType Directory -Path $packagesDir -Force | Out-Null }
if (-not (Test-Path $binDir)) { New-Item -ItemType Directory -Path $binDir -Force | Out-Null }

$msixFile = Join-Path $packagesDir "Claude-win-x64.msix"
$expectedSha256 = "ecd354206b5f00c4a7b47e15f4779be8e7385e7074e2ca4a8424a8adac75abd3"

$msixUrl = if ($Source -eq "mirror") {
    "https://claudeapp.agentsmirror.com/latest/win-x64"
} else {
    "https://downloads.claude.ai/releases/win32/x64/2.31226.1/Claude-8576520051724193e9f74fc538f9ce8125e9ddd2.msix"
}

Write-Host ">>> 检查 Claude Desktop 离线安装包 (MSIX)..." -ForegroundColor Cyan

$needDownload = $true
if (Test-Path $msixFile) {
    if (-not $Force) {
        Write-Host "  计算本地 MSIX SHA256 哈希..." -ForegroundColor Gray
        $localHash = (Get-FileHash -Path $msixFile -Algorithm SHA256).Hash.ToLower()
        if ($localHash -eq $expectedSha256) {
            Write-Host "  [OK] 本地 MSIX 校验通过 ($localHash)" -ForegroundColor Green
            $needDownload = $false
        } else {
            Write-Host "  [WARN] 本地文件哈希不匹配，准备重新下载..." -ForegroundColor Yellow
        }
    }
}

if ($needDownload) {
    Write-Host "  正在从 $msixUrl 下载 Claude-win-x64.msix..." -ForegroundColor Cyan
    curl.exe -L -# -o $msixFile $msixUrl
    $newHash = (Get-FileHash -Path $msixFile -Algorithm SHA256).Hash.ToLower()
    if ($newHash -ne $expectedSha256) {
        throw "下载文件 SHA256 校验失败! 期望: $expectedSha256, 实际: $newHash"
    }
    Write-Host "  [OK] 下载完成并校验成功: $msixFile" -ForegroundColor Green
}

# 检查 claude.exe
$claudeBin = Join-Path $binDir "claude.exe"
if (-not (Test-Path $claudeBin)) {
    $existing = (Get-Command claude -ErrorAction SilentlyContinue).Source
    if ($existing -and (Test-Path $existing)) {
        Write-Host "  从本地系统环境同步 claude.exe: $existing" -ForegroundColor Cyan
        Copy-Item -LiteralPath $existing -Destination $claudeBin -Force
    } else {
        Write-Host "  [WARN] 未找到本地 claude.exe，请确保将官方 claude.exe 放入: $binDir" -ForegroundColor Yellow
    }
}

Write-Host ">>> 离线包依赖资源准备完毕！" -ForegroundColor Green
