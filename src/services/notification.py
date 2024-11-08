"""
Notification service module.

This module handles sending notifications to users and admins.
"""

import logging
from typing import Optional
from telegram import Bot
from colorama import Fore

from src.utils.logger import get_logger
from src.config.settings import config
from src.services.translation import TranslationService

logger = get_logger("addarr.notification")

class NotificationService:
    """Service for handling notifications"""
    
    _instance = None
    _bot: Optional[Bot] = None
    
    def __new__(cls):
        """Ensure only one instance exists"""
        if cls._instance is None:
            cls._instance = super(NotificationService, cls).__new__(cls)
            cls._initialize()
        return cls._instance
    
    @classmethod
    def _initialize(cls):
        """Initialize the notification service"""
        cls.translation = TranslationService()
        cls.admin_notify_id = config.get("logging", {}).get("adminNotifyId")
        
    def set_bot(self, bot: Bot):
        """Set the bot instance for sending notifications"""
        self._bot = bot
        
    async def notify_admin(self, message: str):
        """Send notification to admin"""
        if not self._bot or not self.admin_notify_id:
            return
            
        try:
            await self._bot.send_message(
                chat_id=self.admin_notify_id,
                text=message
            )
        except Exception as e:
            logger.error(f"Failed to send admin notification: {e}")
            
    async def notify_user(self, chat_id: int, message: str):
        """Send notification to user"""
        if not self._bot:
            return
            
        try:
            await self._bot.send_message(
                chat_id=chat_id,
                text=message
            )
        except Exception as e:
            logger.error(f"Failed to send user notification: {e}")
            
    async def notify_action(self, action: str, user_data: dict, **kwargs):
        """Send action notification to admin"""
        if not self._bot or not self.admin_notify_id:
            return
            
        try:
            # Get translated notification message
            message = self.translation.get_text(
                f"Notifications.{action}",
                first_name=user_data.get("first_name", "Unknown"),
                chat_id=user_data.get("chat_id", "Unknown"),
                **kwargs
            )
            
            await self._bot.send_message(
                chat_id=self.admin_notify_id,
                text=message
            )
        except Exception as e:
            logger.error(f"Failed to send action notification: {e}") 