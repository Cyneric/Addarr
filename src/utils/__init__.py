"""
Filename: __init__.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Utils package initialization.
"""

from colorama import init as init_colorama

def init_utils():
    """Initialize utility modules"""
    # Initialize colorama for cross-platform colored output
    init_colorama(autoreset=True)
    
    # Import error classes
    from .error_handler import (
        AddarrError,
        ConfigError,
        ValidationError,
        handle_token_error,
        handle_missing_token_error,
        handle_network_error,
        handle_initialization_error,
        handle_telegram_error,
        send_error_message
    )
    
    return {
        'AddarrError': AddarrError,
        'ConfigError': ConfigError,
        'ValidationError': ValidationError,
        'handle_token_error': handle_token_error,
        'handle_missing_token_error': handle_missing_token_error,
        'handle_network_error': handle_network_error,
        'handle_initialization_error': handle_initialization_error,
        'handle_telegram_error': handle_telegram_error,
        'send_error_message': send_error_message
    }

# Import and export prerun_checker
from .prerun import PreRunChecker
prerun_checker = PreRunChecker()

__all__ = ['init_utils', 'prerun_checker']
