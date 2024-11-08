"""
Filename: __init__.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Data models package.

This package contains all the data models used throughout the application,
including models for media items (movies, series, artists) and notifications.
These models provide type safety and structure for data handling.
"""

from .media import MediaItem, Movie, Series, Artist, SearchResult, QualityProfile, RootFolder, Tag
from .notification import Notification, NotificationType

__all__ = [
    'MediaItem', 'Movie', 'Series', 'Artist', 'SearchResult',
    'QualityProfile', 'RootFolder', 'Tag',
    'Notification', 'NotificationType'
]
