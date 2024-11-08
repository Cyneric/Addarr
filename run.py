#!/usr/bin/env python3
"""
Main entry point for Addarr.
"""

import sys
import os
import argparse

# Only import prerun_checker initially
from src.utils import prerun_checker

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Addarr - Media Management Bot')
    
    # Add command line arguments
    parser.add_argument('--setup', action='store_true', help='Run initial setup wizard')
    parser.add_argument('--configure', action='store_true', help='Add/modify services')
    parser.add_argument('--check', action='store_true', help='Show configuration status')
    parser.add_argument('--version', action='store_true', help='Show version info')
    parser.add_argument('--backup', action='store_true', help='Create a backup of the current configuration')
    parser.add_argument('--reset', action='store_true', help='Reset configuration to default')
    parser.add_argument('--validate-i18n', action='store_true', help='Validate translation files')
    
    args = parser.parse_args()
    
    # Handle validation command separately as it doesn't need config
    if args.validate_i18n:
        # Import only what's needed for validation
        from src.utils.validate_translations import main as validate_translations
        validate_translations()
        return
        
    # Run pre-run checks (unless we're running setup)
    if not args.setup and not prerun_checker.run_checks():
        sys.exit(1)
    
    # Now we can safely initialize everything else
    from src.utils import init_utils
    utils = init_utils()
    
    # Import other modules after checks pass
    from src.setup import SetupWizard
    from src.utils.splash import show_splash_screen, show_version
    from src.main import run_bot
    from src.utils.validation import check_config
    from src.utils.backup import create_backup
    
    try:
        # Handle command line arguments
        if args.setup:
            wizard = SetupWizard()
            wizard.run(reset=True if os.path.exists(prerun_checker.config_path) else False)
        elif args.configure:
            wizard = SetupWizard()
            wizard.configure_services()
        elif args.check:
            check_config()
        elif args.version:
            show_version()
        elif args.backup:
            create_backup()
        elif args.reset:
            wizard = SetupWizard()
            wizard.run(reset=True)
        else:
            # No arguments provided, run the bot
            show_splash_screen()
            run_bot()
            
    except KeyboardInterrupt:
        print(f"\n{prerun_checker.colors.Fore.YELLOW}Shutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"{prerun_checker.colors.Fore.RED}Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()