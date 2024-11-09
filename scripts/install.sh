#!/bin/bash

# Filename: install.sh
# Author: Christian Blank (https://github.com/cyneric)
# Created Date: 2024-11-08
# Description: Bash installer script for Addarr.
# License: MIT

# ANSI color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Minimum required Python version
MIN_PYTHON_VERSION="3.8"

echo -e "${BLUE}
╔═══════════════════════════════════════╗
║           Addarr Installer            ║
║     Media Management Telegram Bot     ║
╚═══════════════════════════════════════╝${NC}"
# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to compare version numbers
version_compare() {
    # $1 is current version, $2 is minimum required version
    printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1 | grep -q "^$2$"
    return $?
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
    if version_compare "$PYTHON_VERSION" "$MIN_PYTHON_VERSION"; then
        echo -e "${GREEN}✓ Python $PYTHON_VERSION detected${NC}"
        return 0
    else
        echo -e "${RED}✗ Python $PYTHON_VERSION detected, but version $MIN_PYTHON_VERSION or higher is required${NC}"
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
        echo "  sudo apt install python3 python3-pip python3-venv"
        echo -e "\nFor Fedora:"
        echo "  sudo dnf install python3 python3-pip python3-venv"
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

# Check for pip
if ! command_exists pip3 && ! command_exists pip; then
    echo -e "${RED}✗ pip not found${NC}"
    echo -e "${YELLOW}Installing pip...${NC}"

    case "$(uname -s)" in
    Linux*)
        sudo apt update && sudo apt install python3-pip ||
            sudo dnf install python3-pip ||
            sudo pacman -S python-pip
        ;;
    Darwin*)
        curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
        python3 get-pip.py
        rm get-pip.py
        ;;
    *)
        echo -e "${RED}Please install pip manually and run this script again.${NC}"
        exit 1
        ;;
    esac
fi

# Check for venv module
if ! $PYTHON_CMD -c "import venv" 2>/dev/null; then
    echo -e "${RED}✗ venv module not found${NC}"
    echo -e "${YELLOW}Installing venv...${NC}"

    case "$(uname -s)" in
    Linux*)
        sudo apt update && sudo apt install python3-venv ||
            sudo dnf install python3-venv ||
            sudo pacman -S python-virtualenv
        ;;
    *)
        echo -e "${RED}Please install the venv module manually and run this script again.${NC}"
        exit 1
        ;;
    esac
fi

# Create virtual environment
echo -e "\n${BLUE}Creating virtual environment...${NC}"
$PYTHON_CMD -m venv venv

# Activate virtual environment
echo -e "${BLUE}Activating virtual environment...${NC}"
source venv/bin/activate || {
    echo -e "${RED}Failed to activate virtual environment${NC}"
    exit 1
}

# Upgrade pip
echo -e "${BLUE}Upgrading pip...${NC}"
pip install --upgrade pip

# Install requirements
echo -e "${BLUE}Installing requirements...${NC}"
pip install -r requirements.txt

# Create necessary directories
echo -e "${BLUE}Creating necessary directories...${NC}"
mkdir -p logs
mkdir -p data
mkdir -p backup

# Check if config.yaml exists
if [ ! -f config.yaml ]; then
    echo -e "${YELLOW}No config.yaml found. Creating from example...${NC}"
    if [ -f config_example.yaml ]; then
        cp config_example.yaml config.yaml
        echo -e "${GREEN}✓ Created config.yaml${NC}"
        echo -e "${YELLOW}Please edit config.yaml with your settings${NC}"
    else
        echo -e "${RED}✗ config_example.yaml not found${NC}"
    fi
fi

echo -e "\n${GREEN}Installation completed!${NC}"
echo -e "\nTo start Addarr:"
echo -e "1. Activate the virtual environment:"
echo -e "   ${BLUE}source venv/bin/activate${NC}"
echo -e "2. Run the setup wizard:"
echo -e "   ${BLUE}python run.py --setup${NC}"
echo -e "3. Start the bot:"
echo -e "   ${BLUE}python run.py${NC}"
echo -e "\n${YELLOW}For more information, visit: https://github.com/cyneric/addarr/wiki${NC}"
