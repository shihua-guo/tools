@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo Missing .venv. Run install_offline.ps1 first.
  exit /b 1
)

"%PYTHON%" "%ROOT%mp4_asr_offline.py" --config "%ROOT%config.yaml" %*
