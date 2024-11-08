"""
Filename: media.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Media service module.

This module handles interactions with media services (Radarr, Sonarr, Lidarr).
"""

from typing import List, Dict, Any
from colorama import Fore

from src.utils.logger import get_logger
from src.config.settings import config
from src.api.radarr import RadarrClient
from src.api.sonarr import SonarrClient
from src.api.lidarr import LidarrClient

logger = get_logger("addarr.services.media")

class MediaService:
    """Service for handling media operations"""
    
    # Class-level storage for singleton instances
    _instance = None
    _radarr = None
    _sonarr = None
    _lidarr = None
    
    def __new__(cls):
        """Ensure only one instance of MediaService exists"""
        if cls._instance is None:
            cls._instance = super(MediaService, cls).__new__(cls)
            cls._initialize_clients()
        return cls._instance
    
    @classmethod
    def _initialize_clients(cls):
        """Initialize API clients if not already initialized"""
        # Initialize Radarr
        if cls._radarr is None:
            try:
                if config.get("radarr", {}).get("enable"):
                    cls._radarr = RadarrClient()
            except Exception as e:
                logger.error(f"Failed to initialize Radarr client: {e}")
                cls._radarr = None
        
        # Initialize Sonarr
        if cls._sonarr is None:
            try:
                if config.get("sonarr", {}).get("enable"):
                    cls._sonarr = SonarrClient()
            except Exception as e:
                logger.error(f"Failed to initialize Sonarr client: {e}")
                cls._sonarr = None
        
        # Initialize Lidarr
        if cls._lidarr is None:
            try:
                if config.get("lidarr", {}).get("enable"):
                    cls._lidarr = LidarrClient()
            except Exception as e:
                logger.error(f"Failed to initialize Lidarr client: {e}")
                cls._lidarr = None
    
    def __init__(self):
        """Initialize the service"""
        self.transmission = None
        self.sabnzbd = None
        
        # Initialize download clients if enabled
        try:
            if config.get("transmission", {}).get("enable"):
                from src.api.transmission import TransmissionClient
                self.transmission = TransmissionClient()
        except ImportError:
            logger.warning("Transmission module not available")
            
        try:
            if config.get("sabnzbd", {}).get("enable"):
                from src.api.sabnzbd import SabnzbdClient
                self.sabnzbd = SabnzbdClient()
        except ImportError:
            logger.warning("SABnzbd module not available")
    
    @property
    def radarr(self):
        return self._radarr
    
    @property
    def sonarr(self):
        return self._sonarr
    
    @property
    def lidarr(self):
        return self._lidarr
    
    async def search_movies(self, query: str) -> List[Dict]:
        """Search for movies using Radarr"""
        if not self.radarr:
            raise ValueError("Radarr is not enabled or configured")
            
        try:
            results = await self.radarr.search(query)
            return [
                {
                    "id": str(movie["tmdbId"]),
                    "title": f"{movie['title']} ({movie.get('year', 'N/A')})",
                    "overview": movie.get("overview", "No overview available"),
                    "year": movie.get("year"),
                    "poster": (
                        # Try Radarr image first
                        next((img["remoteUrl"] for img in movie.get("images", []) 
                             if img.get("coverType", "").lower() == "poster"), None)
                        # Fallback to TMDB
                        or (f"https://image.tmdb.org/t/p/w500/{movie.get('remotePoster')}"
                            if movie.get("remotePoster")
                            else None)
                    ),
                    "ratings": {
                        "imdb": movie.get("ratings", {}).get("imdb", {}).get("value", "N/A"),
                        "rottenTomatoes": movie.get("ratings", {}).get("rottenTomatoes", {}).get("value", "N/A")
                    },
                    "studio": movie.get("studio", "N/A"),  # Added studio info
                    "status": movie.get("status", "unknown"),
                    "runtime": movie.get("runtime", "N/A"),
                    "genres": movie.get("genres", []),  # Full genre list
                    "data": movie
                }
                for movie in results
                if movie.get("tmdbId")
            ]
        except Exception as e:
            logger.error(f"Error searching movies: {e}")
            raise
    
    async def search_series(self, query: str) -> List[Dict]:
        """Search for TV series using Sonarr"""
        if not self.sonarr:
            raise ValueError("Sonarr is not enabled or configured")
            
        try:
            results = await self.sonarr.search(query)
            return [
                {
                    "id": str(series["tvdbId"]),
                    "title": f"{series['title']} ({series.get('year', 'N/A')})",
                    "overview": series.get("overview", "No overview available"),
                    "year": series.get("year"),
                    "poster": (
                        # Try Sonarr image first
                        next((img["remoteUrl"] for img in series.get("images", []) 
                             if img.get("coverType", "").lower() == "poster"), None)
                        # Fallback to TVDB
                        or (f"https://artworks.thetvdb.com/banners/{series.get('remotePoster')}"
                            if series.get('remotePoster')
                            else None)
                    ),
                    "ratings": {
                        "tmdb": series.get("ratings", {}).get("tmdb", {}).get("value", "N/A"),
                        "votes": series.get("ratings", {}).get("tmdb", {}).get("votes", 0)
                    },
                    "network": series.get("network", "N/A"),
                    "studio": series.get("studio", "N/A"),  # Added studio info
                    "status": series.get("status", "unknown"),
                    "seasons": len(series.get("seasons", [])),
                    "runtime": series.get("runtime", "N/A"),
                    "genres": series.get("genres", []),  # Full genre list
                    "data": series
                }
                for series in results
                if series.get("tvdbId")
            ]
        except Exception as e:
            logger.error(f"Error searching series: {e}")
            raise
    
    async def search_music(self, query: str) -> List[Dict]:
        """Search for music using Lidarr"""
        if not self.lidarr:
            raise ValueError("Lidarr is not enabled or configured")
            
        try:
            results = await self.lidarr.search(query)
            return [
                {
                    "id": str(artist["foreignArtistId"]),
                    "title": artist["artistName"],
                    "overview": artist.get("overview", "No overview available"),
                    "year": artist.get("statistics", {}).get("yearStart", "N/A"),
                    "poster": (
                        # Try Lidarr image first
                        next((img["remoteUrl"] for img in artist.get("images", []) 
                             if img.get("coverType", "").lower() in ["poster", "cover"]), None)
                        # Try MusicBrainz image
                        or (f"https://coverartarchive.org/release-group/{artist.get('foreignArtistId')}/front"
                            if artist.get("foreignArtistId")
                            else None)
                        # Try Last.fm image as final fallback
                        or (f"https://ws.audioscrobbler.com/2.0/?method=artist.getinfo"
                            f"&artist={artist['artistName']}&format=json"
                            if artist.get('artistName')
                            else None)
                    ),
                    "rating": artist.get("ratings", {}).get("value", "N/A"),
                    "genres": ", ".join(artist.get("genres", ["Unknown"])),
                    "type": artist.get("artistType", "Unknown"),
                    "status": artist.get("status", "unknown"),
                    "data": artist
                }
                for artist in results
                if artist.get("foreignArtistId")
            ]
        except Exception as e:
            logger.error(f"Error searching music: {e}")
            raise
    
    async def add_movie(self, tmdb_id: str) -> tuple[bool, str]:
        """Add a movie to Radarr"""
        if not self.radarr:
            raise ValueError("Radarr is not enabled or configured")
            
        try:
            # Get root folder and quality profiles
            root_folders = await self.radarr.get_root_folders()
            if not root_folders:
                return False, "No root folders configured in Radarr"
                
            quality_profiles = await self.radarr.get_quality_profiles()
            if not quality_profiles:
                return False, "No quality profiles configured in Radarr"
            
            # Get movie details using proper lookup endpoint
            lookup_results = await self.radarr.get_movie(tmdb_id)  # Use get_movie instead of search
            if not lookup_results:
                return False, "Movie not found"
            
            movie = lookup_results
            
            # Format quality profiles for selection
            profile_text = "Select quality profile:\n\n"
            for i, profile in enumerate(quality_profiles, 1):
                profile_text += f"{i}. {profile['name']}\n"
            
            # Store information for later use
            return {
                "type": "quality_selection",
                "profiles": quality_profiles,
                "root_folder": root_folders[0],  # Use first root folder for now
                "movie": movie,
                "message": profile_text
            }
            
        except Exception as e:
            logger.error(f"❌ Error in MediaService.add_movie: {str(e)}")
            return False, str(e)
            
    async def add_movie_with_profile(self, tmdb_id: str, profile_id: int, root_folder: str) -> tuple[bool, str]:
        """Add a movie to Radarr with selected quality profile"""
        if not self.radarr:
            raise ValueError("Radarr is not enabled or configured")
            
        try:
            # Add the movie with selected profile
            success, message = await self.radarr.add_movie(
                int(tmdb_id),
                root_folder,
                profile_id
            )
            
            if success:
                logger.info(f"✅ Movie added successfully")
            else:
                logger.info(f"ℹ️ {message}")
                
            return success, message
            
        except Exception as e:
            logger.error(f"❌ Error in MediaService.add_movie: {str(e)}")
            return False, str(e)
    
    async def add_series(self, tvdb_id: str) -> tuple[bool, str]:
        """Add a TV series to Sonarr"""
        if not self.sonarr:
            raise ValueError("Sonarr is not enabled or configured")
            
        try:
            # Get root folder and quality profiles
            root_folders = await self.sonarr.get_root_folders()
            if not root_folders:
                return False, "No root folders configured in Sonarr"
                
            quality_profiles = await self.sonarr.get_quality_profiles()
            if not quality_profiles:
                return False, "No quality profiles configured in Sonarr"
            
            # Get series details and seasons
            lookup_results = await self.sonarr.get_series(tvdb_id)
            if not lookup_results:
                return False, "Series not found"
                
            seasons = await self.sonarr.get_seasons(tvdb_id)
            if not seasons:
                return False, "No seasons found for series"
            
            series = lookup_results
            
            # Format quality profiles for selection
            profile_text = "Select quality profile:\n\n"
            for i, profile in enumerate(quality_profiles, 1):
                profile_text += f"{i}. {profile['name']}\n"
            
            # Store information for later use
            return {
                "type": "quality_selection",
                "profiles": quality_profiles,
                "root_folder": root_folders[0],  # Use first root folder for now
                "series": series,
                "seasons": seasons,  # Add seasons to context
                "message": profile_text
            }
            
        except Exception as e:
            logger.error(f"❌ Error in MediaService.add_series: {str(e)}")
            return False, str(e)
            
    async def add_series_with_profile(self, tvdb_id: str, profile_id: int, root_folder: str, selected_seasons: List[int] = None) -> tuple[bool, str]:
        """Add a series to Sonarr with selected quality profile and seasons"""
        if not self.sonarr:
            raise ValueError("Sonarr is not enabled or configured")
            
        try:
            # Get all seasons
            seasons = await self.sonarr.get_seasons(tvdb_id)
            
            # Format season data
            season_data = []
            for season in seasons:
                season_number = season.get("seasonNumber")
                if season_number is not None:
                    season_data.append({
                        "seasonNumber": season_number,
                        "monitored": selected_seasons is None or season_number in selected_seasons
                    })
            
            # Add the series with selected profile and seasons
            success, message = await self.sonarr.add_series(
                int(tvdb_id),
                root_folder,
                profile_id,
                season_data
            )
            
            if success:
                logger.info(f"✅ Series added successfully")
            else:
                logger.info(f"ℹ️ {message}")
                
            return success, message
            
        except Exception as e:
            logger.error(f"❌ Error in MediaService.add_series: {str(e)}")
            return False, str(e)
    
    async def add_music(self, artist_id: str) -> tuple[bool, str]:
        """Add an artist to Lidarr"""
        if not self.lidarr:
            raise ValueError("Lidarr is not enabled or configured")
            
        try:
            # Get root folder and quality profiles
            root_folders = await self.lidarr.get_root_folders()
            if not root_folders:
                return False, "No root folders configured in Lidarr"
                
            quality_profiles = await self.lidarr.get_quality_profiles()
            if not quality_profiles:
                return False, "No quality profiles configured in Lidarr"
            
            # Get artist details
            lookup_results = await self.lidarr.get_artist(artist_id)
            if not lookup_results:
                return False, "Artist not found"
            
            artist = lookup_results
            
            # Format quality profiles for selection
            profile_text = "Select quality profile:\n\n"
            for i, profile in enumerate(quality_profiles, 1):
                profile_text += f"{i}. {profile['name']}\n"
            
            # Store information for later use
            return {
                "type": "quality_selection",
                "profiles": quality_profiles,
                "root_folder": root_folders[0],  # Use first root folder for now
                "artist": artist,
                "message": profile_text
            }
            
        except Exception as e:
            logger.error(f"❌ Error in MediaService.add_music: {str(e)}")
            return False, str(e)
            
    async def add_music_with_profile(self, artist_id: str, profile_id: int, root_folder: str) -> tuple[bool, str]:
        """Add an artist to Lidarr with selected quality profile"""
        if not self.lidarr:
            raise ValueError("Lidarr is not enabled or configured")
            
        try:
            # Add the artist with selected profile
            success, message = await self.lidarr.add_artist(
                artist_id,
                root_folder,
                profile_id
            )
            
            if success:
                logger.info(f"✅ Artist added successfully")
            else:
                logger.info(f"ℹ️ {message}")
                
            return success, message
            
        except Exception as e:
            logger.error(f"❌ Error in MediaService.add_music: {str(e)}")
            return False, str(e)

    async def get_radarr_status(self) -> bool:
        """Check if Radarr is available"""
        try:
            return await self.radarr.check_status() if self.radarr else False
        except Exception as e:
            logger.error(f"Error checking Radarr status: {e}")
            return False

    async def get_sonarr_status(self) -> bool:
        """Check if Sonarr is available"""
        try:
            return await self.sonarr.check_status() if self.sonarr else False
        except Exception as e:
            logger.error(f"Error checking Sonarr status: {e}")
            return False

    async def get_lidarr_status(self) -> bool:
        """Check if Lidarr is available"""
        try:
            return await self.lidarr.check_status() if self.lidarr else False
        except Exception as e:
            logger.error(f"Error checking Lidarr status: {e}")
            return False

    async def get_transmission_status(self) -> bool:
        """Check if Transmission is available"""
        try:
            return await self.transmission.check_status() if self.transmission else False
        except Exception as e:
            logger.error(f"Error checking Transmission status: {e}")
            return False

    async def get_sabnzbd_status(self) -> bool:
        """Check if SABnzbd is available"""
        try:
            return await self.sabnzbd.check_status() if self.sabnzbd else False
        except Exception as e:
            logger.error(f"Error checking SABnzbd status: {e}")
            return False