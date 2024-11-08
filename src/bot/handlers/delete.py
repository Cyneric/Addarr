"""
Filename: delete.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Delete handler module.

This module handles media deletion operations.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes, CallbackQueryHandler
from colorama import Fore

from src.utils.logger import get_logger, log_user_interaction
from src.services.media import MediaService
from src.bot.handlers.auth import require_auth
from src.services.translation import TranslationService

logger = get_logger("addarr.delete")

class DeleteHandler:
    """Handler for delete operations"""
    
    def __init__(self):
        self.media_service = MediaService()
        self.translation = TranslationService()
    
    def get_handler(self):
        """Get delete command handlers"""
        return [
            CommandHandler("delete", self.handle_delete),
            CallbackQueryHandler(self.handle_delete_selection, pattern="^delete_")
        ]
    
    @require_auth
    async def handle_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle delete command"""
        if not update.effective_message or not update.effective_user:
            return
            
        log_user_interaction(logger, update.effective_user, "/delete")
        
        # Create media type selection keyboard
        keyboard = [
            [
                InlineKeyboardButton(
                    f"🎬 {self.translation.get_text('Movie')}", 
                    callback_data="delete_type_movie"
                ),
                InlineKeyboardButton(
                    f"📺 {self.translation.get_text('Series')}", 
                    callback_data="delete_type_series"
                )
            ],
            [
                InlineKeyboardButton(
                    f"🎵 {self.translation.get_text('Music')}", 
                    callback_data="delete_type_music"
                )
            ],
            [
                InlineKeyboardButton(
                    f"❌ {self.translation.get_text('Stop')}", 
                    callback_data="delete_cancel"
                )
            ]
        ]
        
        await update.message.reply_text(
            self.translation.get_text("What is this?"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def handle_delete_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle delete selection"""
        if not update.callback_query:
            return
            
        query = update.callback_query
        await query.answer()
        
        action = query.data.replace("delete_", "")
        
        if action == "cancel":
            await query.message.edit_text(
                self.translation.get_text("End")
            )
            return
            
        if action.startswith("type_"):
            # Handle media type selection
            media_type = action.replace("type_", "")
            context.user_data["delete_type"] = media_type
            
            try:
                # Get list of media based on type
                if media_type == "movie":
                    items = await self.media_service.get_movies()
                elif media_type == "series":
                    items = await self.media_service.get_series()
                elif media_type == "music":
                    items = await self.media_service.get_music()
                else:
                    await query.message.edit_text("❌ Invalid media type")
                    return
                
                if not items:
                    await query.message.edit_text(
                        self.translation.get_message("NoExist", subject=media_type)
                    )
                    return
                
                # Create selection keyboard
                keyboard = []
                for item in items:
                    keyboard.append([
                        InlineKeyboardButton(
                            item["title"], 
                            callback_data=f"delete_item_{item['id']}"
                        )
                    ])
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"❌ {self.translation.get_text('StopDelete')}", 
                        callback_data="delete_cancel"
                    )
                ])
                
                await query.message.edit_text(
                    self.translation.get_text("Select"),
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
            except Exception as e:
                logger.error(f"Error getting media list: {e}")
                await query.message.edit_text(
                    "❌ Error getting media list"
                )
                
        elif action.startswith("item_"):
            # Handle specific item deletion
            item_id = action.replace("item_", "")
            media_type = context.user_data.get("delete_type")
            
            if not media_type:
                await query.message.edit_text("❌ Media type not found")
                return
                
            try:
                # Get item details for confirmation
                if media_type == "movie":
                    item = await self.media_service.get_movie(item_id)
                elif media_type == "series":
                    item = await self.media_service.get_series(item_id)
                elif media_type == "music":
                    item = await self.media_service.get_music(item_id)
                else:
                    await query.message.edit_text("❌ Invalid media type")
                    return
                
                if not item:
                    await query.message.edit_text(
                        self.translation.get_message("NoExist", subject=media_type)
                    )
                    return
                
                # Store item for confirmation
                context.user_data["delete_item"] = item
                
                # Create confirmation keyboard
                keyboard = [
                    [
                        InlineKeyboardButton(
                            f"✅ {self.translation.get_text('Delete')}", 
                            callback_data="delete_confirm"
                        ),
                        InlineKeyboardButton(
                            f"❌ {self.translation.get_text('StopDelete')}", 
                            callback_data="delete_cancel"
                        )
                    ]
                ]
                
                await query.message.edit_text(
                    self.translation.get_message("ThisDelete", 
                        subject=media_type,
                        title=item["title"]
                    ),
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
            except Exception as e:
                logger.error(f"Error getting item details: {e}")
                await query.message.edit_text(
                    "❌ Error getting item details"
                )
                
        elif action == "confirm":
            # Handle deletion confirmation
            media_type = context.user_data.get("delete_type")
            item = context.user_data.get("delete_item")
            
            if not media_type or not item:
                await query.message.edit_text("❌ Item data not found")
                return
                
            try:
                # Delete the item
                if media_type == "movie":
                    success = await self.media_service.delete_movie(item["id"])
                elif media_type == "series":
                    success = await self.media_service.delete_series(item["id"])
                elif media_type == "music":
                    success = await self.media_service.delete_music(item["id"])
                else:
                    await query.message.edit_text("❌ Invalid media type")
                    return
                
                if success:
                    await query.message.edit_text(
                        self.translation.get_message("DeleteSuccess", 
                            subject=media_type,
                            title=item["title"]
                        )
                    )
                else:
                    await query.message.edit_text(
                        self.translation.get_message("DeleteFailed", 
                            subject=media_type,
                            title=item["title"]
                        )
                    )
                    
            except Exception as e:
                logger.error(f"Error deleting item: {e}")
                await query.message.edit_text(
                    self.translation.get_message("DeleteFailed", 
                        subject=media_type,
                        title=item["title"]
                    )
                )