"""
Filename: logger.py
Author: Christian Blank
Created Date: 2024-11-08
Description: Logging configuration module for Addarr. This module sets up logging for the application, configuring both file
and console logging with proper formatting and log rotation. It provides
a consistent logging interface across the application.
"""

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Optional
from colorama import Fore, Style, init
from logging.handlers import RotatingFileHandler
import datetime

from ..config.settings import config
from ..definitions import LOG_PATH, ERROR_LOG_PATH

# Initialize colorama
init(autoreset=True)

# Add custom logging level for success messages
SUCCESS_LEVEL = 25  # Between INFO and WARNING
logging.addLevelName(SUCCESS_LEVEL, 'SUCCESS')

class ColoredFormatter(logging.Formatter):
    """Custom formatter adding colors to log levels"""
    
    def format(self, record):
        # Save the original message
        original_msg = record.msg
        
        # Add color based on level without modifying anything else
        if record.levelno >= logging.ERROR:
            record.msg = f"{Fore.RED}{original_msg}{Style.RESET_ALL}"
        elif record.levelno >= logging.WARNING:
            record.msg = f"{Fore.YELLOW}{original_msg}{Style.RESET_ALL}"
        elif record.levelno >= logging.INFO:
            record.msg = f"{Fore.BLUE}{original_msg}{Style.RESET_ALL}"
        elif record.levelno >= logging.DEBUG:
            record.msg = f"{Fore.CYAN}{original_msg}{Style.RESET_ALL}"
            
        # Format the message
        result = super().format(record)
        
        # Restore the original message for file logging
        record.msg = original_msg
        return result

class ColoredLogger(logging.Logger):
    """Logger class with success method"""
    def success(self, msg, *args, **kwargs):
        """Log success messages"""
        if self.isEnabledFor(SUCCESS_LEVEL):
            self._log(SUCCESS_LEVEL, msg, args, **kwargs)

class LoggerSetup:
    """Setup logging for the application"""
    
    def __init__(self):
        self.log_level = logging.DEBUG if config.get("debugLogging") else logging.INFO
        self.log_to_console = config.get("logToConsole", True)
        
        # Register the custom logger class
        logging.setLoggerClass(ColoredLogger)
        
    def get_logger(self, name: str) -> logging.Logger:
        """Get a configured logger instance
        
        Args:
            name: Logger name
            
        Returns:
            Configured logger instance
        """
        logger = logging.getLogger(name)
        logger.setLevel(self.log_level)
        
        # Remove existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            
        # Add file handler
        if LOG_PATH:
            self._add_file_handler(logger)
            
        # Add console handler if enabled
        if self.log_to_console:
            self._add_console_handler(logger)
            
        # Prevent propagation to avoid duplicate logs
        logger.propagate = False
            
        return logger
        
    def _add_file_handler(self, logger: logging.Logger):
        """Add file handler to logger"""
        # Create log directory if it doesn't exist
        log_dir = os.path.dirname(LOG_PATH)
        os.makedirs(log_dir, exist_ok=True)
        
        handler = logging.handlers.TimedRotatingFileHandler(
            LOG_PATH,
            when="midnight",
            interval=1,
            backupCount=7,
            encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        handler.setLevel(self.log_level)
        logger.addHandler(handler)
        
    def _add_console_handler(self, logger: logging.Logger):
        """Add console handler to logger"""
        handler = logging.StreamHandler()
        handler.setFormatter(ColoredFormatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        handler.setLevel(self.log_level)
        logger.addHandler(handler)

# Create global logger setup instance
logger_setup = LoggerSetup()

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with both file and console handlers
    
    Args:
        name: The name of the logger
        
    Returns:
        logging.Logger: Configured logger instance
    """
    # Register the custom logger class
    logging.setLoggerClass(ColoredLogger)
    
    logger = logging.getLogger(name)
    
    if not logger.handlers:  # Only add handlers if they don't exist
        logger.setLevel(logging.DEBUG)
        
        # Create logs directory if it doesn't exist
        log_dir = os.path.dirname(LOG_PATH)
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        
        # File handler for general logs (no colors)
        file_handler = RotatingFileHandler(
            LOG_PATH,
            maxBytes=1024*1024,  # 1MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # File handler for error logs (no colors)
        error_handler = RotatingFileHandler(
            ERROR_LOG_PATH,
            maxBytes=1024*1024,  # 1MB
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        error_handler.setFormatter(error_formatter)
        logger.addHandler(error_handler)
        
        # Console handler with colors - IMPORTANT CHANGE HERE
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        # Use ColoredFormatter with minimal format for console
        colored_formatter = ColoredFormatter('%(message)s')
        console_handler.setFormatter(colored_formatter)
        logger.addHandler(console_handler)
        
        # Don't propagate to root logger
        logger.propagate = False
    
    return logger

def log_exception(logger: logging.Logger, e: Exception, context: str = None):
    """
    Helper function to log exceptions with full context
    
    Args:
        logger: Logger instance
        e: Exception to log
        context: Additional context information
    """
    error_msg = f"{Fore.RED}❌ Error"
    if context:
        error_msg += f" in {context}"
    error_msg += f": {str(e)}"
    
    logger.error(
        error_msg,
        exc_info=True,
        stack_info=True
    )

def log_user_interaction(logger, user, action: str, input_data: str = None):
    """Log user interaction with the bot with emojis
    
    Args:
        logger: Logger instance
        user: Telegram user object
        action: Action/command being performed
        input_data: Optional input data from user
    """
    username = user.username or "Unknown"
    user_id = user.id
    
    # Define emojis for different actions
    action_emojis = {
        # Authentication
        "/auth": "🔐",
        "auth_success": "✅",
        "auth_failed": "❌",
        "auth_cancelled": "🚫",
        
        # Main menu
        "/start": "🚀",
        "menu_movie": "🎬",
        "menu_series": "📺",
        "menu_music": "🎵",
        "menu_delete": "❌",
        "menu_status": "📊",
        "menu_settings": "⚙️",
        "menu_help": "❓",
        
        # Media actions
        "/movie": "🎬",
        "/series": "📺",
        "/music": "🎵",
        "search_movie": "🔍",
        "search_series": "🔍",
        "search_music": "🔍",
        "add_movie": "➕",
        "add_series": "➕",
        "add_music": "➕",
        "cancel_search": "🚫",
        
        # System commands
        "/status": "📊",
        "/settings": "⚙️",
        "/help": "❓",
        "/delete": "❌",
        
        # Download clients
        "/transmission": "📥",
        "/sabnzbd": "📥",
        
        # System actions
        "system_refresh": "🔄",
        "system_back": "⬅️",
    }
    
    # Get emoji for action, default to 🔹 if not found
    emoji = action_emojis.get(action, "🔹")
    
    # Create interaction log file if it doesn't exist
    interaction_log_path = os.path.join(os.path.dirname(LOG_PATH), "interactions.log")
    
    # Format the log message with emoji
    log_message = f"{emoji} User: {username} ({user_id}) - Action: {action}"
    if input_data:
        log_message += f" - Input: {input_data}"
    
    # Log to console with color
    logger.info(Fore.CYAN + log_message)
    
    # Log to interaction log file
    try:
        with open(interaction_log_path, 'a', encoding='utf-8') as f:
            f.write(log_message + "\n")
    except Exception as e:
        logger.error(f"Failed to write to interaction log: {e}")