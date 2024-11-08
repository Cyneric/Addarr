"""
Filename: prerun.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Pre-run checks module.

This module handles all pre-run checks like dependency verification,
colorama initialization, and other startup requirements.
"""

import sys
import os
import subprocess
import json
from pathlib import Path
from typing import List, Set

class ColorHandler:
    """Handle color output with fallback to dummy classes"""
    class DummyFore:
        RED = ''
        GREEN = ''
        YELLOW = ''
        CYAN = ''
    
    class DummyStyle:
        RESET_ALL = ''
    
    def __init__(self):
        try:
            from colorama import Fore, Style, init
            init(autoreset=True)
            self.Fore = Fore
            self.Style = Style
        except ImportError:
            self.Fore = self.DummyFore()
            self.Style = self.DummyStyle()
    
    def reload(self):
        """Reload colorama after installation"""
        try:
            from colorama import Fore, Style, init
            init(autoreset=True)
            self.Fore = Fore
            self.Style = Style
        except ImportError:
            pass

class PreRunChecker:
    """Handle pre-run checks and initialization"""
    
    def __init__(self):
        self.colors = ColorHandler()
        self.root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.config_path = os.path.join(self.root_dir, "config.yaml")
        
    def check_config_exists(self) -> bool:
        """Check if config exists and handle setup if needed"""
        # Only import config_handler after dependencies are checked
        from .config_handler import config_handler
        config_handler.colors = self.colors
        
        if not os.path.exists(self.config_path):
            print(f"\n{self.colors.Fore.RED}❌ Configuration file not found at: {self.config_path}")
            while True:
                response = input(f"{self.colors.Fore.YELLOW}Would you like to run the setup wizard? (y/n): {self.colors.Style.RESET_ALL}").lower()
                if response in ['y', 'yes']:
                    print(f"\n{self.colors.Fore.CYAN}Starting setup wizard...")
                    
                    # Create config from example first
                    if not config_handler.create_from_example():
                        return False
                    
                    # Now run setup wizard with the new config as base
                    from src.setup import SetupWizard
                    wizard = SetupWizard()
                    wizard.run()
                    return True
                elif response in ['n', 'no']:
                    print(f"\n{self.colors.Fore.RED}Cannot continue without configuration. Exiting...")
                    return False
                print(f"{self.colors.Fore.RED}Please answer with 'y' or 'n'")
        return True
    
    def parse_requirements(self, filename: str = "requirements.txt") -> List[str]:
        """Parse requirements.txt file"""
        # Core dependencies needed for basic functionality
        core_deps = [
            'colorama',
            'ruamel.yaml',  # Added ruamel.yaml as core dependency
            'python-telegram-bot',
            'pyyaml'
        ]
        
        requirements = []
        try:
            with open(filename, 'r') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    # Remove version specifiers and comments
                    package = line.split('>=')[0].split('<=')[0].split('==')[0].split('#')[0].strip()
                    if package:
                        requirements.append(package.lower())  # Convert to lowercase
        except FileNotFoundError:
            print(f"{self.colors.Fore.RED}❌ requirements.txt not found")
            return core_deps  # Return at least core dependencies if requirements.txt is missing
        return list(set(requirements + core_deps))  # Combine and deduplicate
    
    def get_installed_packages(self) -> Set[str]:
        """Get list of installed packages using pip list"""
        try:
            # Run pip list in JSON format
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'list', '--format=json'],
                capture_output=True,
                text=True
            )
            packages = json.loads(result.stdout)
            
            # Create a set with multiple variations of package names
            installed = set()
            for pkg in packages:
                name = pkg['name'].lower()
                installed.add(name)
                installed.add(name.replace('-', '_'))  # Add underscore version
                installed.add(name.replace('_', '-'))  # Add hyphen version
                
            return installed
        except Exception as e:
            print(f"{self.colors.Fore.RED}Error getting installed packages: {e}")
            return set()
    
    def check_dependencies(self) -> bool:
        """Check if all required dependencies are installed"""
        required_packages = self.parse_requirements()
        if not required_packages:
            print(f"{self.colors.Fore.RED}❌ No dependencies found in requirements.txt")
            return False
        
        # Get installed packages
        installed_packages = self.get_installed_packages()
        
        # Check which required packages are missing
        missing_packages = []
        for pkg in required_packages:
            pkg_lower = pkg.lower()
            pkg_underscore = pkg_lower.replace('-', '_')
            pkg_hyphen = pkg_lower.replace('_', '-')
            
            # Check all variations of the package name
            if not any(p in installed_packages for p in [pkg_lower, pkg_underscore, pkg_hyphen]):
                missing_packages.append(pkg)
        
        if missing_packages:
            print(f"\n{self.colors.Fore.YELLOW}Missing required dependencies: {', '.join(missing_packages)}")
            while True:
                response = input(f"{self.colors.Fore.YELLOW}Would you like to install them now? (y/n): {self.colors.Style.RESET_ALL}").lower()
                if response in ['y', 'yes']:
                    try:
                        print(f"\n{self.colors.Fore.CYAN}Installing dependencies...")
                        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
                        print(f"{self.colors.Fore.GREEN}✅ Dependencies installed successfully!")
                        
                        # Reload colorama if it was just installed
                        if 'colorama' in missing_packages:
                            self.colors.reload()
                        
                        return True
                    except subprocess.CalledProcessError as e:
                        print(f"{self.colors.Fore.RED}Failed to install dependencies: {str(e)}")
                        return False
                elif response in ['n', 'no']:
                    print(f"\n{self.colors.Fore.RED}Cannot continue without required dependencies.")
                    return False
                print(f"{self.colors.Fore.RED}Please answer with 'y' or 'n'")
        
        return True
    
    def run_checks(self) -> bool:
        """Run all pre-run checks
        
        Returns:
            bool: True if all checks pass, False otherwise
        """
        # Check dependencies first
        if not self.check_dependencies():
            return False
            
        # Check config exists
        if not self.check_config_exists():
            return False
            
        # Add any additional checks here
        # For example:
        # - Check Python version
        # - Check system requirements
        # - Check file permissions
        # - etc.
        
        return True

# Create global instance
prerun_checker = PreRunChecker() 