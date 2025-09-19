"""
FastAPI server for WoW combat log streaming and queries.

This package provides:
- WebSocket streaming endpoints
- REST API for queries
- Authentication and rate limiting
- Real-time data access
"""

from .streaming_server import create_app
from .auth import authenticate_api_key
from .models import StreamMessage, AuthResponse

__all__ = ["create_app", "authenticate_api_key", "StreamMessage", "AuthResponse"]