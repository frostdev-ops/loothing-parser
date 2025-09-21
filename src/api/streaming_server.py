"""
FastAPI streaming server for WoW combat log processing.

Provides WebSocket endpoints for real-time log streaming and REST APIs
for querying processed data.
"""

import asyncio
import json
import time
import uuid
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    Depends,
    Query,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from .models import (
    StreamMessage,
    StreamResponse,
    SessionStart,
    ErrorResponse,
    EncounterUpdate,
    StreamStats,
)
from .auth import auth_manager, authenticate_api_key, AuthResponse
from ..streaming.processor import StreamProcessor
from ..streaming.session import SessionManager, StreamSession, SessionStatus
from src.database.schema import DatabaseManager, create_tables
from src.database.query import QueryAPI
from src.config.loader import load_and_apply_config

logger = logging.getLogger(__name__)


class StreamingServer:
    """
    Main streaming server class.

    Coordinates WebSocket connections, authentication, stream processing,
    and database operations for real-time combat log analysis.
    """

    def __init__(self, db_path: str = "combat_logs.db"):
        """
        Initialize streaming server.

        Args:
            db_path: Path to SQLite database
        """
        # Core components
        self.db = DatabaseManager(db_path)
        self.session_manager = SessionManager()
        self.stream_processor = StreamProcessor(
            self.db, on_encounter_update=self._handle_encounter_update
        )
        self.query_api = QueryAPI(self.db)

        # Connection tracking
        self._websocket_connections: Dict[str, WebSocket] = {}

        # Server state
        self._running = False
        self._start_time = time.time()

        # Initialize database
        create_tables(self.db)

    async def start(self):
        """Start all server components."""
        if self._running:
            return

        self._running = True
        await self.session_manager.start()
        await self.stream_processor.start()

        logger.info("Streaming server started")

    async def stop(self):
        """Stop all server components."""
        if not self._running:
            return

        self._running = False

        # Stop processing first
        await self.stream_processor.stop()
        await self.session_manager.stop()

        # Close database
        self.query_api.close()
        self.db.close()

        logger.info("Streaming server stopped")

    async def handle_websocket_connection(self, websocket: WebSocket, api_key: str):
        """
        Handle a new WebSocket connection.

        Args:
            websocket: WebSocket connection
            api_key: Client API key
        """
        # Authenticate
        auth_response = authenticate_api_key(api_key)
        if not auth_response.authenticated:
            await websocket.close(code=4001, reason="Authentication failed")
            return

        client_id = auth_response.client_id
        session_id = str(uuid.uuid4())

        # Check rate limits
        allowed, reason = auth_manager.check_rate_limit(client_id, is_connection=True)
        if not allowed:
            await websocket.close(code=4029, reason=f"Rate limited: {reason}")
            return

        # Accept connection
        await websocket.accept()

        try:
            # Create session
            session = self.session_manager.create_session(
                client_id=client_id, session_id=session_id, api_key=api_key
            )

            session.websocket_connected = True
            session.remote_address = websocket.client.host if websocket.client else "unknown"

            # Track connection
            auth_manager.track_connection(client_id, session_id)
            self._websocket_connections[session_id] = websocket

            # Create processing context
            context_id = await self.stream_processor.create_processing_context(session)

            # Send welcome message
            welcome = StreamResponse(
                type="status",
                message="Connected successfully",
                data={
                    "session_id": session_id,
                    "rate_limits": auth_response.rate_limit,
                    "permissions": auth_response.permissions,
                },
            )
            await websocket.send_text(welcome.model_dump_json())

            logger.info(f"WebSocket connected: {client_id} (session: {session_id})")

            # Handle messages
            await self._handle_websocket_messages(websocket, session, context_id)

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {client_id} (session: {session_id})")

        except Exception as e:
            logger.error(f"WebSocket error for {client_id}: {e}")

        finally:
            # Cleanup
            await self._cleanup_websocket_connection(session_id, context_id)

    async def _handle_websocket_messages(
        self, websocket: WebSocket, session: StreamSession, context_id: str
    ):
        """Handle incoming WebSocket messages."""
        while True:
            try:
                # Receive message
                raw_message = await websocket.receive_text()
                message = StreamMessage.model_validate_json(raw_message)

                # Update session activity
                session.update_activity()

                # Process message based on type
                if message.type == "log_line":
                    await self._handle_log_line(websocket, session, context_id, message)

                elif message.type == "start_session":
                    await self._handle_session_start(websocket, session, message)

                elif message.type == "end_session":
                    await self._handle_session_end(websocket, session, context_id)
                    break

                elif message.type == "heartbeat":
                    await self._handle_heartbeat(websocket, session)

                elif message.type == "checkpoint":
                    await self._handle_checkpoint(websocket, session, message)

                elif message.type == "subscribe_upload":
                    await self._handle_upload_subscription(websocket, session, message)

                elif message.type == "unsubscribe_upload":
                    await self._handle_upload_unsubscription(websocket, session, message)

                else:
                    logger.warning(f"Unknown message type: {message.type}")

            except WebSocketDisconnect:
                break
            except json.JSONDecodeError as e:
                error_response = StreamResponse(type="error", message=f"Invalid JSON: {e}")
                await websocket.send_text(error_response.model_dump_json())
            except Exception as e:
                logger.error(f"Error handling message: {e}")
                error_response = StreamResponse(type="error", message=f"Processing error: {e}")
                await websocket.send_text(error_response.model_dump_json())

    async def _handle_log_line(
        self,
        websocket: WebSocket,
        session: StreamSession,
        context_id: str,
        message: StreamMessage,
    ):
        """Handle a log line message."""
        if not message.line:
            return

        # Process the line
        success = await self.stream_processor.process_line(
            context_id=context_id,
            line=message.line,
            timestamp=message.timestamp,
            sequence=message.sequence,
        )

        if success:
            # Send acknowledgment
            if message.sequence is not None:
                ack = StreamResponse(
                    type="ack", sequence_ack=message.sequence, data={"processed": True}
                )
                await websocket.send_text(ack.model_dump_json())
        else:
            # Send error
            error = StreamResponse(
                type="error",
                message="Failed to process line",
                data={"sequence": message.sequence},
            )
            await websocket.send_text(error.model_dump_json())

    async def _handle_session_start(
        self, websocket: WebSocket, session: StreamSession, message: StreamMessage
    ):
        """Handle session start message."""
        if message.metadata:
            try:
                session_start = SessionStart(**message.metadata)
                session.client_version = session_start.client_version
                session.character_name = session_start.character_name
                session.server = session_start.server
                session.region = session_start.region
            except Exception as e:
                logger.warning(f"Invalid session start metadata: {e}")

        session.status = SessionStatus.ACTIVE

        response = StreamResponse(
            type="status",
            message="Session started",
            data={"session_id": session.session_id},
        )
        await websocket.send_text(response.model_dump_json())

    async def _handle_session_end(
        self, websocket: WebSocket, session: StreamSession, context_id: str
    ):
        """Handle session end message."""
        session.status = SessionStatus.DISCONNECTED

        # Stop processing context
        await self.stream_processor.stop_processing_context(context_id)

        response = StreamResponse(type="status", message="Session ended")
        await websocket.send_text(response.model_dump_json())

    async def _handle_heartbeat(self, websocket: WebSocket, session: StreamSession):
        """Handle heartbeat message."""
        session.update_heartbeat()

        response = StreamResponse(
            type="status",
            message="Heartbeat received",
            data={"server_time": time.time()},
        )
        await websocket.send_text(response.model_dump_json())

    async def _handle_checkpoint(
        self, websocket: WebSocket, session: StreamSession, message: StreamMessage
    ):
        """Handle checkpoint message."""
        if message.sequence is not None:
            session.acknowledge_sequence(message.sequence)

        response = StreamResponse(
            type="ack", sequence_ack=message.sequence, message="Checkpoint acknowledged"
        )
        await websocket.send_text(response.model_dump_json())

    async def _handle_upload_subscription(
        self, websocket: WebSocket, session: StreamSession, message: StreamMessage
    ):
        """Handle upload subscription message."""
        try:
            upload_id = message.metadata.get("upload_id") if message.metadata else None
            if not upload_id:
                error_response = StreamResponse(
                    type="error", message="Missing upload_id in metadata"
                )
                await websocket.send_text(error_response.model_dump_json())
                return

            # Get WebSocket notifier and subscribe
            from .v1.services.websocket_notifier import get_websocket_notifier

            notifier = get_websocket_notifier()

            # Set up WebSocket connections reference if not already done
            notifier.set_websocket_connections(self._websocket_connections)

            # Subscribe to upload progress
            notifier.subscribe_to_upload(session.session_id, upload_id)

            response = StreamResponse(
                type="status",
                message="Subscribed to upload progress",
                data={"upload_id": upload_id, "session_id": session.session_id},
            )
            await websocket.send_text(response.model_dump_json())

            logger.debug(f"Session {session.session_id} subscribed to upload {upload_id}")

        except Exception as e:
            error_response = StreamResponse(
                type="error", message=f"Failed to subscribe to upload: {str(e)}"
            )
            await websocket.send_text(error_response.model_dump_json())

    async def _handle_upload_unsubscription(
        self, websocket: WebSocket, session: StreamSession, message: StreamMessage
    ):
        """Handle upload unsubscription message."""
        try:
            upload_id = message.metadata.get("upload_id") if message.metadata else None
            if not upload_id:
                error_response = StreamResponse(
                    type="error", message="Missing upload_id in metadata"
                )
                await websocket.send_text(error_response.model_dump_json())
                return

            # Get WebSocket notifier and unsubscribe
            from .v1.services.websocket_notifier import get_websocket_notifier

            notifier = get_websocket_notifier()
            notifier.unsubscribe_from_upload(session.session_id, upload_id)

            response = StreamResponse(
                type="status",
                message="Unsubscribed from upload progress",
                data={"upload_id": upload_id, "session_id": session.session_id},
            )
            await websocket.send_text(response.model_dump_json())

            logger.debug(f"Session {session.session_id} unsubscribed from upload {upload_id}")

        except Exception as e:
            error_response = StreamResponse(
                type="error", message=f"Failed to unsubscribe from upload: {str(e)}"
            )
            await websocket.send_text(error_response.model_dump_json())

    async def _cleanup_websocket_connection(
        self, session_id: str, context_id: Optional[str] = None
    ):
        """Clean up WebSocket connection resources."""
        # Remove from tracking
        if session_id in self._websocket_connections:
            del self._websocket_connections[session_id]

        # Get session info for cleanup
        session = self.session_manager.get_session(session_id)
        if session:
            # Untrack connection for rate limiting
            auth_manager.untrack_connection(session.client_id, session_id)

        # Clean up WebSocket upload subscriptions
        try:
            from .v1.services.websocket_notifier import get_websocket_notifier
            notifier = get_websocket_notifier()
            notifier.cleanup_session(session_id)
        except Exception as e:
            logger.debug(f"Failed to cleanup WebSocket subscriptions for {session_id}: {e}")

        # Stop processing context
        if context_id:
            await self.stream_processor.stop_processing_context(context_id)

        # Remove session
        await self.session_manager.remove_session(session_id)

    async def _handle_encounter_update(self, encounter_update: EncounterUpdate):
        """Handle encounter state updates (broadcast to relevant clients)."""
        # For now, just log the update
        # In the future, this could broadcast to Discord or other services
        logger.info(f"Encounter update: {encounter_update.boss_name} - {encounter_update.status}")

    def get_server_stats(self) -> Dict[str, Any]:
        """Get comprehensive server statistics."""
        uptime = time.time() - self._start_time

        return {
            "server": {
                "uptime_seconds": uptime,
                "running": self._running,
                "start_time": self._start_time,
                "active_websockets": len(self._websocket_connections),
            },
            "authentication": auth_manager.get_all_stats(),
            "sessions": self.session_manager.get_stats(),
            "processing": self.stream_processor.get_global_stats(),
            "database": self.query_api.get_database_stats(),
        }


