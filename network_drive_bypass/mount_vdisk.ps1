$vdiskPath = "\\192.168.2.200\data4t\VirtualData.vhdx"
$script = @"
select vdisk file="$vdiskPath"
attach vdisk
"@
$tempFile = "$env:TEMP\mount_vdisk.txt"
$script | Out-File -FilePath $tempFile -Encoding ASCII

$logFile = "$env:TEMP\diskpart_output.txt"
$process = Start-Process -FilePath "diskpart" -ArgumentList "/s $tempFile" -Verb RunAs -Wait -PassThru
Write-Host "diskpart exit code: $($process.ExitCode)"

Remove-Item $tempFile -ErrorAction SilentlyContinue

Start-Sleep -Seconds 2
$img = Get-DiskImage -ImagePath $vdiskPath -ErrorAction SilentlyContinue
if ($img -and $img.Attached) {
    Write-Host "VHDX mounted successfully!"
    $partitions = Get-Partition -DiskNumber $img.Number -ErrorAction SilentlyContinue
    $partitions | Format-Table -AutoSize
    # Try to assign drive letter if needed
    foreach ($p in $partitions) {
        if ($p.DriveLetter -eq [char]0 -or $p.DriveLetter -eq '') {
            $letters = [char[]](65..90) | Where-Object { (Get-Volume -DriveLetter $_ -ErrorAction SilentlyContinue) -eq $null }
            if ($letters.Count -gt 0) {
                $newLetter = $letters[0]
                Write-Host "Assigning drive letter $newLetter to partition $($p.PartitionNumber)"
                Set-Partition -DiskNumber $img.Number -PartitionNumber $p.PartitionNumber -NewDriveLetter $newLetter
            }
        }
    }
    Get-Volume | Where-Object { $_.DriveLetter -ne [char]0 } | Format-Table DriveLetter, FileSystemLabel, SizeRemaining, Size -AutoSize
} else {
    Write-Host "VHDX failed to mount. Status:"
    Get-DiskImage -ImagePath $vdiskPath
}
