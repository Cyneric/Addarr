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

# XDG Base Directory paths
XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
XDG_BIN_HOME="$HOME/.local/bin"

# Application directories
APP_DATA_DIR="$XDG_DATA_HOME/addarr"
APP_CONFIG_DIR="$XDG_CONFIG_HOME/addarr"
APP_CACHE_DIR="$XDG_CACHE_HOME/addarr"

# Source directory (where the script is running from)
if [ -n "${BASH_SOURCE[0]}" ]; then
    SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
else
    # When script is piped to bash, try to download files directly
    SOURCE_DIR=$(mktemp -d)
    echo -e "${BLUE}Downloading Addarr files...${NC}"
    echo -e "${BLUE}Using temporary directory: $SOURCE_DIR${NC}"

    # Function to download a file with error checking
    download_file() {
        local url="$1"
        local output="$2"
        echo -e "${BLUE}Downloading: $url${NC}"

        # Try curl first with strict SSL
        if curl -sfL "$url" -o "$output"; then
            echo -e "${GREEN}Successfully downloaded: $output${NC}"
            return 0
        fi

        # If curl fails, try with insecure option (not recommended but might help diagnose the issue)
        echo -e "${YELLOW}First attempt failed, trying alternate method...${NC}"
        if curl -sfLk "$url" -o "$output"; then
            echo -e "${GREEN}Successfully downloaded: $output (using relaxed SSL)${NC}"
            return 0
        fi

        # If curl still fails, try wget as a fallback
        echo -e "${YELLOW}Curl failed, trying wget...${NC}"
        if wget --quiet "$url" -O "$output"; then
            echo -e "${GREEN}Successfully downloaded: $output (using wget)${NC}"
            return 0
        fi

        # If all methods fail, show detailed error information
        echo -e "${RED}Failed to download: $url${NC}"
        echo -e "${RED}Curl Status: $(curl -s -o /dev/null -w "%{http_code}" "$url")${NC}"
        echo -e "${RED}Curl Error: $(curl -sS "$url" 2>&1)${NC}"
        return 1
    }

    # Create directories
    mkdir -p "$SOURCE_DIR/src"

    # Download files with error checking
    files_to_download=(
        "https://raw.githubusercontent.com/cyneric/addarr/main/requirements.txt:$SOURCE_DIR/requirements.txt"
        "https://raw.githubusercontent.com/cyneric/addarr/main/src/run.py:$SOURCE_DIR/src/run.py"
        "https://raw.githubusercontent.com/cyneric/addarr/main/config_example.yaml:$SOURCE_DIR/config_example.yaml"
    )

    download_failed=0
    for file_pair in "${files_to_download[@]}"; do
        url="${file_pair%%:*}"
        output="${file_pair#*:}"
        if ! download_file "$url" "$output"; then
            download_failed=1
        fi
    done

    if [ $download_failed -eq 1 ]; then
        echo -e "${RED}One or more files failed to download${NC}"
        echo -e "${YELLOW}Cleaning up temporary directory: $SOURCE_DIR${NC}"
        rm -rf "$SOURCE_DIR"
        exit 1
    fi

    echo -e "${BLUE}Directory contents:${NC}"
    ls -R "$SOURCE_DIR"
fi

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
    local pip_version=$(pip --version | awk '{print $2}')
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

    # Remove surrounding quotes but preserve internal quotes
    command=$(echo "$command" | sed 's/^"\(.*\)"$/\1/')

    if [ "$hide_output" = true ]; then
        # First try: With hidden output
        if timeout $timeout_duration bash -c "$command" >/dev/null 2>&1; then
            echo -e "${GREEN}✓${NC}"
            return 0
        else
            # If failed, retry with visible output
            echo -e "${YELLOW}\nRetrying...${NC}"
            if timeout $timeout_duration bash -c "$command"; then
                echo -e "${GREEN}✓${NC}"
                return 0
            else
                echo -e "${RED}✗${NC}"
                return 1
            fi
        fi
    else
        # Run with visible output from the start
        if timeout $timeout_duration bash -c "$command"; then
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

# Function to check and update PATH
check_path() {
    if [[ ":$PATH:" != *":$XDG_BIN_HOME:"* ]]; then
        echo -e "${YELLOW}Warning: $XDG_BIN_HOME is not in your PATH${NC}"
        echo -e "Add the following line to your ~/.bashrc or ~/.zshrc:"
        echo -e "${BLUE}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
        return 1
    fi
    return 0
}

# Function to create XDG directories
create_xdg_dirs() {
    echo -e "\n${BLUE}Creating directory structure...${NC}"
    progress "Creating data directory" "mkdir -p \"$APP_DATA_DIR\""
    progress "Creating config directory" "mkdir -p \"$APP_CONFIG_DIR\""
    progress "Creating cache directory" "mkdir -p \"$APP_CACHE_DIR\""
    progress "Creating bin directory" "mkdir -p \"$XDG_BIN_HOME\""
}

