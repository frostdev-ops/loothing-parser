"""
Performance monitoring middleware for API v1.

Tracks request timing, response sizes, and other performance metrics
for monitoring and optimization purposes.
"""

import time
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class PerformanceMiddleware(BaseHTTPMiddleware):
    """
    Middleware for tracking API performance metrics.

    Monitors request processing time, response sizes, and adds
    performance headers to responses.
    """

    def __init__(self, app, enable_detailed_logging: bool = False):
        """
        Initialize performance middleware.

        Args:
            app: FastAPI application instance
            enable_detailed_logging: Whether to log detailed performance data
        """
        super().__init__(app)
        self.enable_detailed_logging = enable_detailed_logging

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and track performance metrics.

        Args:
            request: FastAPI request object
            call_next: Next middleware/endpoint in chain

        Returns:
            Response with added performance headers
        """
        # Start timing
        start_time = time.time()
        process_start = time.process_time()

        # Add request ID for tracking
        request_id = f"req_{int(start_time * 1000000)}"
        request.state.request_id = request_id

        try:
            # Process request
            response = await call_next(request)

            # Calculate timing metrics
            end_time = time.time()
            process_end = time.process_time()

            duration_ms = (end_time - start_time) * 1000
            cpu_time_ms = (process_end - process_start) * 1000

            # Add performance headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
            response.headers["X-CPU-Time"] = f"{cpu_time_ms:.2f}ms"

            # Calculate response size if available
            response_size = 0
            if hasattr(response, "body") and response.body:
                response_size = len(response.body)
                response.headers["X-Response-Size"] = str(response_size)

            # Log performance data if enabled
            if self.enable_detailed_logging:
                logger.info(
                    f"API Request: {request.method} {request.url.path} - "
                    f"Status: {response.status_code} - "
                    f"Duration: {duration_ms:.2f}ms - "
                    f"CPU: {cpu_time_ms:.2f}ms - "
                    f"Size: {response_size} bytes - "
                    f"ID: {request_id}"
                )

            return response

        except Exception as e:
            # Log errors with timing information
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000

            logger.error(
                f"API Error: {request.method} {request.url.path} - "
                f"Duration: {duration_ms:.2f}ms - "
                f"Error: {str(e)} - "
                f"ID: {request_id}"
            )

            # Re-raise the exception
            raise
