"""
Health monitoring service module.

This module provides centralized health monitoring functionality for all services.
Includes both one-time checks and periodic monitoring.
"""

import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from colorama import Fore, Style

from src.config.settings import config
from src.utils.logger import get_logger

logger = get_logger("addarr.health")

def display_health_status(results: Dict[str, List[Dict]]) -> bool:
    """Display health check results
    
    Args:
        results: Health check results
        
    Returns:
        bool: True if all enabled services are healthy
    """
    print(f"\n{Fore.CYAN}{'═' * 50}")
    print(f"{Fore.CYAN} 🏥 Starting initial service health check...")
    print(f"{Fore.CYAN}{'═' * 50}")
    
    all_healthy = True
    
    if results["media_services"]:
        print(f"\n{Fore.YELLOW}Media Services:")
        for service in results["media_services"]:
            status_color = Fore.GREEN if service["healthy"] else Fore.RED
            print(f"• {service['name']}: {status_color}{service['status']}{Style.RESET_ALL}")
            all_healthy &= service["healthy"]
    
    if results["download_clients"]:
        print(f"\n{Fore.YELLOW}Download Clients:")
        for client in results["download_clients"]:
            status_color = Fore.GREEN if client["healthy"] else Fore.RED
            print(f"• {client['name']}: {status_color}{client['status']}{Style.RESET_ALL}")
            all_healthy &= client["healthy"]
    
    print(f"\n{Fore.CYAN}{'═' * 50}")
    
    if all_healthy:
        print(f"{Fore.GREEN}✅ All services are healthy!\n")
    else:
        print(f"{Fore.RED}❌ Some services are not responding!\n")
        print(f"{Fore.YELLOW}Please check your configuration and ensure all services are running.\n")
    
    return all_healthy

