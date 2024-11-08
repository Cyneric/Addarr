"""
Filename: handlers.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Telegram bot command handlers package.

This package contains all the command handlers for the Telegram bot,
including authentication, media management, deletion, and system commands.
Each handler is responsible for managing a specific type of user interaction.
"""

from .auth import AuthHandler
from .media import MediaHandler
from .delete import DeleteHandler
from .system import SystemHandler

__all__ = ['AuthHandler', 'MediaHandler', 'DeleteHandler', 'SystemHandler']
