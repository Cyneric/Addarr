"""
Helper functions module.

This module contains utility functions used throughout the application,
including authentication checks, chat ID management, and data formatting.
These functions provide common functionality needed by multiple components.
"""

import os
from typing import List, Optional
from telegram import Bot
from telegram.ext import ContextTypes
from ..config.settings import config
from ..definitions import CHATID_PATH, ADMIN_PATH, ALLOWLIST_PATH

def check_auth(func):
    """Decorator to check if user is authenticated"""
    async def wrapper(self, update, context, *args, **kwargs):
        if not await is_authenticated(update.effective_chat.id):
            await update.message.reply_text(
                "You need to authenticate first. Use /auth to begin."
            )
            return None
        return await func(self, update, context, *args, **kwargs)
    return wrapper

async def get_authorized_chats() -> List[int]:
    """Get list of authorized chat IDs"""
    if not os.path.exists(CHATID_PATH):
        return []
        
    with open(CHATID_PATH, 'r') as f:
        return [
            int(line.split(' - ')[0]) 
            for line in f.readlines() 
            if line.strip()
        ]

async def get_chat_name(bot: Bot, chat_id: int) -> str:
    """Get chat name for a given chat ID
    
    Args:
        bot: Telegram bot instance
        chat_id: Chat ID to get name for
        
    Returns:
        str: Chat name in format "chat_id - name"
    """
    chat = await bot.get_chat(chat_id)
    
    # Try different chat attributes in order of preference
    name = None
    if chat.username:
        name = chat.username
    elif chat.title:
        name = chat.title
    elif chat.last_name and chat.first_name:
        name = f"{chat.first_name} {chat.last_name}"
    elif chat.first_name:
        name = chat.first_name
    elif chat.last_name:
        name = chat.last_name
        
    if name:
        return f"{chat_id} - {name}"
    return str(chat_id)

def save_chat_id(chat_id: int, chat_name: Optional[str] = None):
    """Save a chat ID to authorized chats"""
    entry = f"{chat_id}"
    if chat_name:
        entry += f" - {chat_name}"
    entry += "\n"
    
    with open(CHATID_PATH, 'a') as f:
        f.write(entry)

def format_bytes(size: int) -> str:
    """Format bytes to human readable string"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"

def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    if not os.path.exists(ADMIN_PATH):
        return False
        
    with open(ADMIN_PATH, 'r') as f:
        admin_ids = [line.strip() for line in f.readlines()]
        return str(user_id) in admin_ids

def is_allowed(user_id: int) -> bool:
    """Check if user is in allowlist"""
    if not config.get("enableAllowlist"):
        return True
        
    if not os.path.exists(ALLOWLIST_PATH):
        return False
        
    with open(ALLOWLIST_PATH, 'r') as f:
        allowed_ids = [line.strip() for line in f.readlines()]
        return str(user_id) in allowed_ids

async def is_authenticated(chat_id: int) -> bool:
    """Check if a chat is authenticated"""
    return chat_id in await get_authorized_chats()