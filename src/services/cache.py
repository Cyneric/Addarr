"""
Cache service module.

This module provides a simple in-memory caching system with expiration.
It helps improve performance by caching frequently accessed data and
automatically removing expired entries.
"""

from typing import Any, Optional
from datetime import datetime, timedelta
import threading

class CacheEntry:
    """Cache entry with expiration"""
    def __init__(self, value: Any, ttl: int):
        self.value = value
        self.expiry = datetime.now() + timedelta(seconds=ttl)
        
    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expiry

class Cache:
    """Simple in-memory cache with expiration"""
    
    def __init__(self, default_ttl: int = 300):
        self._cache = {}
        self._default_ttl = default_ttl
        self._lock = threading.Lock()
        
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        with self._lock:
            entry = self._cache.get(key)
            if entry and not entry.is_expired:
                return entry.value
            if entry:
                del self._cache[key]
            return None
            
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with TTL"""
        with self._lock:
            self._cache[key] = CacheEntry(
                value,
                ttl or self._default_ttl
            )
            
    def delete(self, key: str) -> None:
        """Delete value from cache"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                
    def clear(self) -> None:
        """Clear all cached values"""
        with self._lock:
            self._cache.clear()
            
    def cleanup(self) -> None:
        """Remove expired entries"""
        with self._lock:
            now = datetime.now()
            expired = [
                k for k, v in self._cache.items()
                if v.is_expired
            ]
            for key in expired:
                del self._cache[key]

# Create global cache instance
cache = Cache() 