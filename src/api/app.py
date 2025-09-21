"""
Unified FastAPI application combining streaming server and REST API v1.

This module creates a single FastAPI application that serves:
- WebSocket streaming endpoints for real-time log processing
- REST API v1 endpoints for queries, uploads, and data access
- Health checks and monitoring endpoints
"""

import os
import logging
import uvicorn
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .streaming_server import create_app as create_streaming_app
from .v1.main import create_v1_app
from ..database.schema import DatabaseManager


def create_unified_app(db_path: str = "combat_logs.db") -> FastAPI:
    """
    Create unified FastAPI application with both streaming and REST API v1.

    Args:
        db_path: Path to SQLite database

    Returns:
        Configured FastAPI application with all endpoints
    """
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

    # Initialize database manager
    db = DatabaseManager(db_path)

    # Create streaming app and mount its endpoints
    streaming_app = create_streaming_app(db_path)

    # Create v1 API app
    v1_app = create_v1_app(db)

    # Mount the streaming endpoints at root level
    # Copy streaming-specific endpoints to main app
    for route in streaming_app.routes:
        if hasattr(route, 'path'):
            # Skip if it's a health endpoint that we'll replace
            if route.path in ["/health", "/health/live", "/health/ready", "/metrics"]:
                continue
            app.routes.append(route)

    # Mount v1 API
    app.mount("/api/v1", v1_app)

    # Add unified health checks
    @app.get("/health", tags=["Health"])
    async def unified_health_check():
        """Unified health check for all services."""
        return {
            "status": "healthy",
            "services": {
                "streaming": "operational",
                "api_v1": "operational",
                "database": "connected"
            },
            "version": "1.0.0"
        }

    @app.get("/health/live", tags=["Health"])
    async def liveness_probe():
        """Kubernetes liveness probe."""
        return {"status": "alive"}

    @app.get("/health/ready", tags=["Health"])
    async def readiness_probe():
        """Kubernetes readiness probe."""
        try:
            # Test database connection
            db.execute("SELECT 1")
            return {"status": "ready"}
        except Exception as e:
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail=f"Not ready: {str(e)}")

    # Copy metrics endpoint from streaming app
    for route in streaming_app.routes:
        if hasattr(route, 'path') and route.path == "/metrics":
            app.routes.append(route)
            break

    return app


def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    db_path: str = "combat_logs.db",
    log_level: str = "info",
):
    """
    Run the unified server with both streaming and REST API.

    Args:
        host: Host to bind to
        port: Port to bind to
        db_path: Database file path
        log_level: Logging level
    """
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Get configuration from environment
    host = os.getenv("HOST", host)
    port = int(os.getenv("PORT", port))
    db_path = os.getenv("DB_PATH", db_path)
    log_level = os.getenv("LOG_LEVEL", log_level)

    # Create unified app
    app = create_unified_app(db_path)

    # Run with uvicorn
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
        access_log=True,
        # Add some production-ready settings
        loop="auto",
        http="auto",
    )


if __name__ == "__main__":
    run_server()