"""
Main application module.

This module initializes and runs the Telegram bot application.
"""

import asyncio
import signal
import sys
import os
from colorama import init
from telegram.ext import Application
from telegram.error import InvalidToken, NetworkError

from src.bot.handlers.auth import AuthHandler
from src.bot.handlers.media import MediaHandler
from src.bot.handlers.transmission import TransmissionHandler
from src.bot.handlers.sabnzbd import SabnzbdHandler
from src.bot.handlers.help import HelpHandler
from src.bot.handlers.start import StartHandler
from src.bot.handlers.status import StatusHandler
from src.config.settings import config
from src.utils.logger import get_logger
from src.utils.splash import show_welcome_screen
from src.utils.validation import check_config
from src.utils.error_handler import (
    handle_token_error,
    handle_missing_token_error,
    handle_network_error,
    handle_initialization_error
)
from src.services.health import health_service, display_health_status

# Initialize colorama
init(autoreset=True)

# Get logger instance
logger = get_logger("addarr.main")

class AddarrBot:
    """Main bot application class"""
    
    def __init__(self):
        self.application = None
        self._running = False
        self.health_checker = health_service
        
    async def initialize(self):
        """Initialize the bot application"""
        try:
            show_welcome_screen()
            
            # Run configuration check before starting
            check_config()
            
            # Run health checks on enabled services as final startup check
            health_results = await health_service.run_health_checks()
            if not display_health_status(health_results):
                logger.error("❌ Health checks failed - some services are not responding")
                logger.error("Please check your configuration and ensure all services are running\n")
            else:
                logger.info("✅ All service health checks passed\n")
            
            token = config.get("telegram", {}).get("token")
            if not token:
                handle_missing_token_error()
                raise ValueError("Telegram bot token not configured")
                
            self.application = Application.builder().token(token).build()
            self._add_handlers()
            
            try:
                await self.application.initialize()
                logger.info("🚀 Bot initialized successfully")
            except InvalidToken:
                if handle_token_error(token):
                    # Token was updated, restart the bot
                    logger.info("🔄 Restarting with new token...")
                    python = sys.executable
                    os.execl(python, python, *sys.argv)
                else:
                    raise
            except NetworkError:
                handle_network_error()
                raise
            except Exception as e:
                handle_initialization_error(e)
                raise
                
        except Exception as e:
            logger.error(f"❌ Initialization error: {str(e)}", exc_info=True)
            raise
            
    def _add_handlers(self):
        """Add all handlers to the application"""
        try:
            # Start handler
            start_handler = StartHandler()
            for handler in start_handler.get_handler():
                self.application.add_handler(handler)
            
            # Auth handler
            auth_handler = AuthHandler()
            for handler in auth_handler.get_handler():
                self.application.add_handler(handler)
            
            # Media handler
            media_handler = MediaHandler()
            for handler in media_handler.get_handler():
                self.application.add_handler(handler)
            
            # Transmission handler (if enabled)
            if config.get("transmission", {}).get("enable", False):
                transmission_handler = TransmissionHandler()
                for handler in transmission_handler.get_handler():
                    self.application.add_handler(handler)
                
            # SABnzbd handler (if enabled)
            if config.get("sabnzbd", {}).get("enable", False):
                sabnzbd_handler = SabnzbdHandler()
                for handler in sabnzbd_handler.get_handler():
                    self.application.add_handler(handler)
                
            # Help handler
            help_handler = HelpHandler()
            for handler in help_handler.get_handler():
                self.application.add_handler(handler)
            
            # Status handler
            status_handler = StatusHandler()
            for handler in status_handler.get_handler():
                self.application.add_handler(handler)
            
        except Exception as e:
            logger.error(f"❌ Error adding handlers: {str(e)}", exc_info=True)
            raise
            
    async def start(self):
        """Start the bot"""
        try:
            logger.info("🚀 Starting bot...")
            await self.application.start()
            self._running = True
            
            # Start health check job
            asyncio.create_task(self.health_checker.start())
            
            # Start polling
            await self.application.updater.start_polling(
                allowed_updates=["message", "callback_query"]
            )
            
            # Keep the bot running until stopped
            while self._running:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"❌ Error starting bot: {str(e)}")
            raise
            
    async def stop(self):
        """Stop the bot gracefully"""
        if self.application:
            try:
                logger.info("🛑 Stopping bot...")
                self._running = False
                
                # Stop health check job
                await self.health_checker.stop()
                
                if hasattr(self.application, 'updater') and self.application.updater.running:
                    await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
            except Exception as e:
                logger.debug(f"Error during shutdown: {str(e)}", exc_info=True)
                # Don't raise the error since we're shutting down anyway

async def main():
    """Main entry point for the application"""
    bot = AddarrBot()
    
    async def start_bot():
        try:
            await bot.initialize()
            await bot.start()
        except Exception as e:
            logger.error(f"❌ Bot error: {str(e)}", exc_info=True)
            await bot.stop()
            sys.exit(1)

    try:
        # Get or create event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Handle shutdown signals
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.stop()))
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                signal.signal(sig, lambda s, f: asyncio.create_task(bot.stop()))

        # Run the bot
        await start_bot()
    except KeyboardInterrupt:
        logger.info("\n{Fore.YELLOW}Shutting down...")
        await bot.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

def run_bot():
    """Entry point for running the bot directly"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n{Fore.YELLOW}Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_bot()