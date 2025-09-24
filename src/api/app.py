"""
Unified FastAPI application combining streaming server and REST API v1.

This module creates a single FastAPI application that serves:
- WebSocket streaming endpoints for real-time log processing
- REST API v1 endpoints for queries, uploads, and data access
- Health checks and monitoring endpoints
"""

import os
import logging
import time
import uvicorn
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .streaming_server import create_app as create_streaming_app
from .v1.main import create_v1_app
from src.database.hybrid_manager import HybridDatabaseManager


def create_unified_app(db_path: str = "combat_logs.db") -> FastAPI:
    """
    Create unified FastAPI application with both streaming and REST API v1.

    Args:
        db_path: Path to SQLite database (used only if PostgreSQL not configured)

    Returns:
        Configured FastAPI application with all endpoints
    """
    # Initialize configuration and logging
    from ..config import get_settings
    settings = get_settings()
    settings.setup_logging()
    settings.validate()
    settings.log_configuration()

    # Create the main application
    app = FastAPI(
        title="WoW Combat Log Analysis API",
        description="""
        Unified API for World of Warcraft combat log analysis providing both
        real-time streaming and comprehensive REST endpoints.

        ## Features

        * **Real-time Streaming**: WebSocket endpoints for live log processing
        * **REST API v1**: Complete set of endpoints for data queries and uploads
        * **Character Analysis**: Detailed performance metrics and history
        * **Encounter Metrics**: Boss fights, DPS/HPS rankings, death analysis
        * **Advanced Analytics**: Trends, class balance, progression tracking
        * **Export Capabilities**: Multiple formats (JSON, CSV, WCL)
        * **Guild Management**: Roster analysis, attendance tracking
        * **Webhooks**: Real-time event notifications
        * **Multi-Backend Support**: Automatic PostgreSQL (Docker) or SQLite (standalone)
        * **Redis Caching**: Improved performance with Redis support

        ## Endpoints

        * **WebSocket Streaming**: `/stream` - Real-time log processing
        * **REST API v1**: `/api/v1/*` - All REST endpoints
        * **Health Checks**: `/health`, `/api/v1/health` - Service status
        * **Metrics**: `/metrics` - Prometheus-compatible metrics
        """,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize hybrid database manager (PostgreSQL + InfluxDB)
    db = HybridDatabaseManager()

    # Initialize cache manager
    from ..cache import get_cache_manager
    cache_manager = get_cache_manager()

    # Create streaming app and mount its endpoints
    streaming_app = create_streaming_app(db_path)

    # Create v1 API app
    v1_app = create_v1_app(db)

    # Mount the streaming endpoints at root level
    # Copy streaming-specific endpoints to main app
    for route in streaming_app.routes:
        if hasattr(route, "path"):
            # Skip if it's a health endpoint that we'll replace
            if route.path in ["/health", "/health/live", "/health/ready", "/metrics"]:
                continue
            app.routes.append(route)

    # Mount v1 API with proper sub-application mounting
    # Note: Using app.mount for proper sub-application isolation
    app.mount("/api/v1", v1_app, name="api_v1")

    # Add unified health checks
    @app.get("/health", tags=["Health"])
    async def unified_health_check():
        """Unified health check for all services."""
        # Check database health (both PostgreSQL and InfluxDB)
        db_health = db.health_check()
        postgres_healthy = db_health.get('postgresql', False)
        influx_healthy = db_health.get('influxdb', False)
        db_healthy = postgres_healthy and influx_healthy

        # Check cache health
        cache_healthy = await cache_manager.health_check()
        cache_status = f"{cache_manager.backend_type}:{'operational' if cache_healthy else 'error'}"

        # Overall status
        overall_status = "healthy" if db_healthy else "degraded"

        return {
            "status": overall_status,
            "services": {
                "streaming": "operational",
                "api_v1": "operational",
                "postgresql": "connected" if postgres_healthy else "disconnected",
                "influxdb": "connected" if influx_healthy else "disconnected",
                "cache": cache_status,
            },
            "version": "1.0.0",
            "timestamp": time.time(),
        }

    @app.get("/health/live", tags=["Health"])
    async def liveness_probe():
        """Kubernetes liveness probe."""
        return {"status": "alive"}

    @app.get("/health/ready", tags=["Health"])
    async def readiness_probe():
        """Kubernetes readiness probe."""
        try:
            # Test database connections (both PostgreSQL and InfluxDB)
            db_health = db.health_check()
            postgres_healthy = db_health.get('postgresql', False)
            influx_healthy = db_health.get('influxdb', False)

            if not (postgres_healthy and influx_healthy):
                from fastapi import HTTPException
                detail = f"Databases not ready - PostgreSQL: {postgres_healthy}, InfluxDB: {influx_healthy}"
                raise HTTPException(status_code=503, detail=detail)

            # Test cache connection (optional - don't fail if cache is down)
            cache_healthy = await cache_manager.health_check()
            if not cache_healthy:
                logger.warning("Cache is not healthy but continuing")

            return {
                "status": "ready",
                "postgresql": "ready" if postgres_healthy else "not_ready",
                "influxdb": "ready" if influx_healthy else "not_ready",
                "cache": f"{cache_manager.backend_type}:{'ready' if cache_healthy else 'degraded'}"
            }
        except Exception as e:
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail=f"Not ready: {str(e)}")

    # Copy metrics endpoint from streaming app
    for route in streaming_app.routes:
        if hasattr(route, "path") and route.path == "/metrics":
            app.routes.append(route)
            break

    return app


def run_server(
    host: str = None,
    port: int = None,
    db_path: str = None,
    log_level: str = None,
):
    """
    Run the unified server with both streaming and REST API.

    Args:
        host: Host to bind to (uses configuration if None)
        port: Port to bind to (uses configuration if None)
        db_path: Database file path (uses configuration if None)
        log_level: Logging level (uses configuration if None)
    """
    # Load configuration
    from ..config import get_settings
    settings = get_settings()

    # Use provided values or fall back to configuration
    host = host or settings.server.host
    port = port or settings.server.port
    db_path = db_path or settings.database.sqlite_path
    log_level = log_level or settings.server.log_level

    # Initialize logger
    logger = logging.getLogger(__name__)

    # Setup logging is handled in create_unified_app
    logger.info(f"Starting WoW Combat Log Parser API on {host}:{port}")

    # Create unified app
    app = create_unified_app(db_path)

    # Production vs development settings
    if settings.environment == "production":
        # Production configuration
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=log_level,
            access_log=True,
            loop="auto",
            http="auto",
            workers=settings.server.workers if settings.server.workers > 1 else None,
        )
    else:
        # Development configuration
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=log_level,
            access_log=True,
            reload=settings.server.reload,
            loop="auto",
            http="auto",
        )


if __name__ == "__main__":
    run_server()
