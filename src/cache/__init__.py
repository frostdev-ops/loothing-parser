"""
Cache module for WoW Combat Log Parser API.

Provides Redis-based caching with automatic fallback to in-memory caching
for improved performance and session management.
"""

from .redis_client import (
    CacheManager,
    CacheBackend,
    RedisBackend,
    MemoryBackend,
    get_cache_manager,
    close_cache_manager
)

__all__ = [
    "CacheManager",
    "CacheBackend",
    "RedisBackend",
    "MemoryBackend",
    "get_cache_manager",
    "close_cache_manager"
]