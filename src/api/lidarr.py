"""
Lidarr API client module.
"""

import aiohttp
from typing import Optional, List, Dict, Any
import logging
from colorama import Fore
import json

from src.config.settings import config
from src.utils.logger import get_logger

logger = get_logger("addarr.lidarr")

class LidarrClient:
    """Lidarr API client"""
    
    def __init__(self):
        """Initialize Lidarr API client"""
        lidarr_config = config.get("lidarr", {})
        server_config = lidarr_config.get("server", {})
        auth_config = lidarr_config.get("auth", {})
        
        # Build API URL from server config
        protocol = "https" if server_config.get("ssl", False) else "http"
        addr = server_config.get("addr")
        port = server_config.get("port")
        path = server_config.get("path", "").rstrip('/')
        
        if not addr or not port:
            logger.error(Fore.RED + "❌ Lidarr server address or port not configured")
            raise ValueError("Lidarr server address or port not configured")
            
        self.api_url = f"{protocol}://{addr}:{port}{path}"
        self.api_key = auth_config.get("apikey")
        
        if not self.api_key:
            logger.error(Fore.RED + "❌ Lidarr API key not configured")
            raise ValueError("Lidarr API key not configured")
            
        self.headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json"
        }
        logger.info(Fore.GREEN + f"✅ Lidarr API client initialized: {self.api_url}")
        
    async def _make_request(self, endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Any:
        """Make API request to Lidarr"""
        url = f"{self.api_url}/api/v1/{endpoint}"  # Note: Lidarr uses v1
        logger.info(Fore.BLUE + f"🌐 API Request: {method} {url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, headers=self.headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(Fore.GREEN + f"✅ API Response: {response.status}")
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(Fore.RED + f"❌ API request failed ({response.status}): {error_text}")
                        return None
                        
        except aiohttp.ClientError as e:
            logger.error(Fore.RED + f"❌ Connection error: {str(e)}")
            return None
        except Exception as e:
            logger.error(Fore.RED + f"❌ Unexpected error: {str(e)}")
            return None
            
    async def search(self, term: str) -> List[Dict]:
        """Search for artists"""
        try:
            logger.info(Fore.BLUE + f"🔍 Searching Lidarr for: {term}")
            results = await self._make_request(f"artist/lookup?term={term}")
            
            if not results:
                logger.warning(Fore.YELLOW + f"⚠️ No results found for: {term}")
                return []
                
            logger.info(Fore.GREEN + f"✅ Found {len(results)} results for: {term}")
            return results
            
        except Exception as e:
            logger.error(Fore.RED + f"❌ Search failed: {str(e)}")
            return []
            
    async def get_artist(self, artist_id: str) -> Optional[Dict]:
        """Get artist by ID"""
        try:
            logger.info(f"🔍 Looking up artist ID: {artist_id}")
            
            # First try direct lookup with musicbrainz ID
            results = await self._make_request(f"artist/lookup?term=lidarr:{artist_id}")
            if results and isinstance(results, list) and results[0]:
                logger.info(f"✅ Found artist: {results[0].get('artistName')}")
                return results[0]
            
            # If that fails, try regular search
            results = await self._make_request(f"artist/lookup?term={artist_id}")
            if results and isinstance(results, list):
                # Try to find exact match by ID
                for result in results:
                    if result.get("foreignArtistId") == artist_id:
                        logger.info(f"✅ Found artist: {result.get('artistName')}")
                        return result
                
                # If no exact match but we have results, use first one
                if results[0]:
                    logger.info(f"✅ Found artist: {results[0].get('artistName')}")
                    return results[0]
            
            logger.warning(f"⚠️ No artist found with ID: {artist_id}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to get artist: {str(e)}")
            return None

    async def add_artist(self, artist_id: str, root_folder: str = None, quality_profile_id: int = None) -> tuple[bool, str]:
        """Add an artist to Lidarr"""
        try:
            # Get artist details from search results
            lookup_response = await self._make_request(f"artist/lookup?term=lidarr:{artist_id}")
            if not lookup_response or not isinstance(lookup_response, list):
                # Try regular search if lidarr: prefix fails
                lookup_response = await self._make_request(f"artist/lookup?term={artist_id}")
                if not lookup_response or not isinstance(lookup_response, list):
                    logger.error(f"❌ No artist found with ID: {artist_id}")
                    return False, "Artist not found"

            # Find the correct artist in results
            artist = None
            for result in lookup_response:
                if result.get("foreignArtistId") == artist_id:
                    artist = result
                    break
            
            # If no exact match, use first result
            if not artist and lookup_response:
                artist = lookup_response[0]

            if not artist:
                logger.error(f"❌ No artist found with ID: {artist_id}")
                return False, "Artist not found"
            
            data = {
                "foreignArtistId": artist["foreignArtistId"],
                "artistName": artist["artistName"],
                "qualityProfileId": quality_profile_id or 1,  # Default profile if not specified
                "metadataProfileId": 1,  # Default metadata profile
                "rootFolderPath": root_folder or "/music",  # Default path if not specified
                "monitored": True,
                "addOptions": {
                    "searchForMissingAlbums": True
                }
            }
            
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"{self.api_url}/api/v1/artist"
                    async with session.post(url, headers=self.headers, json=data) as response:
                        response_text = await response.text()
                        
                        # Check if response can be parsed as JSON
                        try:
                            response_data = json.loads(response_text)
                            
                            # If we get an artist object back, it was successful
                            if isinstance(response_data, dict) and response_data.get("id"):
                                logger.info(f"✅ Successfully added artist: {artist['artistName']}")
                                return True, f"Successfully added {artist['artistName']}"
                                
                            # If we get an error array back
                            if isinstance(response_data, list) and response_data:
                                error_msg = response_data[0].get("errorMessage")
                                if error_msg:
                                    if "already exists" in error_msg.lower():
                                        logger.info(f"ℹ️ Artist already exists: {artist['artistName']}")
                                        return False, f"{artist['artistName']} is already in your library"
                                    logger.warning(f"⚠️ API Error: {error_msg}")
                                    return False, error_msg
                                    
                        except json.JSONDecodeError:
                            pass
                        
                        # If we can't parse the response or don't recognize the format
                        if response.status == 201 or response.status == 200:
                            logger.info(f"✅ Successfully added artist: {artist['artistName']}")
                            return True, f"Successfully added {artist['artistName']}"
                        else:
                            logger.error(f"❌ Failed to add artist: {response_text}")
                            return False, f"Failed to add {artist['artistName']}"
                        
            except aiohttp.ClientError as e:
                logger.error(f"❌ Connection error: {str(e)}")
                return False, f"Connection error: {str(e)}"
            except Exception as e:
                logger.error(f"❌ Error adding artist: {str(e)}")
                return False, str(e)

        except Exception as e:
            logger.error(f"❌ Error in add_artist: {str(e)}")
            return False, str(e)

    async def get_root_folders(self) -> List[str]:
        """Get available root folders"""
        try:
            results = await self._make_request("rootFolder")
            if results:
                return [folder["path"] for folder in results]
            return []
        except Exception as e:
            logger.error(f"Failed to get root folders: {str(e)}")
            return []

    async def get_quality_profiles(self) -> List[Dict]:
        """Get available quality profiles"""
        try:
            logger.info("🔍 Getting quality profiles from Lidarr")
            results = await self._make_request("qualityprofile")
            
            if not results:
                logger.warning("⚠️ No quality profiles found")
                return []
            
            profiles = [
                {
                    "id": profile["id"],
                    "name": profile["name"],
                    "description": profile.get("upgradeAllowed", False) and "Upgrades allowed" or "No upgrades"
                }
                for profile in results
            ]
            
            logger.info(f"✅ Found {len(profiles)} quality profiles")
            return profiles
            
        except Exception as e:
            logger.error(f"❌ Failed to get quality profiles: {str(e)}")
            return []

    async def get_metadata_profiles(self) -> List[Dict]:
        """Get available metadata profiles"""
        try:
            results = await self._make_request("metadataprofile")
            if results:
                return [{"id": profile["id"], "name": profile["name"]} for profile in results]
            return []
        except Exception as e:
            logger.error(f"Failed to get metadata profiles: {str(e)}")
            return []

    async def check_status(self) -> bool:
        """Check if Lidarr is available"""
        try:
            result = await self._make_request("system/status")
            return result is not None
        except Exception as e:
            logger.error(f"Error checking Lidarr status: {e}")
            return False