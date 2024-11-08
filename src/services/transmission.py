"""
Filename: transmission.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Transmission service module.

This module provides functionality to control Transmission's download speeds
through its command-line interface. It handles speed limit toggling and
authentication with the Transmission daemon.
"""

import os
from typing import Optional
from ..config.settings import config
from ..utils.logger import get_logger

class TransmissionService:
    """Service for interacting with Transmission"""
    
    def __init__(self):
        self.config = config["transmission"]
        self.logger = get_logger("addarr.transmission")
        
    async def set_speed(self, speed_type: str) -> bool:
        """Set transmission speed limit
        
        Args:
            speed_type: Either 'normal' or 'limited'
            
        Returns:
            bool: True if successful
        """
        try:
            command = ["transmission-remote", self.config["host"]]
            
            if self.config["authentication"]:
                auth = f"{self.config['username']}:{self.config['password']}"
                command.extend(["--auth", auth])
                
            if speed_type == "normal":
                command.append("--no-alt-speed")
            else:
                command.append("--alt-speed")
                
            result = os.system(" ".join(command))
            return result == 0
            
        except Exception as e:
            self.logger.error(f"Failed to set transmission speed: {str(e)}")
            return False