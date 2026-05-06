# 需要以管理员身份运行
# 功能：移除 PowerShell 7 的右键菜单

Remove-Item -Path "HKLM:\SOFTWARE\Classes\Directory\Background\shell\pwsh" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "HKLM:\SOFTWARE\Classes\Directory\Background\shell\pwsh_admin" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "HKLM:\SOFTWARE\Classes\Directory\shell\pwsh" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "HKLM:\SOFTWARE\Classes\Directory\shell\pwsh_admin" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "已移除 PowerShell 7 右键菜单" -ForegroundColor Yellow
