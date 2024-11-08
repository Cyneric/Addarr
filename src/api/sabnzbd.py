"""
SABnzbd API client module.
"""

import aiohttp
from typing import Optional, Dict, Any
import logging
from colorama import Fore

from src.config.settings import config
from src.utils.logger import get_logger

logger = get_logger("addarr.sabnzbd")

class SabnzbdClient:
    """SABnzbd API client"""
    
    def __init__(self):
        """Initialize SABnzbd API client"""
        sabnzbd_config = config.get("sabnzbd", {})
        server_config = sabnzbd_config.get("server", {})
        auth_config = sabnzbd_config.get("auth", {})
        
        # Build API URL from server config
        protocol = "https" if server_config.get("ssl", False) else "http"
        addr = server_config.get("addr")
        port = server_config.get("port")
        path = server_config.get("path", "").rstrip('/')
        
        if not addr or not port:
            logger.error(Fore.RED + "❌ SABnzbd server address or port not configured")
            raise ValueError("SABnzbd server address or port not configured")
            
        self.api_url = f"{protocol}://{addr}:{port}{path}"
        self.api_key = auth_config.get("apikey")
        
        if not self.api_key:
            logger.error(Fore.RED + "❌ SABnzbd API key not configured")
            raise ValueError("SABnzbd API key not configured")
            
        logger.info(Fore.GREEN + f"✅ SABnzbd API client initialized: {self.api_url}")

    async def check_status(self) -> bool:
        """Check if SABnzbd is available"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_url}/api?mode=queue&output=json&apikey={self.api_key}"
                async with session.get(url) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Error checking SABnzbd status: {e}")
            return False 