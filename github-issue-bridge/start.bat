@echo off
setlocal

cd /d "%~dp0"
set PYTHONPATH=%~dp0src

echo Starting issue-bridge daemon...
echo Config: %~dp0issue-bridge.json
echo.

python -m issue_bridge.main --config "%~dp0issue-bridge.json"