# Global server instance
_server_instance: Optional[StreamingServer] = None


def create_app(db_path: str = "combat_logs.db") -> FastAPI:
    """
    Create FastAPI application with streaming endpoints.

    Args:
        db_path: Path to SQLite database

    Returns:
        Configured FastAPI app
    """
    global _server_instance

    app = FastAPI(
        title="WoW Combat Log Streaming API",
        description="Real-time combat log processing and analysis",
        version="1.0.0",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize server
    _server_instance = StreamingServer(db_path)

    @app.on_event("startup")
    async def startup_event():
        # Load custom configuration
        load_and_apply_config()
        logger.info("Custom configuration loaded")
        await _server_instance.start()

    @app.on_event("shutdown")
    async def shutdown_event():
        await _server_instance.stop()

    # WebSocket endpoint for streaming
    @app.websocket("/stream")
    async def websocket_endpoint(websocket: WebSocket, api_key: str):
        """Main streaming WebSocket endpoint."""
        await _server_instance.handle_websocket_connection(websocket, api_key)

    # REST API endpoints
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "timestamp": time.time()}

    @app.get("/health/live")
    async def liveness_probe():
        """Kubernetes liveness probe."""
        return {"status": "alive", "timestamp": time.time()}

    @app.get("/health/ready")
    async def readiness_probe():
        """Kubernetes readiness probe."""
        # Check if critical components are ready
        try:
            # Test database connection
            _server_instance.db.execute("SELECT 1")

            # Check if server is running
            if not _server_instance._running:
                raise Exception("Server not running")

            return {"status": "ready", "timestamp": time.time()}
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Not ready: {str(e)}")

    @app.get("/metrics")
    async def get_metrics():
        """Prometheus-compatible metrics endpoint."""
        stats = _server_instance.get_server_stats()

        # Convert to Prometheus format
        metrics = []

        # Server metrics
        server_stats = stats["server"]
        metrics.append(f"loothing_server_uptime_seconds {server_stats['uptime_seconds']}")
        metrics.append(f"loothing_server_running {int(server_stats['running'])}")
        metrics.append(f"loothing_websocket_connections_active {server_stats['active_websockets']}")

        # Processing metrics
        processing_stats = stats["processing"]
        metrics.append(f"loothing_processing_contexts_active {processing_stats['active_contexts']}")
        metrics.append(
            f"loothing_processing_lines_total {processing_stats['total_lines_processed']}"
        )
        metrics.append(
            f"loothing_processing_events_total {processing_stats['total_events_generated']}"
        )
        metrics.append(f"loothing_processing_errors_total {processing_stats['total_parse_errors']}")
        metrics.append(
            f"loothing_processing_lines_per_second {processing_stats['lines_per_second']}"
        )
        metrics.append(
            f"loothing_processing_events_per_second {processing_stats['events_per_second']}"
        )
        metrics.append(f"loothing_processing_error_rate_percent {processing_stats['error_rate']}")

        # Database metrics
        db_stats = stats["database"]
        metrics.append(f"loothing_database_encounters_total {db_stats['total_encounters']}")
        metrics.append(f"loothing_database_characters_total {db_stats['total_characters']}")
        metrics.append(f"loothing_database_blocks_total {db_stats['total_blocks']}")
        metrics.append(f"loothing_database_events_total {db_stats['total_events']}")
        metrics.append(f"loothing_database_compressed_bytes {db_stats['total_compressed_bytes']}")
        metrics.append(
            f"loothing_database_uncompressed_bytes {db_stats['total_uncompressed_bytes']}"
        )

        # Authentication metrics
        auth_stats = stats["authentication"]
        metrics.append(f"loothing_auth_api_keys_total {auth_stats['total_api_keys']}")
        metrics.append(f"loothing_auth_api_keys_active {auth_stats['active_api_keys']}")
        metrics.append(f"loothing_auth_connections_total {auth_stats['total_active_connections']}")
        metrics.append(f"loothing_auth_clients_unique {auth_stats['unique_clients']}")

        # Session metrics
        session_stats = stats["sessions"]
        metrics.append(f"loothing_sessions_total {session_stats['total_sessions']}")
        metrics.append(f"loothing_sessions_events_total {session_stats['total_events_processed']}")
        metrics.append(
            f"loothing_sessions_events_per_second_avg {session_stats['average_events_per_second']}"
        )

        return "\n".join(metrics) + "\n"

    @app.get("/stats")
    async def get_stats():
        """Get server statistics."""
        return _server_instance.get_server_stats()

    @app.get("/encounters/recent")
    async def get_recent_encounters(limit: int = Query(10, ge=1, le=100)):
        """Get recent encounters."""
        encounters = _server_instance.query_api.get_recent_encounters(limit)
        return [encounter.model_dump() for encounter in encounters]

    @app.get("/encounters/{encounter_id}")
    async def get_encounter(encounter_id: int):
        """Get specific encounter details."""
        encounter = _server_instance.query_api.get_encounter(encounter_id)
        if not encounter:
            raise HTTPException(status_code=404, detail="Encounter not found")
        return encounter.model_dump()

    @app.get("/characters/{character_name}/metrics")
    async def get_character_metrics(character_name: str, encounter_id: Optional[int] = Query(None)):
        """Get character performance metrics."""
        if encounter_id:
            metrics = _server_instance.query_api.get_character_metrics(encounter_id, character_name)
        else:
            # Get recent metrics
            metrics = _server_instance.query_api.get_top_performers(limit=1)
            metrics = [m for m in metrics if m.character_name.lower() == character_name.lower()]

        return [metric.model_dump() for metric in metrics]

    @app.get("/encounters/search")
    async def search_encounters(
        boss_name: Optional[str] = Query(None),
        difficulty: Optional[str] = Query(None),
        encounter_type: Optional[str] = Query(None),
        success: Optional[bool] = Query(None),
        limit: int = Query(50, ge=1, le=200),
    ):
        """Search encounters with filters."""
        encounters = _server_instance.query_api.search_encounters(
            boss_name=boss_name,
            difficulty=difficulty,
            encounter_type=encounter_type,
            success=success,
            limit=limit,
        )
        return [encounter.model_dump() for encounter in encounters]

    @app.get("/characters/{character_name}/events")
    async def get_character_events(
        character_name: str,
        encounter_id: int,
        start_time: Optional[float] = Query(None),
        end_time: Optional[float] = Query(None),
        event_types: Optional[str] = Query(None),
        limit: int = Query(1000, ge=1, le=10000),
    ):
        """Get detailed events for a character in an encounter."""
        event_types_list = event_types.split(",") if event_types else None

        events = _server_instance.query_api.get_character_events(
            character_name=character_name,
            encounter_id=encounter_id,
            start_time=start_time,
            end_time=end_time,
            event_types=event_types_list,
        )

        # Limit results for API response
        limited_events = events[:limit]

        return {
            "character_name": character_name,
            "encounter_id": encounter_id,
            "total_events": len(events),
            "returned_events": len(limited_events),
            "events": [
                {
                    "timestamp": event.timestamp,
                    "event_type": event.event.event_type,
                    "event_data": event.event.model_dump(),
                }
                for event in limited_events
            ],
        }

    @app.get("/characters/{character_name}/spells")
    async def get_character_spells(
        character_name: str,
        encounter_id: Optional[int] = Query(None),
        spell_name: Optional[str] = Query(None),
        days: int = Query(30, ge=1, le=365),
    ):
        """Get spell usage statistics for a character."""
        spells = _server_instance.query_api.get_spell_usage(
            character_name=character_name,
            encounter_id=encounter_id,
            spell_name=spell_name,
            days=days,
        )
        return [spell.model_dump() for spell in spells]

    @app.get("/performance/top")
    async def get_top_performers(
        metric: str = Query(
            "dps", regex="^(dps|hps|damage_done|healing_done|activity_percentage)$"
        ),
        encounter_type: Optional[str] = Query(None),
        boss_name: Optional[str] = Query(None),
        days: int = Query(7, ge=1, le=365),
        limit: int = Query(10, ge=1, le=100),
    ):
        """Get top performing characters by metric."""
        performers = _server_instance.query_api.get_top_performers(
            metric=metric,
            encounter_type=encounter_type,
            boss_name=boss_name,
            days=days,
            limit=limit,
        )
        return [performer.model_dump() for performer in performers]

    @app.get("/database/stats")
    async def get_database_stats():
        """Get comprehensive database statistics."""
        return _server_instance.query_api.get_database_stats()

    @app.post("/database/optimize")
    async def optimize_database(admin_key: str = "admin_secret"):
        """Trigger database optimization (admin only)."""
        if admin_key != "admin_secret":
            raise HTTPException(status_code=403, detail="Invalid admin key")

        try:
            from database.schema import optimize_database

            optimize_database(_server_instance.db)
            return {"status": "success", "message": "Database optimization completed"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Optimization failed: {str(e)}")

    @app.get("/export/encounters/{encounter_id}")
    async def export_encounter(
        encounter_id: int, format: str = Query("json", regex="^(json|csv)$")
    ):
        """Export encounter data in specified format."""
        encounter = _server_instance.query_api.get_encounter(encounter_id)
        if not encounter:
            raise HTTPException(status_code=404, detail="Encounter not found")

        metrics = _server_instance.query_api.get_character_metrics(encounter_id)

        if format == "json":
            return {
                "encounter": encounter.model_dump(),
                "character_metrics": [metric.model_dump() for metric in metrics],
            }
        else:  # CSV format
            from fastapi.responses import StreamingResponse
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)

            # Write encounter header
            writer.writerow(["encounter_id", "boss_name", "difficulty", "success", "combat_length"])
            writer.writerow(
                [
                    encounter.encounter_id,
                    encounter.boss_name,
                    encounter.difficulty,
                    encounter.success,
                    encounter.combat_length,
                ]
            )

            # Write metrics
            writer.writerow([])  # Empty row
            writer.writerow(
                [
                    "character_name",
                    "dps",
                    "hps",
                    "damage_done",
                    "healing_done",
                    "death_count",
                ]
            )

            for metric in metrics:
                writer.writerow(
                    [
                        metric.character_name,
                        metric.dps,
                        metric.hps,
                        metric.damage_done,
                        metric.healing_done,
                        metric.death_count,
                    ]
                )

            output.seek(0)
            return StreamingResponse(
                io.StringIO(output.getvalue()),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=encounter_{encounter_id}.csv"
                },
            )

    @app.post("/auth/generate-key")
    async def generate_api_key(
        client_id: str,
        description: str,
        admin_key: str = "admin_secret",  # Simple admin auth for demo
    ):
        """Generate a new API key."""
        if admin_key != "admin_secret":
            raise HTTPException(status_code=403, detail="Invalid admin key")

        key_id, api_key = auth_manager.generate_api_key(client_id, description)
        return {
            "key_id": key_id,
            "api_key": api_key,
            "client_id": client_id,
            "description": description,
        }

    return app


def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    db_path: str = "combat_logs.db",
    log_level: str = "info",
):
    """
    Run the streaming server.

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

    # Create app
    app = create_app(db_path)

    # Run with uvicorn
    uvicorn.run(app, host=host, port=port, log_level=log_level, access_log=True)


if __name__ == "__main__":
    run_server()
