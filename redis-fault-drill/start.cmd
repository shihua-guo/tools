@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python "%~dp0redis_fault.py" menu
) else (
  py -3 "%~dp0redis_fault.py" menu
)
if errorlevel 1 pause
