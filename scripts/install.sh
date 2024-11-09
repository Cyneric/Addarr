#!/bin/bash

# Filename: install.sh
# Author: Christian Blank (https://github.com/cyneric)
# Created Date: 2024-11-08
# Description: Bash installer script for Addarr, a Media Management Telegram Bot.
# License: MIT

# ANSI color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Spinner function
spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='|/-\'
    while [ "$(ps a | awk '{print $1}' | grep $pid)" ]; do
        local temp=${spinstr#?}
        printf " [%c]  " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        printf "\b\b\b\b\b\b"
        sleep $delay
    done
    printf "    \b\b\b\b"
}

# Progress message with spinner
progress() {
    local message=$1
    local command=$2
    echo -ne "${BLUE}${message}...${NC}"
    eval $command &
    spinner $!
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗${NC}"
        return 1
    fi
}

# Minimum required Python version
MIN_PYTHON_VERSION="3.8"

# Minimum required pip version
MIN_PIP_VERSION="20.0" # Example minimum version

# Check for sudo privileges
check_sudo() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${YELLOW}This script requires sudo privileges to install system packages.${NC}"
        echo -e "${YELLOW}Please run with: sudo $0${NC}"
        exit 1
    fi
}

# Function to install system packages
install_system_packages() {
    local packages=("$@")
    local system
    
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        system="$ID"
    elif [ -f /etc/debian_version ]; then
        system="debian"
    elif [ -f /etc/redhat-release ]; then
        system="rhel"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        system="macos"
    else
        system="unknown"
    fi

    echo -e "${BLUE}Installing required system packages...${NC}"
    
    case "$system" in
        "ubuntu"|"debian")
            apt-get update -qq
            apt-get install -y "${packages[@]}"
            ;;
        "fedora")
            dnf install -y "${packages[@]}"
            ;;
        "rhel"|"centos")
            yum install -y "${packages[@]}"
            ;;
        "arch")
            pacman -Sy --noconfirm "${packages[@]}"
            ;;
        "macos")
            if ! command -v brew >/dev/null 2>&1; then
                echo -e "${RED}Homebrew is required for macOS installation.${NC}"
                echo -e "Install from: https://brew.sh"
                exit 1
            fi
            for package in "${packages[@]}"; do
                brew install "$package"
            done
            ;;
        *)
            echo -e "${RED}Unsupported system: $system${NC}"
            echo -e "Please install the following packages manually: ${packages[*]}"
            exit 1
            ;;
    esac
}

# Check for required tools and install if missing
check_and_install_requirements() {
    local missing_packages=()

    # Check for unzip
    if ! command -v unzip >/dev/null 2>&1; then
        missing_packages+=("unzip")
    fi

    # Check for Python
    if ! command -v python3 >/dev/null 2>&1; then
        case "$(uname -s)" in
            Linux*)
                missing_packages+=("python3" "python3-pip" "python3-venv")
                ;;
            Darwin*)
                missing_packages+=("python")
                ;;
        esac
    fi

    # Check for pip
    if ! command -v pip3 >/dev/null 2>&1 && ! command -v pip >/dev/null 2>&1; then
        case "$(uname -s)" in
            Linux*)
                missing_packages+=("python3-pip")
                ;;
        esac
    fi

    # If there are missing packages, install them
    if [ ${#missing_packages[@]} -gt 0 ]; then
        echo -e "${YELLOW}The following packages need to be installed: ${missing_packages[*]}${NC}"
        check_sudo
        install_system_packages "${missing_packages[@]}"
    fi
}

# Call the check and install function early in the script
check_and_install_requirements

echo -e "${BLUE}
╔═══════════════════════════════════════╗
║           Addarr Installer            ║
║     Media Management Telegram Bot     ║
╚═══════════════════════════════════════╝${NC}"
# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check Python version
check_python_version() {
    if command_exists python3; then
        PYTHON_CMD="python3"
    elif command_exists python; then
        PYTHON_CMD="python"
    else
        return 1
    fi

    PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')

    # Simple version comparison - convert to comparable numbers
    current_ver=$(echo "$PYTHON_VERSION" | sed 's/\.//g')
    min_ver=$(echo "$MIN_PYTHON_VERSION" | sed 's/\.//g')

    if [ "$current_ver" -ge "$min_ver" ]; then
        echo -e "${GREEN}✓ Python $PYTHON_VERSION detected${NC}"
        return 0
    else
        echo -e "${RED}✗ Python $PYTHON_VERSION detected, but version $MIN_PYTHON_VERSION or higher is required${NC}"
        return 1
    fi
}

# Function to check pip version
check_pip_version() {
    local pip_cmd
    if command -v pip3 >/dev/null 2>&1; then
        pip_cmd="pip3"
    elif command -v pip >/dev/null 2>&1; then
        pip_cmd="pip"
    else
        echo -e "${RED}✗ pip not found${NC}"
        return 1
    fi

    local pip_version=$($pip_cmd --version | awk '{print $2}')
    local current_ver=$(echo "$pip_version" | sed 's/\.//g')
    local min_ver=$(echo "$MIN_PIP_VERSION" | sed 's/\.//g')

    if [ "$current_ver" -ge "$min_ver" ]; then
        echo -e "${GREEN}✓ pip $pip_version detected${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️ pip $pip_version detected, version $MIN_PIP_VERSION or higher recommended${NC}"
        return 1
    fi
}

# Check for Python installation
if ! check_python_version; then
    echo -e "${YELLOW}Python $MIN_PYTHON_VERSION or higher is required but not found.${NC}"
    echo -e "Please install Python using one of these methods:\n"

    case "$(uname -s)" in
    Linux*)
        echo "For Debian/Ubuntu:"
        echo "  sudo apt update"
        echo "  sudo apt install python3 python3-pip"
        echo -e "\nFor Fedora:"
        echo "  sudo dnf install python3 python3-pip"
        echo -e "\nFor Arch Linux:"
        echo "  sudo pacman -S python python-pip"
        ;;
    Darwin*)
        echo "Using Homebrew:"
        echo "  brew install python"
        echo -e "\nOr download from:"
        echo "  https://www.python.org/downloads/"
        ;;
    MINGW* | CYGWIN* | MSYS*)
        echo "Download the installer from:"
        echo "  https://www.python.org/downloads/"
        echo -e "\nOr using winget:"
        echo "  winget install Python.Python.3"
        ;;
    esac

    echo -e "\n${YELLOW}Please install Python and run this script again.${NC}"
    exit 1
