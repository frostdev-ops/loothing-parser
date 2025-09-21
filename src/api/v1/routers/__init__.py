"""
API v1 routers package.

This package contains all the FastAPI routers for different endpoint categories:
- characters: Character-related endpoints
- encounters: Encounter analysis endpoints
- analytics: Advanced analytics and trends
- logs: Log processing and upload endpoints
- guilds: Guild management endpoints
- export: Data export endpoints
- webhooks: Webhook management endpoints
"""

from . import characters, encounters, analytics, logs, guilds, export, webhooks

__all__ = ["characters", "encounters", "analytics", "logs", "guilds", "export", "webhooks"]
