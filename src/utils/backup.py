"""
Filename: backup.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Backup utility module.

This module provides backup functionality for Addarr configuration files.
"""

import os
import shutil
import datetime
from pathlib import Path
from colorama import Fore, Style
from typing import Optional

from src.definitions import CONFIG_PATH

def create_backup(source_path: str = CONFIG_PATH) -> Optional[str]:
    """Create a backup of a configuration file
    
    Args:
        source_path: Path to the file to backup (default: config.yaml)
        
    Returns:
        Optional[str]: Path to backup file if successful, None otherwise
    """
    if os.path.exists(source_path):
        try:
            # Create backup directory if it doesn't exist
            backup_dir = os.path.join(os.path.dirname(source_path), "backup")
            Path(backup_dir).mkdir(parents=True, exist_ok=True)
            
            # Generate timestamp for backup file
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.basename(source_path)
            backup_file = os.path.join(backup_dir, f"{filename.rsplit('.', 1)[0]}_{timestamp}.yaml")
            
            # Copy file to backup directory
            shutil.copy2(source_path, backup_file)
            
            # Only print once
            print(f"{Fore.GREEN}✅ Configuration backed up to: {backup_file}")
            
            return backup_file
            
        except Exception as e:
            error_msg = f"Error creating backup: {str(e)}"
            print(f"{Fore.RED}❌ {error_msg}")
            return None
    else:
        print(f"{Fore.YELLOW}⚠️ No configuration file found to backup.")
        return None

def restore_backup(backup_path: str) -> bool:
    """Restore a configuration from backup
    
    Args:
        backup_path: Path to the backup file to restore
        
    Returns:
        bool: True if restore was successful
    """
    try:
        if not os.path.exists(backup_path):
            print(f"{Fore.RED}❌ Backup file not found: {backup_path}")
            return False
            
        # Create backup of current config before restoring
        current_backup = create_backup()
        
        # Restore the backup
        shutil.copy2(backup_path, CONFIG_PATH)
        print(f"{Fore.GREEN}✅ Configuration restored from: {backup_path}")
        
        if current_backup:
            print(f"{Fore.YELLOW}ℹ️ Previous configuration backed up to: {current_backup}")
            
        return True
        
    except Exception as e:
        error_msg = f"Error restoring backup: {str(e)}"
        print(f"{Fore.RED}❌ {error_msg}")
        return False

def list_backups() -> list[str]:
    """List available configuration backups
    
    Returns:
        list[str]: List of backup file paths
    """
    backup_dir = os.path.join(os.path.dirname(CONFIG_PATH), "backup")
    if not os.path.exists(backup_dir):
        return []
        
    return sorted(
        [f for f in os.listdir(backup_dir) if f.endswith('.yaml')],
        reverse=True
    )