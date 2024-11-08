# File: addarr.service.ps1
# Author: Christian Blank (https://github.com/Cyneric)
# Created Date: 2024-11-08
# Description: This script configures a Windows service for the Addarr Media Management Bot.
# Save as: scripts/addarr.service.ps1

$ServiceName = "AddarrBot"
$DisplayName = "Addarr Media Bot"
$Description = "Telegram bot for media management through Radarr, Sonarr, and Lidarr"
$InstallPath = "$env:LOCALAPPDATA\Addarr"
$BinPath = "$InstallPath\venv\Scripts\python.exe"
$ScriptPath = "$InstallPath\run.py"

# Create service wrapper script
$WrapperScript = @"
Set-Location "$InstallPath"
& "$BinPath" "$ScriptPath"
"@

$WrapperPath = "$InstallPath\service-wrapper.ps1"
$WrapperScript | Out-File -FilePath $WrapperPath -Encoding UTF8

# Service configuration
$ServiceParams = @{
    Name = $ServiceName
    BinaryPathName = "powershell.exe -ExecutionPolicy Bypass -NoProfile -File `"$WrapperPath`""
    DisplayName = $DisplayName
    Description = $Description
    StartupType = "Automatic"
}

# Create and configure the service
New-Service @ServiceParams

# Set recovery options
sc.exe failure $ServiceName reset= 86400 actions= restart/30000/restart/60000/restart/120000

Write-Host "Service installed successfully. You can manage it with:"
Write-Host "Start-Service $ServiceName"
Write-Host "Stop-Service $ServiceName"
Write-Host "Restart-Service $ServiceName"
Write-Host "Get-Service $ServiceName" 