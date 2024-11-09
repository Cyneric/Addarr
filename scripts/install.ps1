# Filename: install.ps1
# Author: Christian Blank (https://github.com/cyneric)
# Created Date: 2024-11-08
# Description: PowerShell installer script for Addarr, a Media Management Telegram Bot.
# License: MIT

# Installer script for Windows
$ErrorActionPreference = "Stop"

# Colors for output
$colors = @{
    Red = [System.ConsoleColor]::Red
    Green = [System.ConsoleColor]::Green
    Yellow = [System.ConsoleColor]::Yellow
    Blue = [System.ConsoleColor]::Blue
}

Write-Host @"

╔═══════════════════════════════════════╗
║           Addarr Installer            ║
║     Media Management Telegram Bot     ║
╚═══════════════════════════════════════╝
"@ -ForegroundColor $colors.Blue

# Check for required commands
function Test-Command {
    param($Command)
    
    if (!(Get-Command $Command -ErrorAction SilentlyContinue)) {
        Write-Host "Error: $Command is required but not installed." -ForegroundColor $colors.Red
        Write-Host "Please install $Command and try again."
        exit 1
    }
}

# Check for admin rights
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Please run this script as Administrator" -ForegroundColor $colors.Red
    exit 1
}

# Check requirements
Test-Command "python"
Test-Command "git"

# Create installation directory
$INSTALL_DIR = "$env:LOCALAPPDATA\Addarr"
Write-Host "`nInstalling Addarr to: $INSTALL_DIR" -ForegroundColor $colors.Yellow

if (Test-Path $INSTALL_DIR) {
    Write-Host "Installation directory already exists. Backing up..." -ForegroundColor $colors.Yellow
    $backupDir = "$INSTALL_DIR.backup.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Move-Item $INSTALL_DIR $backupDir
}

# Clone repository
Write-Host "`nCloning repository..." -ForegroundColor $colors.Blue
try {
    git clone https://github.com/cyneric/addarr.git $INSTALL_DIR
} catch {
    Write-Host "Failed to clone repository" -ForegroundColor $colors.Red
    exit 1
}

# Create virtual environment
Write-Host "`nCreating virtual environment..." -ForegroundColor $colors.Blue
Set-Location $INSTALL_DIR
python -m venv venv

# Activate virtual environment and install dependencies
Write-Host "`nInstalling dependencies..." -ForegroundColor $colors.Blue
& "$INSTALL_DIR\venv\Scripts\activate.ps1"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to install dependencies" -ForegroundColor $colors.Red
    exit 1
}

# Create launcher script
$LAUNCHER = "$env:LOCALAPPDATA\Microsoft\WindowsApps\addarr.cmd"
@"
@echo off
call "$INSTALL_DIR\venv\Scripts\activate.bat"
python "$INSTALL_DIR\run.py" %*
"@ | Out-File -FilePath $LAUNCHER -Encoding ASCII

# Add installation directory to PATH
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$env:LOCALAPPDATA\Microsoft\WindowsApps*") {
    [Environment]::SetEnvironmentVariable(
        "Path",
        "$userPath;$env:LOCALAPPDATA\Microsoft\WindowsApps",
        "User"
    )
}

# Ask about Windows service installation
Write-Host "`nWould you like to install Addarr as a Windows service? [y/N]" -ForegroundColor $colors.Yellow
$installService = Read-Host
if ($installService -eq 'y' -or $installService -eq 'Y') {
    # Create service wrapper script
    $serviceWrapper = "$INSTALL_DIR\service-wrapper.ps1"
@"
`$env:PATH = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
Set-Location "$INSTALL_DIR"
& "$INSTALL_DIR\venv\Scripts\activate.ps1"
python "$INSTALL_DIR\run.py"
"@ | Out-File -FilePath $serviceWrapper -Encoding UTF8

    # Create service using NSSM (Non-Sucking Service Manager)
    Write-Host "`nDownloading NSSM (Service Manager)..." -ForegroundColor $colors.Blue
    $nssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
    $nssmZip = "$env:TEMP\nssm.zip"
    $nssmPath = "$INSTALL_DIR\tools"
    
    # Download and extract NSSM
    Invoke-WebRequest -Uri $nssmUrl -OutFile $nssmZip
    Expand-Archive -Path $nssmZip -DestinationPath $nssmPath -Force
    Copy-Item "$nssmPath\nssm-2.24\win64\nssm.exe" "$nssmPath\nssm.exe"
    Remove-Item -Path $nssmZip
    Remove-Item -Path "$nssmPath\nssm-2.24" -Recurse

    # Install the service
    $nssm = "$nssmPath\nssm.exe"
    & $nssm install Addarr "powershell.exe" "-ExecutionPolicy Bypass -NoProfile -File `"$serviceWrapper`""
    & $nssm set Addarr DisplayName "Addarr Media Bot"
    & $nssm set Addarr Description "Telegram bot for media management through Radarr, Sonarr, and Lidarr"
    & $nssm set Addarr ObjectName LocalSystem
    & $nssm set Addarr Start SERVICE_AUTO_START
    
    # Ask about starting at boot
    Write-Host "`nWould you like Addarr to start automatically at boot? [y/N]" -ForegroundColor $colors.Yellow
    $startBoot = Read-Host
    if ($startBoot -eq 'y' -or $startBoot -eq 'Y') {
        & $nssm set Addarr Start SERVICE_AUTO_START
        Write-Host "✓ Addarr will start automatically at boot" -ForegroundColor $colors.Green
    } else {
        & $nssm set Addarr Start SERVICE_DEMAND_START
    }

    # Ask about starting now
    Write-Host "`nWould you like to start Addarr now? [y/N]" -ForegroundColor $colors.Yellow
    $startNow = Read-Host
    if ($startNow -eq 'y' -or $startNow -eq 'Y') {
        Start-Service Addarr
        Write-Host "✓ Addarr service started" -ForegroundColor $colors.Green
        Write-Host "`nYou can manage the service with:" -ForegroundColor $colors.Blue
        Write-Host "Start-Service Addarr"
        Write-Host "Stop-Service Addarr"
        Write-Host "Restart-Service Addarr"
        Write-Host "Get-Service Addarr"
    }
}

Write-Host "`nInstallation complete!" -ForegroundColor $colors.Green
Write-Host "`nTo get started:" -ForegroundColor $colors.Yellow
Write-Host "1. Run initial setup:" -NoNewline
Write-Host " addarr (on first run, setup wizard will start automatically)" -ForegroundColor $colors.Blue
if ($installService -ne 'y' -and $installService -ne 'Y') {
    Write-Host "2. Start the bot:" -NoNewline
    Write-Host " addarr" -ForegroundColor $colors.Blue
}
Write-Host "`nFor more information, visit: " -NoNewline
Write-Host "https://github.com/cyneric/addarr/wiki" -ForegroundColor $colors.Blue

# Refresh environment variables in current session
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")