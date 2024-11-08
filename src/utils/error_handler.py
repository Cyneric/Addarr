"""
Filename: error_handler.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Error handling module for Addarr. This module provides centralized error handling and user feedback functionality.
"""

from colorama import Fore, Style
import sys
import yaml
from typing import Optional
from telegram import Update, Message
from telegram.error import InvalidToken, NetworkError, BadRequest, Forbidden
from src.utils.logger import get_logger

logger = get_logger("addarr.errors")

# Custom Exception Classes
class AddarrError(Exception):
    """Base exception class for Addarr errors"""
    def __init__(self, message: str, user_message: Optional[str] = None):
        super().__init__(message)
        self.user_message = user_message or message

class ConfigError(AddarrError):
    """Configuration related errors"""
    pass

class APIError(AddarrError):
    """API related errors"""
    pass

class AuthenticationError(AddarrError):
    """Authentication related errors"""
    pass

class ValidationError(AddarrError):
    """Data validation errors"""
    pass

class ServiceNotEnabledError(AddarrError):
    """Raised when trying to use a service that is not enabled"""
    pass

# Error Handlers
def handle_token_error(token: str) -> bool:
    """Handle invalid or missing Telegram token errors
    
    Returns:
        bool: True if token was updated, False otherwise
    """
    print(f"\n{Fore.RED}❌ Error: Invalid Telegram Bot Token!")
    print(f"\n{Fore.YELLOW}The token '{token}' was rejected by Telegram.")
    
    while True:
        choice = input(f"\n{Fore.CYAN}Would you like to update the token now? (y/n): {Style.RESET_ALL}").lower()
        
        if choice == 'y':
            new_token = input(f"\n{Fore.CYAN}Please enter the new token from @BotFather: {Style.RESET_ALL}")
            
            if new_token.strip():
                try:
                    # Load current config
                    with open("config.yaml", 'r') as f:
                        full_config = yaml.safe_load(f)
                    
                    # Update token
                    if 'telegram' not in full_config:
                        full_config['telegram'] = {}
                    full_config['telegram']['token'] = new_token
                    
                    # Save updated config
                    with open("config.yaml", 'w') as f:
                        yaml.dump(full_config, f, default_flow_style=False)
                    
                    print(f"\n{Fore.GREEN}✅ Token updated successfully!")
                    print(f"{Fore.CYAN}Restarting bot with new token...{Style.RESET_ALL}")
                    return True
                    
                except Exception as e:
                    print(f"\n{Fore.RED}❌ Error updating token: {str(e)}")
                    print("Please update the token manually in config.yaml")
                    return False
            else:
                print(f"\n{Fore.RED}❌ Invalid token entered. Please try again.")
                continue
                
        elif choice == 'n':
            print(f"\n{Fore.YELLOW}To update the token later:")
            print("1. Get a valid token from @BotFather:")
            print("   • Open Telegram and message @BotFather")
            print("   • Use /newbot to create a new bot")
            print("   • Copy the token you receive")
            print("\n2. Update your configuration:")
            print("   • Run: python run.py --setup")
            print("   • Or manually update the token in config.yaml")
            print(f"\n{Fore.CYAN}Need help? Visit: https://github.com/cyneric/addarr/wiki")
            return False
            
        else:
            print(f"\n{Fore.RED}Invalid choice. Please enter 'y' or 'n'")

def handle_missing_token_error() -> None:
    """Handle missing token configuration"""
    print(f"\n{Fore.RED}❌ Error: No Telegram bot token found!")
    print(f"\n{Fore.YELLOW}The bot token is required to connect to Telegram.")
    print("\nTo fix this:")
    print("1. Run the setup wizard:")
    print(f"   {Fore.CYAN}python run.py --setup")
    print("\n2. Or manually add your token to config.yaml:")
    print("   telegram:")
    print("     token: \"YOUR_BOT_TOKEN\"")
    print(f"\n{Fore.CYAN}Need help? Visit: https://github.com/cyneric/addarr/wiki/Setup")

def handle_network_error() -> None:
    """Handle network connection errors"""
    print(f"\n{Fore.RED}❌ Error: Cannot connect to Telegram!")
    print(f"\n{Fore.YELLOW}Unable to establish a connection to Telegram servers.")
    print("\nPlease check:")
    print("1. Your internet connection is working")
    print("2. You can access telegram.org in your browser")
    print("3. Your firewall isn't blocking the connection")
    print("4. You're not using a VPN that blocks Telegram")
    print("5. Telegram is accessible in your region")
    print(f"\n{Fore.CYAN}Need help? Visit: https://github.com/cyneric/addarr/wiki/Troubleshooting")

def handle_initialization_error(error: Exception) -> None:
    """Handle general initialization errors"""
    print(f"\n{Fore.RED}❌ Error: Could not start the bot!")
    print(f"\n{Fore.YELLOW}Details: {str(error)}")
    print("\nTroubleshooting steps:")
    print("1. Check your configuration:")
    print("   • Run: python run.py --check")
    print("2. Try running setup again:")
    print("   • Run: python run.py --setup")
    print("3. Look for errors in the log file")
    print("4. Make sure all required services are running")
    print(f"\n{Fore.CYAN}Need help? Visit: https://github.com/cyneric/addarr/wiki/Troubleshooting")

async def handle_telegram_error(update: Update, error: Exception) -> None:
    """Handle Telegram-specific errors"""
    if isinstance(error, InvalidToken):
        handle_token_error(str(error))
    elif isinstance(error, NetworkError):
        handle_network_error()
    elif isinstance(error, (BadRequest, Forbidden)):
        logger.error(f"Telegram API error: {str(error)}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ An error occurred while processing your request.\n"
                "Please try again later."
            )
    else:
        logger.error(f"Unexpected error: {str(error)}", exc_info=error)
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ An unexpected error occurred.\n"
                "Please try again later."
            )

async def send_error_message(message: Message, text: str, reply_markup=None) -> None:
    """Send an error message, handling both photo and text messages"""
    try:
        if message.photo:
            await message.edit_caption(
                caption=text,
                reply_markup=reply_markup
            )
        else:
            await message.edit_text(
                text=text,
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Error sending error message: {e}")
        # Fallback: send new message
        await message.reply_text(text, reply_markup=reply_markup)