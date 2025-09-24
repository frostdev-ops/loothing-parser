"""
Configuration for existing schema adapter integration.

This module provides configuration settings and utilities for integrating
the parser with the existing lootbong database schema.
"""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class ExistingSchemaConfig:
    """Configuration for existing schema integration."""

    # Database connection settings
    use_existing_schema: bool = True
    skip_table_creation: bool = True

    # Schema mapping settings
    encounter_id_format: str = "uuid"  # "uuid" or "string"
    character_guid_format: str = "{name}-{server}"

    # Data conversion settings
    duration_unit: str = "seconds"  # Parser expects seconds, DB stores milliseconds
    timestamp_format: str = "unix"  # Convert to unix timestamps

    # Default values for missing fields
    default_region: str = "US"
    default_faction: Optional[str] = None
    default_pull_number: int = 1

    # Performance settings
    default_query_limit: int = 50
    max_query_limit: int = 1000
    enable_query_caching: bool = True
    cache_ttl_seconds: int = 300

    # Error handling
    ignore_missing_fields: bool = True
    fallback_to_defaults: bool = True
    strict_uuid_validation: bool = False

    # Logging settings
    log_sql_queries: bool = False
    log_parameter_values: bool = False
    log_conversion_errors: bool = True


def get_existing_schema_config() -> ExistingSchemaConfig:
    """
    Get existing schema configuration from environment variables and defaults.

    Returns:
        ExistingSchemaConfig instance with settings from environment
    """
    return ExistingSchemaConfig(
        # Core settings
        use_existing_schema=_get_bool_env("PARSER_USE_EXISTING_SCHEMA", True),
        skip_table_creation=_get_bool_env("PARSER_SKIP_TABLE_CREATION", True),

        # Format settings
        encounter_id_format=os.getenv("PARSER_ENCOUNTER_ID_FORMAT", "uuid"),
        character_guid_format=os.getenv("PARSER_CHARACTER_GUID_FORMAT", "{name}-{server}"),

        # Conversion settings
        duration_unit=os.getenv("PARSER_DURATION_UNIT", "seconds"),
        timestamp_format=os.getenv("PARSER_TIMESTAMP_FORMAT", "unix"),

        # Defaults
        default_region=os.getenv("PARSER_DEFAULT_REGION", "US"),
        default_faction=os.getenv("PARSER_DEFAULT_FACTION"),  # Can be None
        default_pull_number=int(os.getenv("PARSER_DEFAULT_PULL_NUMBER", "1")),

        # Performance
        default_query_limit=int(os.getenv("PARSER_DEFAULT_QUERY_LIMIT", "50")),
        max_query_limit=int(os.getenv("PARSER_MAX_QUERY_LIMIT", "1000")),
        enable_query_caching=_get_bool_env("PARSER_ENABLE_QUERY_CACHING", True),
        cache_ttl_seconds=int(os.getenv("PARSER_CACHE_TTL_SECONDS", "300")),

        # Error handling
        ignore_missing_fields=_get_bool_env("PARSER_IGNORE_MISSING_FIELDS", True),
        fallback_to_defaults=_get_bool_env("PARSER_FALLBACK_TO_DEFAULTS", True),
        strict_uuid_validation=_get_bool_env("PARSER_STRICT_UUID_VALIDATION", False),

        # Logging
        log_sql_queries=_get_bool_env("PARSER_LOG_SQL_QUERIES", False),
        log_parameter_values=_get_bool_env("PARSER_LOG_PARAMETER_VALUES", False),
        log_conversion_errors=_get_bool_env("PARSER_LOG_CONVERSION_ERRORS", True),
    )


def _get_bool_env(key: str, default: bool) -> bool:
    """Get boolean environment variable with default."""
    value = os.getenv(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


def get_database_config() -> Dict[str, Any]:
    """
    Get database configuration for existing schema integration.

    This function checks for the existing lootbong database configuration
    and returns connection parameters.

    Returns:
        Database configuration dictionary
    """
    # Check for existing database configuration
    db_config = {
        "type": "postgresql",  # Existing system uses PostgreSQL
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "loottracker"),
        "user": os.getenv("DB_USER", "lootuser"),
        "password": os.getenv("DB_PASSWORD", ""),
    }

    # Validate required fields
    if not db_config["password"]:
        raise ValueError("DB_PASSWORD environment variable is required")

    return db_config


def validate_existing_schema_environment() -> Dict[str, bool]:
    """
    Validate that the environment is properly configured for existing schema integration.

    Returns:
        Dictionary with validation results for each check
    """
    checks = {}

    # Check database environment variables
    required_db_vars = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    for var in required_db_vars:
        checks[f"env_var_{var}"] = bool(os.getenv(var))

    # Check database connectivity (would need actual database connection to test)
    checks["database_connection"] = None  # Placeholder - implement with actual DB test

    # Check that required tables exist (would need database connection)
    required_tables = ["combat_encounters", "combat_performances", "characters", "guilds"]
    for table in required_tables:
        checks[f"table_{table}"] = None  # Placeholder

    # Check configuration validity
    config = get_existing_schema_config()
    checks["config_valid"] = True  # Basic validation passed if we get here
    checks["encounter_id_format_valid"] = config.encounter_id_format in ["uuid", "string"]
    checks["duration_unit_valid"] = config.duration_unit in ["seconds", "milliseconds"]

    return checks


def create_adapter_from_config(db_connection) -> 'ExistingSchemaAdapter':
    """
    Create an ExistingSchemaAdapter instance using configuration settings.

    Args:
        db_connection: Database connection instance

    Returns:
        Configured ExistingSchemaAdapter instance
    """
    from ..database.existing_schema_adapter import ExistingSchemaAdapter

    # Get configuration
    config = get_existing_schema_config()

    # Create adapter with configuration
    adapter = ExistingSchemaAdapter(db_connection)

    # Apply configuration settings
    if hasattr(adapter, 'config'):
        adapter.config = config
    else:
        # Store config as attribute
        adapter._config = config

    return adapter


def get_schema_migration_status() -> Dict[str, Any]:
    """
    Get status of schema migration from parser schema to existing schema.

    Returns:
        Dictionary with migration status information
    """
    return {
        "migration_type": "adapter_based",
        "uses_existing_tables": True,
        "creates_new_tables": False,
        "migration_required": False,
        "backwards_compatible": True,
        "adapter_version": "1.0.0",
        "supported_parser_versions": ["2.0.0+"],
        "database_schema_version": "existing_lootbong",
        "notes": [
            "Uses ExistingSchemaAdapter to map parser calls to existing database schema",
            "No schema migration required - works with current database",
            "Read-only adapter - does not modify existing data structure",
            "Provides compatibility layer between parser expectations and database reality"
        ]
    }


# Export configuration for easy import
__all__ = [
    'ExistingSchemaConfig',
    'get_existing_schema_config',
    'get_database_config',
    'validate_existing_schema_environment',
    'create_adapter_from_config',
    'get_schema_migration_status'
]