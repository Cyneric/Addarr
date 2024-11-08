"""
Filename: settings.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Configuration management module.

This module handles loading and validating the application configuration
from YAML files. It provides access to configuration values and ensures
all required settings are present and valid.
"""

import os
import yaml
import questionary
from typing import Dict, Any, List
from colorama import Fore, Style
from pathlib import Path

from ..definitions import CONFIG_PATH, CONFIG_EXAMPLE_PATH
from ..utils.backup import create_backup

class ConfigurationError(Exception):
    """Base class for configuration errors"""
    pass

class Config:
    """Configuration management class"""
    
    def __init__(self):
        self._config = self._load_config()
        self._validate_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        if not os.path.exists(CONFIG_PATH):
            raise ConfigurationError(f"Configuration file not found: {CONFIG_PATH}")
            
        with open(CONFIG_PATH, 'r') as f:
            return yaml.safe_load(f)
            
    def _validate_config(self):
        """Validate configuration against example config"""
        with open(CONFIG_EXAMPLE_PATH, 'r') as f:
            example_config = yaml.safe_load(f)
            
        missing_keys = self._get_missing_keys(example_config, self._config)
        if missing_keys:
            print(f"\n{Fore.YELLOW}Missing configuration keys detected: {', '.join(missing_keys)}")
            if questionary.confirm("Would you like to configure these settings now?").ask():
                # Create backup before modifying
                create_backup()
                
                for key in missing_keys:
                    self._configure_missing_key(key)
                
                # Save updated configuration
                with open(CONFIG_PATH, 'w') as f:
                    yaml.dump(self._config, f, default_flow_style=False)
                    
                print(f"{Fore.GREEN}✅ Configuration updated successfully!")
            else:
                raise ConfigurationError(
                    f"Missing required configuration keys: {', '.join(missing_keys)}"
                )
            
        self._validate_values()
        
    def _configure_missing_key(self, key: str):
        """Configure a missing configuration key"""
        parts = key.split('.')
        current = self._config
        
        # Build up the configuration path
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
            
        # Handle specific configuration types
        if key.endswith('.enable'):
            value = questionary.confirm(
                f"Enable {parts[0].title()}?",
                default=False
            ).ask()
        elif key.endswith('.apikey'):
            value = questionary.password(
                f"Enter {parts[0].title()} API key:"
            ).ask()
        elif key.endswith('.token'):
            value = questionary.password(
                f"Enter {parts[0].title()} token:"
            ).ask()
        else:
            # Default to text input
            value = questionary.text(
                f"Enter value for {key}:"
            ).ask()
            
        # Set the value
        current[parts[-1]] = value
        
    def _validate_values(self):
        """Validate configuration values"""
        # Validate language
        valid_languages = [
            "de-de", "en-us", "es-es", "fr-fr", 
            "it-it", "nl-be", "pl-pl", "pt-pt", "ru-ru"
        ]
        if self._config.get("language") not in valid_languages:
            raise ConfigurationError(
                f"Invalid language. Must be one of: {', '.join(valid_languages)}"
            )
            
        # Add other validation as needed...
        
    def _get_missing_keys(self, example: Dict, config: Dict, prefix="") -> List[str]:
        """Recursively find missing configuration keys"""
        missing = []
        for key, value in example.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if key not in config:
                missing.append(full_key)
            elif isinstance(value, dict):
                missing.extend(
                    self._get_missing_keys(value, config[key], full_key)
                )
        return missing
        
    def __getitem__(self, key):
        return self._config[key]
        
    def get(self, key, default=None):
        return self._config.get(key, default)

# Create global config instance
config = Config() 