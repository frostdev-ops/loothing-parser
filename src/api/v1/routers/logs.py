"""
Log processing and upload API endpoints for v1.

Provides endpoints for log file upload, processing status tracking,
and batch log operations with real-time progress notifications.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query, Path
from fastapi.responses import JSONResponse

from src.database.schema import DatabaseManager
from ..services.upload_service import UploadService, UploadStatus
from ..dependencies import get_authenticated_user
from ...models import AuthResponse

router = APIRouter()

# Global upload service instance (will be injected via dependency)
_upload_service: Optional[UploadService] = None


def get_upload_service(db: DatabaseManager = Depends()) -> UploadService:
    """Get or create upload service instance."""
    global _upload_service
    if _upload_service is None:
        _upload_service = UploadService(db)
    return _upload_service


@router.post("/logs/upload")
async def upload_log_file(
    file: UploadFile = File(...),
    process_async: bool = Query(True, description="Process file asynchronously"),
    auth: AuthResponse = Depends(get_authenticated_user),
    upload_service: UploadService = Depends(get_upload_service),
) -> Dict[str, Any]:
    """
    Upload a combat log file for processing.

    Args:
        file: Combat log file (.txt or .log)
        process_async: Whether to process asynchronously (recommended for large files)
        auth: Authenticated user with guild context

    Returns:
        Upload status with ID for tracking progress
    """
    # Validate guild_id is present
    if auth.guild_id is None:
        raise HTTPException(
            status_code=400,
            detail="Guild ID is required. Please ensure your API key is associated with a guild.",
        )

    try:
        status = await upload_service.upload_file(
            file, guild_id=auth.guild_id, process_async=process_async
        )

        return {
            "upload_id": status.upload_id,
            "guild_id": auth.guild_id,
            "guild_name": auth.guild_name,
            "file_name": status.file_name,
            "file_size": status.file_size,
            "status": status.status,
            "progress": status.progress,
            "message": f"File uploaded successfully for {auth.guild_name}. Upload ID: {status.upload_id}",
            "duplicate": False,  # For compatibility
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/logs/{upload_id}/status")
async def get_log_status(
    upload_id: str = Path(..., description="Upload ID"),
    auth: AuthResponse = Depends(get_authenticated_user),
    upload_service: UploadService = Depends(get_upload_service),
) -> Dict[str, Any]:
    """
    Get processing status for an uploaded log file.

    Args:
        upload_id: Upload ID returned from upload endpoint
        auth: Authenticated user with guild context

    Returns:
        Current processing status and progress
    """
    status = upload_service.get_upload_status(upload_id)

    if not status:
        raise HTTPException(
            status_code=404, detail="Upload not found or not accessible by your guild"
        )

    return {
        "upload_id": status.upload_id,
        "guild_id": auth.guild_id,
        "guild_name": auth.guild_name,
        "file_name": status.file_name,
        "file_size": status.file_size,
        "status": status.status,
        "progress": status.progress,
        "encounters_found": status.encounters_found,
        "characters_found": status.characters_found,
        "events_processed": status.events_processed,
        "error_message": status.error_message,
        "start_time": status.start_time.isoformat() if status.start_time else None,
        "end_time": status.end_time.isoformat() if status.end_time else None,
    }


@router.get("/logs/{upload_id}/progress")
async def get_log_progress(
    upload_id: str = Path(..., description="Upload ID"),
    upload_service: UploadService = Depends(get_upload_service),
) -> Dict[str, Any]:
    """
    Get real-time processing progress for an uploaded log file.

    This endpoint provides the same information as /status but is optimized
    for polling by real-time monitoring clients.

    Args:
        upload_id: Upload ID returned from upload endpoint

    Returns:
        Current processing progress with detailed metrics
    """
    status = upload_service.get_upload_status(upload_id)

    if not status:
        raise HTTPException(status_code=404, detail="Upload not found")

    # Calculate processing rate if available
    processing_rate = 0.0
    estimated_completion = None

    if status.start_time and status.progress > 0:
        elapsed = (datetime.now() - status.start_time).total_seconds()
        if elapsed > 0:
            processing_rate = status.progress / elapsed
            if processing_rate > 0 and status.progress < 100:
                remaining_progress = 100 - status.progress
                estimated_completion = remaining_progress / processing_rate

    return {
        "upload_id": status.upload_id,
        "status": status.status,
        "progress": status.progress,
        "encounters_found": status.encounters_found,
        "characters_found": status.characters_found,
        "events_processed": status.events_processed,
        "processing_rate_percent_per_second": round(processing_rate, 2),
        "estimated_completion_seconds": (
            round(estimated_completion) if estimated_completion else None
        ),
        "error_message": status.error_message,
        "is_complete": status.status in ["completed", "error"],
    }


@router.get("/logs")
async def list_uploaded_logs(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of logs to return"),
    status_filter: Optional[str] = Query(
        None, description="Filter by status (pending, processing, completed, error)"
    ),
    upload_service: UploadService = Depends(get_upload_service),
) -> Dict[str, Any]:
    """
    List recently uploaded log files with optional status filtering.

    Args:
        limit: Maximum number of logs to return (1-100)
        status_filter: Optional status filter

    Returns:
        List of uploaded logs with their current status
    """
    try:
        uploads = upload_service.list_uploads(limit=limit, status_filter=status_filter)

        return {
            "uploads": [
                {
                    "upload_id": upload.upload_id,
                    "file_name": upload.file_name,
                    "file_size": upload.file_size,
                    "status": upload.status,
                    "progress": upload.progress,
                    "encounters_found": upload.encounters_found,
                    "characters_found": upload.characters_found,
                    "events_processed": upload.events_processed,
                    "start_time": upload.start_time.isoformat() if upload.start_time else None,
                    "end_time": upload.end_time.isoformat() if upload.end_time else None,
                    "error_message": upload.error_message,
                }
                for upload in uploads
            ],
            "total_returned": len(uploads),
            "limit": limit,
            "status_filter": status_filter,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list uploads: {str(e)}")


@router.get("/logs/stats")
async def get_upload_stats(
    upload_service: UploadService = Depends(get_upload_service),
) -> Dict[str, Any]:
    """
    Get statistics about uploaded log files.

    Returns:
        Upload statistics including counts, sizes, and processing metrics
    """
    try:
        return upload_service.get_upload_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get upload stats: {str(e)}")


@router.post("/logs/batch")
async def process_batch_logs(
    upload_ids: List[str], upload_service: UploadService = Depends(get_upload_service)
) -> Dict[str, Any]:
    """
    Get status for multiple uploaded log files in a single request.

    Args:
        upload_ids: List of upload IDs to check

    Returns:
        Status information for all requested uploads
    """
    if len(upload_ids) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 upload IDs per batch request")

    results = {}
    not_found = []

    for upload_id in upload_ids:
        status = upload_service.get_upload_status(upload_id)
        if status:
            results[upload_id] = {
                "file_name": status.file_name,
                "status": status.status,
                "progress": status.progress,
                "encounters_found": status.encounters_found,
                "characters_found": status.characters_found,
                "events_processed": status.events_processed,
                "error_message": status.error_message,
            }
        else:
            not_found.append(upload_id)

    return {
        "results": results,
        "not_found": not_found,
        "total_requested": len(upload_ids),
        "total_found": len(results),
    }


@router.delete("/logs/{upload_id}")
async def delete_upload_record(
    upload_id: str = Path(..., description="Upload ID"),
    upload_service: UploadService = Depends(get_upload_service),
) -> Dict[str, Any]:
    """
    Delete an upload record from the database.

    Note: This only removes the upload tracking record, not the processed
    encounter and character data.

    Args:
        upload_id: Upload ID to delete

    Returns:
        Confirmation of deletion
    """
    try:
        # Check if upload exists
        status = upload_service.get_upload_status(upload_id)
        if not status:
            raise HTTPException(status_code=404, detail="Upload not found")

        # Delete from database
        upload_service.db.execute("DELETE FROM uploads WHERE upload_id = %s", (upload_id,))

        # Remove from active uploads if present
        if upload_id in upload_service.active_uploads:
            del upload_service.active_uploads[upload_id]

        return {
            "message": f"Upload record {upload_id} deleted successfully",
            "upload_id": upload_id,
            "file_name": status.file_name,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete upload: {str(e)}")


# Import datetime for progress calculations
from datetime import datetime
