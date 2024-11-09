"""
Filename: status.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Status command handler module.

This module handles the /status command, showing system and service health information.
"""

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from datetime import datetime
from typing import List

from src.utils.logger import get_logger
from src.config.settings import config

logger = get_logger("addarr.handlers.status")

class StatusHandler:
    """Handler for the /status command"""
    
    def __init__(self):
        self.command = "status"
        
    def get_handler(self) -> List[CommandHandler]:
        """Get the command handler"""
        return [CommandHandler(self.command, self._handle_status)]
    
    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /status command
        
        Shows current system status and health information for all services
        """
        try:
            # Get bot instance from context
            bot = context.application.bot_instance
            
            # Get health checker status
            health_status = bot.health_checker.get_status()
            
            # Build status message
            message = "📊 *System Status*\n\n"
            
            # Health check status
            message += "🏥 *Health Check*\n"
            message += f"• Status: {'✅ Running' if health_status['running'] else '❌ Stopped'}\n"
            message += f"• Interval: {health_status['check_interval']} minutes\n"
            
            if health_status['last_check']:
                last_check = health_status['last_check'].strftime("%Y-%m-%d %H:%M:%S")
                message += f"• Last Check: {last_check}\n"
            
            # Service health
            message += "\n🔧 *Services*\n"
            if health_status['unhealthy_services']:
                message += "❌ Unhealthy Services:\n"
                for service in health_status['unhealthy_services']:
                    message += f"• {service}\n"
            else:
                message += "✅ All services are healthy\n"
            
            if update.callback_query:
                # If it's a callback query, edit the message
                await update.callback_query.message.edit_text(
                    message,
                    parse_mode='Markdown'
                )
            else:
                # If it's a direct command, send a new message
                await update.message.reply_text(
                    message,
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            logger.error(f"Error handling status command: {str(e)}")
            error_message = "❌ Error getting system status. Please try again later."
            
            if update.callback_query:
                await update.callback_query.message.edit_text(error_message)
            else:
                await update.message.reply_text(error_message)

    async def refresh_status(self, query):
        """Refresh status message"""
        try:
            # Get bot instance
            bot = query.bot.application.bot_instance
            
            # Get updated health status
            health_status = bot.health_checker.get_status()
            
            # Build status message (same as _handle_status)
            message = "📊 *System Status*\n\n"
            # ... (rest of message building)
            
            await query.message.edit_text(
                message,
                parse_mode='Markdown'
            )
            await query.answer("Status refreshed")
            
        except Exception as e:
            logger.error(f"Error refreshing status: {str(e)}")
            await query.answer("Failed to refresh status", show_alert=True)