"""
Filename: config_handler.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Configuration file handler module.

This module handles all configuration file operations including:
- Creating new config from example
- Loading config while preserving comments
- Saving config while preserving formatting
- Backing up config files
"""

import os
import shutil
from datetime import datetime
from pathlib import Path
from ruamel.yaml import YAML
from typing import Any, Dict, List

# Initialize YAML handler
yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)

class ConfigHandler:
    """Handle configuration file operations"""
    
    def __init__(self, colors):
        self.colors = colors
        self.root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.config_path = os.path.join(self.root_dir, "config.yaml")
        self.config_example_path = os.path.join(self.root_dir, "config_example.yaml")
        
    def create_from_example(self) -> bool:
        """Create a new config.yaml from config_example.yaml
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create backup if config exists
            if os.path.exists(self.config_path):
                self.create_backup()
            
            # Copy example config while preserving formatting and comments
            shutil.copy2(self.config_example_path, self.config_path)
            print(f"{self.colors.Fore.GREEN}Created new config from example")
            return True
            
        except Exception as e:
            print(f"{self.colors.Fore.RED}Error creating config: {str(e)}")
            return False
            
    def create_backup(self) -> str:
        """Create a backup of current config
        
        Returns:
            str: Path to backup file
        """
        if os.path.exists(self.config_path):
            backup_dir = os.path.join(self.root_dir, "backup")
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"config_{timestamp}.yaml")
            shutil.copy2(self.config_path, backup_path)
            print(f"{self.colors.Fore.YELLOW}Created backup at: {backup_path}")
            return backup_path
        return ""
            
    def load_config(self) -> Dict[str, Any]:
        """Load config while preserving comments and structure"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.load(f)
        except Exception as e:
            print(f"{self.colors.Fore.RED}Error loading config: {e}")
            return {}
            
    def save_config(self, config: Dict[str, Any]) -> bool:
        """Save config while preserving formatting and comments
        
        Args:
            config: Configuration dictionary to save
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create backup before saving
            self.create_backup()
            
            # Save with preserved formatting
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f)
            return True
                
        except Exception as e:
            print(f"{self.colors.Fore.RED}Error saving configuration: {e}")
            return False
            
    def update_value(self, config: Dict[str, Any], path: List[str], value: Any) -> None:
        """Update a config value while preserving structure
        
        Args:
            config: Configuration dictionary to update
            path: List of nested keys to reach target
            value: New value to set
        """
        current = config
        for key in path[:-1]:
            current = current.setdefault(key, {})
        current[path[-1]] = value

# Create global instance (without colors - will be set by PreRunChecker)
config_handler = ConfigHandler(None) 