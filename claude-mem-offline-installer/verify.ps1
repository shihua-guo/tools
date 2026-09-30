<#
.SYNOPSIS
    Claude-Mem Offline Verification Script (Windows)
#>

[CmdletBinding()]
param(
    [int]$WorkerPort = 37777
)

$ErrorActionPreference = 'Continue'

function Write-Check([string]$name, [bool]$passed, [string]$detail) {
    if ($passed) {
        Write-Host "  [PASS] $name" -ForegroundColor Green
        if ($detail) { Write-Host "         $detail" -ForegroundColor DarkGray }
    } else {
        Write-Host "  [FAIL] $name" -ForegroundColor Red
        if ($detail) { Write-Host "         $detail" -ForegroundColor Yellow }
    }
}

$UserHome = [System.Environment]::GetFolderPath('UserProfile')
$BunExe = Join-Path $UserHome ".bun\bin\bun.exe"
$MarketplaceDir = Join-Path $UserHome ".claude\plugins\marketplaces\thedotmack"
$PluginCacheDir = Join-Path $UserHome ".claude\plugins\cache\claude-mem@thedotmack\13.28.0"
$ClaudeSettings = Join-Path $UserHome ".claude\settings.json"
$InstalledPlugins = Join-Path $UserHome ".claude\plugins\installed_plugins.json"
$KnownMarketplaces = Join-Path $UserHome ".claude\plugins\known_marketplaces.json"
$ClaudeMemDb = Join-Path $UserHome ".claude-mem\claude-mem.db"
$MemSettings = Join-Path $UserHome ".claude-mem\settings.json"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "         Claude-Mem Offline Diagnostics & Self-Check      " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Bun runtime
$bunVer = ""
if (Test-Path $BunExe) {
    $bunVer = & $BunExe --version 2>$null
}
Write-Check "Bun Runtime" ($bunVer -ne "") "Path: $BunExe (Version: $bunVer)"

# 2. Files
$mktOk = (Test-Path (Join-Path $MarketplaceDir "plugin\scripts\worker-service.cjs"))
Write-Check "Marketplace Files" $mktOk "Path: $MarketplaceDir"

$cacheOk = (Test-Path (Join-Path $PluginCacheDir "scripts\worker-service.cjs"))
Write-Check "Plugin Cache Files" $cacheOk "Path: $PluginCacheDir"

$nodeModulesOk = (Test-Path (Join-Path $PluginCacheDir "node_modules\zod"))
Write-Check "Plugin Offline Dependencies" $nodeModulesOk "Zod, Tree-sitter, etc."

# 3. Claude Code configuration
$mktRegOk = $false
if (Test-Path $KnownMarketplaces) {
    $raw = Get-Content $KnownMarketplaces -Raw -Encoding utf8
    $mktRegOk = $raw -match "thedotmack"
}
Write-Check "Claude Known Marketplace Registration" $mktRegOk $KnownMarketplaces

$pluginRegOk = $false
if (Test-Path $InstalledPlugins) {
    $raw = Get-Content $InstalledPlugins -Raw -Encoding utf8
    $pluginRegOk = $raw -match "claude-mem@thedotmack"
}
Write-Check "Claude Installed Plugin Registration" $pluginRegOk $InstalledPlugins

$settingsOk = $false
if (Test-Path $ClaudeSettings) {
    $raw = Get-Content $ClaudeSettings -Raw -Encoding utf8
    $settingsOk = ($raw -match "claude-mem@thedotmack")
}
Write-Check "Claude Settings Plugin Enabled" $settingsOk $ClaudeSettings

# 4. Intranet settings
$intranetOk = $false
if (Test-Path $MemSettings) {
    $raw = Get-Content $MemSettings -Raw -Encoding utf8
    $intranetOk = ($raw -match "CLAUDE_MEM_DISABLE_VECTOR_SEARCH")
}
Write-Check "Intranet Offline Settings (SQLite FTS5 / No Telemetry)" $intranetOk $MemSettings

# 5. Worker health check
$workerOk = $false
$healthUrl = "http://127.0.0.1:$WorkerPort/api/health"
try {
    $resp = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2 -ErrorAction Stop
    if ($resp.status -eq 'ok') {
        $workerOk = $true
        Write-Check "Worker Daemon Status" $true "PID: $($resp.pid), Port: $WorkerPort, Uptime: $($resp.uptime)s"
    } else {
        Write-Check "Worker Daemon Status" $false "Unexpected status: $($resp.status)"
    }
} catch {
    Write-Check "Worker Daemon Status" $false "Not responding on port $WorkerPort (run 'claude-mem start' or use Claude Code)"
}

Write-Host "==========================================================" -ForegroundColor Cyan
if ($bunVer -and $mktOk -and $cacheOk -and $nodeModulesOk -and $mktRegOk -and $pluginRegOk -and $settingsOk) {
    Write-Host "All components verified! Claude-Mem is ready for offline operation." -ForegroundColor Green
} else {
    Write-Host "Some components missing. Please re-run install.ps1." -ForegroundColor Yellow
}
