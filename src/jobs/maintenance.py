"""
Filename: maintenance.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Maintenance jobs module.

This module defines scheduled maintenance tasks that run periodically,
such as cleaning up the cache and checking service health. These jobs
help keep the application running smoothly.
"""

from src.services.system import SystemService
from ..services.cache import cache
from ..services.scheduler import scheduler
from ..utils.logger import get_logger

logger = get_logger("addarr.jobs")

async def cleanup_cache():
    """Clean up expired cache entries"""
    logger.debug("Running cache cleanup")
    cache.cleanup()

async def check_services():
    """Check if all services are available"""
    logger.debug("Checking service availability")
    system_service = SystemService()
    await system_service.get_status()
    logger.debug("Services are available")
    pass

def setup_jobs():
    """Set up scheduled jobs"""
    # Clean cache every hour
    scheduler.add_job(
        "cache_cleanup",
        cleanup_cache,
        "0 * * * *"
    )
    
    # Check services every 5 minutes
    scheduler.add_job(
        "service_check",
        check_services,
        "*/5 * * * *"
    ) 