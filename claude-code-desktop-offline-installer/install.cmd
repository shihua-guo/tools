@echo off
setlocal
chcp 65001 >nul
title Claude Code Desktop 离线安装程序

echo ============================================================
echo       Claude Code Desktop 离线安装程序 (v2.31226.1)
echo ============================================================
echo.

:: 检查是否具备管理员权限
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] 正在申请管理员权限 (UAC 提权)...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell.exe -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"\"%~dp0install.ps1\"\"' -Verb RunAs"
    exit /b
)

:: 已具有管理员权限，直接运行 install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
