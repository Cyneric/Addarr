"""
Job scheduler service module.

This module provides a cron-based job scheduling system for running
periodic tasks. It manages job lifecycles and provides error handling
for scheduled tasks.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional, Any
import aiocron
from ..utils.logger import get_logger

logger = get_logger("addarr.scheduler")

class JobScheduler:
    """Service for scheduling and managing jobs"""
    
    def __init__(self):
        self.jobs: Dict[str, aiocron.Cron] = {}
        self.running = False
        
    def add_job(
        self,
        name: str,
        func: Callable,
        cron: str
    ) -> None:
        """Add a new scheduled job
        
        Args:
            name: Unique job name
            func: Async function to execute
            cron: Cron expression
        """
        if name in self.jobs:
            logger.warning(f"Job {name} already exists, replacing")
            self.remove_job(name)
            
        async def wrapped_job():
            try:
                logger.debug(f"Running job {name}")
                await func()
            except Exception as e:
                logger.error(f"Error in job {name}: {str(e)}", exc_info=e)
                
        job = aiocron.crontab(cron, func=wrapped_job, start=self.running)
        self.jobs[name] = job
        logger.info(f"Added job {name} with schedule {cron}")
        
    def remove_job(self, name: str) -> None:
        """Remove a scheduled job
        
        Args:
            name: Job name to remove
        """
        if job := self.jobs.pop(name, None):
            job.stop()
            logger.info(f"Removed job {name}")
            
    def start(self) -> None:
        """Start the scheduler"""
        self.running = True
        for job in self.jobs.values():
            job.start()
        logger.info("Scheduler started")
        
    def stop(self) -> None:
        """Stop the scheduler"""
        self.running = False
        for job in self.jobs.values():
            job.stop()
        logger.info("Scheduler stopped")

# Create global scheduler instance
scheduler = JobScheduler() 