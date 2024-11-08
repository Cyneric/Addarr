"""
Filename: transmission.py
Author: Christian Blank (https://github.com/cyneric)
Created Date: 2024-11-09
Description: Telegram command handler for Transmission operations.
"""

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from telegram.constants import ParseMode
from typing import List


from ...services.transmission import transmission_service
from ...utils.logger import get_logger
from src.bot.keyboards import get_yes_no_keyboard
from ...utils.error_handler import ServiceNotEnabledError

logger = get_logger("addarr.handlers.transmission")

class TransmissionHandler:
    """Handler for Transmission-related commands"""
    
    def __init__(self):
        """Initialize the handler"""
        self.service = transmission_service
        
    def get_handler(self) -> List:
        """Get the command and callback handlers
        
        Returns:
            List of handlers
        """
        return [
            CommandHandler("transmission", self.transmission_command),
            CallbackQueryHandler(self.handle_callback, pattern=r"^transmission_.*")
        ]
        
    async def transmission_command(self, update: Update, context: CallbackContext) -> None:
        """Handle /transmission command
        
        Shows Transmission status and turtle mode options
        """
        if not self.service.is_enabled():
            await update.message.reply_text(
                "❌ Transmission integration is not enabled.\n"
                "Enable it in config.yaml to use this feature."
            )
            return
            
        status = self.service.get_status()
        
        if not status["connected"]:
            await update.message.reply_text(
                f"❌ Cannot connect to Transmission:\n{status.get('error', 'Unknown error')}"
            )
            return
            
        # Create status message
        turtle_status = "🐢 Enabled" if status["alt_speed_enabled"] else "🚀 Disabled"
        message = (
            f"*Transmission Status*\n\n"
            f"Version: `{status['version']}`\n"
            f"Turtle Mode: {turtle_status}\n\n"
            f"Would you like to toggle Turtle Mode?"
        )
        
        # Create inline keyboard
        keyboard = get_yes_no_keyboard(
            "transmission_toggle",
            "Yes, toggle turtle mode",
            "No, keep current setting"
        )
        
        await update.message.reply_text(
            message,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
    async def handle_callback(self, update: Update, context: CallbackContext) -> None:
        """Handle callback queries for Transmission commands"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "transmission_toggle_yes":
            # Get current status and toggle
            status = self.service.get_status()
            current_state = status.get("alt_speed_enabled", False)
            
            if self.service.set_alt_speed(not current_state):
                new_state = "enabled 🐢" if not current_state else "disabled 🚀"
                message = f"✅ Turtle Mode {new_state}"
            else:
                message = "❌ Failed to toggle Turtle Mode"
                
            # Update the message
            await query.edit_message_text(
                message,
                parse_mode=ParseMode.MARKDOWN
            )
            
        elif query.data == "transmission_toggle_no":
            await query.edit_message_text(
                "👍 Keeping current settings",
                parse_mode=ParseMode.MARKDOWN
            ) 