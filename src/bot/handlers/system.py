"""
Filename: system.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: System command handler module.
"""

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, CallbackQueryHandler
from colorama import Fore

from src.utils.logger import get_logger, log_user_interaction
from src.bot.handlers.auth import require_auth
from src.bot.keyboards import get_system_keyboard

logger = get_logger("addarr.system")

class SystemHandler:
    """Handler for system-related commands"""
    
    def get_handler(self):
        """Get system command handlers"""
        return [
            CommandHandler("status", self.show_status),
            CallbackQueryHandler(self.handle_system_action, pattern="^system_")
        ]
    
    @require_auth
    async def show_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show system status"""
        if not update.effective_user:
            return
            
        log_user_interaction(logger, update.effective_user, "/status")
        
        await update.message.reply_text(
            "📊 System Status",
            reply_markup=get_system_keyboard()
        )
    
    @require_auth
    async def handle_system_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle system action selection"""
        if not update.callback_query:
            return
            
        query = update.callback_query
        action = query.data.replace("system_", "")
        
        log_user_interaction(logger, query.from_user, f"system_{action}")