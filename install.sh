#!/bin/bash
# Filename: install.sh
# Author: Christian Blank (https://github.com/cyneric)
# Created Date: 2024-11-08
# Description: Bash installer script for Addarr, a Media Management Telegram Bot.
# License: MIT

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}
╔═══════════════════════════════════════╗
║           Addarr Installer            ║
║     Media Management Telegram Bot     ║
╚═══════════════════════════════════════╝${NC}"

# Check for required commands
check_command() {
    if ! command -v "$1" &>/dev/null; then
        echo -e "${RED}Error: $1 is required but not installed.${NC}"
        echo -e "Please install $1 and try again."
        exit 1
    fi
}

check_command "python3"
check_command "pip3"
check_command "git"

# Create installation directory
INSTALL_DIR="$HOME/.addarr"
echo -e "\n${YELLOW}Installing Addarr to: ${INSTALL_DIR}${NC}"

if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}Installation directory already exists. Backing up...${NC}"
    mv "$INSTALL_DIR" "${INSTALL_DIR}.backup.$(date +%Y%m%d_%H%M%S)"
fi

# Clone repository
echo -e "\n${BLUE}Cloning repository...${NC}"
git clone https://github.com/cyneric/addarr.git "$INSTALL_DIR"

if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to clone repository${NC}"
    exit 1
fi

# Create virtual environment
echo -e "\n${BLUE}Creating virtual environment...${NC}"
cd "$INSTALL_DIR"
python3 -m venv venv

# Activate virtual environment and install dependencies
echo -e "\n${BLUE}Installing dependencies...${NC}"
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to install dependencies${NC}"
    exit 1
fi

# Create launcher script
LAUNCHER="$HOME/.local/bin/addarr"
mkdir -p "$(dirname "$LAUNCHER")"

cat >"$LAUNCHER" <<'EOF'
#!/bin/bash
ADDARR_DIR="$HOME/.addarr"
source "$ADDARR_DIR/venv/bin/activate"
python "$ADDARR_DIR/run.py" "$@"
EOF

chmod +x "$LAUNCHER"

# Add to PATH if needed
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >>"$HOME/.bashrc"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >>"$HOME/.zshrc" 2>/dev/null || true
fi

# Ask about systemd service installation
if command -v systemctl &>/dev/null; then
    echo -e "\n${YELLOW}Would you like to install Addarr as a system service? [y/N]${NC}"
    read -r install_service

    if [[ "$install_service" =~ ^[Yy]$ ]]; then
        # Create systemd service file
        SERVICE_FILE="$HOME/.config/systemd/user/addarr.service"
        mkdir -p "$(dirname "$SERVICE_FILE")"

        cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Addarr Telegram Bot
After=network.target

[Service]
Type=simple
ExecStart=$LAUNCHER
Restart=always
RestartSec=10
Environment=PATH=$PATH
WorkingDirectory=$INSTALL_DIR

[Install]
WantedBy=default.target
EOF

        # Reload systemd
        systemctl --user daemon-reload

        # Ask about starting at boot
        echo -e "\n${YELLOW}Would you like Addarr to start automatically at boot? [y/N]${NC}"
        read -r start_boot

        if [[ "$start_boot" =~ ^[Yy]$ ]]; then
            # Enable service and lingering for user
            systemctl --user enable addarr.service
            loginctl enable-linger "$USER"
            echo -e "${GREEN}✓ Addarr will start automatically at boot${NC}"
        fi

        # Ask about starting the service now
        echo -e "\n${YELLOW}Would you like to start Addarr now? [y/N]${NC}"
        read -r start_now

        if [[ "$start_now" =~ ^[Yy]$ ]]; then
            systemctl --user start addarr.service
            echo -e "${GREEN}✓ Addarr service started${NC}"
            echo -e "\n${BLUE}You can manage the service with:${NC}"
            echo -e "systemctl --user status addarr"
            echo -e "systemctl --user start addarr"
            echo -e "systemctl --user stop addarr"
            echo -e "systemctl --user restart addarr"
        fi
    fi
fi

echo -e "\n${GREEN}Installation complete!${NC}"
echo -e "\n${YELLOW}To get started:${NC}"
echo -e "1. Run initial setup:${BLUE} addarr --setup${NC}"
if [[ ! "$install_service" =~ ^[Yy]$ ]]; then
    echo -e "2. Start the bot:${BLUE} addarr${NC}"
fi
echo -e "\nFor more information, visit: ${BLUE}https://github.com/cyneric/addarr/wiki${NC}"
