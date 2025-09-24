"""
Upload service for WoW combat log files.

Handles file uploads validation processing and real-time progress tracking.
"""

import os
import uuid
import hashlib
import logging
import asyncio
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
from dataclasses import dataclass, asdict
from fastapi import UploadFile, HTTPException

from src.database.schema import DatabaseManager, create_tables
from src.database.storage import EventStorage
from src.processing.unified_parallel_processor import UnifiedParallelProcessor
from src.models.unified_encounter import UnifiedEncounter

logger = logging.getLogger(__name__)


@dataclass
class UploadStatus:
    """Status of an uploaded file."""

    upload_id: str
    file_name: str
    file_size: int
    file_hash: Optional[str] = None
    guild_id: Optional[int] = None
    status: str = "pending"  # pending processing completed error
    progress: float = 0.0
    encounters_found: int = 0
    characters_found: int = 0
    events_processed: int = 0
    error_message: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class UploadService:
    """
    Service for handling combat log file uploads and processing.

    Features:
    - File validation and duplicate detection
    - Asynchronous processing with progress tracking
    - Real-time WebSocket notifications
    - Database storage and querying
    """

    def __init__(
        self,
        db: DatabaseManager,
        upload_dir: Optional[Path] = None,
        max_file_size: int = 2 * 1024 * 1024 * 1024,  # 2GB
        progress_callback: Optional[Callable[[str, UploadStatus], None]] = None,
    ):
        """
        Initialize upload service.

        Args:
            db: Database manager
            upload_dir: Directory for temporary file storage
            max_file_size: Maximum allowed file size in bytes
            progress_callback: Callback for progress updates
        """
        self.db = db

        # Ensure database schema is created
        create_tables(db)

        # Ensure default guild exists for backward compatibility
        self._ensure_default_guild(db)

        self.storage = EventStorage(db)
        self.processor = UnifiedParallelProcessor()
        self.max_file_size = max_file_size
        self.progress_callback = progress_callback

        # Set up upload directory
        if upload_dir:
            self.upload_dir = upload_dir
        else:
            self.upload_dir = Path(tempfile.gettempdir()) / "loothing_uploads"

        self.upload_dir.mkdir(exist_ok=True, parents=True)

        # Track active uploads
        self.active_uploads: Dict[str, UploadStatus] = {}

        # Initialize database schema
        self._init_upload_tables()

    def _init_upload_tables(self):
        """Initialize database tables for upload tracking."""
        try:
            # Skip table creation if using PostgreSQL or HybridDatabaseManager (tables already exist)
            if (hasattr(self.db, 'db_type') and self.db.db_type == 'postgresql') or \
               (hasattr(self.db, 'postgres') and hasattr(self.db, 'influx')):
                logger.info("Using PostgreSQL/Hybrid manager - skipping upload table creation (using existing schema)")
                return

            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS uploads (
                    upload_id TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    file_hash TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    progress REAL DEFAULT 0.0,
                    encounters_found INTEGER DEFAULT 0,
                    characters_found INTEGER DEFAULT 0,
                    events_processed INTEGER DEFAULT 0,
                    error_message TEXT,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Index for fast lookups
            self.db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_uploads_hash ON uploads(file_hash)
            """
            )
            self.db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_uploads_status ON uploads(status)
            """
            )

            logger.info("Upload tables initialized")
        except Exception as e:
            logger.error(f"Failed to initialize upload tables: {e}")
            raise

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file for duplicate detection."""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def _validate_file(self, file: UploadFile) -> None:
        """Validate uploaded file."""
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")

        if not file.filename.lower().endswith((".txt", ".log")):
            raise HTTPException(
                status_code=400, detail="Invalid file type. Only .txt and .log files are supported"
            )

        # Note: file.size might not be available in all cases
        # We'll check size after saving the file

    async def _save_upload_file(self, file: UploadFile) -> Path:
        """Save uploaded file to temporary directory."""
        upload_id = str(uuid.uuid4())
        file_path = self.upload_dir / f"{upload_id}_{file.filename}"

        file_size = 0
        try:
            with open(file_path, "wb") as f:
                while chunk := await file.read(8192):
                    file_size += len(chunk)

                    # Check file size limit
                    if file_size > self.max_file_size:
                        f.close()
                        file_path.unlink(missing_ok=True)
                        raise HTTPException(
                            status_code=413,
                            detail=f"File too large. Maximum size is {self.max_file_size // (1024*1024)}MB"
                        )

                    f.write(chunk)

            logger.info(f"Saved upload file: {file_path} ({file_size} bytes)")
            return file_path

        except Exception as e:
            # Clean up on error
            file_path.unlink(missing_ok=True)
            logger.error(f"Failed to save upload file: {e}")
            raise

    def _check_duplicate(self, file_hash: str) -> Optional[UploadStatus]:
        """Check if file has already been uploaded."""
        try:
            result = self.db.execute(
                "SELECT * FROM uploads WHERE file_hash = %s ORDER BY created_at DESC LIMIT 1",
                (file_hash,) 
            ).fetchone()

            if result:
                return UploadStatus(
                    upload_id=result["upload_id"],
                    file_name=result["file_name"],
                    file_size=result["file_size"],
                    file_hash=result["file_hash"],
                    status=result["status"],
                    progress=result["progress"],
                    encounters_found=result["encounters_found"],
                    characters_found=result["characters_found"],
                    events_processed=result["events_processed"],
                    error_message=result["error_message"],
                    start_time=(
                        datetime.fromisoformat(result["start_time"])
                        if result["start_time"]
                        else None
                    ),
                    end_time=(
                        datetime.fromisoformat(result["end_time"]) if result["end_time"] else None
                    ),
                )
        except Exception as e:
            logger.error(f"Error checking for duplicate: {e}")

        return None

    def _save_upload_status(self, status: UploadStatus):
        """Save upload status to database."""
        try:
            self.db.execute(
                """
                INSERT INTO uploads (
                    upload_id, file_name, file_size, file_hash, status, progress,
                    encounters_found, characters_found, events_processed,
                    error_message, start_time, end_time
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (upload_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    progress = EXCLUDED.progress,
                    encounters_found = EXCLUDED.encounters_found,
                    characters_found = EXCLUDED.characters_found,
                    events_processed = EXCLUDED.events_processed,
                    error_message = EXCLUDED.error_message,
                    start_time = EXCLUDED.start_time,
                    end_time = EXCLUDED.end_time
            """,
                (
                    status.upload_id,
                    status.file_name,
                    status.file_size,
                    status.file_hash,
                    status.status,
                    status.progress,
                    status.encounters_found,
                    status.characters_found,
                    status.events_processed,
                    status.error_message,
                    status.start_time.isoformat() if status.start_time else None,
                    status.end_time.isoformat() if status.end_time else None,
                ) 
            )
            logger.debug(f"Saved upload status for {status.upload_id}")
        except Exception as e:
            logger.error(f"Failed to save upload status: {e}")

    def _notify_progress(self, upload_id: str, status: UploadStatus):
        """Send progress notification via callback and WebSocket."""
        try:
            self.active_uploads[upload_id] = status
            self._save_upload_status(status)

            # Call synchronous callback if provided
            if self.progress_callback:
                self.progress_callback(upload_id, status)

            # Send WebSocket notification asynchronously
            try:
                import asyncio
                from .websocket_notifier import get_websocket_notifier

                notifier = get_websocket_notifier()

                # Schedule the async notification
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(notifier.notify_upload_progress(upload_id, status))
                    else:
                        loop.run_until_complete(notifier.notify_upload_progress(upload_id, status))
                except RuntimeError:
                    # No event loop running, skip WebSocket notification
                    logger.debug("No event loop running, skipping WebSocket notification")

            except Exception as ws_error:
                logger.debug(f"WebSocket notification failed (non-critical): {ws_error}")

        except Exception as e:
            logger.error(f"Failed to notify progress: {e}")

    async def _process_file_async(self, upload_id: str, file_path: Path, status: UploadStatus):
        """Process uploaded file asynchronously."""
        try:
            logger.info(f"Starting async processing of {file_path}")

            # Update status to processing
            status.status = "processing"
            status.start_time = datetime.now()
            self._notify_progress(upload_id, status)

            # Process with UnifiedParallelProcessor
            encounters = self.processor.process_file(file_path)

            # Store encounters in database
            storage_result = self.storage.store_unified_encounters(
                encounters=encounters,
                log_file_path=str(file_path),
                guild_id=status.guild_id, 
            )

            # Update final status
            status.status = "completed"
            status.progress = 100.0
            status.encounters_found = len(encounters)
            status.characters_found = storage_result.get("characters_stored", 0)
            status.events_processed = storage_result.get("events_stored", 0)
            status.end_time = datetime.now()

            self._notify_progress(upload_id, status)

            logger.info(
                f"Completed processing {file_path}: {len(encounters)} encounters "
                f"{status.characters_found} characters, {status.events_processed} events"
            )

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")

            # Update error status
            status.status = "error"
            status.error_message = str(e)
            status.end_time = datetime.now()
            self._notify_progress(upload_id, status)

        finally:
            # Clean up temporary file
            try:
                file_path.unlink(missing_ok=True)
                logger.debug(f"Cleaned up temporary file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file {file_path}: {e}")

    def _ensure_default_guild(self, db: DatabaseManager) -> None:
        """Ensure a default guild exists for backward compatibility."""
        try:
            # Skip guild creation for PostgreSQL/HybridDatabaseManager - assume guilds exist in main DB
            if (hasattr(db, 'db_type') and db.db_type == 'postgresql') or \
               (hasattr(db, 'postgres') and hasattr(db, 'influx')):
                logger.info("Using PostgreSQL/Hybrid manager - skipping default guild creation (using existing data)")
                return

            # Check if guild with ID=1 exists (PostgreSQL/SQLite)
            cursor = db.execute("SELECT guild_id FROM guilds WHERE guild_id = %s", (1,))
            if not cursor.fetchone():
                # Insert default guild
                db.execute("""
                    INSERT INTO guilds (guild_id, guild_name, server, region, faction)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (guild_id) DO NOTHING
                """, (1, 'Default Guild', 'Unknown', 'US', None))
                if hasattr(db, 'commit'):
                    db.commit()
                logger.info("Created default guild with ID=1")
        except Exception as e:
            logger.warning(f"Could not ensure default guild: {e}")
            # Non-critical, continue

    async def upload_file(self, file: UploadFile, guild_id: Optional[int] = None, process_async: bool = True) -> UploadStatus:
        """
        Upload and process a combat log file.

        Args:
            file: Uploaded file
            guild_id: Guild ID for multi-tenant isolation
            process_async: Whether to process asynchronously

        Returns:
            Upload status
        """
        self._validate_file(file)

        # Save file temporarily
        file_path = await self._save_upload_file(file)

        try:
            # Calculate file hash for duplicate detection
            file_hash = self._calculate_file_hash(file_path)

            # Check for duplicates
            existing = self._check_duplicate(file_hash)
            if existing and existing.status == "completed":
                logger.info(f"Duplicate file detected: {file.filename} (hash: {file_hash[:8]})")
                file_path.unlink(missing_ok=True)  # Clean up duplicate
                return existing

            # Create upload status
            upload_id = str(uuid.uuid4())
            status = UploadStatus(
                upload_id=upload_id,
                file_name=file.filename,
                file_size=file_path.stat().st_size,
                file_hash=file_hash,
                guild_id=guild_id,
                status="pending", 
            )

            # Save initial status
            self._notify_progress(upload_id, status)

            if process_async:
                # Start async processing
                asyncio.create_task(self._process_file_async(upload_id, file_path, status))
                logger.info(f"Started async processing for upload {upload_id}")
            else:
                # Process synchronously (for smaller files)
                await self._process_file_async(upload_id, file_path, status)

            return status

        except Exception as e:
            # Clean up on error
            file_path.unlink(missing_ok=True)
            logger.error(f"Upload failed: {e}")
            raise

    def get_upload_status(self, upload_id: str, guild_id: Optional[int] = None) -> Optional[UploadStatus]:
        """Get current status of an upload."""
        # Check in-memory first
        if upload_id in self.active_uploads:
            return self.active_uploads[upload_id]

        # Check database
        try:
            result = self.db.execute(
                "SELECT * FROM uploads WHERE upload_id = %s", (upload_id,)
            ).fetchone()

            if result:
                return UploadStatus(
                    upload_id=result["upload_id"],
                    file_name=result["file_name"],
                    file_size=result["file_size"],
                    file_hash=result["file_hash"],
                    status=result["status"],
                    progress=result["progress"],
                    encounters_found=result["encounters_found"],
                    characters_found=result["characters_found"],
                    events_processed=result["events_processed"],
                    error_message=result["error_message"],
                    start_time=(
                        datetime.fromisoformat(result["start_time"])
                        if result["start_time"]
                        else None
                    ),
                    end_time=(
                        datetime.fromisoformat(result["end_time"]) if result["end_time"] else None
                    ),
                )
        except Exception as e:
            logger.error(f"Error getting upload status: {e}")

        return None

    def list_uploads(
        self, limit: int = 50, status_filter: Optional[str] = None
    ) -> List[UploadStatus]:
        """List recent uploads with optional status filter."""
        try:
            query = "SELECT * FROM uploads"
            params = []

            if status_filter:
                query += " WHERE status = %s"
                params.append(status_filter)

            query += " ORDER BY created_at DESC LIMIT %s"
            params.append(limit)

            results = self.db.execute(query, params).fetchall()

            uploads = []
            for result in results:
                uploads.append(
                    UploadStatus(
                        upload_id=result["upload_id"],
                        file_name=result["file_name"],
                        file_size=result["file_size"],
                        file_hash=result["file_hash"],
                        status=result["status"],
                        progress=result["progress"],
                        encounters_found=result["encounters_found"],
                        characters_found=result["characters_found"],
                        events_processed=result["events_processed"],
                        error_message=result["error_message"],
                        start_time=(
                            datetime.fromisoformat(result["start_time"])
                            if result["start_time"]
                            else None
                        ),
                        end_time=(
                            datetime.fromisoformat(result["end_time"])
                            if result["end_time"]
                            else None
                        ),
                    )
                )

            return uploads

        except Exception as e:
            logger.error(f"Error listing uploads: {e}")
            return []

    def get_upload_stats(self) -> Dict[str, Any]:
        """Get upload statistics."""
        try:
            stats = self.db.execute(
                """
                SELECT
                    COUNT(*) as total_uploads,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_uploads,
                    COUNT(CASE WHEN status = 'processing' THEN 1 END) as processing_uploads,
                    COUNT(CASE WHEN status = 'error' THEN 1 END) as failed_uploads,
                    SUM(file_size) as total_bytes,
                    SUM(encounters_found) as total_encounters,
                    SUM(events_processed) as total_events
                FROM uploads
            """
            ).fetchone()

            return {
                "total_uploads": stats["total_uploads"] or 0,
                "completed_uploads": stats["completed_uploads"] or 0,
                "processing_uploads": stats["processing_uploads"] or 0,
                "failed_uploads": stats["failed_uploads"] or 0,
                "total_bytes": stats["total_bytes"] or 0,
                "total_encounters": stats["total_encounters"] or 0,
                "total_events": stats["total_events"] or 0,
                "active_uploads": len(self.active_uploads), 
            }

        except Exception as e:
            logger.error(f"Error getting upload stats: {e}")
            return {}

    def cleanup_old_uploads(self, days: int = 7):
        """Clean up old upload records and temporary files."""
        try:
            # Remove old database records
            self.db.execute(
                "DELETE FROM uploads WHERE created_at < datetime('now' '-{} days')".format(days)
            )

            # Clean up any orphaned temporary files
            for file_path in self.upload_dir.glob("*"):
                try:
                    if file_path.stat().st_mtime < (time.time() - days * 24 * 3600):
                        file_path.unlink()
                        logger.debug(f"Cleaned up old temporary file: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up {file_path}: {e}")

            logger.info(f"Cleaned up uploads older than {days} days")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
