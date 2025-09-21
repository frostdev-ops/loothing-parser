"""
Main FastAPI v1 application for WoW combat log analysis.

This module creates the FastAPI application instance and configures all
routers, middleware, and dependencies for the v1 API.
"""

import time
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from .routers import characters, encounters, analytics, logs, guilds, export, webhooks
from .middleware.performance import PerformanceMiddleware
from .middleware.rate_limiting import RateLimitMiddleware
from .dependencies import DatabaseDependency
from ..auth import auth_manager
from ...database.schema import DatabaseManager


def create_v1_app(db: DatabaseManager) -> FastAPI:
    """
    Create and configure the FastAPI v1 application.

    Args:
        db: Database manager instance

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="WoW Combat Log Analysis API v1",
        description="""
        Comprehensive REST API for World of Warcraft combat log analysis.

        ## Features

        * **Character Analysis**: Detailed performance metrics and history
        * **Encounter Metrics**: Boss fights, DPS/HPS rankings, death analysis
        * **Advanced Analytics**: Trends, class balance, progression tracking
        * **Real-time Processing**: Live log streaming and processing
        * **Export Capabilities**: Multiple formats (JSON, CSV, WCL)
        * **Guild Management**: Roster analysis, attendance tracking
        * **Webhooks**: Real-time event notifications

        ## Authentication

        All endpoints require API key authentication via the `api_key` query parameter
        or `X-API-Key` header.

        ## Rate Limiting

        Requests are rate limited based on your API key tier:
        - Free: 100 requests/hour
        - Premium: 1000 requests/hour
        - Enterprise: 10000 requests/hour

        ## Pagination

        List endpoints support pagination with `limit` and `offset` parameters.
        Maximum limit is 1000 items per request.
        """,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Add middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(PerformanceMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # Global exception handler
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Custom HTTP exception handler with detailed error responses."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.status_code,
                    "message": exc.detail,
                    "timestamp": time.time(),
                    "path": str(request.url.path),
                    "method": request.method,
                }
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions."""
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": 500,
                    "message": "Internal server error",
                    "timestamp": time.time(),
                    "path": str(request.url.path),
                    "method": request.method,
                }
            },
        )

    # Health check endpoints
    @app.get("/api/v1/health", tags=["Health"])
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "version": "1.0.0", "timestamp": time.time()}

    @app.get("/api/v1/status", tags=["Health"])
    async def api_status():
        """Detailed API status information."""
        return {
            "api_version": "1.0.0",
            "status": "operational",
            "timestamp": time.time(),
            "database": "connected",
            "cache": "operational",
            "features": {
                "real_time_processing": True,
                "advanced_analytics": True,
                "export_capabilities": True,
                "webhook_support": True,
            },
        }

    # Include routers with dependency injection
    db_dependency = DatabaseDependency(db)

    app.include_router(
        characters.router,
        tags=["Characters"],
        dependencies=[db_dependency.dependency],
    )

    app.include_router(
        encounters.router,
        tags=["Encounters"],
        dependencies=[db_dependency.dependency],
    )

    app.include_router(
        analytics.router,
        tags=["Analytics"],
        dependencies=[db_dependency.dependency],
    )

    app.include_router(
        logs.router,
        tags=["Log Processing"],
        dependencies=[db_dependency.dependency],
    )

    app.include_router(
        guilds.router,
        tags=["Guild Management"],
        dependencies=[db_dependency.dependency],
    )

    app.include_router(export.router, tags=["Export"], dependencies=[db_dependency.dependency])

    app.include_router(
        webhooks.router,
        tags=["Webhooks"],
        dependencies=[db_dependency.dependency],
    )

    return app
