"""
Redis client for caching and session management.

Provides Redis integration for the parser API with fallback to in-memory caching
when Redis is not available.
"""

import json
import logging
import time
from typing import Optional, Any, Dict, Union
from abc import ABC, abstractmethod

try:
    import redis
    from redis.connection import ConnectionPool
    _redis_available = True
except ImportError:
    _redis_available = False

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Abstract base class for cache backends."""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value by key."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value with optional TTL."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete key."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check backend health."""
        pass


class RedisBackend(CacheBackend):
    """Redis cache backend."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: Optional[str] = None,
        db: int = 0,
        **kwargs
    ):
        """
        Initialize Redis backend.

        Args:
            host: Redis host
            port: Redis port
            password: Redis password
            db: Redis database number
        """
        if not _redis_available:
            raise ImportError("redis package is required for Redis backend")

        self.host = host
        self.port = port
        self.password = password
        self.db = db

        # Create connection pool
        pool_kwargs = {
            "host": host,
            "port": port,
            "db": db,
            "decode_responses": True,
            "socket_connect_timeout": 5,
            "socket_timeout": 5,
            "retry_on_timeout": True,
            "health_check_interval": 30,
        }

        if password:
            pool_kwargs["password"] = password

        # Add any additional connection parameters
        pool_kwargs.update(kwargs)

        self.pool = ConnectionPool(**pool_kwargs)
        self.client = redis.Redis(connection_pool=self.pool)

        logger.info(f"Redis backend initialized: {host}:{port}")

    async def get(self, key: str) -> Optional[Any]:
        """Get value by key."""
        try:
            value = self.client.get(key)
            if value is None:
                return None

            # Try to parse as JSON, fall back to string
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        except Exception as e:
            logger.warning(f"Redis GET failed for key '{key}': {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value with optional TTL."""
        try:
            # Serialize value as JSON if it's not a string
            if isinstance(value, str):
                serialized_value = value
            else:
                serialized_value = json.dumps(value)

            result = self.client.set(key, serialized_value, ex=ttl)
            return bool(result)

        except Exception as e:
            logger.warning(f"Redis SET failed for key '{key}': {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key."""
        try:
            result = self.client.delete(key)
            return result > 0
        except Exception as e:
            logger.warning(f"Redis DELETE failed for key '{key}': {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        try:
            return bool(self.client.exists(key))
        except Exception as e:
            logger.warning(f"Redis EXISTS failed for key '{key}': {e}")
            return False

    async def health_check(self) -> bool:
        """Check Redis health."""
        try:
            response = self.client.ping()
            return response is True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False

    def close(self):
        """Close Redis connection."""
        try:
            self.pool.disconnect()
            logger.info("Redis connection pool closed")
        except Exception as e:
            logger.warning(f"Error closing Redis connection: {e}")


class MemoryBackend(CacheBackend):
    """In-memory cache backend (fallback)."""

    def __init__(self, max_size: int = 1000):
        """
        Initialize memory backend.

        Args:
            max_size: Maximum number of items to store
        """
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.max_size = max_size
        logger.info("Memory cache backend initialized")

    async def get(self, key: str) -> Optional[Any]:
        """Get value by key."""
        entry = self.cache.get(key)
        if not entry:
            return None

        # Check TTL
        if entry.get("expires") and entry["expires"] < time.time():
            del self.cache[key]
            return None

        return entry["value"]

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value with optional TTL."""
        # Evict old entries if at capacity
        if len(self.cache) >= self.max_size and key not in self.cache:
            # Remove oldest entry
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]

        entry = {"value": value}
        if ttl:
            entry["expires"] = time.time() + ttl

        self.cache[key] = entry
        return True

    async def delete(self, key: str) -> bool:
        """Delete key."""
        if key in self.cache:
            del self.cache[key]
            return True
        return False

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        entry = self.cache.get(key)
        if not entry:
            return False

        # Check TTL
        if entry.get("expires") and entry["expires"] < time.time():
            del self.cache[key]
            return False

        return True

    async def health_check(self) -> bool:
        """Memory backend is always healthy."""
        return True


class CacheManager:
    """
    Cache manager with automatic backend selection.

    Automatically selects Redis (if available) or falls back to in-memory caching.
    """

    def __init__(
        self,
        redis_host: Optional[str] = None,
        redis_port: int = 6379,
        redis_password: Optional[str] = None,
        redis_db: int = 0,
        **kwargs
    ):
        """
        Initialize cache manager.

        Args:
            redis_host: Redis host (if None, uses memory backend)
            redis_port: Redis port
            redis_password: Redis password
            redis_db: Redis database number
        """
        self.backend = None
        self.backend_type = None

        # Try Redis first if configured
        if redis_host and _redis_available:
            try:
                self.backend = RedisBackend(
                    host=redis_host,
                    port=redis_port,
                    password=redis_password,
                    db=redis_db,
                    **kwargs
                )
                self.backend_type = "redis"
                logger.info("Using Redis cache backend")
            except Exception as e:
                logger.warning(f"Failed to initialize Redis backend: {e}")
                logger.info("Falling back to memory cache backend")

        # Fall back to memory backend
        if not self.backend:
            self.backend = MemoryBackend()
            self.backend_type = "memory"

    async def get(self, key: str) -> Optional[Any]:
        """Get value by key."""
        return await self.backend.get(key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value with optional TTL."""
        return await self.backend.set(key, value, ttl)

    async def delete(self, key: str) -> bool:
        """Delete key."""
        return await self.backend.delete(key)

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        return await self.backend.exists(key)

    async def health_check(self) -> bool:
        """Check cache backend health."""
        return await self.backend.health_check()

    def close(self):
        """Close cache backend."""
        if hasattr(self.backend, 'close'):
            self.backend.close()

    # Convenience methods for common patterns
    async def get_or_set(
        self,
        key: str,
        factory_func,
        ttl: Optional[int] = None
    ) -> Any:
        """
        Get value or set it using factory function.

        Args:
            key: Cache key
            factory_func: Function to generate value if not in cache
            ttl: Time to live in seconds

        Returns:
            Cached or newly generated value
        """
        value = await self.get(key)
        if value is not None:
            return value

        # Generate new value
        if callable(factory_func):
            value = factory_func()
        else:
            value = factory_func

        await self.set(key, value, ttl)
        return value

    async def cache_api_key_validation(self, api_key: str, is_valid: bool, ttl: int = 300):
        """Cache API key validation result."""
        cache_key = f"api_key_valid:{api_key}"
        await self.set(cache_key, is_valid, ttl)

    async def get_cached_api_key_validation(self, api_key: str) -> Optional[bool]:
        """Get cached API key validation result."""
        cache_key = f"api_key_valid:{api_key}"
        result = await self.get(cache_key)
        return result if isinstance(result, bool) else None


# Global cache manager instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """Get the global cache manager instance."""
    global _cache_manager

    if _cache_manager is None:
        # Initialize based on configuration
        from ..config import get_settings
        settings = get_settings()

        redis_settings = settings.redis
        if redis_settings.enabled:
            _cache_manager = CacheManager(
                redis_host=redis_settings.host,
                redis_port=redis_settings.port,
                redis_password=redis_settings.password,
                redis_db=redis_settings.db
            )
        else:
            _cache_manager = CacheManager()

    return _cache_manager


def close_cache_manager():
    """Close the global cache manager."""
    global _cache_manager
    if _cache_manager:
        _cache_manager.close()
        _cache_manager = None