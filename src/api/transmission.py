"""
Filename: transmission.py
Author: Christian Blank (https://github.com/cyneric)
Created Date: 2024-11-09
Description: Transmission API client for Addarr. Handles communication with Transmission torrent client.
"""

import requests
from typing import Dict, Any, Optional
from .base import BaseApiClient
from ..utils.logger import get_logger

logger = get_logger("addarr.api.transmission")

class TransmissionAPI(BaseApiClient):
    """API client for Transmission torrent client"""
    
    def __init__(self, host: str, port: int, username: Optional[str] = None, 
                 password: Optional[str] = None, ssl: bool = False):
        """Initialize Transmission API client
        
        Args:
            host: Transmission host address
            port: Transmission port number
            username: Optional username for authentication
            password: Optional password for authentication
            ssl: Whether to use HTTPS
        """
        super().__init__()
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.ssl = ssl
        self.session_id = None
        self.base_url = f"{'https' if ssl else 'http'}://{host}:{port}/transmission/rpc"
        
    def _get_auth(self) -> Optional[tuple]:
        """Get authentication tuple if credentials are provided"""
        if self.username and self.password:
            return (self.username, self.password)
        return None
        
    def _make_request(self, method: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Make request to Transmission RPC
        
        Args:
            method: RPC method name
            arguments: Method arguments
            
        Returns:
            API response data
            
        Raises:
            requests.exceptions.RequestException: If request fails
        """
        headers = {'X-Transmission-Session-Id': self.session_id} if self.session_id else {}
        data = {
            'method': method,
            'arguments': arguments
        }
        
        try:
            response = requests.post(
                self.base_url,
                json=data,
                headers=headers,
                auth=self._get_auth(),
                timeout=10
            )
            
            # Handle session ID
            if response.status_code == 409:
                self.session_id = response.headers['X-Transmission-Session-Id']
                return self._make_request(method, arguments)
                
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Transmission API request failed: {str(e)}")
            raise
            
    def get_session(self) -> Dict[str, Any]:
        """Get current session information"""
        return self._make_request('session-get', {})
        
    def set_alt_speed_enabled(self, enabled: bool) -> Dict[str, Any]:
        """Enable or disable alternative speed limits
        
        Args:
            enabled: Whether to enable alt speed limits
            
        Returns:
            API response data
        """
        return self._make_request('session-set', {
            'alt-speed-enabled': enabled
        })
        
    def test_connection(self) -> bool:
        """Test connection to Transmission
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.get_session()
            return True
        except:
            return False 