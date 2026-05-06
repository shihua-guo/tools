@echo off
:: 检查是否具有管理员权限
NET SESSION >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Requesting Administrator privileges to mount the virtual drive...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo 正在挂载网络虚拟硬盘...
echo select vdisk file="\\192.168.2.200\data4t\VirtualData.vhdx" > "%temp%\mount_vdisk.txt"
echo attach vdisk >> "%temp%\mount_vdisk.txt"

diskpart /s "%temp%\mount_vdisk.txt"
del "%temp%\mount_vdisk.txt"

echo 挂载完成！
timeout /t 3 >nul
