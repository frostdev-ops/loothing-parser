"""
Configuration module for WoW Combat Log Parser API.

Provides centralized configuration management for database connections,
server settings, authentication, and environment-specific configurations.
"""

from .settings import (
    ApplicationSettings,
    DatabaseSettings,
    RedisSettings,
    ServerSettings,
    AuthSettings,
    UploadSettings,
    get_settings,
    reload_settings,
    get_database_config,
    is_docker_environment,
    is_production_environment,
    settings
)

__all__ = [
    "ApplicationSettings",
    "DatabaseSettings",
    "RedisSettings",
    "ServerSettings",
    "AuthSettings",
    "UploadSettings",
    "get_settings",
    "reload_settings",
    "get_database_config",
    "is_docker_environment",
    "is_production_environment",
    "settings"
]