fi

# Install pip if not present
if ! command -v pip >/dev/null 2>&1 && ! command -v pip3 >/dev/null 2>&1; then
    echo -e "${YELLOW}Installing pip...${NC}"
    case "$(uname -s)" in
    Linux*)
        if command -v apt-get >/dev/null 2>&1; then
            sudo apt-get update
            sudo apt-get install -y python3-pip
        elif command -v dnf >/dev/null 2>&1; then
            sudo dnf install -y python3-pip
        elif command -v pacman >/dev/null 2>&1; then
            sudo pacman -S python-pip
        else
            echo -e "${RED}Unable to install pip. Please install pip manually.${NC}"
            exit 1
        fi
        ;;
    Darwin*)
        if command -v brew >/dev/null 2>&1; then
            brew install python
        else
            echo -e "${RED}Please install Homebrew first: https://brew.sh${NC}"
            exit 1
        fi
        ;;
    esac
fi

# Configuration
INSTALL_TIMEOUT=120 # 2 minutes timeout for installations
UPGRADE_TIMEOUT=120 # 2 minutes timeout for upgrades

# Function to run command with timeout and fallback
run_with_timeout() {
    local command="$1"
    local timeout_duration="$2"
    local description="$3"
    local hide_output="$4" # true/false for hiding output

    echo -ne "${BLUE}${description}...${NC}"

    if [ "$hide_output" = true ]; then
        # First try: With hidden output
        if timeout $timeout_duration $command >/dev/null 2>&1; then
            echo -e "${GREEN}✓${NC}"
            return 0
        else
            # If failed, retry with visible output
            echo -e "${YELLOW}\nRetrying...${NC}"
            if timeout $timeout_duration $command; then
                echo -e "${GREEN}✓${NC}"
                return 0
            else
                echo -e "${RED}✗${NC}"
                return 1
            fi
        fi
    else
        # Run with visible output from the start
        if timeout $timeout_duration $command; then
            echo -e "${GREEN}✓${NC}"
            return 0
        else
            echo -e "${RED}✗${NC}"
            return 1
        fi
    fi
}

# Check pip version and only upgrade if needed
if ! check_pip_version; then
    if [ "$SKIP_PIP_UPGRADE" != "true" ]; then
        echo -e "${YELLOW}Would you like to upgrade pip? [y/N]${NC}"
        read -r response
        if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
            if ! run_with_timeout "pip install --upgrade pip" $UPGRADE_TIMEOUT "Upgrading pip" true; then
                echo -e "${RED}Failed to upgrade pip. Try continuing with current version...${NC}"
            fi
        else
            echo -e "${BLUE}Skipping pip upgrade${NC}"
        fi
    fi
