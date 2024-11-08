"""
Translation service module.

This module handles loading and managing translations for the bot.
"""

import os
import yaml
from typing import Dict, Any
from pathlib import Path

from src.utils.logger import get_logger
from src.config.settings import config

logger = get_logger("addarr.translation")

class TranslationService:
    """Service for handling translations"""
    
    _instance = None
    _translations: Dict[str, Dict[str, Any]] = {}
    _current_language = "en-us"  # Default language
    _fallback_language = "en-us"  # Fallback language
    
    def __new__(cls):
        """Ensure only one instance exists"""
        if cls._instance is None:
            cls._instance = super(TranslationService, cls).__new__(cls)
            cls._initialize()
        return cls._instance
    
    @classmethod
    def _initialize(cls):
        """Initialize the translation service"""
        cls._load_translations()
        # Set current language from config
        cls._current_language = config.get("language", cls._fallback_language)
        
    @classmethod
    def _load_translations(cls):
        """Load all translation files"""
        translations_dir = Path("translations")
        if not translations_dir.exists():
            logger.error("❌ Translations directory not found")
            return
            
        for file in translations_dir.glob("addarr.*.yml"):
            try:
                lang_code = file.stem.split('.')[1]  # Get language code from filename
                with open(file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if data and lang_code in data:
                        cls._translations[lang_code] = data[lang_code]
                        logger.info(f"✅ Loaded translations for {lang_code}")
                    else:
                        logger.warning(f"⚠️ Invalid translation file format: {file}")
            except Exception as e:
                logger.error(f"❌ Error loading translation file {file}: {e}")
    
    @property
    def current_language(self) -> str:
        """Get current language code"""
        return self._current_language
    
    @property
    def fallback_language(self) -> str:
        """Get fallback language code"""
        return self._fallback_language
    
    def get_text(self, key: str, **kwargs) -> str:
        """
        Get translated text for a given key with parameter substitution.
        
        Args:
            key: The translation key to look up
            **kwargs: Format parameters to substitute in the text
            
        Returns:
            The translated and formatted text
        """
        try:
            # Get the translation for the current language
            current = self._translations.get(self._current_language, {}).get(key)
            
            # If not found, try fallback language
            if not current:
                current = self._translations.get(self._fallback_language, {}).get(key)
            
            # If still not found, return the key itself
            if not current:
                logger.warning(f"⚠️ Translation not found for key: {key}")
                return key
            
            # Format the string using %-formatting
            return current % kwargs
            
        except Exception as e:
            logger.error(f"Translation error for key '{key}': {str(e)}")
            return key
    
    def get_message(self, key: str, subject: str = None, title: str = None, **kwargs) -> str:
        """Get a message translation with subject handling
        
        Args:
            key: Message key
            subject: Subject type (movie, series, music)
            title: Title of the media
            **kwargs: Additional format parameters
            
        Returns:
            str: Formatted message
        """
        params = kwargs.copy()
        
        if subject:
            # Get subject translations
            params["subject"] = self.get_text(subject)
            params["subjectWithArticle"] = self.get_text(f"{subject}WithArticle")
            
        if title:
            params["title"] = title
            
        return self.get_text(f"messages.{key}", **params)