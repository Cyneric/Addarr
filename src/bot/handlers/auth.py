"""
Authentication handler module.

This module handles user authentication through the bot.
"""

import os
import yaml
from pathlib import Path
from telegram import Update
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from colorama import Fore, Style
from functools import wraps

from src.utils.chat import get_chat_name
from src.utils.logger import get_logger, log_user_interaction
from src.config.settings import config
from src.definitions import CONFIG_PATH
from src.services.translation import TranslationService

# Get logger instance
logger = get_logger("addarr.auth")

# States
PASSWORD = 0

def require_auth(func):
    """Decorator to require authentication for handlers"""
    @wraps(func)
    async def wrapped(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user:
            return
            
        if not AuthHandler.is_authenticated(update.effective_user.id):
            translation = TranslationService()
            await update.message.reply_text(
                translation.get_text("NotAuthorized", default="🔒 You need to authenticate first.\nUse /start to begin authentication.")
            )
            return
        return await func(self, update, context, *args, **kwargs)
    return wrapped

class AuthHandler:
    """Handler for user authentication"""
    
    # Class-level storage for authenticated users
    _authenticated_users = set()
    
    def __init__(self):
        self.password = config.get("telegram", {}).get("password", "")
        self.translation = TranslationService()
        # Load authenticated users from config
        AuthHandler._authenticated_users = set(config.get("authenticated_users", []))
        
    @classmethod
    def is_authenticated(cls, user_id: int) -> bool:
        """Check if a user is authenticated"""
        return user_id in cls._authenticated_users
        
    def _save_authenticated_users(self):
        """Save authenticated users to config file"""
        try:
            # Load current config
            with open(CONFIG_PATH, 'r') as f:
                current_config = yaml.safe_load(f)
            
            # Update authenticated users
            current_config["authenticated_users"] = list(AuthHandler._authenticated_users)
            
            # Save updated config
            with open(CONFIG_PATH, 'w') as f:
                yaml.safe_dump(current_config, f, default_flow_style=False)
                
        except Exception as e:
            logger.error(f"Error saving authenticated users to config: {e}")
    
    def get_handler(self):
        """Get the conversation handler for authentication"""
        return [
            ConversationHandler(
                entry_points=[CommandHandler("auth", self.start_auth)],
                states={
                    PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.check_password)]
                },
                fallbacks=[CommandHandler("cancel", self.cancel_auth)],
                name="auth_conversation"
            )
        ]
        
    async def start_auth(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the authentication process"""
        if not update.effective_message or not update.effective_user:
            return ConversationHandler.END
            
        user = update.effective_user
        chat = update.effective_message.chat
        
        log_user_interaction(logger, user, "/auth", "authentication attempt")
        
        # Check if user is already authenticated
        if self.is_authenticated(user.id):
            logger.info(Fore.GREEN + f"👤 User {user.username} ({user.id}) is already authenticated")
            await update.message.reply_text(
                self.translation.get_text("Chatid already allowed")
            )
            return ConversationHandler.END
        
        # Log authentication attempt
        logger.info(Fore.CYAN + f"👤 User {user.username} ({user.id}) started authentication in {get_chat_name(chat.id, chat.title)}")
        
        await update.message.reply_text(
            self.translation.get_text("Authorize")
        )
        
        return PASSWORD
        
    async def check_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check the provided password"""
        if not update.effective_message or not update.effective_user:
            return ConversationHandler.END
            
        user = update.effective_user
        chat = update.effective_message.chat
        message = update.effective_message
        
        # Delete password message for security
        await message.delete()
        
        if message.text == self.password:
            # Add user to authenticated users and save
            AuthHandler._authenticated_users.add(user.id)
            self._save_authenticated_users()
            
            log_user_interaction(logger, user, "auth_success")
            
            # Log successful authentication
            logger.info(Fore.GREEN + f"✅ User {user.username} ({user.id}) authenticated successfully")
            
            # Show success message
            await chat.send_message(
                self.translation.get_text("Chatid added")
            )
            
            # Trigger the start command to show the menu
            await context.bot.send_message(
                chat.id,
                "/start"
            )
            
            return ConversationHandler.END
        else:
            log_user_interaction(logger, user, "auth_failed")
            
            # Log failed authentication
            logger.warning(Fore.RED + f"❌ User {user.username} ({user.id}) failed authentication")
            
            await chat.send_message(
                self.translation.get_text("Wrong password")
            )
            return ConversationHandler.END
        
    async def cancel_auth(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel the authentication process"""
        if update.effective_message:
            log_user_interaction(logger, update.effective_user, "auth_cancelled")
            await update.message.reply_text(
                self.translation.get_text("End")
            )
        return ConversationHandler.END