"""
Rate limiting middleware for API v1.

Implements rate limiting based on API keys, IP addresses, and request patterns
to prevent abuse and ensure fair resource usage.
"""

import time
import logging
from typing import Dict, Tuple, Optional, Callable
from collections import defaultdict, deque
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RateLimitConfig:
    """Configuration for rate limiting rules."""

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        burst_limit: int = 10,
        window_size: int = 60,
    ):
        """
        Initialize rate limit configuration.

        Args:
            requests_per_minute: Max requests per minute
            requests_per_hour: Max requests per hour
            burst_limit: Max burst requests in short time
            window_size: Time window in seconds for burst detection
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.burst_limit = burst_limit
        self.window_size = window_size


class RateLimitTracker:
    """Tracks rate limiting for individual clients."""

    def __init__(self, config: RateLimitConfig):
        """Initialize rate limit tracker with configuration."""
        self.config = config
        self.minute_counts: Dict[str, int] = defaultdict(int)
        self.hour_counts: Dict[str, int] = defaultdict(int)
        self.burst_times: Dict[str, deque] = defaultdict(lambda: deque())
        self.last_reset_minute: Dict[str, int] = {}
        self.last_reset_hour: Dict[str, int] = {}

    def is_rate_limited(self, client_id: str) -> Tuple[bool, str, Dict[str, int]]:
        """
        Check if client is rate limited.

        Args:
            client_id: Unique identifier for the client

        Returns:
            Tuple of (is_limited, reason, remaining_limits)
        """
        current_time = time.time()
        current_minute = int(current_time // 60)
        current_hour = int(current_time // 3600)

        # Reset counters if needed
        if (
            client_id not in self.last_reset_minute
            or self.last_reset_minute[client_id] != current_minute
        ):
            self.minute_counts[client_id] = 0
            self.last_reset_minute[client_id] = current_minute

        if client_id not in self.last_reset_hour or self.last_reset_hour[client_id] != current_hour:
            self.hour_counts[client_id] = 0
            self.last_reset_hour[client_id] = current_hour

        # Check burst limit
        burst_window_start = current_time - self.config.window_size
        burst_times = self.burst_times[client_id]

        # Remove old burst entries
        while burst_times and burst_times[0] < burst_window_start:
            burst_times.popleft()

        if len(burst_times) >= self.config.burst_limit:
            remaining = {
                "minute": max(0, self.config.requests_per_minute - self.minute_counts[client_id]),
                "hour": max(0, self.config.requests_per_hour - self.hour_counts[client_id]),
                "burst": 0,
            }
            return True, "Burst limit exceeded", remaining

        # Check minute limit
        if self.minute_counts[client_id] >= self.config.requests_per_minute:
            remaining = {
                "minute": 0,
                "hour": max(0, self.config.requests_per_hour - self.hour_counts[client_id]),
                "burst": max(0, self.config.burst_limit - len(burst_times)),
            }
            return True, "Minute limit exceeded", remaining

        # Check hour limit
        if self.hour_counts[client_id] >= self.config.requests_per_hour:
            remaining = {
                "minute": max(0, self.config.requests_per_minute - self.minute_counts[client_id]),
                "hour": 0,
                "burst": max(0, self.config.burst_limit - len(burst_times)),
            }
            return True, "Hour limit exceeded", remaining

        # Update counters
        self.minute_counts[client_id] += 1
        self.hour_counts[client_id] += 1
        burst_times.append(current_time)

        # Calculate remaining limits
        remaining = {
            "minute": max(0, self.config.requests_per_minute - self.minute_counts[client_id]),
            "hour": max(0, self.config.requests_per_hour - self.hour_counts[client_id]),
            "burst": max(0, self.config.burst_limit - len(burst_times)),
        }

        return False, "", remaining


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware for API rate limiting.

    Implements rate limiting based on API keys with configurable limits
    and provides rate limit headers in responses.
    """

    def __init__(
        self,
        app,
        default_config: Optional[RateLimitConfig] = None,
        custom_configs: Optional[Dict[str, RateLimitConfig]] = None,
    ):
        """
        Initialize rate limiting middleware.

        Args:
            app: FastAPI application instance
            default_config: Default rate limit configuration
            custom_configs: Custom configurations for specific API keys
        """
        super().__init__(app)
        self.default_config = default_config or RateLimitConfig()
        self.custom_configs = custom_configs or {}
        self.trackers: Dict[str, RateLimitTracker] = {}

    def get_client_id(self, request: Request) -> str:
        """
        Extract client ID from request for rate limiting.

        Args:
            request: FastAPI request object

        Returns:
            Client identifier string
        """
        # Try to get API key from various sources
        api_key = None

        # Check Authorization header
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            api_key = auth_header[7:]

        # Check query parameter
        if not api_key:
            api_key = request.query_params.get("api_key")

        # Check X-API-Key header
        if not api_key:
            api_key = request.headers.get("x-api-key")

        # Fall back to IP address if no API key
        if not api_key:
            client_host = request.client.host if request.client else "unknown"
            return f"ip:{client_host}"

        return f"api_key:{api_key}"

    def get_tracker(self, client_id: str) -> RateLimitTracker:
        """
        Get or create rate limit tracker for client.

        Args:
            client_id: Client identifier

        Returns:
            RateLimitTracker instance
        """
        if client_id not in self.trackers:
            # Determine which config to use
            config = self.default_config
            if client_id.startswith("api_key:"):
                api_key = client_id[8:]  # Remove "api_key:" prefix
                if api_key in self.custom_configs:
                    config = self.custom_configs[api_key]

            self.trackers[client_id] = RateLimitTracker(config)

        return self.trackers[client_id]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and apply rate limiting.

        Args:
            request: FastAPI request object
            call_next: Next middleware/endpoint in chain

        Returns:
            Response with rate limit headers

        Raises:
            HTTPException: If rate limit is exceeded
        """
        # Skip rate limiting for health checks and docs
        if request.url.path in [
            "/health",
            "/api/v1/health",
            "/api/v1/docs",
            "/api/v1/redoc",
            "/api/v1/openapi.json",
        ]:
            return await call_next(request)

        # Get client ID and tracker
        client_id = self.get_client_id(request)
        tracker = self.get_tracker(client_id)

        # Check rate limits
        is_limited, reason, remaining = tracker.is_rate_limited(client_id)

        if is_limited:
            logger.warning(f"Rate limit exceeded for {client_id}: {reason}")
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {reason}",
                headers={
                    "X-RateLimit-Limit-Minute": str(tracker.config.requests_per_minute),
                    "X-RateLimit-Limit-Hour": str(tracker.config.requests_per_hour),
                    "X-RateLimit-Remaining-Minute": str(remaining["minute"]),
                    "X-RateLimit-Remaining-Hour": str(remaining["hour"]),
                    "X-RateLimit-Remaining-Burst": str(remaining["burst"]),
                    "Retry-After": "60",  # Suggest retry after 1 minute
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit-Minute"] = str(tracker.config.requests_per_minute)
        response.headers["X-RateLimit-Limit-Hour"] = str(tracker.config.requests_per_hour)
        response.headers["X-RateLimit-Remaining-Minute"] = str(remaining["minute"])
        response.headers["X-RateLimit-Remaining-Hour"] = str(remaining["hour"])
        response.headers["X-RateLimit-Remaining-Burst"] = str(remaining["burst"])

        return response
