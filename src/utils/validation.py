"""
Validation and pre-run checks module.

This module handles all validation, including configuration checks,
dependency verification, and pre-run requirements.
"""

import sys
import os
import subprocess
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from colorama import Fore, Style
from .error_handler import ValidationError
from ..config.settings import config

def check_dependencies() -> bool:
    """Check if all required dependencies are installed"""
    required_packages = parse_requirements()
    if not required_packages:
        print(f"{Fore.RED}❌ No dependencies found in requirements.txt")
        return False
    
    # Get installed packages
    installed_packages = get_installed_packages()
    
    # Check which required packages are missing
    missing_packages = []
    for pkg in required_packages:
        pkg_lower = pkg.lower()
        pkg_underscore = pkg_lower.replace('-', '_')
        pkg_hyphen = pkg_lower.replace('_', '-')
        
        if not any(p in installed_packages for p in [pkg_lower, pkg_underscore, pkg_hyphen]):
            missing_packages.append(pkg)
    
    if missing_packages:
        print(f"\n{Fore.YELLOW}Missing required dependencies: {', '.join(missing_packages)}")
        while True:
            response = input(f"{Fore.YELLOW}Would you like to install them now? (y/n): {Style.RESET_ALL}").lower()
            if response in ['y', 'yes']:
                try:
                    print(f"\n{Fore.CYAN}Installing dependencies...")
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
                    print(f"{Fore.GREEN}✅ Dependencies installed successfully!")
                    return True
                except subprocess.CalledProcessError as e:
                    print(f"{Fore.RED}Failed to install dependencies: {str(e)}")
                    return False
            elif response in ['n', 'no']:
                print(f"\n{Fore.RED}Cannot continue without required dependencies.")
                return False
            print(f"{Fore.RED}Please answer with 'y' or 'n'")
    
    return True

def check_config() -> bool:
    """Check configuration status and display results"""
    print(f"\n{Fore.CYAN}{'═' * 50}")
    print(f"{Fore.CYAN} 🔍 Checking configuration status...")
    print(f"{Fore.CYAN}{'═' * 50}")
    
    try:
        # Check core settings
        print(f"\n{Fore.YELLOW}Core Settings:")
        _check_core_settings()
        
        # Check media services
        print(f"\n{Fore.YELLOW}Media Services:")
        _check_media_services()
        
        # Check download clients
        print(f"\n{Fore.YELLOW}Download Clients:")
        _check_download_clients()
        
        # Check security settings
        print(f"\n{Fore.YELLOW}Security Settings:")
        _check_security_settings()
        
        print(f"\n{Fore.GREEN}✅ Configuration check completed successfully!")
        return True
        
    except ValidationError as e:
        print(f"\n{Fore.RED}❌ Configuration error: {e.message}")
        return False
    except Exception as e:
        print(f"\n{Fore.RED}❌ Error checking configuration: {str(e)}")
        return False

def _check_core_settings():
    """Check core configuration settings"""
    # Check Telegram settings
    if not config.get("telegram", {}).get("token"):
        print(f"{Fore.RED}❌ Telegram bot token not configured")
    else:
        print(f"{Fore.GREEN}✅ Telegram bot token configured")
        
    # Check language setting
    language = config.get("language", "")
    valid_languages = ["de-de", "en-us", "es-es", "fr-fr", "it-it", "nl-be", "pl-pl", "pt-pt", "ru-ru"]
    if language in valid_languages:
        print(f"{Fore.GREEN}✅ Language set to: {language}")
    else:
        print(f"{Fore.RED}❌ Invalid language setting: {language}")

def _check_media_services():
    """Check media service configurations"""
    services = {
        "Radarr": config.get("radarr", {}),
        "Sonarr": config.get("sonarr", {}),
        "Lidarr": config.get("lidarr", {})
    }
    
    for name, service in services.items():
        if service.get("enable"):
            if service.get("auth", {}).get("apikey"):
                print(f"{Fore.GREEN}✅ {name} enabled and configured")
            else:
                print(f"{Fore.YELLOW}⚠️ {name} enabled but API key missing")
        else:
            print(f"{Fore.BLUE}ℹ️ {name} disabled")