else
    echo -e "${BLUE}pip version is up to date${NC}"
fi

# Function to check if git is installed
check_git() {
    if ! command -v git >/dev/null 2>&1; then
        echo -e "${YELLOW}Git is not installed. Installing git...${NC}"
        case "$(get_system_info)" in
            "ubuntu"|"debian")
                sudo apt-get update && sudo apt-get install -y git
                ;;
            "fedora")
                sudo dnf install -y git
                ;;
            "rhel"|"centos")
                sudo yum install -y git
                ;;
            "arch")
                sudo pacman -S --noconfirm git
                ;;
            "macos")
                if command -v brew >/dev/null 2>&1; then
                    brew install git
                else
                    echo -e "${RED}Homebrew is required for macOS installation.${NC}"
                    echo -e "Install from: https://brew.sh"
                    exit 1
                fi
                ;;
            *)
                echo -e "${RED}Please install git manually and try again${NC}"
                exit 1
                ;;
        esac
    fi
}

# Check and install git if needed
check_git

# Create installation directory if it doesn't exist
INSTALL_DIR="$HOME/.addarr"
echo -e "\n${BLUE}Installing Addarr to: $INSTALL_DIR${NC}"

if [ -d "$INSTALL_DIR" ]; then
    # Check if it's a valid installation
    if [ ! -f "$INSTALL_DIR/run.py" ]; then
        echo -e "${YELLOW}Warning: Existing directory doesn't seem to be a valid Addarr installation${NC}"
    fi
    echo -e "${YELLOW}Installation directory already exists. Creating backup...${NC}"
    BACKUP_DIR="$INSTALL_DIR.backup.$(date +%Y%m%d_%H%M%S)"
    if ! mv "$INSTALL_DIR" "$BACKUP_DIR"; then
        echo -e "${RED}Failed to create backup${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Backup created at: $BACKUP_DIR${NC}"
fi

# Clone repository with progress
echo -e "\n${BLUE}Cloning Addarr repository...${NC}"
if ! git clone --progress https://github.com/Cyneric/Addarr.git "$INSTALL_DIR" 2>&1 | while read -r line; do
    echo -ne "\r\033[K${BLUE}Progress: ${NC}$line"
done; then
    echo -e "\n${RED}Failed to clone repository${NC}"
    exit 1
fi
echo -e "\n${GREEN}✓ Repository cloned successfully${NC}"

# Create necessary directories
echo -e "\n${BLUE}Creating directory structure...${NC}"
progress "Creating logs directory" "mkdir -p $INSTALL_DIR/logs"
progress "Creating data directory" "mkdir -p $INSTALL_DIR/data"
progress "Creating backup directory" "mkdir -p $INSTALL_DIR/backup"

# Create command shortcut
SHORTCUT_DIR="$HOME/.local/bin"
mkdir -p "$SHORTCUT_DIR"

echo -e "\n${BLUE}Creating command shortcut...${NC}"
cat > "$SHORTCUT_DIR/addarr" << 'EOF'
#!/bin/bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
INSTALL_DIR="$HOME/.addarr"
source "$INSTALL_DIR/venv/bin/activate"
cd "$INSTALL_DIR"
python run.py "$@"
EOF

chmod +x "$SHORTCUT_DIR/addarr"

# Add to PATH if needed
if [[ ":$PATH:" != *":$SHORTCUT_DIR:"* ]]; then
    echo -e "\n${YELLOW}Adding $SHORTCUT_DIR to PATH...${NC}"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >>"$HOME/.bashrc"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >>"$HOME/.profile"
fi

echo -e "\n${GREEN}Installation completed!${NC}"
echo -e "\n${BLUE}Starting setup wizard...${NC}"

# Determine the correct Python command
get_python_cmd() {
    if command -v python3 >/dev/null 2>&1; then
        echo "python3"
    elif command -v python >/dev/null 2>&1; then
        echo "python"
    else
        echo ""
    fi
}

# Determine the correct pip command
get_pip_cmd() {
    if command -v pip3 >/dev/null 2>&1; then
        echo "pip3"
    elif command -v pip >/dev/null 2>&1; then
        echo "pip"
    else
        echo ""
    fi
}

# Get system information
get_system_info() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "$ID"
    elif [ -f /etc/debian_version ]; then
        echo "debian"
    elif [ -f /etc/redhat-release ]; then
        echo "rhel"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    else
        echo "unknown"
    fi
}

