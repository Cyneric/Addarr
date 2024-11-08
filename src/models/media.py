"""
Filename: media.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Media data models module.

This module defines the data structures for different types of media
(movies, series, artists) and their related components (quality profiles,
root folders, etc.). These models ensure consistent data representation
throughout the application.
"""

from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

@dataclass
class MediaItem:
    """Base class for media items"""
    id: str
    title: str
    year: Optional[int]
    overview: Optional[str]
    poster_url: Optional[str]
    
@dataclass
class Movie(MediaItem):
    """Movie data model"""
    tmdb_id: int
    quality_profile_id: Optional[int] = None
    monitored: bool = True
    minimum_availability: str = "announced"
    
@dataclass
class Series(MediaItem):
    """Series data model"""
    tvdb_id: int
    season_count: int
    monitored_seasons: List[int]
    quality_profile_id: Optional[int] = None
    season_folder: bool = True
    
@dataclass
class Artist(MediaItem):
    """Artist data model"""
    artist_id: str
    artist_type: str
    metadata_profile_id: Optional[int] = None
    album_folder: bool = True
    
@dataclass
class QualityProfile:
    """Quality profile data model"""
    id: int
    name: str
    
@dataclass
class RootFolder:
    """Root folder data model"""
    path: str
    free_space: int
    
@dataclass
class Tag:
    """Tag data model"""
    id: int
    label: str
    
@dataclass
class SearchResult:
    """Search result data model"""
    media_type: str
    items: List[MediaItem]
    total_results: int
    page: int = 1 