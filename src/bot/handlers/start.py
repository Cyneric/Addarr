"""
Filename: start.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Start handler module.

This module handles the main entry point and menu for the bot.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters
)
from colorama import Fore

from src.utils.logger import get_logger, log_user_interaction
from src.bot.handlers.auth import require_auth
from src.bot.handlers.media import MediaHandler, SEARCHING
from src.bot.handlers.help import HelpHandler
from src.bot.keyboards import get_main_menu_keyboard
from src.services.translation import TranslationService

logger = get_logger("addarr.start")
logger.info("Start handler module initialized")

class StartHandler:
    """Handler for start command and main menu"""
    
    def __init__(self):
        self.media_handler = MediaHandler()
        self.help_handler = HelpHandler()
        self.translation = TranslationService()
    
    def get_handler(self):
        """Get the command handlers"""
        MENU_STATE = 1  # Add a state for menu interactions
        
        return [
            ConversationHandler(
                entry_points=[CommandHandler("start", self.show_menu)],
                states={
                    MENU_STATE: [
                        CallbackQueryHandler(self.handle_menu_selection, pattern="^menu_"),
                    ],
                    SEARCHING: [
                        MessageHandler(
                            filters.TEXT & ~filters.COMMAND,
                            self.media_handler.handle_search
                        ),
                        CallbackQueryHandler(self.handle_menu_selection, pattern="^menu_")
                    ]
                },
                fallbacks=[
                    CommandHandler("cancel", self.media_handler.cancel_search),
                ],
                name="start_conversation",
                persistent=False
            )
        ]
    
    @require_auth
    async def show_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show the main menu"""
        log_user_interaction(logger, update.effective_user, "/start")

        welcome_text = self.translation.get_text("mainMenu")
        
        if update.callback_query:
            # Handle callback query
            query = update.callback_query
            await query.answer()
            await query.message.edit_text(
                welcome_text,
                reply_markup=get_main_menu_keyboard()
            )
        elif update.effective_message:
            # Handle direct command
            await update.effective_message.reply_text(
                welcome_text,
                reply_markup=get_main_menu_keyboard()
            )
        
        return 1  # Return MENU_STATE to enter the menu state
    
    @require_auth
    async def handle_menu_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle menu button selections"""
        logger.info("handle_menu_selection called")
        
        if not update.callback_query:
            logger.warning("Received menu selection without callback query")
            return
            
        query = update.callback_query
        logger.info(f"Received callback query with data: {query.data}")
        
        await query.answer()
        
        action = query.data.replace("menu_", "")
        user = query.from_user
        
        logger.info(f"Menu button pressed - Action: {action}, User: {user.first_name} (ID: {user.id})")
        log_user_interaction(logger, user, f"menu_{action}")
        
        if action == "back":
            logger.info(f"Back to menu requested by user {user.first_name} (ID: {user.id})")
            await self.show_menu(update, context)
            return
            
        if action == "cancel":
            logger.info(f"Cancel action triggered by user {user.first_name} (ID: {user.id})")
            # Clean up any user data that might have been set
            if context.user_data:
                context.user_data.clear()
                
            # Edit the message to show cancellation
            await query.message.edit_text(
                self.translation.get_text("messages.Canceled")
            )
            return ConversationHandler.END
            
        if action in ["movie", "series", "music"]:
            logger.info(f"Search initiated for {action} by user {user.first_name} (ID: {user.id})")
            # Set search type in context
            context.user_data["search_type"] = action
            
            # Get translated prompt based on media type
            prompts = {
                "movie": self.translation.get_text("Title", subject="Movie"),
                "series": self.translation.get_text("Title", subject="Series"),
                "music": self.translation.get_text("Title", subject="Music")
            }
            
            cancel_hint = self.translation.get_text("messages.CancelHint", default="(Use /cancel to cancel)")
            
            await query.message.edit_text(
                f"{prompts[action]}\n{cancel_hint}"
            )
            
            return SEARCHING
            
        elif action == "delete":
            logger.info(f"Delete menu opened by user {user.first_name} (ID: {user.id})")
            delete_text = self.translation.get_text("messages.DeletePrompt")
            await query.message.edit_text(delete_text)
        elif action == "status":
            logger.info(f"Status check requested by user {user.first_name} (ID: {user.id})")
            await self.media_handler.handle_status(update, context)
        elif action == "settings":
            logger.info(f"Settings menu opened by user {user.first_name} (ID: {user.id})")
            await self.media_handler.handle_settings(update, context)
        elif action == "help":
            logger.info(f"Help requested by user {user.first_name} (ID: {user.id})")
            await self.help_handler.show_help(update, context)
        else:
            logger.warning(f"Unknown menu action '{action}' from user {user.first_name} (ID: {user.id})")
    
    async def start_movie_search(self, query):
        """Start movie search conversation"""
        await query.message.edit_text(
            "🎬 Please enter the name of the movie you want to search for:\n"
            "(Use /cancel to cancel)"
        )
        # Set conversation state for movie search
        
    # ... (similar methods for other menu options) 