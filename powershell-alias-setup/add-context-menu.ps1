# 需要以管理员身份运行
# 功能：添加 PowerShell 7 的右键菜单（Shift+右键 可见）

$pwshPath = "C:\Program Files\PowerShell\7\pwsh.exe"
$displayName = "在此处打开 PowerShell 7"

# 1. 在文件夹空白处右键（背景菜单）
$bgPath = "HKLM:\SOFTWARE\Classes\Directory\Background\shell\pwsh"
New-Item -Path $bgPath -Force | Out-Null
Set-ItemProperty -Path $bgPath -Name "(default)" -Value $displayName
Set-ItemProperty -Path $bgPath -Name "Icon" -Value $pwshPath
Set-ItemProperty -Path $bgPath -Name "Extended" -Value ""  # Shift+右键 才显示

New-Item -Path "$bgPath\command" -Force | Out-Null
Set-ItemProperty -Path "$bgPath\command" -Name "(default)" -Value "`"$pwshPath`" -NoExit -WorkingDirectory `"%V`""

# 2. 在文件夹上右键（目录菜单）
$dirPath = "HKLM:\SOFTWARE\Classes\Directory\shell\pwsh"
New-Item -Path $dirPath -Force | Out-Null
Set-ItemProperty -Path $dirPath -Name "(default)" -Value $displayName
Set-ItemProperty -Path $dirPath -Name "Icon" -Value $pwshPath
Set-ItemProperty -Path $dirPath -Name "Extended" -Value ""  # Shift+右键 才显示

New-Item -Path "$dirPath\command" -Force | Out-Null
Set-ItemProperty -Path "$dirPath\command" -Name "(default)" -Value "`"$pwshPath`" -NoExit -WorkingDirectory `"%V`""

# 3. 添加管理员运行版本（背景）
$bgAdminPath = "HKLM:\SOFTWARE\Classes\Directory\Background\shell\pwsh_admin"
New-Item -Path $bgAdminPath -Force | Out-Null
Set-ItemProperty -Path $bgAdminPath -Name "(default)" -Value "以管理员身份打开 PowerShell 7"
Set-ItemProperty -Path $bgAdminPath -Name "Icon" -Value $pwshPath
Set-ItemProperty -Path $bgAdminPath -Name "Extended" -Value ""  # Shift+右键 才显示

New-Item -Path "$bgAdminPath\command" -Force | Out-Null
Set-ItemProperty -Path "$bgAdminPath\command" -Name "(default)" -Value "powershell.exe -Command `"Start-Process '$pwshPath' -ArgumentList '-NoExit -WorkingDirectory ''%V''' -Verb RunAs`""

# 4. 添加管理员运行版本（目录）
$dirAdminPath = "HKLM:\SOFTWARE\Classes\Directory\shell\pwsh_admin"
New-Item -Path $dirAdminPath -Force | Out-Null
Set-ItemProperty -Path $dirAdminPath -Name "(default)" -Value "以管理员身份打开 PowerShell 7"
Set-ItemProperty -Path $dirAdminPath -Name "Icon" -Value $pwshPath
Set-ItemProperty -Path $dirAdminPath -Name "Extended" -Value ""  # Shift+右键 才显示

New-Item -Path "$dirAdminPath\command" -Force | Out-Null
Set-ItemProperty -Path "$dirAdminPath\command" -Name "(default)" -Value "powershell.exe -Command `"Start-Process '$pwshPath' -ArgumentList '-NoExit -WorkingDirectory ''%V''' -Verb RunAs`""

Write-Host "完成！Shift+右键 现在可以看到以下菜单：" -ForegroundColor Green
Write-Host "  - 在此处打开 PowerShell 7" -ForegroundColor Cyan
Write-Host "  - 以管理员身份打开 PowerShell 7" -ForegroundColor Cyan
