"""
Filename: transmission.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Transmission handler module.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes, CallbackQueryHandler
from colorama import Fore

from src.utils.logger import get_logger, log_user_interaction
from src.services.transmission import TransmissionService
from src.bot.handlers.auth import require_auth
from src.services.translation import TranslationService

logger = get_logger("addarr.handlers.transmission")

class TransmissionHandler:
    """Handler for Transmission-related commands"""
    
    def __init__(self):
        try:
            self.transmission_service = TransmissionService()
            self.translation = TranslationService()
        except Exception as e:
            logger.error(f"Failed to initialize TransmissionService: {e}")
            self.transmission_service = None
            
    def get_handler(self):
        """Get the conversation handler for Transmission"""
        if not self.transmission_service:
            logger.warning("Transmission service not available, skipping handler registration")
            return []
            
        return [
            CommandHandler("transmission", self.handle_transmission),
            CallbackQueryHandler(self.handle_speed_selection, pattern="^transmission_speed_")
        ]
        
    @require_auth
    async def handle_transmission(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle transmission command"""
        if not update.effective_user:
            return
            
        log_user_interaction(logger, update.effective_user, "/transmission")
        
        if not self.transmission_service:
            await update.message.reply_text(
                self.translation.get_text("Transmission.NotEnabled")
            )
            return
            
        # Create speed selection keyboard
        keyboard = [
            [
                InlineKeyboardButton(
                    self.translation.get_text("Transmission.TSL"), 
                    callback_data="transmission_speed_tsl"
                ),
                InlineKeyboardButton(
                    self.translation.get_text("Transmission.Normal"), 
                    callback_data="transmission_speed_normal"
                )
            ]
        ]
        
        await update.message.reply_text(
            self.translation.get_text("Transmission.Speed"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    async def handle_speed_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle speed selection"""
        if not update.callback_query:
            return
            
        query = update.callback_query
        await query.answer()
        
        speed = query.data.replace("transmission_speed_", "")
        
        try:
            if speed == "tsl":
                await self.transmission_service.enable_alt_speed()
                message_key = "Transmission.ChangedToTSL"
            else:
                await self.transmission_service.disable_alt_speed()
                message_key = "Transmission.ChangedToNormal"
                
            await query.message.edit_text(
                self.translation.get_text(message_key)
            )
            
        except Exception as e:
            logger.error(f"Error setting Transmission speed: {e}")
            await query.message.edit_text(
                self.translation.get_text("Transmission.Error", default="Error setting speed limit")
            ) 