param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venv = Join-Path $root ".venv"
$wheelhouse = Join-Path $root "wheelhouse"

if (-not (Test-Path (Join-Path $wheelhouse "*.whl"))) {
    throw "wheelhouse is missing. On an Internet-connected machine, run prepare_offline_wheels.ps1 and copy the whole tool directory."
}

& $Python -c "import sys; assert sys.version_info[:2] == (3, 13), 'Python 3.13 x64 is required'; assert sys.maxsize > 2**32, '64-bit Python is required'"
if ($LASTEXITCODE -ne 0) { throw "Please install/use a 64-bit Python 3.13 interpreter, then pass it with -Python." }

if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    & $Python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Failed to create .venv." }
}

$venvPython = Join-Path $venv "Scripts\python.exe"
& $venvPython -m pip install --no-index --find-links $wheelhouse -r (Join-Path $root "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Offline dependency installation failed." }

& $venvPython (Join-Path $root "mp4_asr_offline.py") --config (Join-Path $root "config.yaml") --check-runtime
if ($LASTEXITCODE -ne 0) { throw "Runtime check failed. Check capswriter_dir in config.yaml and the CapsWriter installation." }

Write-Host "Installation complete. Edit config.yaml, then run run.cmd."