# Function to install application files
install_app_files() {
    echo -e "\n${BLUE}Installing Addarr...${NC}"

    # Create src directory if it doesn't exist
    mkdir -p "$APP_DATA_DIR/src"

    # Copy application files
    progress "Copying application files" "cp -r \"$SOURCE_DIR/src\"/* \"$APP_DATA_DIR/src/\""
    progress "Copying requirements.txt" "cp \"$SOURCE_DIR/requirements.txt\" \"$APP_DATA_DIR/\""

    # Create run script
    cat >"$XDG_BIN_HOME/addarr" <<EOF
#!/bin/bash
cd "$APP_DATA_DIR"
PYTHONPATH="$APP_DATA_DIR" python3 "$APP_DATA_DIR/src/run.py" "\$@"
EOF
    progress "Setting executable permissions" "chmod +x \"$XDG_BIN_HOME/addarr\""
}

# Function to handle configuration
setup_configuration() {
    if [ ! -f "$APP_CONFIG_DIR/config.yaml" ]; then
        echo -e "\n${YELLOW}No config.yaml found. Creating from example...${NC}"
        if [ -f "$SOURCE_DIR/config_example.yaml" ]; then
            progress "Creating config.yaml" "cp \"$SOURCE_DIR/config_example.yaml\" \"$APP_CONFIG_DIR/config.yaml\""
            echo -e "${GREEN}✓ Created config.yaml${NC}"
            echo -e "${YELLOW}Please edit $APP_CONFIG_DIR/config.yaml with your settings${NC}"
        else
            echo -e "${RED}✗ config_example.yaml not found at $SOURCE_DIR/config_example.yaml${NC}"
            return 1
        fi
    fi
}

# Check for required tools
check_required_tools() {
    local missing_tools=()

    if ! command -v curl >/dev/null && ! command -v wget >/dev/null; then
        missing_tools+=("curl or wget")
    fi

    if [ ${#missing_tools[@]} -ne 0 ]; then
        echo -e "${RED}Error: Required tools are missing: ${missing_tools[*]}${NC}"
        echo -e "${YELLOW}Please install the missing tools and try again.${NC}"
        echo -e "On Ubuntu/Debian: sudo apt-get install curl wget"
        echo -e "On Fedora: sudo dnf install curl wget"
        exit 1
    fi
}

# Call the check near the start of the script
check_required_tools

# Main installation process
echo -e "${BLUE}"
echo "======================================"
echo "          Addarr Installer            "
echo "    Media Management Telegram Bot     "
echo "======================================"
echo -e "${NC}"

# Check Python and pip versions (keep existing checks)
# [Previous version checking code remains unchanged]

# Create XDG directories
create_xdg_dirs

# Install requirements
echo -e "\n${BLUE}Installing dependencies...${NC}"
if [ ! -f "$SOURCE_DIR/requirements.txt" ]; then
    echo -e "${RED}Error: requirements.txt not found at $SOURCE_DIR/requirements.txt${NC}"
    exit 1
fi

# Updated command without quotes around the path
if ! run_with_timeout "pip install --user -r \"$SOURCE_DIR/requirements.txt\"" $INSTALL_TIMEOUT "Installing required packages" true; then
    echo -e "${RED}Failed to install some dependencies. Please check the output above.${NC}"
    echo -e "${YELLOW}Would you like to retry with more detailed console output? [Y/n]${NC}"
    read -r response
    if [[ ! "$response" =~ ^([nN][oO]|[nN])$ ]]; then
        run_with_timeout "pip install --user -r \"$SOURCE_DIR/requirements.txt\"" $INSTALL_TIMEOUT "Retrying installation" false
    fi
fi

# Install application files
install_app_files

# Setup configuration
setup_configuration

# Check PATH
check_path

echo -e "\n${GREEN}Installation completed successfully!${NC}"
echo -e "\n${YELLOW}Installation locations:${NC}"
echo -e "Application files: ${BLUE}$APP_DATA_DIR${NC}"
echo -e "Configuration:     ${BLUE}$APP_CONFIG_DIR${NC}"
echo -e "Cache:            ${BLUE}$APP_CACHE_DIR${NC}"
echo -e "Command:          ${BLUE}$XDG_BIN_HOME/addarr${NC}"

echo -e "\n${YELLOW}Next steps:${NC}"
echo -e "1. Run the setup wizard to configure Addarr:"
echo -e "   ${BLUE}addarr --setup${NC}"
echo -e "2. Start the bot:"
echo -e "   ${BLUE}addarr${NC}"

if ! check_path; then
    echo -e "\n${YELLOW}Note: After updating your PATH, you'll need to restart your terminal${NC}"
fi

echo -e "\n${YELLOW}For more information, visit:${NC}"
echo -e "${BLUE}https://github.com/cyneric/addarr/wiki${NC}"
