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

# Create installation directory
mkdir -p "$INSTALL_DIR"

# Function to format size in human-readable format
format_size() {
    local bytes=$1
    if [ $bytes -gt 1073741824 ]; then
        echo "$(awk "BEGIN {printf \"%.1f\", $bytes/1073741824}") GB"
    elif [ $bytes -gt 1048576 ]; then
        echo "$(awk "BEGIN {printf \"%.1f\", $bytes/1048576}") MB"
    elif [ $bytes -gt 1024 ]; then
        echo "$(awk "BEGIN {printf \"%.1f\", $bytes/1024}") KB"
    else
        echo "$bytes B"
    fi
}

# Function to download with progress bar
download_with_progress() {
    local url="$1"
    local output_file="$2"
    local title="$3"

    # Create a temporary file for progress output
    local tmp_progress="/tmp/curl_progress.$$"

    # Start curl in the background with progress to temp file
    (curl -L --progress-bar "$url" -o "$output_file" 2>"$tmp_progress") &
    local curl_pid=$!

    echo -e "${BLUE}${title}...${NC}"
    
    # Variables for progress calculation
    local downloaded=0
    local total_size=0
    local percentage=0
    local bar_size=40
    local progress_chars=""

    # Update progress while curl is running
    while kill -0 $curl_pid 2>/dev/null; do
        if [ -f "$tmp_progress" ]; then
            # Parse curl's progress output
            local curl_output=$(tail -n 1 "$tmp_progress")
            if [[ $curl_output =~ [0-9]+/([0-9]+) ]]; then
                downloaded=$(echo "$curl_output" | grep -o '[0-9]*' | head -1)
                total_size=$(echo "$curl_output" | grep -o '[0-9]*' | tail -1)
                
                if [ $total_size -gt 0 ]; then
                    percentage=$((downloaded * 100 / total_size))
                    filled_length=$((percentage * bar_size / 100))
                    unfilled_length=$((bar_size - filled_length))
                    
                    # Create progress bar
                    progress_chars=""
                    for ((i=0; i<filled_length; i++)); do progress_chars+="█"; done
                    for ((i=0; i<unfilled_length; i++)); do progress_chars+="░"; done
                    
                    # Clear line and show progress
                    echo -ne "\r\033[K"
                    echo -ne "${BLUE}Progress: ${NC}[${GREEN}${progress_chars}${NC}] "
                    echo -ne "${YELLOW}${percentage}%${NC} "
                    echo -ne "($(format_size $downloaded)/$(format_size $total_size))"
                fi
            fi
        fi
        sleep 0.1
    done

    # Wait for curl to finish and get its exit status
    wait $curl_pid
    local exit_status=$?

    # Clean up
    rm -f "$tmp_progress"

    # Final newline
    echo

    return $exit_status
}

# Replace the existing download section with this:
echo -e "\n${BLUE}Downloading Addarr...${NC}"
TMP_ZIP="/tmp/addarr.zip"
if ! download_with_progress "https://github.com/cyneric/addarr/archive/main.zip" "$TMP_ZIP" "Downloading repository"; then
    echo -e "${RED}Failed to download repository${NC}"
    exit 1
fi

echo -e "${BLUE}Extracting files...${NC}"
if ! unzip -o -q "$TMP_ZIP" -d "/tmp"; then
    echo -e "${RED}Failed to extract files${NC}"
    rm -f "$TMP_ZIP"
    exit 1
fi

# Find the correct directory name
EXTRACTED_DIR=$(find /tmp -maxdepth 1 -type d -name "Addarr-*" -print -quit)
if [ -z "$EXTRACTED_DIR" ]; then
    echo -e "${RED}Could not find extracted directory${NC}"
    rm -f "$TMP_ZIP"
    exit 1
fi

# Move files to installation directory (force overwrite)
echo -e "${BLUE}Installing files...${NC}"
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

if ! cp -rf "$EXTRACTED_DIR"/* "$INSTALL_DIR/"; then
    echo -e "${RED}Failed to copy files${NC}"
    rm -f "$TMP_ZIP"
    rm -rf "$EXTRACTED_DIR"
    exit 1
fi

# Copy hidden files (if any)
cp -rf "$EXTRACTED_DIR"/.[!.]* "$INSTALL_DIR/" 2>/dev/null || true

# Cleanup
rm -f "$TMP_ZIP"
rm -rf "$EXTRACTED_DIR"

# Verify requirements.txt exists
if [ ! -f "$INSTALL_DIR/requirements.txt" ]; then
    echo -e "${RED}Error: requirements.txt not found in installation directory${NC}"
    echo -e "${BLUE}Contents of $INSTALL_DIR:${NC}"
    ls -la "$INSTALL_DIR"
    exit 1
fi

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
    # Remove temporary files
    rm -f "$TMP_ZIP" 2>/dev/null
    rm -rf "$EXTRACTED_DIR" 2>/dev/null
    
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
