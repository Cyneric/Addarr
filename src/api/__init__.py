"""
Filename: __init__.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: API client package for external services.

This package contains API client implementations for Radarr, Sonarr,
and Lidarr services. It provides a consistent interface for interacting
with these services through their REST APIs.
"""

from .base import BaseApiClient
from .radarr import RadarrClient
from .sonarr import SonarrClient
from .lidarr import LidarrClient

__all__ = ['BaseApiClient', 'RadarrClient', 'SonarrClient', 'LidarrClient']
