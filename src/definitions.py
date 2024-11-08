"""
Filename: definitions.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Project path definitions module.

This module defines all the important paths used throughout the application,
including paths for configuration files, logs, translations, and user data.
It also defines default settings for the application configuration.
"""

import os
from pathlib import Path
import yaml

# Set Projects Root Directory
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.normpath(__file__)))

# Set Projects Configuration path
CONFIG_PATH = os.path.join(ROOT_DIR, "config.yaml")
CONFIG_EXAMPLE_PATH = os.path.join(ROOT_DIR, "config_example.yaml")
TRANSLATIONS_PATH = os.path.join(ROOT_DIR, "translations")
LANG_PATH = os.path.join(ROOT_DIR, "translations/")
CHATID_PATH = os.path.join(ROOT_DIR, "chatid.txt")
LOG_PATH = os.path.join(ROOT_DIR, "logs", "addarr.log")
ERROR_LOG_PATH = os.path.join(ROOT_DIR, "logs", "error.log")
ADMIN_PATH = os.path.join(ROOT_DIR, "admin.txt")
ALLOWLIST_PATH = os.path.join(ROOT_DIR, "allowlist.txt")

# Data directory for persistent storage
DATA_PATH = os.path.join(ROOT_DIR, "data")

# Default configuration settings
DEFAULT_SETTINGS = {
    "entrypointAuth": "auth",      # auth or a custom entrypoint
    "entrypointAdd": "start",      # start or a custom entrypoint
    "entrypointDelete": "delete",  # delete or a custom entrypoint
    "entrypointAllSeries": "allSeries",  # allSeries or a custom entrypoint
    "entrypointAllMovies": "allMovies",  # allMovies or a custom entrypoint
    "entrypointAllMusic": "allMusic",    # allMusic or a custom entrypoint
    "entrypointTransmission": "transmission",  # transmission or a custom entrypoint
    "entrypointSabnzbd": "sabnzbd",      # sabnzbd or a custom entrypoint
    "logToConsole": True,
    "debugLogging": False,
    "language": "en-us",
    "transmission": { "enable": False },
    "enableAdmin": False
}

def load_config():
    config_path = Path("config.yaml")
    if not config_path.exists():
        raise FileNotFoundError("config.yaml not found. Please copy config_example.yaml to config.yaml and configure it.")
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def get_admins():
    """Get list of admin IDs from config"""
    config = load_config()
    return config.get('admins', [])

def get_allowed_users():
    """Get list of allowed user IDs from config"""
    config = load_config()
    return config.get('allow_list', [])

def get_allowed_chats():
    """Get list of allowed chat IDs from config"""
    config = load_config()
    return config.get('chat_id', [])

def is_admin(user_id: int) -> bool:
    """Check if user ID is an admin"""
    return user_id in get_admins()

def is_allowed_user(user_id: int) -> bool:
    """Check if user ID is allowed"""
    # If allowlist is disabled, all users are allowed
    config = load_config()
    if not config.get('security', {}).get('enableAllowlist', False):
        return True
    return user_id in get_allowed_users()

def is_allowed_chat(chat_id: int) -> bool:
    """Check if chat ID is allowed"""
    return chat_id in get_allowed_chats()