# Install Python if needed
install_python() {
    local system=$(get_system_info)

    case "$system" in
    "ubuntu" | "debian")
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip
        ;;
    "fedora")
        sudo dnf install -y python3 python3-pip
        ;;
    "rhel" | "centos")
        sudo yum install -y python3 python3-pip
        ;;
    "arch")
        sudo pacman -S --noconfirm python python-pip
        ;;
    "macos")
        if ! command -v brew >/dev/null 2>&1; then
            echo -e "${RED}Homebrew is required for macOS installation.${NC}"
            echo -e "Install from: https://brew.sh"
            exit 1
        fi
        brew install python
        ;;
    *)
        echo -e "${RED}Unsupported system: $system${NC}"
        echo -e "Please install Python 3.8+ manually and try again."
        exit 1
        ;;
    esac
}

# Get Python command
PYTHON_CMD=$(get_python_cmd)
if [ -z "$PYTHON_CMD" ]; then
    echo -e "${YELLOW}Python not found. Attempting to install...${NC}"
    install_python
    PYTHON_CMD=$(get_python_cmd)
    if [ -z "$PYTHON_CMD" ]; then
        echo -e "${RED}Failed to install Python. Please install Python 3.8+ manually and try again.${NC}"
        exit 1
    fi
fi

# Create and activate virtual environment
echo -e "\n${BLUE}Creating virtual environment...${NC}"
if ! $PYTHON_CMD -m venv "$INSTALL_DIR/venv"; then
    echo -e "${RED}Failed to create virtual environment. Please install python3-venv:${NC}"
    echo "sudo apt install python3-venv"
    exit 1
fi

# Activate virtual environment
if ! source "$INSTALL_DIR/venv/bin/activate"; then
    echo -e "${RED}Failed to activate virtual environment${NC}"
    exit 1
fi

# Update pip in virtual environment
echo -e "\n${BLUE}Updating pip in virtual environment...${NC}"
if ! "$INSTALL_DIR/venv/bin/pip" install --upgrade pip; then
    echo -e "${RED}Failed to upgrade pip in virtual environment${NC}"
    exit 1
fi

# Install requirements
echo -e "\n${BLUE}Installing dependencies...${NC}"
if ! "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"; then
    echo -e "${RED}Failed to install dependencies${NC}"
    exit 1
fi

# Installation Summary
echo -e "\n${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         Installation Complete! 🎉     ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}\n"

echo -e "${BLUE}📂 Installation Details:${NC}"
echo -e "   • Installation Directory: ${GREEN}$INSTALL_DIR${NC}"
echo -e "   • Command Location: ${GREEN}$SHORTCUT_DIR/addarr${NC}"
echo -e "   • Config File: ${GREEN}$INSTALL_DIR/config.yaml${NC}"
echo -e "   • Log Directory: ${GREEN}$INSTALL_DIR/logs${NC}"

echo -e "\n${BLUE}🚀 Next Steps:${NC}"
echo -e "   1. Start Addarr: ${YELLOW}addarr${NC} (on first run, setup wizard will start automatically)"
echo -e "   2. Stop Addarr: ${YELLOW}Ctrl+C${NC}"

echo -e "\n${BLUE}📚 Documentation:${NC}"
echo -e "   • GitHub Wiki: ${YELLOW}https://github.com/cyneric/addarr/wiki${NC}"
echo -e "   • Report Issues: ${YELLOW}https://github.com/cyneric/addarr/issues${NC}"

echo -e "\n${BLUE}💡 Quick Tips:${NC}"
echo -e "   • Run setup wizard again: ${YELLOW}addarr --setup${NC}"
echo -e "   • Check configuration: ${YELLOW}addarr --check${NC}"
echo -e "   • Backup configuration: ${YELLOW}addarr --backup${NC}"
echo -e "   • Edit config: ${YELLOW}nano $INSTALL_DIR/config.yaml${NC}"

# Add note about PATH if it was modified
if [[ ":$PATH:" != *":$SHORTCUT_DIR:"* ]]; then
    echo -e "${YELLOW}NOTE: Please restart your terminal or run:${NC}"
    echo -e "${YELLOW}source ~/.bashrc${NC}"
    echo -e "${YELLOW}to use the 'addarr' command.${NC}\n"
fi

cleanup() {
    # If installation failed, restore backup if it exists
    if [ "$1" = "error" ] && [ -d "$BACKUP_DIR" ]; then
        echo -e "${YELLOW}Restoring backup...${NC}"
        rm -rf "$INSTALL_DIR"
        mv "$BACKUP_DIR" "$INSTALL_DIR"
    fi
}

# Add trap
trap 'cleanup error' ERR
trap cleanup EXIT
