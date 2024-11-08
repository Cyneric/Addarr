"""
Filename: keyboards.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Keyboard layouts module.

This module provides centralized keyboard layouts for the bot.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict
from src.services.translation import TranslationService

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Get the main menu keyboard"""
    translation = TranslationService()
    keyboard = [
        [
            InlineKeyboardButton(
                f"🎬 {translation.get_text('Movie')}", 
                callback_data="menu_movie"
            ),
            InlineKeyboardButton(
                f"📺 {translation.get_text('Series')}", 
                callback_data="menu_series"
            ),
        ],
        [
            InlineKeyboardButton(
                f"🎵 {translation.get_text('Music')}", 
                callback_data="menu_music"
            ),
            InlineKeyboardButton(
                f"🗑 {translation.get_text('Delete')}", 
                callback_data="menu_delete"
            ),
        ],
        [
            InlineKeyboardButton(
                f"⚙️ {translation.get_text('Settings')}", 
                callback_data="menu_settings"
            ),
            InlineKeyboardButton(
                f"📊 {translation.get_text('Status')}", 
                callback_data="menu_status"
            ),
        ],
        [
            InlineKeyboardButton(
                f"❓ {translation.get_text('HelpButton')}", 
                callback_data="menu_help"
            ),
            InlineKeyboardButton(
                f"❌ {translation.get_text('Cancel')}", 
                callback_data="menu_cancel"
            ),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_system_keyboard() -> InlineKeyboardMarkup:
    """Get system status keyboard"""
    translation = TranslationService()
    keyboard = [
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="system_refresh"),
            InlineKeyboardButton("📊 Details", callback_data="system_details")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data="system_back")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_media_results_keyboard(results: List[Dict], show_next: bool = True) -> InlineKeyboardMarkup:
    """Get keyboard for media search results"""
    translation = TranslationService()
    keyboard = [
        [InlineKeyboardButton(result["title"], callback_data=f"select_{result['id']}")]
        for result in results
    ]
    
    nav_buttons = []
    if show_next:
        nav_buttons.append(
            InlineKeyboardButton(
                f"➡️ {translation.get_text('Next result')}", 
                callback_data="nav_next"
            )
        )
    
    if nav_buttons:
        keyboard.append(nav_buttons)
        
    keyboard.append([
        InlineKeyboardButton(
            f"❌ {translation.get_text('Stop')}", 
            callback_data="select_cancel"
        )
    ])
    
    return InlineKeyboardMarkup(keyboard)

def get_delete_keyboard(items: List[Dict]) -> InlineKeyboardMarkup:
    """Get keyboard for delete selection"""
    translation = TranslationService()
    keyboard = [
        [InlineKeyboardButton(item["title"], callback_data=f"delete_{item['id']}")]
        for item in items
    ]
    keyboard.append([
        InlineKeyboardButton(
            f"❌ {translation.get_text('StopDelete')}", 
            callback_data="delete_cancel"
        )
    ])
    return InlineKeyboardMarkup(keyboard)

def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Get settings menu keyboard"""
    translation = TranslationService()
    keyboard = [
        [
            InlineKeyboardButton("🎬 Radarr", callback_data="settings_radarr"),
            InlineKeyboardButton("📺 Sonarr", callback_data="settings_sonarr")
        ],
        [
            InlineKeyboardButton("🎵 Lidarr", callback_data="settings_lidarr"),
            InlineKeyboardButton("📥 Downloads", callback_data="settings_downloads")
        ],
        [
            InlineKeyboardButton("👥 Users", callback_data="settings_users"),
            InlineKeyboardButton(
                f"🌐 {translation.get_text('Language')}", 
                callback_data="settings_language"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back", 
                callback_data="menu_back"
            )
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_confirmation_keyboard(action: str) -> InlineKeyboardMarkup:
    """Get confirmation keyboard"""
    translation = TranslationService()
    keyboard = [
        [
            InlineKeyboardButton(
                f"✅ {translation.get_text('Add')}", 
                callback_data=f"confirm_{action}"
            ),
            InlineKeyboardButton(
                f"❌ {translation.get_text('Stop')}", 
                callback_data="confirm_cancel"
            )
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard() -> InlineKeyboardMarkup:
    """Get simple back to menu keyboard"""
    keyboard = [
        [InlineKeyboardButton("🔙 Back", callback_data="menu_back")]
    ]
    return InlineKeyboardMarkup(keyboard) 