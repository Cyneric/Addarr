<div align="center">

# 🚀 Addarr Refresh

</div>

<br>
<br>

<div align="center" style="display: flex; justify-content: center; align-items: center; gap: 10px;">

![Telegram](https://img.shields.io/badge/Telegram-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)
![Python](https://img.shields.io/badge/Python-FFD43B?style=for-the-badge&logo=python&logoColor=blue)
![Docker](https://img.shields.io/badge/Docker-2CA5E0?style=for-the-badge&logo=docker&logoColor=white)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
</div>

<br>
<br>

<div align="center" style="display: flex; justify-content: center; align-items: center; gap: 40px;">
<img src="https://raw.githubusercontent.com/telegramdesktop/tdesktop/refs/heads/dev/Telegram/Resources/art/icon64.png" width="64px" height="64px" alt="Telegram">
<img src="https://raw.githubusercontent.com/Radarr/Radarr/refs/heads/develop/Logo/64.png" width="64px" height="64px" alt="Radarr">
<img src="https://raw.githubusercontent.com/Sonarr/Sonarr/refs/heads/develop/Logo/64.png" width="64px" height="64px" alt="Sonarr">
<img src="https://raw.githubusercontent.com/Lidarr/Lidarr/refs/heads/develop/Logo/64.png" width="64px" height="64px" alt="Lidarr">
<img src="https://raw.githubusercontent.com/sabnzbd/sabnzbd/refs/heads/develop/icons/logo-arrow.svg" width="64px" height="64px" alt="Sabnzbd">
<img src="https://raw.githubusercontent.com/transmission/transmission/refs/heads/main/web/assets/img/logo.png" width="64px" height="64px" alt="Transmission">
</div>

<br>
<br>

<div align="center">

*A Telegram bot to manage your media collection through Radarr, Sonarr, and Lidarr*

<br>
<br>

Addarr Refresh is a modern Telegram bot that helps you manage your media collection through Radarr, Sonarr, and Lidarr. This user-friendly fork of Addarr adds powerful new features like:

  🎯 Improved search accuracy and matching
  <br>
  🔔 Enhanced notifications and status updates
  <br>
  🛠️ Interactive setup wizard for easy configuration
  <br>
  🌐 Multi-language support
  <br>
  🔒 Advanced user authentication and permissions
  <br>
  📊 Detailed health monitoring and statistics
  <br>
  🎨 Modern UI with inline keyboards and rich media
  <br>
  📁 Helm chart for easy deployment
  <br>
  🐳 Docker image for easy containerization
  <br>
  🔍 Validations and error handling

<br>

Whether you're managing movies, TV shows, or music, Addarr Refresh makes it simple to search, download, and organize your media library right from Telegram.

---


## 🚀 Quick Install

#### Linux/macOS
Open a terminal and run:

```bash
sudo wget -qO- https://raw.githubusercontent.com/cyneric/addarr/main/scripts/install.sh | bash
```

#### Windows
Open PowerShell as Administrator and run:

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://raw.githubusercontent.com/cyneric/addarr/main/scripts/install.ps1'))
```

For more options, see [🛠️ Installation](#️-installation)


---

[Features](#-features) | [System Requirements](#-system-requirements) | [Installation](#️-installation) | [Usage](#-usage) | [Configuration](#basic-configuration) | [Contributing](#-contributing)

</div>

<div align="center">
  <img src="https://github.com/user-attachments/assets/db261a61-d49c-45f7-b103-d39d3b3a17ef" alt="Addarr Refresh Splash">
</div>


## 📋 Table of Contents

- [🚀 Addarr Refresh](#-addarr-refresh)
  - [🚀 Quick Install](#-quick-install)
      - [Linux/macOS](#linuxmacos)
      - [Windows](#windows)
  - [📋 Table of Contents](#-table-of-contents)
  - [✨ Features](#-features)
  - [💻 System Requirements](#-system-requirements)
    - [Supported Operating Systems](#supported-operating-systems)
    - [Prerequisites](#prerequisites)
    - [Python Installation](#python-installation)
      - [Windows](#windows-1)
      - [Linux (Debian/Ubuntu)](#linux-debianubuntu)
      - [macOS](#macos)
  - [🛠️ Installation](#️-installation)
    - [Option 1: Install Script (easy)](#option-1-install-script-easy)
      - [Linux/macOS](#linuxmacos-1)
      - [Windows](#windows-2)
    - [Option 2: Git Clone (advanced)](#option-2-git-clone-advanced)
    - [Option 3: Manual installation from zip file (advanced)](#option-3-manual-installation-from-zip-file-advanced)
    - [Option 4: Docker Installation (advanced)](#option-4-docker-installation-advanced)
      - [Using Docker Compose](#using-docker-compose)
      - [Using Docker standalone](#using-docker-standalone)
  - [🎮 Usage](#-usage)
    - [Available Commands](#available-commands)
    - [Authentication](#authentication)
    - [Adding Media](#adding-media)
    - [Command Line Options](#command-line-options)
      - [Command Details](#command-details)
    - [Configuration Backups](#configuration-backups)
  - [⚙️ Configuration](#️-configuration)
    - [Basic Configuration](#basic-configuration)
    - [Service Configuration](#service-configuration)
    - [Resetting Configuration](#resetting-configuration)
  - [🏥 Health Monitoring](#-health-monitoring)
    - [Features](#features)
    - [Health Check Details](#health-check-details)
    - [Configuration](#configuration)
    - [Status Command](#status-command)
    - [Automatic Recovery](#automatic-recovery)
  - [🌐 Internationalization](#-internationalization)
    - [Supported Languages](#supported-languages)
    - [Adding Translations](#adding-translations)
  - [🔧 Service Management](#-service-management)
    - [Windows Service](#windows-service)
    - [Linux Systemd Service](#linux-systemd-service)
  - [☁️ Deployment Options](#️-deployment-options)
    - [Docker Deployment](#docker-deployment)
    - [Kubernetes Deployment](#kubernetes-deployment)
  - [👨‍💻 Development](#-development)
    - [Project Structure](#project-structure)
    - [Development Setup](#development-setup)
  - [🤝 Contributing](#-contributing)
  - [📄 License](#-license)
  - [Author](#author)
  - [🙏 Acknowledgments](#-acknowledgments)

## ✨ Features

- 🎬 **Movie Management**
  - Search and add movies through Radarr
  - Preview movie posters and descriptions
  - Select quality profiles and paths
  - Automatic movie monitoring

- 📺 **TV Show Management**
  - Add TV series via Sonarr
  - Season selection support
  - Quality profile management
  - Automatic episode monitoring

- 🎵 **Music Management**
  - Artist and album search through Lidarr
  - Quality profile selection
  - Automatic release monitoring
  - Album organization

- 🛠️ **Advanced Features**
  - 🖼️ Rich media previews with posters
  - 🌍 Multi-language support
  - 🔒 Secure chat-based authentication
  - ⚡ Download speed control
  - 📁 Custom path selection
  - 🎚️ Quality profile management
  - 🔄 Automatic media monitoring
  - 📝 Detailed logging system

- 🏥 **Health Monitoring**
  - Real-time service health checks
  - Automatic service recovery detection
  - Detailed version information
  - Service connectivity monitoring
  - Status reporting via `/status` command
  - Configurable check intervals
  - Colorized health status output

## 💻 System Requirements

### Supported Operating Systems
- **Windows** 10/11
- **Linux** (Ubuntu 20.04+, Debian 10+, CentOS 8+)
- **macOS** (10.15 Catalina or newer)

### Prerequisites
- Python 3.9 or higher
- pip (Python package installer)
- At least one of: Radarr, Sonarr, or Lidarr instance(s)
- Telegram Bot Token (from @BotFather)

### Python Installation

#### Windows
1. Download Python from [python.org](https://www.python.org/downloads/)
2. Run the installer (make sure to check "Add Python to PATH")
3. Verify installation:
   ```cmd
   python --version
   pip --version
   ```

#### Linux (Debian/Ubuntu)
```bash
# Update package list
sudo apt update

# Install Python and pip
sudo apt install python3 python3-pip

# Verify installation
python3 --version
pip3 --version
```

#### macOS
1. Install Homebrew if not already installed:
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/scripts/install.sh)"
   ```
2. Install Python:
   ```bash
   brew install python
   ```
3. Verify installation:
   ```bash
   python3 --version
   pip3 --version
   ```

## 🛠️ Installation

### Option 1: Install Script (easy)
*(Linux/macOS/Windows)*

Install Addarr with a single command

#### Linux/macOS

Using curl:
```bash
sudo curl -sSL https://raw.githubusercontent.com/cyneric/addarr/main/scripts/install.sh | bash
```

or Using wget:
```bash
sudo wget -qO- https://raw.githubusercontent.com/cyneric/addarr/main/scripts/install.sh | bash
```

The linux/macOS installer will:
- Create a dedicated installation directory at `~/.addarr`
- Set up a Python virtual environment
- Install all required dependencies
- Create the `addarr` command for easy access
- Back up any existing installation

After installation:
1. Run `addarr` (on first run, setup wizard will start automatically)
2. Run `addarr` to start the bot

#### Windows

Using PowerShell:
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://raw.githubusercontent.com/cyneric/addarr/main/scripts/install.ps1'))
```

The windows installer will:
- Create a dedicated installation directory at `C:\Users\<username>\AppData\Local\Addarr`
- Set up a Python virtual environment
- Install all required dependencies
- Create the `addarr` command for easy access
- Back up any existing installation

After installation:
1. Run `addarr` (on first run, setup wizard will start automatically)
2. Run `addarr` to start the bot


### Option 2: Git Clone (advanced)
*(Linux/macOS/Windows)*

*Requires git to be installed and available in the command line.*

1. **Clone the repository**
   ```bash
   git clone https://github.com/Cyneric/Addarr.git
   ```

2. **Change into the Addarr directory**
   ```bash
   cd addarr
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Start the Bot**
   ```bash
   python run.py
   ```

   The bot will automatically start the setup wizard of no configuration file is found.


### Option 3: Manual installation from zip file (advanced)
  *(Windows)*
  
  *Requires python to be installed and available in the command line.*

1. **Download the zip file**
   Download the zip file from [here](https://github.com/Cyneric/Addarr/archive/refs/heads/main.zip)

2. **Extract the zip file**
   Extract the zip file and change into the Addarr directory

3. **Copy or rename the config file**
   Copy or rename the `config_example.yaml` file to `config.yaml`

4. **Edit the config file**
   Edit the `config.yaml` file with your settings.

5. **Run configuration check**
   ```bash
   python run.py --check
   ```

6. **Start the bot**
   ```bash
   python run.py
   ```

### Option 4: Docker Installation (advanced)
*(Linux/macOS/Windows)*

#### Using Docker Compose
1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/addarr.git
   cd addarr
   ```

2. **Configure the bot**
   ```bash
   cp config_example.yaml config.yaml
   # Edit config.yaml with your settings
   ```

3. **Start with Docker Compose**
   ```bash
   docker-compose up -d
   ```

#### Using Docker standalone
1. **Build the image**
   ```bash
   docker build -t addarr .
   ```

2. **Run the container**
   ```bash
   docker run -d \
     --name addarr \
     -v $(pwd)/config.yaml:/app/config.yaml \
     -v $(pwd)/logs:/app/logs \
     addarr
   ```

## 🎮 Usage

### Available Commands
- `/start` - Start the bot
- `/auth` - Authenticate with the bot
- `/movie` - Search and add movies
- `/series` - Search and add TV shows
- `/music` - Search and add music
- `/delete` - Delete media
- `/status` - Check system status
- `/settings` - Manage settings
- `/help` - Show help message

### Authentication
1. Start the bot with `/start`
2. Use `/auth` to authenticate
3. Enter the password configured in `config.yaml`

### Adding Media
1. Use the appropriate command (`/movie`, `/series`, `/music`)
2. Enter search term
3. Select from search results
4. Choose quality profile and path
5. Confirm addition

### Command Line Options
The bot can be controlled through various command-line options:

```bash
# Normal startup (on first run, setup wizard will start automatically)
python run.py

# Reset the configuration and start from scratch
python run.py --reset

# Create a backup of the current configuration
python run.py --backup

# Check current configuration and service status
python run.py --check

# Show version information
python run.py --version

# Validate translation files
python run.py --validate-i18n

# Show help message and available commands
python run.py --help
```

#### Command Details
- `--setup`: Launches the interactive setup wizard to create a new configuration
- `--reset`: Creates a backup of the existing configuration in the backup directory and starts fresh setup
- `--backup`: Creates a timestamped backup of the current configuration in the backup directory
- `--check`: Displays the current status of all configured services
- `--version`: Shows the current version of Addarr
- `--validate-i18n`: Validates the translation files
- `--help`: Displays help message with all available commands and their descriptions

### Configuration Backups
Addarr automatically manages configuration backups:

- **Manual Backup**: Use `python run.py --backup` to create a backup anytime
- **Auto Backup on Reset**: When using `--reset`, the existing configuration is automatically backed up
- **Backup Location**: All backups are stored in the `backup` directory with timestamps
- **Backup Format**: `config_YYYYMMDD_HHMMSS.yaml`

This ensures you never lose your configuration and can easily revert to previous versions if needed.

## ⚙️ Configuration

### Basic Configuration
```yaml
telegram:
  token: "your-bot-token"
  
language: "en-us"  # Available: en-us, de-de, etc.

logging:
  debug: false
  toConsole: true
  
security:
  enableAdmin: false
  password: "your-password"
```

### Service Configuration
```yaml
radarr:
  server:
    addr: "localhost"
    port: 7878
    ssl: false
  auth:
    apikey: "your-radarr-api-key"

sonarr:
  server:
    addr: "localhost"
    port: 8989
    ssl: false
  auth:
    apikey: "your-sonarr-api-key"

lidarr:
  server:
    addr: "localhost"
    port: 8686
    ssl: false
  auth:
    apikey: "your-lidarr-api-key"
```

### Resetting Configuration
If you want to reset your configuration and start from scratch, you can use the `--reset` argument when running the setup script:

```bash
python setup.py --reset
```

This will delete the existing `config.yaml` file and prompt you to create a new one.

## 🏥 Health Monitoring

Addarr Refresh includes a comprehensive health monitoring system that continuously checks the status of all configured services:

### Features
- Periodic health checks of all enabled services
- Real-time service status monitoring
- Automatic detection of service recovery
- Detailed version information for each service
- Service connectivity validation
- Status reporting via `/status` command

### Health Check Details
The health monitoring system checks:
- **Media Services**
  - Radarr connectivity and version
  - Sonarr connectivity and version
  - Lidarr connectivity and version
- **Download Clients**
  - SABnzbd connectivity and version
  - Transmission connectivity and status

### Configuration
Health checks can be configured in `config.yaml`:
```yaml
monitoring:
  interval: 15  # Check interval in minutes
  enabled: true # Enable/disable health monitoring
```

### Status Command
Use the `/status` command in Telegram to get a detailed health report:
- Current status of all services
- Version information
- Last check time
- Any service issues or warnings

### Automatic Recovery
The system will:
- Detect when services become unavailable
- Log all service state changes
- Notify when services recover
- Provide detailed error information
- Track service uptime and status history

## 🌐 Internationalization

Addarr Refresh supports multiple languages:

### Supported Languages
- **English** (en-us)
- **German** (de-de)
- **Spanish** (es-es)
- **French** (fr-fr)
- **Italian** (it-it)
- **Dutch** (nl-be)
- **Polish** (pl-pl)
- **Portuguese** (pt-pt)

### Adding Translations
If you want to add a new language, follow these steps:
1. Create a new translation file in the `translations` directory
2. Add the new language code to the `language` field in `config.yaml`
3. Translate the messages in the new file
4. Run `python run.py --validate-i18n` to validate the translations

## 🔧 Service Management

Addarr Refresh can be run as a Windows service or a Linux Systemd service:

### Windows Service
1. Open PowerShell as Administrator
2. Navigate to the scripts directory:
   ```powershell
   cd C:\Users\<username>\AppData\Local\Addarr\scripts
   ```
3. Run the service installation script:
   ```powershell
   .\addarr.service.ps1
   ```
4. Manage the service:
   ```powershell
   Start-Service AddarrBot
   Stop-Service AddarrBot
   Restart-Service AddarrBot
   Get-Service AddarrBot
   ```

### Linux Systemd Service
1. Create the user service directory:
   ```bash
   mkdir -p ~/.config/systemd/user/
   ```
2. Copy the service file:
   ```bash
   cp ~/.addarr/scripts/addarr.service ~/.config/systemd/user/
   ```
3. Reload systemd:
   ```bash
   systemctl --user daemon-reload
   ```
4. Enable and start the service:
   ```bash
   systemctl --user enable addarr
   systemctl --user start addarr
   ```
5. Enable user service persistence:
   ```bash
   loginctl enable-linger $USER
   ```
6. Manage the service:
   ```bash
   systemctl --user status addarr
   systemctl --user start addarr
   systemctl --user stop addarr
   systemctl --user restart addarr
   ```

## ☁️ Deployment Options

Addarr Refresh can be deployed using Docker or Kubernetes:

### Docker Deployment
1. **Clone the repository**
   ```bash
   git clone https://github.com/Cyneric/Addarr.git
   cd addarr
   ```

2. **Configure the bot**
   ```bash
   cp config_example.yaml config.yaml
   # Edit config.yaml with your settings
   ```

3. **Start with Docker Compose**
   ```bash
   docker-compose up -d
   ```

### Kubernetes Deployment
1. **Create a Kubernetes deployment**
   ```bash
   kubectl apply -f kubernetes/deployment.yaml
   ```

2. **Create a Kubernetes service**
   ```bash
   kubectl apply -f kubernetes/service.yaml
   ```

## 👨‍💻 Development

### Project Structure

```
addarr/
├── src/                    # Source code directory
│   ├── api/               # API clients
│   │   ├── __init__.py
│   │   ├── base.py       # Base API client
│   │   ├── radarr.py     # Radarr API client
│   │   ├── sonarr.py     # Sonarr API client
│   │   ├── lidarr.py     # Lidarr API client
│   │   ├── transmission.py # Transmission API client
│   │   └── sabnzbd.py    # SABnzbd API client
│   ├── bot/              # Telegram bot components
│   │   ├── __init__.py
│   │   ├── handlers/     # Command handlers
│   │   │   ├── __init__.py
│   │   │   ├── auth.py   # Authentication handler
│   │   │   ├── media.py  # Media management handler
│   │   │   ├── start.py  # Start/menu handler
│   │   │   ├── help.py   # Help handler
│   │   │   ├── sabnzbd.py # SABnzbd handler
│   │   │   └── transmission.py # Transmission handler
│   │   └── keyboards.py  # Keyboard layouts
│   ├── config/           # Configuration management
│   │   ├── __init__.py
│   │   └── settings.py   # Configuration handling
│   ├── services/         # Business logic services
│   │   ├── __init__.py
│   │   ├── media.py      # Media service
│   │   ├── translation.py # Translation service
│   │   ├── transmission.py # Transmission service
│   │   └── sabnzbd.py    # SABnzbd service
│   ├── utils/            # Utility functions
│   │   ├── __init__.py
│   │   ├── logger.py     # Logging setup
│   │   └── validate_translations.py # Translation validation
│   ├── __init__.py
│   └── main.py          # Application entry point
├── translations/         # Translation files
│   ├── addarr.template.yml # Translation template
│   ├── addarr.en-us.yml
│   ├── addarr.de-de.yml
│   ├── addarr.es-es.yml
│   ├── addarr.fr-fr.yml
│   ├── addarr.it-it.yml
│   ├── addarr.nl-be.yml
│   ├── addarr.pl-pl.yml
│   └── addarr.pt-pt.yml
├── config.yaml          # User configuration
├── config_example.yaml  # Example configuration
├── run.py              # Application launcher
├── requirements.txt    # Python dependencies
├── Dockerfile         # Docker build file
└── docker-compose.yml # Docker compose config
```

### Development Setup

1. **Create development environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   venv\Scripts\activate     # Windows
   ```

2. **Install development dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # Development dependencies
   ```

3. **Set up pre-commit hooks**
   ```bash
   pre-commit install
   ```

4. **Run tests**
   ```bash
   pytest tests/
   ```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author
<a href="https://github.com/cyneric"><img src="https://github.com/cyneric.png" width="50px" alt="@cyneric" /> Christian Blank (@cyneric)</a>

## 🙏 Acknowledgments

This project is a modernized fork of [Addarr](https://github.com/Waterboy1602/Addarr), building upon its foundation with enhanced features, improved architecture, and a more robust codebase. Special thanks to @Waterboy1602 for creating the original project that made this possible.

[🔗 python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
[🔗 Radarr](https://radarr.video/)
[🔗 Sonarr](https://sonarr.tv/)
[🔗 Lidarr](https://lidarr.audio/)

---

<div align="center">
Made with ❤️
</div>