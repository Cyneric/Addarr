"""
Filename: sonarr.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Sonarr API client module.
"""

import aiohttp
from typing import Optional, List, Dict, Any
import logging
from colorama import Fore
import json

from src.config.settings import config
from src.utils.logger import get_logger

logger = get_logger("addarr.sonarr")

class SonarrClient:
    """Sonarr API client"""
    
    def __init__(self):
        """Initialize Sonarr API client"""
        sonarr_config = config.get("sonarr", {})
        server_config = sonarr_config.get("server", {})
        auth_config = sonarr_config.get("auth", {})
        
        # Build API URL from server config
        protocol = "https" if server_config.get("ssl", False) else "http"
        addr = server_config.get("addr")
        port = server_config.get("port")
        path = server_config.get("path", "").rstrip('/')
        
        if not addr or not port:
            logger.error(Fore.RED + "❌ Sonarr server address or port not configured")
            raise ValueError("Sonarr server address or port not configured")
            
        self.api_url = f"{protocol}://{addr}:{port}{path}"
        self.api_key = auth_config.get("apikey")
        
        if not self.api_key:
            logger.error(Fore.RED + "❌ Sonarr API key not configured")
            raise ValueError("Sonarr API key not configured")
            
        self.headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json"
        }
        logger.info(Fore.GREEN + f"✅ Sonarr API client initialized: {self.api_url}")
        
    async def _make_request(self, endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Any:
        """Make API request to Sonarr"""
        url = f"{self.api_url}/api/v3/{endpoint}"
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
        """Search for TV series"""
        try:
            logger.info(Fore.BLUE + f"🔍 Searching Sonarr for: {term}")
            results = await self._make_request(f"series/lookup?term={term}")
            
            if not results:
                logger.warning(Fore.YELLOW + f"⚠️ No results found for: {term}")
                return []
                
            logger.info(Fore.GREEN + f"✅ Found {len(results)} results for: {term}")
            return results
            
        except Exception as e:
            logger.error(Fore.RED + f"❌ Search failed: {str(e)}")
            return []

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
            results = await self._make_request("qualityProfile")
            if results:
                return [{"id": profile["id"], "name": profile["name"]} for profile in results]
            return []
        except Exception as e:
            logger.error(f"Failed to get quality profiles: {str(e)}")
            return []

    async def get_seasons(self, tvdb_id: str) -> List[Dict]:
        """Get available seasons for a series"""
        try:
            logger.info(f"🔍 Getting seasons for series with TVDB ID: {tvdb_id}")
            results = await self._make_request(f"series/lookup?term=tvdb:{tvdb_id}")
            
            if results and isinstance(results, list) and results[0]:
                series = results[0]
                seasons = series.get("seasons", [])
                logger.info(f"✅ Found {len(seasons)} seasons")
                return seasons
                
            logger.warning(f"⚠️ No seasons found for TVDB ID: {tvdb_id}")
            return []
            
        except Exception as e:
            logger.error(f"❌ Failed to get seasons: {str(e)}")
            return []

    async def add_series(self, tvdb_id: int, root_folder: str, quality_profile_id: int, seasons: List[Dict] = None) -> tuple[bool, str]:
        """Add a TV series to Sonarr with optional season selection"""
        try:
            # Get series details from search results
            lookup_response = await self._make_request(f"series/lookup?term=tvdb:{tvdb_id}")
            if not lookup_response or not isinstance(lookup_response, list) or not lookup_response[0]:
                logger.error(f"❌ No series found with TVDB ID: {tvdb_id}")
                return False, "Series not found"

            series = lookup_response[0]  # Use first result
            
            data = {
                "tvdbId": series["tvdbId"],
                "title": series["title"],
                "qualityProfileId": quality_profile_id,
                "rootFolderPath": root_folder,
                "monitored": True,
                "addOptions": {
                    "searchForMissingEpisodes": True
                }
            }
            
            # Add season selection if provided
            if seasons is not None:
                data["seasons"] = seasons
            
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"{self.api_url}/api/v3/series"
                    async with session.post(url, headers=self.headers, json=data) as response:
                        response_text = await response.text()
                        
                        # Check if response can be parsed as JSON
                        try:
                            response_data = json.loads(response_text)
                            
                            # If we get a series object back, it was successful
                            if isinstance(response_data, dict) and response_data.get("id"):
                                logger.info(f"✅ Successfully added series: {series['title']}")
                                return True, f"Successfully added {series['title']}"
                                
                            # If we get an error array back
                            if isinstance(response_data, list) and response_data:
                                error_msg = response_data[0].get("errorMessage")
                                if error_msg:
                                    if "already" in error_msg.lower():
                                        logger.info(f"ℹ️ Series already exists: {series['title']}")
                                        return False, f"{series['title']} is already in your library"
                                    logger.warning(f"⚠️ API Error: {error_msg}")
                                    return False, error_msg
                                    
                        except json.JSONDecodeError:
                            pass
                        
                        # If we can't parse the response or don't recognize the format
                        if response.status == 201 or response.status == 200:
                            logger.info(f"✅ Successfully added series: {series['title']}")
                            return True, f"Successfully added {series['title']}"
                        else:
                            logger.error(f"❌ Failed to add series: {response_text}")
                            return False, f"Failed to add {series['title']}"
                        
            except aiohttp.ClientError as e:
                logger.error(f"❌ Connection error: {str(e)}")
                return False, f"Connection error: {str(e)}"
            except Exception as e:
                logger.error(f"❌ Error adding series: {str(e)}")
                return False, str(e)

        except Exception as e:
            logger.error(f"❌ Error in add_series: {str(e)}")
            return False, str(e)

    async def get_series(self, tvdb_id: str) -> Optional[Dict]:
        """Get series details by TVDB ID"""
        try:
            logger.info(f"🔍 Looking up series with TVDB ID: {tvdb_id}")
            results = await self._make_request(f"series/lookup/tvdb/{tvdb_id}")
            
            if results:
                logger.info(f"✅ Found series: {results.get('title')}")
                return results
            
            # Fallback to search with tvdb: prefix if direct lookup fails
            results = await self._make_request(f"series/lookup?term=tvdb:{tvdb_id}")
            if results and len(results) > 0:
                logger.info(f"✅ Found series: {results[0].get('title')}")
                return results[0]
                
            logger.warning(f"⚠️ No series found with TVDB ID: {tvdb_id}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to get series: {str(e)}")
            return None

    async def check_status(self) -> bool:
        """Check if Sonarr is available"""
        try:
            result = await self._make_request("system/status")
            return result is not None
        except Exception as e:
            logger.error(f"Error checking Sonarr status: {e}")
            return False