"""
Filename: setup.py
Author: Christian Blank (https://github.com/Cyneric)
Created Date: 2024-11-08
Description: Interactive setup script for Addarr.

This script guides users through the initial setup process, helping them:
1. Create necessary directories
2. Configure media services (Radarr, Sonarr, Lidarr)
3. Set up Telegram bot settings
4. Configure access control
5. Generate config.yaml
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List
import questionary
from colorama import Fore, Style, init
import aiohttp
import asyncio
from urllib.parse import urlparse
import shutil
import datetime
from ruamel.yaml import YAML

# Add src directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.splash import show_splash_screen
from src.definitions import CONFIG_PATH, CONFIG_EXAMPLE_PATH, LOG_PATH
from src.utils.config_handler import config_handler
from src.utils.backup import create_backup

# Initialize colorama
init(autoreset=True)

# Initialize YAML handler
yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)

class SetupWizard:
    def __init__(self):
        """Initialize setup wizard"""
        self.config = config_handler.load_config()
        # Add root directory path
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
    def _save_config(self):
        """Save config while preserving formatting and comments"""
        config_handler.save_config(self.config)
            
    def _update_config_value(self, path: List[str], value: Any):
        """Update a config value while preserving structure"""
        config_handler.update_value(self.config, path, value)

    def run(self, reset: bool = False):
        """Run the setup wizard synchronously"""
        show_splash_screen()
        
        if reset:
            self._reset_config()
        
        print(f"\n{Fore.GREEN}Welcome to the Addarr Setup Wizard! 🧙‍♂️")
        print("This wizard will help you create your configuration file.")
        
        self._create_directories()
        
        try:
            # Get or create event loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Run async setup
            loop.run_until_complete(self._async_setup())
            
        except Exception as e:
            print(f"{Fore.RED}Error during setup: {e}")
            sys.exit(1)
            
        print(f"\n{Fore.GREEN}✅ Setup completed successfully!")
        print(f"{Fore.CYAN}You can now start Addarr with: python run.py\n")

    async def _async_setup(self):
        """Async portion of the setup process"""
        # Configure language first
        await self._configure_language()
        
        # Select services to configure
        services = await self._select_services()
        
        # Configure selected services
        for service in services:
            await self._configure_service(service)
            
        # Configure Telegram bot
        await self._configure_telegram()
        
        # Configure access control
        await self._configure_access_control()
        
        # Configure logging
        await self._configure_logging()
        
        # Save configuration
        self._save_config()

    def _create_directories(self):
        """Create necessary directories"""
        directories = [
            os.path.dirname(LOG_PATH),
            "translations"
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
            
    async def _select_services(self) -> List[str]:
        """Let user select which services to configure"""
        print(f"\n{Fore.CYAN}Media Services Configuration")
        print(f"{Fore.YELLOW}Note: At least one media service must be enabled")
        print(f"{Fore.YELLOW}Select at least one of: Radarr, Sonarr, or Lidarr")
        
        media_services = await questionary.checkbox(
            "Select media services to enable (select one or more):",
            choices=[
                questionary.Choice("🎬 Radarr - Movies", "radarr"),
                questionary.Choice("📺 Sonarr - TV Shows", "sonarr"),
                questionary.Choice("🎵 Lidarr - Music", "lidarr")
            ]
        ).ask_async()
        
        if not media_services:
            print(f"{Fore.RED}⚠️  Error: At least one media service must be selected")
            return await self._select_services()
            
        # Optional download clients
        print(f"\n{Fore.CYAN}Download Clients Configuration")
        print(f"{Fore.YELLOW}Note: Download clients are completely optional")
        
        should_configure_clients = await questionary.confirm(
            "Would you like to configure download clients? (optional)",
            default=False
        ).ask_async()
        
        download_clients = []
        if should_configure_clients:
            download_clients = await questionary.checkbox(
                "Select download clients to configure:",
                choices=[
                    questionary.Choice("📥 SABnzbd - Usenet (optional)", "sabnzbd"),
                    questionary.Choice("⬇️ Transmission - Torrents (optional)", "transmission"),
                    questionary.Choice("❌ None - Skip download client configuration", "none")
                ]
            ).ask_async()
            
            if not download_clients or "none" in download_clients:
                print(f"{Fore.YELLOW}ℹ️  Skipping download client configuration")
                download_clients = []
        else:
            print(f"{Fore.YELLOW}ℹ️  Skipping download client configuration")
        
        print(f"\n{Fore.GREEN}✅ Selected services:")
        for service in media_services:
            print(f"  • {service.title()} (Media Service)")
        for client in download_clients:
            if client != "none":
                print(f"  • {client.title()} (Download Client)")
        
        return media_services + download_clients
        
    async def _configure_service(self, service: str):
        """Configure a specific service"""
        print(f"\n{Fore.CYAN}Configuring {service.title()} 🔧")
        
        # Service was selected by user, so it is enabled
        enabled = True
        
        config = self._get_default_service_config(service)
        config["enable"] = enabled
        
        if enabled:
            try:
                # Get validated service configuration
                service_config = await self._get_valid_service_config(service)
                config.update(service_config)
                
                if service in ["radarr", "sonarr", "lidarr"]:
                    config["features"] = await self._configure_arr_features(service)
            except Exception as e:
                print(f"{Fore.RED}Error configuring {service}: {e}")
                print(f"{Fore.YELLOW}Using default configuration for {service}")
                config["enable"] = False
        
        self.config[service] = config
        
    async def _configure_sabnzbd(self, config: Dict[str, Any]):
        """Configure SABnzbd (required)"""
        config["server"].update({
            "addr": await questionary.text(
                "Enter SABnzbd server address:",
                default="localhost"
            ).ask_async(),
            "port": await self._get_valid_port(
                "Enter SABnzbd port:",
                "8090"
            ),
            "ssl": await questionary.confirm(
                "Use SSL/HTTPS?",
                default=False
            ).ask_async()
        })
        
        config["auth"]["apikey"] = await questionary.password(
            "Enter SABnzbd API key (required):"
        ).ask_async()
        
        if not config["auth"]["apikey"]:
            raise ValueError("SABnzbd API key is required")
            
        if await questionary.confirm(
            "Use username/password authentication?",
            default=False
        ).ask_async():
            config["auth"].update({
                "username": await questionary.text("Username:").ask_async(),
                "password": await questionary.password("Password:").ask_async()
            })
        
    async def _configure_arr_service(self, service: str, config: Dict[str, Any]):
        """Configure *arr service"""
        print(f"\n{Fore.CYAN}Configuring {service.title()} 🔧")
        
        # Basic server configuration
        config["server"].update({
            "addr": await questionary.text(
                f"Enter {service} server address:",
                default="localhost"
            ).ask_async(),
            "port": await self._get_valid_port(
                f"Enter {service} port:",
                self._get_default_port(service)
            ),
            "ssl": await questionary.confirm(
                "Use SSL/HTTPS?",
                default=False
            ).ask_async()
        })
        
        # Authentication
        config["auth"]["apikey"] = await questionary.password(
            f"Enter {service} API key:"
        ).ask_async()
        
        if await questionary.confirm(
            "Use username/password authentication?",
            default=False
        ).ask_async():
            config["auth"].update({
                "username": await questionary.text("Username:").ask_async(),
                "password": await questionary.password("Password:").ask_async()
            })
            
        # Service-specific configuration
        if service in ["radarr", "sonarr", "lidarr"]:
            config["features"] = await self._configure_arr_features(service)
        
        self.config[service] = config
        
    def _get_default_port(self, service: str) -> str:
        """Get default port for a service"""
        defaults = {
            "radarr": "7878",
            "sonarr": "8989",
            "lidarr": "8686",
            "transmission": "9091",
            "sabnzbd": "8090"
        }
        return defaults.get(service, "8090")
        
    async def _get_valid_port(self, message: str, default: str) -> int:
        """Get a valid port number from user input"""
        while True:
            try:
                port = await questionary.text(
                    message,
                    default=default
                ).ask_async()
                port_num = int(port)
                if 1 <= port_num <= 65535:
                    return port_num
                print(f"{Fore.RED}Port must be between 1 and 65535")
            except ValueError:
                print(f"{Fore.RED}Please enter a valid port number")
        
    async def _configure_arr_features(self, service: str) -> Dict[str, Any]:
        """Configure *arr specific features"""
        features = {
            "search": await questionary.confirm(
                "Enable automatic searching when adding new media?",
                default=True
            ).ask_async()
        }
        
        if service == "radarr":
            features["minimumAvailability"] = await questionary.select(
                "Select minimum availability requirement:",
                choices=[
                    {"name": "Announced - As soon as movie is announced", "value": "announced"},
                    {"name": "In Cinemas - When movie is in theaters", "value": "inCinemas"},
                    {"name": "Released - Physical/Web release", "value": "released"},
                    {"name": "PreDB - When release is confirmed", "value": "preDB"}
                ],
                use_shortcuts=True
            ).ask_async()
        elif service == "sonarr":
            features["seasonFolder"] = await questionary.confirm(
                "Organize episodes in season folders?",
                default=True
            ).ask_async()
        elif service == "lidarr":
            features["albumFolder"] = await questionary.confirm(
                "Organize tracks in album folders?",
                default=True
            ).ask_async()
            features["monitorOption"] = await questionary.select(
                "Select which releases to monitor:",
                choices=[
                    {"name": "All Releases", "value": "all"},
                    {"name": "Future Releases Only", "value": "future"},
                    {"name": "Missing Releases Only", "value": "missing"},
                    {"name": "None", "value": "none"}
                ],
                use_shortcuts=True
            ).ask_async()
            
        return features
        
    async def _configure_telegram(self):
        """Configure Telegram bot settings"""
        print(f"\n{Fore.CYAN}Configuring Telegram Bot 🤖")
        
        self.config["telegram"] = {
            "token": await questionary.password(
                "Enter your Telegram bot token (from @BotFather):"
            ).ask_async(),
            "password": await questionary.password(
                "Enter a password for chat authentication:"
            ).ask_async()
        }
        
    async def _configure_access_control(self):
        """Configure access control settings"""
        print(f"\n{Fore.CYAN}Configuring Access Control 🔒")
        
        self.config["security"] = {
            "enableAdmin": await questionary.confirm(
                "Enable admin features?",
                default=True
            ).ask_async(),
            "enableAllowlist": await questionary.confirm(
                "Enable allowlist restriction?",
                default=True
            ).ask_async()
        }
        
        # Admin IDs
        admin_ids = []
        while True:
            admin_id = await questionary.text(
                "Enter admin Telegram ID (or leave empty to finish):"
            ).ask_async()
            
            if not admin_id:
                break
                
            try:
                admin_id_int = int(admin_id)
                admin_ids.append(admin_id_int)
            except ValueError:
                print(f"{Fore.RED}❌ Invalid ID format. Please enter a numeric Telegram ID")
                continue
            
        self.config["admins"] = admin_ids
        
        # Allowed users
        if self.config["security"]["enableAllowlist"]:
            allowed_users = []
            while True:
                user_id = await questionary.text(
                    "Enter allowed user Telegram ID (or leave empty to finish):"
                ).ask_async()
                
                if not user_id:
                    break
                    
                try:
                    user_id_int = int(user_id)
                    allowed_users.append(user_id_int)
                except ValueError:
                    print(f"{Fore.RED}❌ Invalid ID format. Please enter a numeric Telegram ID")
                    continue
                    
            self.config["allow_list"] = allowed_users
            
    async def _configure_logging(self):
        """Configure logging settings"""
        print(f"\n{Fore.CYAN}Configuring Logging 📝")
        
        self.config["logging"] = {
            "toConsole": await questionary.confirm(
                "Enable console logging?",
                default=True
            ).ask_async(),
            "debug": await questionary.confirm(
                "Enable debug logging?",
                default=False
            ).ask_async()
        }
        
        while True:
            admin_notify = await questionary.text(
                "Enter Telegram chat ID for admin notifications (or leave empty to skip):"
            ).ask_async()
            
            if not admin_notify:
                self.config["logging"]["adminNotifyId"] = 0  # Default value
                break
                
            try:
                notify_id = int(admin_notify)
                self.config["logging"]["adminNotifyId"] = notify_id
                break
            except ValueError:
                print(f"{Fore.RED}❌ Invalid ID format. Please enter a numeric Telegram chat ID")
                continue
        
    async def _configure_language(self):
        """Configure language settings"""
        print(f"\n{Fore.CYAN}Language Configuration 🌍")
        
        languages = [
            {
                "name": "English (US)",
                "value": "en-us",
                "description": "American English"
            },
            {
                "name": "Deutsch",
                "value": "de-de",
                "description": "German"
            },
            {
                "name": "Español",
                "value": "es-es",
                "description": "Spanish"
            },
            {
                "name": "Français",
                "value": "fr-fr",
                "description": "French"
            },
            {
                "name": "Italiano",
                "value": "it-it",
                "description": "Italian"
            },
            {
                "name": "Nederlands (België)",
                "value": "nl-be",
                "description": "Belgian Dutch"
            },
            {
                "name": "Polski",
                "value": "pl-pl",
                "description": "Polish"
            },
            {
                "name": "Português",
                "value": "pt-pt",
                "description": "Portuguese"
            },
            {
                "name": "Русский",
                "value": "ru-ru",
                "description": "Russian"
            }
        ]
        
        selected_language = await questionary.select(
            "Select your preferred language:",
            choices=[
                {
                    "name": lang["name"],
                    "value": lang["value"],
                    "help": lang["description"]
                }
                for lang in languages
            ],
            use_shortcuts=True,
            use_indicator=True,
            instruction="Use arrow keys to navigate, Enter to select"
        ).ask_async()
        
        self.config["language"] = selected_language
        print(f"{Fore.GREEN}✅ Language set to: {next(lang['name'] for lang in languages if lang['value'] == selected_language)}")
        
    def _get_default_service_config(self, service: str) -> Dict[str, Any]:
        """Get default configuration for a service"""
        base_config = {
            "enable": False,
            "server": {
                "addr": "localhost",
                "port": self._get_default_port(service),
                "path": "/",
                "ssl": False
            },
            "auth": {
                "apikey": "",
                "username": "",
                "password": ""
            },
            "features": {"search": True},
            "paths": {"excludedRootFolders": [], "narrowRootFolderNames": True},
            "quality": {"excludedProfiles": []},
            "tags": {"default": ["telegram"], "addRequesterIdTag": True},
            "adminRestrictions": False
        }
        
        if service == "lidarr":
            base_config["metadataProfileId"] = 1
            base_config["features"]["albumFolder"] = True
            base_config["features"]["monitorOption"] = "all"
        elif service == "radarr":
            base_config["features"]["minimumAvailability"] = "announced"
        elif service == "sonarr":
            base_config["features"]["seasonFolder"] = True
        elif service == "transmission":
            return {
                "enable": False,
                "onlyAdmin": True,
                "host": "localhost",
                "authentication": False,
                "username": "",
                "password": ""
            }
        elif service == "sabnzbd":
            return {
                "enable": False,
                "onlyAdmin": True,
                "server": {
                    "addr": "localhost",
                    "port": 8090,
                    "path": "/",
                    "ssl": False
                },
                "auth": {
                    "apikey": "",
                    "username": "",
                    "password": ""
                }
            }
        
        return base_config

    async def _configure_required_value(self, service: str, value: str):
        """Configure a single required value for a service"""
        if service == 'telegram':
            if value == 'token':
                if 'telegram' not in self.config:
                    self.config['telegram'] = {}
                self.config['telegram']['token'] = await questionary.password(
                    "Enter your Telegram bot token (from @BotFather):"
                ).ask_async()
                # Add password field if it doesn't exist
                if 'password' not in self.config['telegram']:
                    self.config['telegram']['password'] = await questionary.password(
                        "Enter a password for chat authentication:"
                    ).ask_async()
        elif service in ['radarr', 'sonarr', 'lidarr']:
            if value == 'apikey':
                if service not in self.config:
                    self.config[service] = self._get_default_service_config(service)
                self.config[service]['auth']['apikey'] = await questionary.password(
                    f"Enter {service.title()} API key:"
                ).ask_async()

    async def _validate_service_connection(self, service: str, url: str, port: int, ssl: bool, apikey: str = None) -> bool:
        """
        Validate connection to a service by testing its API endpoint
        Returns True if connection is successful
        """
        protocol = "https" if ssl else "http"
        base_url = f"{protocol}://{url}:{port}"
        
        # Define test endpoints and expected responses for each service
        endpoints = {
            "radarr": {
                "path": "/api/v3/system/status",
                "headers": {"X-Api-Key": apikey} if apikey else {},
                "expected_keys": ["version"]  # Keys we expect in a successful response
            },
            "sonarr": {
                "path": "/api/v3/system/status",
                "headers": {"X-Api-Key": apikey} if apikey else {},
                "expected_keys": ["version"]
            },
            "lidarr": {
                "path": "/api/v1/system/status",
                "headers": {"X-Api-Key": apikey} if apikey else {},
                "expected_keys": ["version"]
            },
            "transmission": {
                "path": "/transmission/rpc",
                "headers": {},
                "expected_status": [200, 401, 409]  # Transmission returns 409 if session ID is missing
            },
            "sabnzbd": {
                "path": "/api",
                "headers": {"X-Api-Key": apikey} if apikey else {},
                "params": {"mode": "version"},
                "expected_keys": ["version"]
            }
        }
        
        if service not in endpoints:
            return False
            
        endpoint = endpoints[service]
        url = f"{base_url}{endpoint['path']}"
        
        try:
            print(f"{Fore.YELLOW}Testing connection to {url}...")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=endpoint["headers"],
                    params=endpoint.get("params", {}),
                    ssl=False,  # Ignore SSL verification for self-signed certs
                    timeout=5
                ) as response:
                    # Check if status code is in expected list (if defined)
                    if "expected_status" in endpoint:
                        if response.status in endpoint["expected_status"]:
                            print(f"{Fore.GREEN}✅ Service responded with status {response.status}")
                            return True
                        print(f"{Fore.RED}❌ Unexpected status code: {response.status}")
                        return False
                    
                    # For regular API endpoints, check response content
                    if response.status == 200:
                        try:
                            data = await response.json()
                            # Verify expected keys are in response
                            if all(key in data for key in endpoint["expected_keys"]):
                                print(f"{Fore.GREEN}✅ Service API responded successfully")
                                return True
                            print(f"{Fore.RED}❌ Response missing expected data")
                            return False
                        except ValueError:
                            print(f"{Fore.RED}❌ Invalid JSON response")
                            return False
                    else:
                        print(f"{Fore.RED}❌ Service returned status code {response.status}")
                        return False
                        
        except aiohttp.ClientError as e:
            print(f"{Fore.RED}❌ Connection error: {str(e)}")
            return False
        except asyncio.TimeoutError:
            print(f"{Fore.RED}❌ Connection timed out")
            return False
        except Exception as e:
            print(f"{Fore.RED}❌ Unexpected error: {str(e)}")
            return False

    async def _get_valid_service_config(self, service: str) -> Dict[str, Any]:
        """Get valid service configuration with connection testing"""
        while True:
            # Get server address
            addr = await questionary.text(
                f"Enter {service} server address:",
                default="localhost"
            ).ask_async()
            
            # Validate URL format
            try:
                parsed = urlparse(f"http://{addr}")
                if not parsed.netloc:
                    print(f"{Fore.RED}Invalid server address format")
                    continue
            except Exception:
                print(f"{Fore.RED}Invalid server address format")
                continue
                
            # Get port
            port = await self._get_valid_port(
                f"Enter {service} port:",
                self._get_default_port(service)
            )
            
            # Get SSL setting
            ssl = await questionary.confirm(
                "Use SSL/HTTPS?",
                default=False
            ).ask_async()
            
            # Build base URL
            protocol = "https" if ssl else "http"
            base_url = f"{protocol}://{addr}:{port}"
            
            # Get API key if applicable
            apikey = None
            if service in ["radarr", "sonarr", "lidarr", "sabnzbd"]:
                apikey = await questionary.password(
                    f"Enter {service} API key:"
                ).ask_async()
            
            print(f"{Fore.YELLOW}Testing connection to {service}...")
            if await self._validate_service_connection(service, addr, port, ssl, apikey):
                print(f"{Fore.GREEN}✅ Successfully connected to {service}")
                
                # Return appropriate configuration structure based on service
                if service == "sabnzbd":
                    return {
                        "enable": True,
                        "onlyAdmin": True,
                        "server": {
                            "addr": addr,
                            "port": port,
                            "path": "/",
                            "ssl": ssl
                        },
                        "auth": {
                            "apikey": apikey,
                            "username": "",
                            "password": ""
                        }
                    }
                else:
                    return {
                        "server": {
                            "addr": addr,
                            "port": port,
                            "path": "/",
                            "ssl": ssl
                        },
                        "auth": {
                            "apikey": apikey or "",
                            "username": "",
                            "password": ""
                        }
                    }
            else:
                print(f"{Fore.RED}❌ Failed to connect to {service}")
                retry = await questionary.confirm(
                    "Would you like to try again?",
                    default=True
                ).ask_async()
                
                if not retry:
                    print(f"{Fore.YELLOW}Skipping connection validation")
                    if service == "sabnzbd":
                        return {
                            "enable": False,
                            "onlyAdmin": True,
                            "server": {
                                "addr": addr,
                                "port": port,
                                "path": "/",
                                "ssl": ssl
                            },
                            "auth": {
                                "apikey": apikey or "",
                                "username": "",
                                "password": ""
                            }
                        }
                    else:
                        return {
                            "server": {
                                "addr": addr,
                                "port": port,
                                "path": "/",
                                "ssl": ssl
                            },
                            "auth": {
                                "apikey": apikey or "",
                                "username": "",
                                "password": ""
                            }
                        }

    def _backup_config(self):
        """Create a backup of the current configuration
        
        Returns:
            str: Path to backup file if successful, None if failed
        """
        # Create backup and return the backup file path
        return create_backup()

    def _reset_config(self):
        """Reset configuration to default state"""
        try:
            print(f"\n{Fore.YELLOW}⚠️  Warning: This will reset your configuration to default values!")
            print(f"{Fore.CYAN}• A backup of your current config will be created in the backup directory")
            print(f"{Fore.CYAN}• A new configuration file will be created from the example config")
            print(f"{Fore.CYAN}• You will be guided through the setup wizard to configure the bot from scratch")
            
            # Modified confirmation prompt
            if not questionary.confirm(
                "Do you want to continue?",  # Removed the \n and using questionary's default formatting
                default=False,
                style=questionary.Style([
                    ('question', 'fg:yellow bold'),  # Style the question text
                    ('pointer', 'fg:cyan bold'),     # Style the pointer (>)
                    ('highlighted', 'fg:cyan bold')  # Style the highlighted option
                ])
            ).ask():
                print(f"\n{Fore.YELLOW}Reset cancelled. Your configuration remains unchanged.")
                sys.exit(0)
                
            # Create backup before resetting
            backup_file = self._backup_config()
            if not backup_file:
                print(f"{Fore.RED}❌ Failed to create backup. Reset cancelled.")
                sys.exit(1)
                
            # Load example config
            example_path = os.path.join(self.root_dir, "config_example.yaml")
            if not os.path.exists(example_path):
                print(f"{Fore.RED}❌ Config example not found: {example_path}")
                sys.exit(1)
                
            # Use ruamel.yaml's load method
            with open(example_path, 'r') as f:
                self.config = yaml.load(f)
                
            # Save the reset config
            self._save_config()
            
            print(f"\n{Fore.GREEN}✅ Configuration reset to default values")
            print(f"{Fore.CYAN}Starting setup wizard...")
            
            # Run the setup wizard
            self.run()
            
        except Exception as e:
            print(f"{Fore.RED}❌ Error resetting configuration: {str(e)}")
            sys.exit(1)

    def configure_services(self):
        """Configure media services and download clients"""
        try:
            show_splash_screen()
            
            print(f"\n{Fore.GREEN}Welcome to the Addarr Service Configuration! 🧙‍♂️")
            print("This wizard will help you configure your media services and download clients.")
            
            # Configure media services
            print(f"\n{Fore.CYAN}Media Services Configuration")
            print("=" * 50)
            
            services = ["radarr", "sonarr", "lidarr"]
            for service in services:
                if questionary.confirm(f"Configure {service.title()}?", default=False).ask():
                    if not self.config.get(service):
                        self.config[service] = {}
                    
                    self.config[service]["enable"] = True
                    
                    # Get service configuration
                    service_config = asyncio.run(self._get_valid_service_config(service))
                    self.config[service].update(service_config)
                    
            # Configure download clients
            print(f"\n{Fore.CYAN}Download Clients Configuration")
            print("=" * 50)
            
            # Configure Transmission
            if questionary.confirm("Configure Transmission?", default=False).ask():
                if not self.config.get("transmission"):
                    self.config["transmission"] = {}
                self.config["transmission"]["enable"] = True
                
                # Configure authentication if needed
                if questionary.confirm("Enable Transmission authentication?", default=False).ask():
                    self.config["transmission"]["authentication"] = True
                    username = questionary.text("Username:").ask()
                    password = questionary.password("Password:").ask()
                    self.config["transmission"]["username"] = username
                    self.config["transmission"]["password"] = password
                    
            # Configure SABnzbd
            if questionary.confirm("Configure SABnzbd?", default=False).ask():
                if not self.config.get("sabnzbd"):
                    self.config["sabnzbd"] = {}
                self.config["sabnzbd"]["enable"] = True
                
                # Get SABnzbd configuration
                sabnzbd_config = asyncio.run(self._get_valid_service_config("sabnzbd"))
                self.config["sabnzbd"].update(sabnzbd_config)
            
            # Save the updated configuration
            self._save_config()
            
            print(f"\n{Fore.GREEN}✅ Service configuration completed successfully!")
            print(f"{Fore.CYAN}Run 'python run.py' to start the bot.")
            
        except Exception as e:
            print(f"{Fore.RED}❌ Error configuring services: {str(e)}")
            sys.exit(1)

def main():
    """Run the setup wizard"""
    reset = '--reset' in sys.argv
    wizard = SetupWizard()
    wizard.run(reset)

if __name__ == "__main__":
    main() 