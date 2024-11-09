"""
Filename: media.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Media handler module.

This module handles media-related commands (movies, TV shows, music).
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)

from src.bot.keyboards import get_system_keyboard
from src.utils.logger import get_logger, log_user_interaction
from src.bot.handlers.auth import require_auth
from src.services.media import MediaService
from src.services.translation import TranslationService

logger = get_logger("addarr.media")

# States
SEARCHING = 1
SELECTING = 2
QUALITY_SELECT = 3
SEASON_SELECT = 4

class MediaHandler:
    """Handler for media-related commands"""
    
    def __init__(self):
        self.media_service = MediaService()
        self.translation = TranslationService()
    
    def get_handler(self):
        """Get command handlers for media operations"""
        return [
            ConversationHandler(
                entry_points=[
                    CommandHandler("movie", self.handle_movie),
                    CommandHandler("series", self.handle_series),
                    CommandHandler("music", self.handle_music),
                    CallbackQueryHandler(self.handle_menu_callback, pattern="^menu_(movie|series|music)$")
                ],
                states={
                    SEARCHING: [
                        MessageHandler(
                            filters.TEXT & ~filters.COMMAND,
                            self.handle_search
                        )
                    ],
                    SELECTING: [
                        CallbackQueryHandler(
                            self.handle_selection,
                            pattern="^select_"
                        ),
                        CallbackQueryHandler(
                            self.handle_navigation,
                            pattern="^nav_"
                        )
                    ],
                    QUALITY_SELECT: [
                        CallbackQueryHandler(
                            self.handle_quality_selection,
                            pattern="^quality_"
                        )
                    ],
                    SEASON_SELECT: [
                        CallbackQueryHandler(
                            self.handle_season_selection,
                            pattern="^season_"
                        ),
                        CallbackQueryHandler(
                            self.handle_season_confirm,
                            pattern="^season_confirm$"
                        ),
                        CallbackQueryHandler(
                            self.cancel_search,
                            pattern="^select_cancel$"
                        )
                    ]
                },
                fallbacks=[
                    CommandHandler("cancel", self.cancel_search),
                    CallbackQueryHandler(self.cancel_search, pattern="^select_cancel$")
                ],
                name="media_conversation",
                persistent=False
            ),
            CommandHandler("status", self.handle_status),
            CommandHandler("settings", self.handle_settings)
        ]

    async def handle_menu_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle menu callbacks from StartHandler"""
        if not update.callback_query:
            return ConversationHandler.END
            
        query = update.callback_query
        action = query.data.replace("menu_", "")
        
        # Set search type in context
        context.user_data["search_type"] = action
        
        # Get translated prompt
        prompt = self.translation.get_text("Title")
        cancel_hint = self.translation.get_text("messages.CancelHint", default="(Use /cancel to cancel)")
        
        await query.message.edit_text(
            f"{prompt}\n{cancel_hint}"
        )
        
        return SEARCHING
    
    @require_auth
    async def handle_movie(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start movie search conversation"""
        if not update.effective_message or not update.effective_user:
            return ConversationHandler.END
            
        log_user_interaction(logger, update.effective_user, "/movie")
        
        context.user_data["search_type"] = "movie"
        prompt = self.translation.get_text("Title")
        cancel_hint = self.translation.get_text("messages.CancelHint", default="(Use /cancel to cancel)")
        
        await update.message.reply_text(
            f"{prompt}\n{cancel_hint}"
        )
        return SEARCHING
    
    @require_auth
    async def handle_series(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start series search conversation"""
        if not update.effective_message or not update.effective_user:
            return ConversationHandler.END
            
        log_user_interaction(logger, update.effective_user, "/series")
        
        context.user_data["search_type"] = "series"
        prompt = self.translation.get_text("Title")
        cancel_hint = self.translation.get_text("messages.CancelHint", default="(Use /cancel to cancel)")
        
        await update.message.reply_text(
            f"{prompt}\n{cancel_hint}"
        )
        return SEARCHING
    
    @require_auth
    async def handle_music(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start music search conversation"""
        if not update.effective_message or not update.effective_user:
            return ConversationHandler.END
            
        log_user_interaction(logger, update.effective_user, "/music")
        
        context.user_data["search_type"] = "music"
        prompt = self.translation.get_text("Title")
        cancel_hint = self.translation.get_text("messages.CancelHint", default="(Use /cancel to cancel)")
        
        await update.message.reply_text(
            f"{prompt}\n{cancel_hint}"
        )
        return SEARCHING
    
    async def handle_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle search query"""
        if not update.effective_message:
            return ConversationHandler.END
            
        search_type = context.user_data.get("search_type")
        query = update.message.text
        
        log_user_interaction(
            logger, 
            update.effective_user, 
            f"search_{search_type}", 
            query
        )
        
        try:
            # Use the appropriate service based on search type
            if search_type == "movie":
                results = await self.media_service.search_movies(query)
            elif search_type == "series":
                results = await self.media_service.search_series(query)
            elif search_type == "music":
                results = await self.media_service.search_music(query)
            else:
                await update.message.reply_text("❌ Invalid search type")
                return ConversationHandler.END
            
            if not results:
                await update.message.reply_text(
                    f"❌ No {search_type} found matching '{query}'"
                )
                return ConversationHandler.END
            
            # Store results and current index in context
            context.user_data["search_results"] = results
            context.user_data["current_index"] = 0
            
            # Show first result
            await self._show_result(update.message, results[0], 0, len(results))
            
            return SELECTING
            
        except Exception as e:
            logger.error(f"Error during search: {e}")
            await update.message.reply_text(
                "❌ An error occurred while searching.\n"
                "Please try again later."
            )
            return ConversationHandler.END

    async def _show_result(self, message, result, index: int, total: int):
        """Show a single search result with navigation buttons"""
        try:
            # Create message text - limit overview length to avoid caption too long error
            overview = result.get('overview', 'No overview available')
            if len(overview) > 300:  # Telegram caption limit is 1024 chars
                overview = overview[:297] + "..."
                
            caption = (
                f"*{result['title']}*\n\n"
                f"_{overview}_\n\n"
            )
            
            # Add media-specific details (keep them concise)
            if "year" in result:
                caption += f"📅 Year: {result.get('year', 'N/A')}\n"
                
            # Add ratings based on media type
            if "ratings" in result:
                ratings = result["ratings"]
                if "imdb" in ratings:  # Movie ratings
                    imdb_rating = ratings["imdb"]
                    if imdb_rating != "N/A":
                        imdb_rating = f"{float(imdb_rating):.1f}/10"
                    caption += f"🎭 IMDB: {imdb_rating}\n"
                    
                    rt_rating = ratings.get("rottenTomatoes")
                    if rt_rating and rt_rating != "N/A":
                        rt_rating = f"{rt_rating}%"
                        caption += f"🍅 Rotten Tomatoes: {rt_rating}\n"
                elif "tmdb" in ratings:  # Series ratings
                    tmdb_rating = ratings["tmdb"]
                    if tmdb_rating != "N/A":
                        rating_value = f"{float(tmdb_rating):.1f}/10"
                        votes = ratings.get("votes", 0)
                        caption += f"📊 TMDB: {rating_value} ({votes:,} votes)\n"
            
            # Add studio/network info
            if "studio" in result:
                studio = result.get("studio", "N/A")
                if "network" in result:  # For TV shows
                    network = result.get("network", "N/A")
                    if studio and studio != network:
                        caption += f"📺 Network: {network} ({studio})\n"
                    else:
                        caption += f"📺 Network: {network}\n"
                else:  # For movies
                    caption += f"🎬 Studio: {studio}\n"
                    
            # Add runtime if available
            if "runtime" in result and result["runtime"] != "N/A":
                caption += f"⏱️ Runtime: {result['runtime']} minutes\n"
                    
            # Add genres
            if "genres" in result:
                genres = result.get("genres", [])
                if genres:
                    caption += f"🎭 Genres: {', '.join(genres[:3])}"  # Show first 3 genres
                    if len(genres) > 3:
                        caption += f" +{len(genres) - 3} more"
                    caption += "\n"
            
            caption += f"\n📊 Result {index + 1} of {total}"
            
            # Create navigation keyboard
            keyboard = []
            
            # Add navigation buttons
            nav_buttons = []
            if index > 0:
                nav_buttons.append(
                    InlineKeyboardButton("⬅️ Previous", callback_data=f"nav_prev_{index}")
                )
            if index < total - 1:
                nav_buttons.append(
                    InlineKeyboardButton("➡️ Next", callback_data=f"nav_next_{index}")
                )
            if nav_buttons:
                keyboard.append(nav_buttons)
                
            # Add action buttons
            keyboard.extend([
                [InlineKeyboardButton("✅ Add to Library", callback_data=f"select_{result['id']}")],
                [InlineKeyboardButton("❌ Cancel", callback_data="select_cancel")]
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Get poster URL
            poster_url = result.get("poster")
            
            if poster_url:
                try:
                    # Create new message with photo
                    new_message = await message.reply_photo(
                        photo=poster_url,
                        caption=caption,
                        parse_mode='Markdown',
                        reply_markup=reply_markup
                    )
                    # Delete old message
                    await message.delete()
                    return new_message
                except Exception as e:
                    logger.error(f"Error sending photo: {e}")
                    # Fallback to text-only message
                    new_message = await message.reply_text(
                        caption,
                        parse_mode='Markdown',
                        reply_markup=reply_markup
                    )
                    await message.delete()
                    return new_message
            else:
                # Send text-only message
                new_message = await message.reply_text(
                    caption,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
                await message.delete()
                return new_message
                
        except Exception as e:
            logger.error(f"Error showing result: {e}")
            # Fallback to simple error message
            try:
                new_message = await message.reply_text(
                    "❌ Error displaying result. Please try your search again.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("❌ Cancel", callback_data="select_cancel")
                    ]])
                )
                await message.delete()
                return new_message
            except Exception as e2:
                logger.error(f"Error in fallback message: {e2}")
                return message

    async def handle_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle result selection"""
        if not update.callback_query:
            return ConversationHandler.END
            
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("select_"):
            selection = query.data.replace("select_", "")
            
            if selection == "cancel":
                if query.message.photo:
                    await query.message.edit_caption(
                        "🚫 Search cancelled.\nUse /start to see the main menu."
                    )
                else:
                    await query.message.edit_text(
                        "🚫 Search cancelled.\nUse /start to see the main menu."
                    )
                return ConversationHandler.END
                
            try:
                # Get selected result
                results = context.user_data.get("search_results", [])
                selected = next(
                    (r for r in results if r["id"] == selection),
                    None
                )
                
                if not selected:
                    await self._send_response(
                        query.message,
                        "❌ Error: Selection not found.\nPlease try your search again."
                    )
                    return ConversationHandler.END
                
                # Store selection for later use
                context.user_data["selected_media"] = selected
                
                # Get quality profiles based on media type
                search_type = context.user_data.get("search_type")
                if search_type == "movie":
                    result = await self.media_service.add_movie(selected["id"])
                elif search_type == "series":
                    result = await self.media_service.add_series(selected["id"])
                elif search_type == "music":
                    result = await self.media_service.add_music(selected["id"])
                
                # Handle quality profile selection
                if isinstance(result, dict) and result.get("type") == "quality_selection":
                    context.user_data["quality_data"] = result
                    
                    # Create keyboard with quality profile buttons
                    keyboard = []
                    for profile in result["profiles"]:
                        keyboard.append([
                            InlineKeyboardButton(
                                profile["name"], 
                                callback_data=f"quality_{profile['id']}"
                            )
                        ])
                    keyboard.append([
                        InlineKeyboardButton("❌ Cancel", callback_data="quality_cancel")
                    ])
                    
                    message_text = (
                        f"Adding: {selected['title']}\n\n"
                        f"Please select a quality profile:"
                    )
                    
                    if query.message.photo:
                        await query.message.edit_caption(
                            caption=message_text,
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                    else:
                        await query.message.edit_text(
                            text=message_text,
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                    return QUALITY_SELECT
                else:
                    success, message = result
                    await self._send_response(
                        query.message,
                        f"{'✅' if success else '❌'} {message}"
                    )
                    return ConversationHandler.END
                
            except Exception as e:
                logger.error(f"Error adding media: {e}")
                await self._send_response(
                    query.message,
                    f"❌ An error occurred: {str(e)}"
                )
                return ConversationHandler.END

    async def handle_quality_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle quality profile selection"""
        if not update.callback_query:
            return ConversationHandler.END
            
        query = update.callback_query
        await query.answer()
        
        if query.data == "quality_cancel":
            await self._send_response(
                query.message,
                "🚫 Operation cancelled.\nUse /start to see the main menu."
            )
            return ConversationHandler.END
            
        try:
            # Get quality selection data
            quality_data = context.user_data.get("quality_data")
            selected = context.user_data.get("selected_media")
            search_type = context.user_data.get("search_type")
            
            if not quality_data or not selected:
                await self._send_response(
                    query.message,
                    "❌ Error: Selection data not found.\nPlease try your search again."
                )
                return ConversationHandler.END
            
            # Get selected profile ID
            profile_id = int(query.data.replace("quality_", ""))
            context.user_data["selected_profile_id"] = profile_id
            context.user_data["selected_root_folder"] = quality_data["root_folder"]
            
            # For series, show season selection
            if search_type == "series" and "seasons" in quality_data:
                seasons = quality_data["seasons"]
                keyboard = [
                    # Add season selection mode buttons
                    [InlineKeyboardButton("👁️ Monitor All", callback_data="season_monitor_all")],
                    [InlineKeyboardButton("📺 All Seasons", callback_data="season_all")],
                    [InlineKeyboardButton("🔄 Future Seasons", callback_data="season_future_seasons")],
                    [InlineKeyboardButton("⏩ Future Episodes", callback_data="season_future_episodes")]
                ]
                
                # Add individual season buttons
                for season in seasons:
                    season_num = season.get("seasonNumber")
                    if season_num is not None:
                        keyboard.append([
                            InlineKeyboardButton(
                                f"Season {season_num}",
                                callback_data=f"season_{season_num}"
                            )
                        ])
                
                # Add confirm and cancel buttons
                keyboard.extend([
                    [InlineKeyboardButton("✅ Confirm Selection", callback_data="season_confirm")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="select_cancel")]
                ])
                
                context.user_data["selected_seasons"] = set()  # Store selected seasons
                context.user_data["future_mode"] = None  # Track future mode
                context.user_data["monitor_all"] = False  # Track monitor all mode
                
                await self._send_response(
                    query.message,
                    f"Adding: {selected['title']}\n\n"
                    "Select seasons to download:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return SEASON_SELECT
            
            # For other media types, proceed with adding
            success, message = await self._add_media_with_profile(
                search_type, selected, profile_id, quality_data["root_folder"]
            )
            
            await self._send_response(
                query.message,
                f"{'✅' if success else '❌'} {message}"
            )
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"Error handling quality selection: {e}")
            await self._send_response(
                query.message,
                "❌ An error occurred while processing your selection.\n"
                "Please try again."
            )
            return ConversationHandler.END

    async def handle_season_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle season selection"""
        if not update.callback_query:
            return ConversationHandler.END
            
        query = update.callback_query
        await query.answer()
        
        if query.data == "select_cancel":
            await self._send_response(
                query.message,
                "🚫 Search cancelled.\nUse /start to see the main menu."
            )
            return ConversationHandler.END
            
        if query.data == "season_confirm":
            return await self.handle_season_confirm(update, context)
            
        quality_data = context.user_data.get("quality_data", {})
        seasons = quality_data.get("seasons", [])
        selected_seasons = context.user_data.get("selected_seasons", set())
        future_mode = context.user_data.get("future_mode", None)
        
        action = query.data.replace("season_", "")
        
        # Handle special actions
        if action == "monitor_all":
            # Toggle monitor all mode
            context.user_data["monitor_all"] = not context.user_data.get("monitor_all", False)
            if context.user_data["monitor_all"]:
                # When enabling monitor all, select all seasons and enable future monitoring
                all_season_numbers = {s.get("seasonNumber") for s in seasons if s.get("seasonNumber") is not None}
                selected_seasons.update(all_season_numbers)
                future_mode = "future_seasons"
                context.user_data["selected_seasons"] = selected_seasons
                context.user_data["future_mode"] = future_mode
                # Automatically submit
                return await self.handle_season_confirm(update, context)
            else:
                selected_seasons.clear()
                future_mode = None
        elif action == "all":
            # Toggle between all seasons and no seasons
            all_season_numbers = {s.get("seasonNumber") for s in seasons if s.get("seasonNumber") is not None}
            if selected_seasons == all_season_numbers:
                # If all seasons are selected, clear selection
                selected_seasons.clear()
                future_mode = None
            else:
                # Otherwise, select all seasons
                selected_seasons.clear()
                selected_seasons.update(all_season_numbers)
                future_mode = "all"
        elif action == "future_seasons":
            # Toggle future seasons mode
            future_mode = "future_seasons" if future_mode != "future_seasons" else None
        elif action == "future_episodes":
            # Toggle future episodes mode
            future_mode = "future_episodes" if future_mode != "future_episodes" else None
        else:
            try:
                # Toggle individual season
                season_num = int(action)
                if season_num in selected_seasons:
                    selected_seasons.remove(season_num)
                else:
                    selected_seasons.add(season_num)
            except ValueError:
                pass
        
        # Create new keyboard with updated button states
        keyboard = [
            [InlineKeyboardButton(
                f"{'✅ ' if context.user_data.get('monitor_all') else ''}👁️ Monitor All",
                callback_data="season_monitor_all"
            )],
            [InlineKeyboardButton(
                f"{'✅ ' if future_mode == 'all' else ''}📺 All Seasons",
                callback_data="season_all"
            )],
            [InlineKeyboardButton(
                f"{'✅ ' if future_mode == 'future_seasons' else ''}🔄 Future Seasons",
                callback_data="season_future_seasons"
            )],
            [InlineKeyboardButton(
                f"{'✅ ' if future_mode == 'future_episodes' else ''}⏩ Future Episodes",
                callback_data="season_future_episodes"
            )]
        ]
        
        # Add season buttons with selection status
        for season in seasons:
            season_number = season.get("seasonNumber")
            if season_number is not None:
                # Show checkmark if season is selected or if in "all" mode
                is_selected = (season_number in selected_seasons or 
                             future_mode == "all")
                keyboard.append([
                    InlineKeyboardButton(
                        f"{'✅ ' if is_selected else ''}Season {season_number}",
                        callback_data=f"season_{season_number}"
                    )
                ])
        
        # Add confirm and cancel buttons
        keyboard.extend([
            [InlineKeyboardButton("✅ Confirm Selection", callback_data="season_confirm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="select_cancel")]
        ])
        
        # Store updated selection and mode
        context.user_data["selected_seasons"] = selected_seasons
        context.user_data["future_mode"] = future_mode
        
        # Only update if keyboard has changed
        new_markup = InlineKeyboardMarkup(keyboard)
        if query.message.reply_markup.to_dict() != new_markup.to_dict():
            await query.message.edit_reply_markup(reply_markup=new_markup)
            
        return SEASON_SELECT

    async def handle_season_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle season selection confirmation"""
        if not update.callback_query:
            return ConversationHandler.END
            
        query = update.callback_query
        await query.answer()
        
        try:
            selected = context.user_data.get("selected_media")
            profile_id = context.user_data.get("selected_profile_id")
            root_folder = context.user_data.get("selected_root_folder")
            selected_seasons = list(context.user_data.get("selected_seasons", set()))
            future_mode = context.user_data.get("future_mode")
            monitor_all = context.user_data.get("monitor_all", False)
            
            # Format seasons data based on selection mode
            if monitor_all:
                # Monitor everything (current and future)
                seasons_data = [{"seasonNumber": season.get("seasonNumber"), "monitored": True} 
                              for season in context.user_data.get("quality_data", {}).get("seasons", [])]
                future_mode = "future_seasons"
            elif future_mode == "all":
                # Monitor all current seasons
                seasons_data = [{"seasonNumber": season.get("seasonNumber"), "monitored": True} 
                              for season in context.user_data.get("quality_data", {}).get("seasons", [])]
            elif future_mode == "future_episodes":
                # Only monitor future episodes
                seasons_data = [{"seasonNumber": season.get("seasonNumber"), "monitored": False} 
                              for season in context.user_data.get("quality_data", {}).get("seasons", [])]
                seasons_data.append({"seasonNumber": -1, "monitored": True})  # Special flag for future episodes
            else:
                # Monitor selected seasons and optionally future seasons
                seasons_data = [{"seasonNumber": season.get("seasonNumber"), 
                               "monitored": season.get("seasonNumber") in selected_seasons} 
                              for season in context.user_data.get("quality_data", {}).get("seasons", [])]
                if future_mode == "future_seasons":
                    seasons_data.append({"seasonNumber": -1, "monitored": True})  # Special flag for future seasons
            
            success, message = await self.media_service.add_series_with_profile(
                selected["id"],
                profile_id,
                root_folder,
                seasons_data
            )
            
            await self._send_response(
                query.message,
                f"{'✅' if success else '❌'} {message}"
            )
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"Error confirming season selection: {e}")
            await self._send_response(
                query.message,
                "❌ An error occurred while processing your selection.\n"
                "Please try again."
            )
            return ConversationHandler.END

    async def _add_media_with_profile(self, media_type: str, selected: dict, profile_id: int, root_folder: str) -> tuple[bool, str]:
        """Add media with selected profile"""
        if media_type == "movie":
            return await self.media_service.add_movie_with_profile(
                selected["id"], profile_id, root_folder
            )
        elif media_type == "series":
            return await self.media_service.add_series_with_profile(
                selected["id"], profile_id, root_folder
            )
        elif media_type == "music":
            return await self.media_service.add_music_with_profile(
                selected["id"], profile_id, root_folder
            )
        return False, "Invalid media type"

    async def _send_response(self, message, text: str, reply_markup=None):
        """Send or edit a message based on message type"""
        try:
            if message.photo:
                await message.edit_caption(
                    caption=text,
                    reply_markup=reply_markup
                )
            else:
                await message.edit_text(
                    text=text,
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Error updating message: {e}")
            # Fallback: send new message
            await message.reply_text(text, reply_markup=reply_markup)

    async def cancel_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel the search process"""
        log_user_interaction(logger, update.effective_user, "cancel_search")
        
        # Handle both direct commands and callback queries
        if update.callback_query:
            await self._send_response(
                update.callback_query.message,
                "🚫 Search cancelled.\nUse /start to see the main menu."
            )
        elif update.message:
            await update.message.reply_text(
                "🚫 Search cancelled.\nUse /start to see the main menu."
            )
        return ConversationHandler.END
    
    @require_auth
    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle status check request"""
        try:
            # Get status from all services
            status_text = await self._get_status_text()
            
            if update.callback_query:
                await update.callback_query.message.edit_text(
                    status_text,
                    reply_markup=get_system_keyboard()
                )
            else:
                await update.message.reply_text(
                    status_text,
                    reply_markup=get_system_keyboard()
                )
        except Exception as e:
            logger.error(f"Error in handle_status: {e}")
            error_msg = "❌ Error getting system status. Please try again later."
            if update.callback_query:
                await update.callback_query.message.edit_text(error_msg)
            else:
                await update.message.reply_text(error_msg)
    
    @require_auth
    async def handle_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle settings management"""
        if not update.effective_message or not update.effective_user:
            return
            
        user = update.effective_user
        logger.info(f"⚙️ User {user.username} ({user.id}) accessed settings")
        
        await update.message.reply_text(
            "⚙️ Settings:\n"
            "Settings management coming soon...\n"
            "For now, please use the config.yaml file to manage settings."
        )

    async def handle_navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle navigation between search results"""
        if not update.callback_query:
            return ConversationHandler.END
            
        query = update.callback_query
        await query.answer()
        
        # Extract direction and current index from callback data
        _, direction, current = query.data.split("_")
        current = int(current)
        
        # Get stored results
        results = context.user_data.get("search_results", [])
        
        # Calculate new index
        if direction == "next":
            new_index = current + 1
        else:  # prev
            new_index = current - 1
            
        # Validate index
        if 0 <= new_index < len(results):
            context.user_data["current_index"] = new_index
            # Show the new result
            await self._show_result(query.message, results[new_index], new_index, len(results))
            return SELECTING
        else:
            logger.error(f"Invalid navigation index: {new_index}")
            return SELECTING

    async def _get_status_text(self) -> str:
        """Get status text from all services"""
        try:
            status_lines = ["📊 System Status\n"]
            
            # Get status from media services
            services = {
                "🎬 Radarr": self.media_service.get_radarr_status,
                "📺 Sonarr": self.media_service.get_sonarr_status,
                "🎵 Lidarr": self.media_service.get_lidarr_status,
            }
            
            for service_name, status_func in services.items():
                try:
                    is_available = await status_func()
                    status = "✅ Online" if is_available else "❌ Offline"
                    status_lines.append(f"{service_name}: {status}")
                except Exception as e:
                    logger.error(f"Error getting status for {service_name}: {e}")
                    status_lines.append(f"{service_name}: ❌ Error")
            
            # Get download client status if configured
            try:
                if await self.media_service.get_transmission_status():
                    status_lines.append("\n📥 Transmission: ✅ Connected")
            except:
                pass
                
            try:
                if await self.media_service.get_sabnzbd_status():
                    status_lines.append("📥 SABnzbd: ✅ Connected")
            except:
                pass
            
            return "\n".join(status_lines)
            
        except Exception as e:
            logger.error(f"Error generating status text: {e}")
            return "❌ Error getting system status"