def _check_download_clients():
    """Check download client configurations"""
    # Check Transmission
    transmission = config.get("transmission", {})
    if transmission.get("enable"):
        print(f"{Fore.GREEN}✅ Transmission enabled")
        if transmission.get("authentication"):
            if transmission.get("username") and transmission.get("password"):
                print(f"{Fore.GREEN}  ✓ Authentication configured")
            else:
                print(f"{Fore.YELLOW}  ⚠️ Authentication enabled but credentials missing")
    else:
        print(f"{Fore.BLUE}ℹ️ Transmission disabled")
        
    # Check SABnzbd
    sabnzbd = config.get("sabnzbd", {})
    if sabnzbd.get("enable"):
        print(f"{Fore.GREEN}✅ SABnzbd enabled")
        if sabnzbd.get("auth", {}).get("apikey"):
            print(f"{Fore.GREEN}  ✓ API key configured")
        else:
            print(f"{Fore.YELLOW}  ⚠️ API key missing")
    else:
        print(f"{Fore.BLUE}ℹ️ SABnzbd disabled")

def _check_security_settings():
    """Check security configuration"""
    security = config.get("security", {})
    
    # Check admin mode
    if security.get("enableAdmin"):
        if config.get("admins"):
            print(f"{Fore.GREEN}✅ Admin mode enabled with {len(config['admins'])} admin(s)")
        else:
            print(f"{Fore.YELLOW}⚠️ Admin mode enabled but no admins configured")
    else:
        print(f"{Fore.BLUE}ℹ️ Admin mode disabled")
        
    # Check allowlist
    if security.get("enableAllowlist"):
        if config.get("allow_list"):
            print(f"{Fore.GREEN}✅ Allowlist enabled with {len(config['allow_list'])} user(s)")
        else:
            print(f"{Fore.YELLOW}⚠️ Allowlist enabled but no users configured")
    else:
        print(f"{Fore.BLUE}ℹ️ Allowlist disabled")

def parse_requirements(filename: str = "requirements.txt") -> List[str]:
    """Parse requirements.txt file"""
    # ... (keep existing implementation)

def get_installed_packages() -> Set[str]:
    """Get list of installed packages using pip list"""
    # ... (keep existing implementation)

class Validator:
    """Base validator class"""
    
    def __init__(self, field_name: str):
        self.field_name = field_name
        
    def validate(self, value: Any) -> None:
        """Validate a value
        
        Args:
            value: Value to validate
            
        Raises:
            ValidationError: If validation fails
        """
        raise NotImplementedError

class RequiredValidator(Validator):
    """Validator for required fields"""
    
    def validate(self, value: Any) -> None:
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValidationError(
                f"Missing required field: {self.field_name}",
                f"The field {self.field_name} is required."
            )

class TypeValidator(Validator):
    """Validator for type checking"""
    
    def __init__(self, field_name: str, expected_type: type):
        super().__init__(field_name)
        self.expected_type = expected_type
        
    def validate(self, value: Any) -> None:
        if not isinstance(value, self.expected_type):
            raise ValidationError(
                f"Invalid type for {self.field_name}. Expected {self.expected_type.__name__}, got {type(value).__name__}",
                f"Invalid value type for {self.field_name}"
            )

class RangeValidator(Validator):
    """Validator for numeric ranges"""
    
    def __init__(self, field_name: str, min_value: Optional[float] = None, max_value: Optional[float] = None):
        super().__init__(field_name)
        self.min_value = min_value
        self.max_value = max_value
        
    def validate(self, value: Any) -> None:
        if not isinstance(value, (int, float)):
            raise ValidationError(
                f"Invalid type for {self.field_name}. Expected number",
                f"Invalid value type for {self.field_name}"
            )
            
        if self.min_value is not None and value < self.min_value:
            raise ValidationError(
                f"{self.field_name} must be at least {self.min_value}",
                f"{self.field_name} is too low"
            )
            
        if self.max_value is not None and value > self.max_value:
            raise ValidationError(
                f"{self.field_name} must be at most {self.max_value}",
                f"{self.field_name} is too high"
            )

def validate_data(data: Dict[str, Any], validators: Dict[str, List[Validator]]) -> None:
    """Validate data against a set of validators
    
    Args:
        data: Data to validate
        validators: Dictionary mapping field names to lists of validators
        
    Raises:
        ValidationError: If validation fails
    """
    for field_name, field_validators in validators.items():
        value = data.get(field_name)
        for validator in field_validators:
            validator.validate(value) 