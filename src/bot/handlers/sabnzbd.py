"""
SABnzbd handler module.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes, CallbackQueryHandler
from colorama import Fore

from src.utils.logger import get_logger, log_user_interaction
from src.services.sabnzbd import SABnzbdService
from src.bot.handlers.auth import require_auth
from src.services.translation import TranslationService

logger = get_logger("addarr.handlers.sabnzbd")

class SabnzbdHandler:
    """Handler for SABnzbd-related commands"""
    
    def __init__(self):
        try:
            self.sabnzbd_service = SABnzbdService()
            self.translation = TranslationService()
        except Exception as e:
            logger.error(f"Failed to initialize SABnzbdService: {e}")
            self.sabnzbd_service = None
            
    def get_handler(self):
        """Get the conversation handler for SABnzbd"""
        if not self.sabnzbd_service:
            logger.warning("SABnzbd service not available, skipping handler registration")
            return []
            
        return [
            CommandHandler("sabnzbd", self.handle_sabnzbd),
            CallbackQueryHandler(self.handle_speed_selection, pattern="^sabnzbd_speed_")
        ]
        
    @require_auth
    async def handle_sabnzbd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle SABnzbd command"""
        if not update.effective_user:
            return
            
        log_user_interaction(logger, update.effective_user, "/sabnzbd")
        
        if not self.sabnzbd_service:
            await update.message.reply_text(
                self.translation.get_text("Sabnzbd.NotEnabled")
            )
            return
            
        # Create speed selection keyboard
        keyboard = [
            [
                InlineKeyboardButton(
                    self.translation.get_text("Sabnzbd.Limit25"), 
                    callback_data="sabnzbd_speed_25"
                ),
                InlineKeyboardButton(
                    self.translation.get_text("Sabnzbd.Limit50"), 
                    callback_data="sabnzbd_speed_50"
                )
            ],
            [
                InlineKeyboardButton(
                    self.translation.get_text("Sabnzbd.Limit100"), 
                    callback_data="sabnzbd_speed_100"
                )
            ]
        ]
        
        await update.message.reply_text(
            self.translation.get_text("Sabnzbd.Speed"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    async def handle_speed_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle speed selection"""
        if not update.callback_query:
            return
            
        query = update.callback_query
        await query.answer()
        
        speed = int(query.data.replace("sabnzbd_speed_", ""))
        
        try:
            await self.sabnzbd_service.set_speed_limit(speed)
            
            # Get appropriate message for speed setting
            message_key = f"Sabnzbd.ChangedTo{speed}"
            await query.message.edit_text(
                self.translation.get_text(message_key)
            )
            
        except Exception as e:
            logger.error(f"Error setting SABnzbd speed: {e}")
            await query.message.edit_text(
                self.translation.get_text("Sabnzbd.Error")
            )