"""
Configuration settings for WoW Combat Log Parser API.

Handles environment variables, database configuration, and application settings
for both Docker and standalone environments.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class DatabaseSettings:
    """Database configuration settings."""

    # PostgreSQL settings (Docker environment)
    host: str = "localhost"
    port: int = 5432
    name: str = "lootdata"
    user: str = "lootbong"
    password: str = ""

    # SQLite settings (standalone environment)
    sqlite_path: str = "combat_logs.db"

    # Connection pool settings
    pool_min: int = 2
    pool_max: int = 20
    pool_timeout: int = 30

    @classmethod
    def from_env(cls) -> "DatabaseSettings":
        """Load database settings from environment variables."""
        return cls(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            name=os.getenv("DB_NAME", "lootdata"),
            user=os.getenv("DB_USER", "lootbong"),
            password=os.getenv("DB_PASSWORD", ""),
            sqlite_path=os.getenv("DB_PATH", "combat_logs.db"),
            pool_min=int(os.getenv("DB_POOL_MIN", "2")),
            pool_max=int(os.getenv("DB_POOL_MAX", "20")),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30"))
        )

    @property
    def use_postgresql(self) -> bool:
        """Determine if PostgreSQL should be used (Docker environment)."""
        return bool(self.host and self.host != "localhost" and self.name and self.user)


@dataclass
class RedisSettings:
    """Redis configuration settings."""

    host: str = "localhost"
    port: int = 6379
    password: str = ""
    db: int = 0
    enabled: bool = False

    @classmethod
    def from_env(cls) -> "RedisSettings":
        """Load Redis settings from environment variables."""
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_enabled = redis_host and redis_host != "localhost"

        return cls(
            host=redis_host,
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD", ""),
            db=int(os.getenv("REDIS_DB", "0")),
            enabled=redis_enabled
        )

    @property
    def url(self) -> str:
        """Get Redis connection URL."""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


@dataclass
class ServerSettings:
    """Server configuration settings."""

    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    workers: int = 1
    log_level: str = "info"

    @classmethod
    def from_env(cls) -> "ServerSettings":
        """Load server settings from environment variables."""
        return cls(
            host=os.getenv("PARSER_HOST", "0.0.0.0"),
            port=int(os.getenv("PARSER_PORT", "8000")),
            reload=os.getenv("PARSER_RELOAD", "false").lower() == "true",
            workers=int(os.getenv("WORKER_COUNT", "1")),
            log_level=os.getenv("LOG_LEVEL", "info").lower()
        )


@dataclass
class AuthSettings:
    """Authentication and security settings."""

    jwt_secret: str = "default-jwt-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    api_key: str = "dev_key_12345"

    @classmethod
    def from_env(cls) -> "AuthSettings":
        """Load auth settings from environment variables."""
        return cls(
            jwt_secret=os.getenv("JWT_SECRET", "default-jwt-secret-change-in-production"),
            jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
            api_key=os.getenv("API_KEY", "dev_key_12345")
        )


@dataclass
class UploadSettings:
    """File upload configuration settings."""

    upload_dir: str = "/app/parser/uploads"
    max_file_size: int = 5368709120  # 5GB
    allowed_extensions: List[str] = field(default_factory=lambda: [".txt", ".log"])

    @classmethod
    def from_env(cls) -> "UploadSettings":
        """Load upload settings from environment variables."""
        upload_dir = os.getenv("UPLOAD_DIR", "/app/parser/uploads")

        return cls(
            upload_dir=upload_dir,
            max_file_size=int(os.getenv("MAX_FILE_SIZE", "5368709120")),
            allowed_extensions=[".txt", ".log", ".gz", ".zip"]
        )

    def ensure_upload_dir(self):
        """Ensure upload directory exists."""
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)


@dataclass
class ApplicationSettings:
    """Main application settings container."""

    database: DatabaseSettings
    redis: RedisSettings
    server: ServerSettings
    auth: AuthSettings
    upload: UploadSettings

    # Runtime settings
    environment: str = "development"
    debug: bool = False

    @classmethod
    def from_env(cls) -> "ApplicationSettings":
        """Load all settings from environment variables."""
        return cls(
            database=DatabaseSettings.from_env(),
            redis=RedisSettings.from_env(),
            server=ServerSettings.from_env(),
            auth=AuthSettings.from_env(),
            upload=UploadSettings.from_env(),
            environment=os.getenv("ENVIRONMENT", "development"),
            debug=os.getenv("DEBUG", "false").lower() == "true"
        )

    def setup_logging(self):
        """Configure logging based on settings."""
        level = getattr(logging, self.server.log_level.upper(), logging.INFO)

        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        if self.debug:
            logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

    def validate(self):
        """Validate configuration settings."""
        errors = []

        # Database validation
        if self.database.use_postgresql:
            if not self.database.password:
                errors.append("PostgreSQL password is required when using database host")

        # Upload directory validation
        try:
            self.upload.ensure_upload_dir()
        except Exception as e:
            errors.append(f"Cannot create upload directory: {e}")

        # Port validation
        if not (1 <= self.server.port <= 65535):
            errors.append(f"Invalid port number: {self.server.port}")

        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")

    def log_configuration(self):
        """Log current configuration (excluding sensitive data)."""
        logger = logging.getLogger(__name__)

        logger.info("=== Parser Configuration ===")
        logger.info(f"Environment: {self.environment}")
        logger.info(f"Debug: {self.debug}")

        # Database
        if self.database.use_postgresql:
            logger.info(f"Database: PostgreSQL ({self.database.host}:{self.database.port}/{self.database.name})")
        else:
            logger.info(f"Database: SQLite ({self.database.sqlite_path})")

        # Redis
        if self.redis.enabled:
            logger.info(f"Redis: Enabled ({self.redis.host}:{self.redis.port})")
        else:
            logger.info("Redis: Disabled")

        # Server
        logger.info(f"Server: {self.server.host}:{self.server.port}")
        logger.info(f"Workers: {self.server.workers}")
        logger.info(f"Log Level: {self.server.log_level}")

        # Upload
        logger.info(f"Upload Directory: {self.upload.upload_dir}")
        logger.info(f"Max File Size: {self.upload.max_file_size / (1024*1024*1024):.1f}GB")

        logger.info("=== End Configuration ===")


# Global settings instance
settings = ApplicationSettings.from_env()


def get_settings() -> ApplicationSettings:
    """Get the global settings instance."""
    return settings


def reload_settings() -> ApplicationSettings:
    """Reload settings from environment variables."""
    global settings
    settings = ApplicationSettings.from_env()
    return settings


# Convenience functions for common operations
def get_database_config() -> Dict[str, Any]:
    """Get database configuration for connection."""
    db_settings = settings.database

    if db_settings.use_postgresql:
        return {
            "type": "postgresql",
            "host": db_settings.host,
            "port": db_settings.port,
            "database": db_settings.name,
            "user": db_settings.user,
            "password": db_settings.password,
            "pool_min": db_settings.pool_min,
            "pool_max": db_settings.pool_max,
        }
    else:
        return {
            "type": "sqlite",
            "path": db_settings.sqlite_path
        }


def is_docker_environment() -> bool:
    """Check if running in Docker environment."""
    return bool(os.getenv("DOCKER_ENV") or os.path.exists("/.dockerenv"))


def is_production_environment() -> bool:
    """Check if running in production environment."""
    return settings.environment.lower() in ("production", "prod")