"""
Filename: help.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Help handler module.

This module provides help and command information to users.
"""

from telegram import Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from colorama import Fore

from src.utils.logger import get_logger, log_user_interaction
from src.bot.handlers.auth import require_auth
from src.bot.keyboards import get_main_menu_keyboard
from src.services.translation import TranslationService

logger = get_logger("addarr.help")

class HelpHandler:
    """Handler for help commands"""
    
    def __init__(self):
        self.translation = TranslationService()
    
    def get_handler(self):
        """Get the command handler for help"""
        return [
            CommandHandler("help", self.show_help),
            CallbackQueryHandler(self.handle_back, pattern="^menu_back$")
        ]
    
    @require_auth
    async def show_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help message with available commands"""
        if not update.effective_user:
            return
            
        user = update.effective_user
        log_user_interaction(logger, user, "/help")
        
        help_text = (
            "🤖 *Available Commands:*\n\n"
            "🎬 */movie* - Search and add movies\n"
            "📺 */series* - Search and add TV shows\n"
            "🎵 */music* - Search and add music\n\n"

            "🚫 */cancel* - Cancel current action\n"
            "❌ */delete* - Delete media\n"
            "📊 */status* - Check system status\n"
            "⚙️ */settings* - Manage settings\n\n"

            "🚀 */allSeries* - Show all series\n"
            "🎬 */allMovies* - Show all movies\n"
            "🎵 */allMusic* - Show all music\n\n"

            "❓ */help* - Show this help message\n\n"


            "📖 Wiki: https://github.com/Cyneric/addarr/wiki\n"
            "🐞 Issues: https://github.com/Cyneric/addarr/issues\n"
            "🔗 Repository: https://github.com/Cyneric/addarr\n\n"

            "👨‍💻 Author: Christian Blank (https://github.com/Cyneric)\n\n"
            "🔄 Version: 0.1.0\n"
        )
        
        # Handle both direct commands and callback queries
        if update.callback_query:
            await update.callback_query.message.edit_text(
                help_text,
                parse_mode='Markdown',
                disable_web_page_preview=True,
            )
        else:
            await update.message.reply_text(
                help_text,
                parse_mode='Markdown',
                disable_web_page_preview=True,
            )
    
    @require_auth
    async def handle_back(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle back button press"""
        if not update.callback_query:
            return
            
        query = update.callback_query
        await query.answer()
        
        log_user_interaction(logger, query.from_user, "menu_back")
        
        # Get translated welcome message
        welcome_text = self.translation.get_text("Start chatting")
        
        await query.message.edit_text(
            welcome_text,
            reply_markup=get_main_menu_keyboard()
        ) 