class HealthService:
    """Service for health monitoring"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(HealthService, cls).__new__(cls)
            cls._initialize()
        return cls._instance
    
    @classmethod
    def _initialize(cls):
        cls._last_check = None
        cls._unhealthy_services = set()
        cls._running = False
        cls._task = None
        cls.interval = 15 * 60  # Default 15 minutes
        
    async def start(self, interval_minutes: int = 15):
        """Start periodic health monitoring"""
        if self._running:
            logger.warning("Health monitoring already running")
            return
            
        self.interval = interval_minutes * 60  # Convert to seconds
        self._running = True
        logger.info(f"🏥 Starting health monitoring (interval: {interval_minutes} minutes)")
        
        self._task = asyncio.create_task(self._monitor_loop())
        
    async def stop(self):
        """Stop health monitoring"""
        if not self._running:
            return
            
        self._running = False
        logger.info("🛑 Stopping health monitoring")
        
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
                
    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self._running:
            try:
                logger.info(f"{Fore.CYAN}{'═' * 50}")
                logger.info(f"{Fore.CYAN}🏥 Running health check...{Style.RESET_ALL}")
                
                results = await self.run_health_checks()
                self._last_check = datetime.now()
                next_check = self._last_check + timedelta(seconds=self.interval)
                
                current_unhealthy = set()
                
                # Process results and update status
                for service_type in ["media_services", "download_clients"]:
                    for service in results[service_type]:
                        if not service["healthy"]:
                            error_msg = f"{service['name']}: {service['status']}"
                            current_unhealthy.add(error_msg)
                            
                # Log changes in service health
                new_failures = current_unhealthy - self._unhealthy_services
                if new_failures:
                    logger.error(f"❌ Services became unhealthy:")
                    for service in new_failures:
                        logger.error(f"  • {service}")
                        
                recovered = self._unhealthy_services - current_unhealthy
                if recovered:
                    logger.info(f"✅ Services recovered:")
                    for service in recovered:
                        logger.info(f"  • {service}")
                        
                self._unhealthy_services = current_unhealthy
                
                if not current_unhealthy:
                    logger.info("✅ All services healthy")
                    
                # Show next check time
                logger.info(f"⏰ Next check at: {next_check.strftime('%H:%M:%S')}")
                logger.info(f"{Fore.CYAN}{'═' * 50}{Style.RESET_ALL}")
                    
            except Exception as e:
                logger.error(f"❌ Error in health monitoring: {str(e)}")
                
            await asyncio.sleep(self.interval)

    async def check_service_health(self, url: str, api_key: str, service_type: str) -> Tuple[bool, str]:
        """Check if a service is responding"""
        try:
            server_url = url.rstrip('/')
            
            # Different endpoints for different services
            if service_type == "radarr":
                api_url = f"{server_url}/api/v3/system/status"
            elif service_type == "sonarr":
                api_url = f"{server_url}/api/v3/system/status"
            elif service_type == "lidarr":
                api_url = f"{server_url}/api/v1/system/status"
            else:
                return False, f"Unknown service type: {service_type}"

            async with aiohttp.ClientSession() as session:
                headers = {'X-Api-Key': api_key}
                logger.debug(f"Checking health of {service_type} at: {api_url}")
                
                async with session.get(api_url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        version = data.get('version', 'Unknown')
                        return True, f"Online (v{version})"
                    else:
                        return False, f"Error: HTTP {response.status}"

        except aiohttp.ClientConnectorError:
            return False, "Error: Connection failed"
        except asyncio.TimeoutError:
            return False, "Error: Connection timeout"
        except Exception as e:
            return False, f"Error: {str(e)}"
            
    async def check_sabnzbd_health(self, url: str, api_key: str) -> Tuple[bool, str]:
        """Check SABnzbd connection"""
        try:
            server_url = url.rstrip('/')
            api_url = f"{server_url}/api"
            
            params = {
                'apikey': api_key,
                'mode': 'version',
                'output': 'json'
            }
            
            async with aiohttp.ClientSession() as session:
                logger.debug(f"Checking SABnzbd health at: {api_url}")
                async with session.get(api_url, params=params, timeout=10) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            version = data.get('version', 'Unknown')
                        except:
                            text = await response.text()
                            if text and len(text) < 20:
                                version = text.strip()
                            else:
                                return False, f"Error: Invalid response format"
                        
                        return True, f"Online (v{version})"
                    else:
                        return False, f"Error: HTTP {response.status}"
                        
        except Exception as e:
            return False, f"Error: {str(e)}"
            
    async def run_health_checks(self) -> Dict[str, List[Dict]]:
        """Run health checks on all enabled services"""
        results = {
            "media_services": [],
            "download_clients": []
        }
        
        # Check media services
        services = [
            ("Radarr", "radarr"),
            ("Sonarr", "sonarr"),
            ("Lidarr", "lidarr")
        ]
        
        for service_name, config_key in services:
            service_config = config.get(config_key, {})
            if service_config.get("enable"):
                server_config = service_config.get("server", {})
                protocol = "https" if server_config.get("ssl", False) else "http"
                addr = server_config.get("addr", "localhost")
                port = server_config.get("port", "")
                base_path = server_config.get("path", "").rstrip('/')
                
                url = f"{protocol}://{addr}:{port}{base_path}"
                api_key = service_config.get("auth", {}).get("apikey")
                
                is_healthy, status = await self.check_service_health(url, api_key, service_name.lower())
                results["media_services"].append({
                    "name": service_name,
                    "healthy": is_healthy,
                    "status": status
                })
        
        # Check SABnzbd
        sabnzbd = config.get("sabnzbd", {})
        if sabnzbd.get("enable"):
            server_config = sabnzbd.get("server", {})
            protocol = "https" if server_config.get("ssl", False) else "http"
            addr = server_config.get("addr", "localhost")
            port = server_config.get("port", "")
            base_path = server_config.get("path", "").rstrip('/')
            
            url = f"{protocol}://{addr}:{port}{base_path}"
            api_key = sabnzbd.get("auth", {}).get("apikey")
            
            is_healthy, status = await self.check_sabnzbd_health(url, api_key)
            results["download_clients"].append({
                "name": "SABnzbd",
                "healthy": is_healthy,
                "status": status
            })
        
        return results
        
    def get_status(self) -> Dict:
        """Get current monitoring status"""
        return {
            "running": self._running,
            "last_check": self._last_check,
            "unhealthy_services": list(self._unhealthy_services)
        }

# Create global instance
health_service = HealthService() 