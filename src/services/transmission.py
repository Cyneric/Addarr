"""
Filename: transmission.py
Author: Christian Blank (https://github.com/cyneric)
Created Date: 2024-11-09
Description: Transmission service for Addarr. Handles business logic for Transmission operations.
"""

from typing import Optional
from ..api.transmission import TransmissionAPI
from ..config.settings import config
from ..utils.logger import get_logger

logger = get_logger("addarr.services.transmission")

class TransmissionService:
    """Service class for Transmission operations"""
    
    def __init__(self):
        """Initialize Transmission service"""
        self._client = None
        self._config = config.get("transmission", {})
        
    @property
    def client(self) -> Optional[TransmissionAPI]:
        """Get or create Transmission API client"""
        if not self._client and self._config.get("enable"):
            try:
                self._client = TransmissionAPI(
                    host=self._config.get("host", "localhost"),
                    port=self._config.get("port", 9091),
                    username=self._config.get("username"),
                    password=self._config.get("password"),
                    ssl=self._config.get("ssl", False)
                )
            except Exception as e:
                logger.error(f"Failed to initialize Transmission client: {str(e)}")
                return None
        return self._client
        
    def is_enabled(self) -> bool:
        """Check if Transmission is enabled in config"""
        return bool(self._config.get("enable"))
        
    def test_connection(self) -> bool:
        """Test connection to Transmission"""
        if not self.client:
            return False
        return self.client.test_connection()
        
    def set_alt_speed(self, enabled: bool) -> bool:
        """Enable or disable alternative speed limits
        
        Args:
            enabled: Whether to enable alt speed limits
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.error("Transmission client not initialized")
            return False
            
        try:
            self.client.set_alt_speed_enabled(enabled)
            status = "enabled" if enabled else "disabled"
            logger.info(f"Alternative speed limits {status}")
            return True
        except Exception as e:
            logger.error(f"Failed to set alt speed: {str(e)}")
            return False
            
    def get_status(self) -> dict:
        """Get current Transmission status
        
        Returns:
            Dict containing status information
        """
        if not self.client:
            return {
                "enabled": False,
                "connected": False,
                "error": "Transmission not initialized"
            }
            
        try:
            session = self.client.get_session()
            return {
                "enabled": True,
                "connected": True,
                "alt_speed_enabled": session.get("arguments", {}).get("alt-speed-enabled", False),
                "version": session.get("arguments", {}).get("version", "Unknown")
            }
        except Exception as e:
            return {
                "enabled": True,
                "connected": False,
                "error": str(e)
            }

# Create global service instance
transmission_service = TransmissionService()