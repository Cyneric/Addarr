"""
Chat utility functions.

This module provides utility functions for handling chat-related operations.
"""

from typing import Optional

def get_chat_name(chat_id: int, chat_title: Optional[str] = None) -> str:
    """
    Get a formatted chat name for logging purposes.
    
    Args:
        chat_id: The Telegram chat ID
        chat_title: The chat title (for group chats)
        
    Returns:
        A formatted string containing the chat name/ID
    """
    if chat_title:
        return f"{chat_title} ({chat_id})"
    return f"chat {chat_id}"