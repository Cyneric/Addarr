"""
Base API client implementation.

This module provides the base class for all API clients, implementing
common functionality like request handling, authentication, and error
handling.
"""

from abc import ABC, abstractmethod
import logging
import json
import aiohttp
from typing import Tuple, Optional, Any, Dict

from ..utils.logger import get_logger
from ..config.settings import config

class APIError(Exception):
    """Custom exception for API errors"""
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        self.message = message
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(self.message)

class BaseApiClient(ABC):
    """Base class for API clients"""
    
    def __init__(self, service_name):
        self.service_name = service_name
        self.config = config[service_name]
        self.logger = get_logger(f"addarr.{service_name}")
        self.base_url = self._build_base_url()
        
    def _build_base_url(self):
        """Build the base URL for API requests"""
        server_config = self.config["server"]
        protocol = "https" if server_config.get("ssl", False) else "http"
        return f"{protocol}://{server_config['addr']}:{server_config['port']}{server_config['path']}"
        
    def _get_headers(self):
        """Get headers for API requests"""
        return {
            'X-Api-Key': self.config["auth"]["apikey"],
            'Content-Type': 'application/json'
        }
        
    def _parse_error_response(self, response_text: str, title: str = None) -> str:
        """Parse error response from API
        
        Args:
            response_text: Raw response text from API
            title: Title/name of the item being processed
            
        Returns:
            str: User-friendly error message
        """
        try:
            if response_text.startswith("["):
                error_data = json.loads(response_text)
                if isinstance(error_data, list) and error_data:
                    error_msg = error_data[0].get("errorMessage")
                    if error_msg:
                        # Add title to "already exists" messages
                        if "already" in error_msg.lower() and title:
                            return f"{title} is already in your library"
                        return error_msg
            return response_text
        except json.JSONDecodeError:
            return response_text
        
    async def _make_request(self, endpoint: str, method: str = "GET", data: Optional[dict] = None, title: str = None) -> Tuple[bool, Any, Optional[str]]:
        """Make an API request
        
        Args:
            endpoint: API endpoint
            method: HTTP method
            data: Request data
            title: Title/name of the item being processed
        
        Returns:
            Tuple[bool, Any, Optional[str]]: (success, data, error_message)
        """
        url = f"{self.base_url}/api/v3/{endpoint}"
        self.logger.info(f"🌐 API Request: {method} {url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, headers=self._get_headers(), json=data) as response:
                    response_text = await response.text()
                    
                    if response.status == 200:
                        self.logger.info(f"✅ API Response: {response.status}")
                        return True, json.loads(response_text) if response_text else None, None
                    
                    # Parse error response with title context
                    error_message = self._parse_error_response(response_text, title)
                    
                    # Log at appropriate level based on error type
                    if "already" in error_message.lower():
                        self.logger.info(f"ℹ️ {error_message}")
                    else:
                        self.logger.error(f"❌ API request failed ({response.status}): {error_message}")
                    
                    return False, None, error_message
                    
        except aiohttp.ClientError as e:
            error_message = f"Connection error: {str(e)}"
            self.logger.error(f"❌ {error_message}")
            return False, None, error_message
        except Exception as e:
            error_message = f"Unexpected error: {str(e)}"
            self.logger.error(f"❌ {error_message}")
            return False, None, error_message
            
    @abstractmethod
    def search(self, term):
        """Search for media"""
        pass
        
    @abstractmethod
    def add_to_library(self, item_id, path, quality_profile_id, tags):
        """Add item to library"""
        pass

    async def check_status(self) -> bool:
        """Check if the service is available"""
        try:
            # Most APIs have a system/status endpoint
            response = await self.get("system/status")
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"Error checking API status: {e}")
            return False