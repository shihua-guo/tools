<#
.SYNOPSIS
    Claude-Mem Offline Installer for Windows PowerShell
#>

[CmdletBinding()]
param(
    [ValidateSet('claude-code', 'cursor', 'codex', 'antigravity', 'all')]
    [string]$Ide = 'claude-code',

    [string]$Provider = 'claude',

    [switch]$KeepAutoMemory,

    [switch]$SkipWorkerStart,

    [int]$WorkerPort = 37777
)

$ErrorActionPreference = 'Stop'

function Write-Step([string]$msg) {
    Write-Host "`n[+] $msg" -ForegroundColor Cyan
}

function Write-Ok([string]$msg) {
    Write-Host "  [OK] $msg" -ForegroundColor Green
}

function Write-Warn([string]$msg) {
    Write-Host "  [WARN] $msg" -ForegroundColor Yellow
}

function Write-Err([string]$msg) {
    Write-Host "  [FAIL] $msg" -ForegroundColor Red
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Version = "13.28.0"
$UserHome = [System.Environment]::GetFolderPath('UserProfile')
$ClaudeDir = Join-Path $UserHome ".claude"
$ClaudeMemDir = Join-Path $UserHome ".claude-mem"
$BunBinDir = Join-Path $UserHome ".bun\bin"
$MarketplaceDir = Join-Path $ClaudeDir "plugins\marketplaces\thedotmack"
$PluginCacheDir = Join-Path $ClaudeDir "plugins\cache\claude-mem@thedotmack\$Version"

Write-Host "==========================================================" -ForegroundColor Green
Write-Host "      Claude-Mem v$Version Offline Installer (Windows)    " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green

# 1. Setup Bun and uv runtimes
Write-Step "1/6 Configuring runtimes (Bun / uv)..."
if (-not (Test-Path $BunBinDir)) {
    New-Item -ItemType Directory -Path $BunBinDir -Force | Out-Null
}

$SourceBunExe = Join-Path $ScriptDir "bin\windows-x64\bun.exe"
$DestBunExe = Join-Path $BunBinDir "bun.exe"
if (Test-Path $SourceBunExe) {
    Copy-Item $SourceBunExe $DestBunExe -Force
    Write-Ok "Bun runtime installed: $DestBunExe"
} else {
    Write-Err "Missing Bun binary at: $SourceBunExe"
    exit 1
}

$SourceUvExe = Join-Path $ScriptDir "bin\windows-x64\uv.exe"
$SourceUvxExe = Join-Path $ScriptDir "bin\windows-x64\uvx.exe"
if (Test-Path $SourceUvExe) {
    Copy-Item $SourceUvExe (Join-Path $BunBinDir "uv.exe") -Force
    Copy-Item $SourceUvxExe (Join-Path $BunBinDir "uvx.exe") -Force
    Write-Ok "uv / uvx tools installed"
}

# Update User and Session PATH
$UserPath = [Environment]::GetEnvironmentVariable("Path", [EnvironmentVariableTarget]::User)
if ($UserPath -notlike "*$BunBinDir*") {
    $NewUserPath = "$BunBinDir;$UserPath"
    [Environment]::SetEnvironmentVariable("Path", $NewUserPath, [EnvironmentVariableTarget]::User)
    Write-Ok "Added $BunBinDir to User PATH"
}
if ($env:Path -notlike "*$BunBinDir*") {
    $env:Path = "$BunBinDir;$env:Path"
}

# Create global command shim: claude-mem.cmd
$CmdShimPath = Join-Path $BunBinDir "claude-mem.cmd"
$CmdShimContent = "@echo off`r`n`"$DestBunExe`" `"%USERPROFILE%\.claude\plugins\marketplaces\thedotmack\plugin\scripts\worker-service.cjs`" %*`r`n"
[System.IO.File]::WriteAllText($CmdShimPath, $CmdShimContent, [System.Text.Encoding]::ASCII)
Write-Ok "Created global command: claude-mem"

# 2. Deploy Marketplace
Write-Step "2/6 Deploying plugin marketplace directory..."
if (Test-Path $MarketplaceDir) {
    Remove-Item $MarketplaceDir -Recurse -Force
}
New-Item -ItemType Directory -Path $MarketplaceDir -Force | Out-Null
Copy-Item (Join-Path $ScriptDir "marketplace\*") $MarketplaceDir -Recurse -Force

$MarketplacePluginDir = Join-Path $MarketplaceDir "plugin"
New-Item -ItemType Directory -Path $MarketplacePluginDir -Force | Out-Null
Copy-Item (Join-Path $ScriptDir "plugin\*") $MarketplacePluginDir -Recurse -Force
Write-Ok "Marketplace directory deployed: $MarketplaceDir"

# 3. Deploy Plugin Cache
Write-Step "3/6 Deploying plugin cache directory..."
if (Test-Path $PluginCacheDir) {
    Remove-Item $PluginCacheDir -Recurse -Force
}
New-Item -ItemType Directory -Path $PluginCacheDir -Force | Out-Null
Copy-Item (Join-Path $ScriptDir "plugin\*") $PluginCacheDir -Recurse -Force
Write-Ok "Plugin cache deployed: $PluginCacheDir"

# 4. Configure Claude Code plugin registration
Write-Step "4/6 Registering plugin in Claude Code..."
New-Item -ItemType Directory -Path (Join-Path $ClaudeDir "plugins") -Force | Out-Null

# 4.1 known_marketplaces.json
$KnownMarketplacesPath = Join-Path $ClaudeDir "plugins\known_marketplaces.json"
$KnownMarketplaces = @{}
if (Test-Path $KnownMarketplacesPath) {
    try {
        $raw = Get-Content $KnownMarketplacesPath -Raw -Encoding utf8
        if ($raw.Trim()) { $KnownMarketplaces = $raw | ConvertFrom-Json -AsHashtable }
    } catch {}
}
$MarketplaceLocation = $MarketplaceDir.Replace('\', '/')
$KnownMarketplaces["thedotmack"] = @{
    source = @{
        source = "github"
        repo = "thedotmack/claude-mem"
    }
    installLocation = $MarketplaceLocation
    lastUpdated = (Get-Date).ToString("o")
    autoUpdate = $false
}
$KnownMarketplaces | ConvertTo-Json -Depth 10 | Set-Content $KnownMarketplacesPath -Encoding utf8
Write-Ok "Updated: $KnownMarketplacesPath"

# 4.2 installed_plugins.json
$InstalledPluginsPath = Join-Path $ClaudeDir "plugins\installed_plugins.json"
$InstalledPlugins = @{
    version = 2
    plugins = @{}
}
if (Test-Path $InstalledPluginsPath) {
    try {
        $raw = Get-Content $InstalledPluginsPath -Raw -Encoding utf8
        if ($raw.Trim()) { $InstalledPlugins = $raw | ConvertFrom-Json -AsHashtable }
    } catch {}
}
if (-not $InstalledPlugins.ContainsKey("plugins") -or $null -eq $InstalledPlugins["plugins"]) {
    $InstalledPlugins["plugins"] = @{}
}
$PluginInstallPath = $PluginCacheDir.Replace('\', '/')
$InstalledPlugins["plugins"]["claude-mem@thedotmack"] = @(
    @{
        scope = "user"
        installPath = $PluginInstallPath
        version = $Version
        installedAt = (Get-Date).ToString("o")
        lastUpdated = (Get-Date).ToString("o")
    }
)
$InstalledPlugins | ConvertTo-Json -Depth 10 | Set-Content $InstalledPluginsPath -Encoding utf8
Write-Ok "Updated: $InstalledPluginsPath"

# 4.3 settings.json
$ClaudeSettingsPath = Join-Path $ClaudeDir "settings.json"
$ClaudeSettings = @{}
if (Test-Path $ClaudeSettingsPath) {
    try {
        $raw = Get-Content $ClaudeSettingsPath -Raw -Encoding utf8
        if ($raw.Trim()) { $ClaudeSettings = $raw | ConvertFrom-Json -AsHashtable }
    } catch {}
}
if (-not $ClaudeSettings.ContainsKey("enabledPlugins") -or $null -eq $ClaudeSettings["enabledPlugins"]) {
    $ClaudeSettings["enabledPlugins"] = @{}
}
$ClaudeSettings["enabledPlugins"]["claude-mem@thedotmack"] = $true

if (-not $KeepAutoMemory) {
    if (-not $ClaudeSettings.ContainsKey("env") -or $null -eq $ClaudeSettings["env"]) {
        $ClaudeSettings["env"] = @{}
    }
    $ClaudeSettings["env"]["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    Write-Ok "Disabled Claude Code native auto-memory to prevent context conflicts"
}
$ClaudeSettings | ConvertTo-Json -Depth 10 | Set-Content $ClaudeSettingsPath -Encoding utf8
Write-Ok "Updated: $ClaudeSettingsPath"

# 5. Configure Claude-Mem intranet settings
Write-Step "5/6 Configuring Claude-Mem intranet settings (~/.claude-mem/settings.json)..."
if (-not (Test-Path $ClaudeMemDir)) {
    New-Item -ItemType Directory -Path $ClaudeMemDir -Force | Out-Null
}
$MemSettingsPath = Join-Path $ClaudeMemDir "settings.json"
$MemSettings = @{
    CLAUDE_MEM_DISABLE_VECTOR_SEARCH = $true
    CLAUDE_MEM_TELEMETRY = $false
    CLAUDE_MEM_AUTO_UPDATE = $false
    CLAUDE_MEM_PROVIDER = $Provider
    CLAUDE_MEM_WORKER_PORT = [string]$WorkerPort
}
if (Test-Path $MemSettingsPath) {
    try {
        $raw = Get-Content $MemSettingsPath -Raw -Encoding utf8
        if ($raw.Trim()) {
            $existing = $raw | ConvertFrom-Json -AsHashtable
            foreach ($k in $existing.Keys) {
                if (-not $MemSettings.ContainsKey($k)) {
                    $MemSettings[$k] = $existing[$k]
                }
            }
        }
    } catch {}
}
$MemSettings | ConvertTo-Json -Depth 10 | Set-Content $MemSettingsPath -Encoding utf8
Write-Ok "Optimized intranet configuration: SQLite FTS5 enabled, telemetry/updates disabled"

# 6. Optional IDE Integrations
if ($Ide -eq 'cursor' -or $Ide -eq 'all') {
    Write-Step "Configuring Cursor integration..."
    $CursorDir = Join-Path $UserHome ".cursor"
    New-Item -ItemType Directory -Path $CursorDir -Force | Out-Null
    $CursorMcpPath = Join-Path $CursorDir "mcp.json"
    $McpConfig = @{
        mcpServers = @{
            "claude-mem" = @{
                command = $DestBunExe.Replace('\', '/')
                args = @(($PluginInstallPath + "/scripts/mcp-server.cjs"))
            }
        }
    }
    $McpConfig | ConvertTo-Json -Depth 10 | Set-Content $CursorMcpPath -Encoding utf8
    Write-Ok "Cursor MCP configured: $CursorMcpPath"
}

if ($Ide -eq 'antigravity' -or $Ide -eq 'all') {
    Write-Step "Configuring Antigravity CLI integration..."
    $AgyConfigDir = Join-Path $UserHome ".gemini\config"
    New-Item -ItemType Directory -Path $AgyConfigDir -Force | Out-Null
    $AgyMcpPath = Join-Path $AgyConfigDir "mcp_config.json"
    $McpConfig = @{
        mcpServers = @{
            "claude-mem" = @{
                command = $DestBunExe.Replace('\', '/')
                args = @(($PluginInstallPath + "/scripts/mcp-server.cjs"))
            }
        }
    }
    $McpConfig | ConvertTo-Json -Depth 10 | Set-Content $AgyMcpPath -Encoding utf8
    Write-Ok "Antigravity MCP configured: $AgyMcpPath"
}

# 7. Start and verify Worker service
if (-not $SkipWorkerStart) {
    Write-Step "6/6 Starting and verifying Claude-Mem Worker service..."
    $WorkerScript = Join-Path $MarketplaceDir "plugin\scripts\worker-service.cjs"
    
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # Stop any previous instance
        $null = & "$DestBunExe" "$WorkerScript" stop 2>$null
        Start-Sleep -Milliseconds 500

        # Start worker
        $null = & "$DestBunExe" "$WorkerScript" start 2>$null
        Start-Sleep -Seconds 2
    } finally {
        $ErrorActionPreference = $oldEap
    }

    # Health check
    $HealthUrl = "http://127.0.0.1:$WorkerPort/api/health"
    try {
        $response = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 3 -ErrorAction Stop
        if ($response.status -eq 'ok') {
            Write-Ok "Worker is running successfully! (PID: $($response.pid), Port: $WorkerPort)"
        } else {
            Write-Warn "Worker responded with: $($response.status)"
        }
    } catch {
        Write-Warn "Worker is initializing in background. Run 'claude-mem status' to check."
    }
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "       Claude-Mem Offline Installation Complete!          " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "You can now run Claude Code and it will automatically capture context." -ForegroundColor White
Write-Host "Management commands:" -ForegroundColor Yellow
Write-Host "  claude-mem status   - Check status and stats" -ForegroundColor Gray
Write-Host "  claude-mem start    - Start worker service" -ForegroundColor Gray
Write-Host "  claude-mem stop     - Stop worker service" -ForegroundColor Gray
Write-Host "  claude-mem doctor   - Run diagnostics`n" -ForegroundColor Gray
