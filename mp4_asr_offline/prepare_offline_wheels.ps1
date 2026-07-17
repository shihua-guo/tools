param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$wheelhouse = Join-Path $root "wheelhouse"
New-Item -ItemType Directory -Force -Path $wheelhouse | Out-Null

& $Python -c "import sys; assert sys.version_info[:2] == (3, 13), 'Python 3.13 x64 is required'; assert sys.maxsize > 2**32, '64-bit Python is required'"
if ($LASTEXITCODE -ne 0) { throw "Please run this with a 64-bit Python 3.13 interpreter." }

& $Python -m pip download --dest $wheelhouse --only-binary=:all: -r (Join-Path $root "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Wheel download failed." }

Write-Host "Offline wheelhouse is ready: $wheelhouse"
