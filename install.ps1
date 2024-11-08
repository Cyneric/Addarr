# Filename: install.ps1
# Author: Christian Blank (https://github.com/cyneric)
# Created Date: 2024-11-08
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
function Check-Command {
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
Check-Command "python"
Check-Command "git"

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

Write-Host "`nInstallation complete!" -ForegroundColor $colors.Green
Write-Host "`nTo get started:" -ForegroundColor $colors.Yellow
Write-Host "1. Run initial setup:" -NoNewline
Write-Host " addarr --setup" -ForegroundColor $colors.Blue
Write-Host "2. Start the bot:" -NoNewline
Write-Host " addarr" -ForegroundColor $colors.Blue
Write-Host "`nFor more information, visit: " -NoNewline
Write-Host "https://github.com/cyneric/addarr/wiki" -ForegroundColor $colors.Blue

# Refresh environment variables in current session
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User") 