"""
WebSocket notification service for upload progress.

Sends real-time notifications about upload progress via existing streaming WebSocket connections.
"""

import json
import logging
from typing import Dict, Set, Optional, Any
from datetime import datetime

from .upload_service import UploadStatus

logger = logging.getLogger(__name__)


class WebSocketNotifier:
    """
    Service for sending upload progress notifications via WebSocket connections.

    Integrates with the existing streaming server to send real-time updates
    about upload progress to connected clients.
    """

    def __init__(self):
        """Initialize WebSocket notifier."""
        # Track which clients are subscribed to which upload IDs
        self._upload_subscriptions: Dict[str, Set[str]] = {}  # upload_id -> set of session_ids
        self._client_subscriptions: Dict[str, Set[str]] = {}  # session_id -> set of upload_ids

        # Reference to streaming server connections (will be injected)
        self._websocket_connections: Dict[str, Any] = {}

    def set_websocket_connections(self, connections: Dict[str, Any]):
        """Set reference to active WebSocket connections from streaming server."""
        self._websocket_connections = connections

    def subscribe_to_upload(self, session_id: str, upload_id: str):
        """Subscribe a WebSocket session to upload progress notifications."""
        if upload_id not in self._upload_subscriptions:
            self._upload_subscriptions[upload_id] = set()

        if session_id not in self._client_subscriptions:
            self._client_subscriptions[session_id] = set()

        self._upload_subscriptions[upload_id].add(session_id)
        self._client_subscriptions[session_id].add(upload_id)

        logger.debug(f"Session {session_id} subscribed to upload {upload_id}")

    def unsubscribe_from_upload(self, session_id: str, upload_id: str):
        """Unsubscribe a WebSocket session from upload progress notifications."""
        if upload_id in self._upload_subscriptions:
            self._upload_subscriptions[upload_id].discard(session_id)
            if not self._upload_subscriptions[upload_id]:
                del self._upload_subscriptions[upload_id]

        if session_id in self._client_subscriptions:
            self._client_subscriptions[session_id].discard(upload_id)
            if not self._client_subscriptions[session_id]:
                del self._client_subscriptions[session_id]

        logger.debug(f"Session {session_id} unsubscribed from upload {upload_id}")

    def cleanup_session(self, session_id: str):
        """Clean up subscriptions when a session disconnects."""
        if session_id in self._client_subscriptions:
            upload_ids = self._client_subscriptions[session_id].copy()
            for upload_id in upload_ids:
                self.unsubscribe_from_upload(session_id, upload_id)

            logger.debug(f"Cleaned up subscriptions for session {session_id}")

    async def notify_upload_progress(self, upload_id: str, status: UploadStatus):
        """Send upload progress notification to all subscribed clients."""
        if upload_id not in self._upload_subscriptions:
            return  # No subscribers

        # Create notification message
        notification = {
            "type": "upload_progress",
            "timestamp": datetime.now().timestamp(),
            "data": {
                "upload_id": upload_id,
                "file_name": status.file_name,
                "status": status.status,
                "progress": status.progress,
                "encounters_found": status.encounters_found,
                "characters_found": status.characters_found,
                "events_processed": status.events_processed,
                "error_message": status.error_message
            }
        }

        # Send to all subscribed sessions
        subscribed_sessions = self._upload_subscriptions[upload_id].copy()
        disconnected_sessions = []

        for session_id in subscribed_sessions:
            try:
                if session_id in self._websocket_connections:
                    websocket = self._websocket_connections[session_id]
                    await websocket.send_text(json.dumps(notification))
                    logger.debug(f"Sent upload progress to session {session_id}")
                else:
                    # Session no longer exists, mark for cleanup
                    disconnected_sessions.append(session_id)

            except Exception as e:
                logger.warning(f"Failed to send notification to session {session_id}: {e}")
                disconnected_sessions.append(session_id)

        # Clean up disconnected sessions
        for session_id in disconnected_sessions:
            self.cleanup_session(session_id)

    async def notify_encounter_found(self, upload_id: str, encounter_data: Dict[str, Any]):
        """Send notification when a new encounter is found during processing."""
        if upload_id not in self._upload_subscriptions:
            return

        notification = {
            "type": "encounter_found",
            "timestamp": datetime.now().timestamp(),
            "data": {
                "upload_id": upload_id,
                "encounter": encounter_data
            }
        }

        subscribed_sessions = self._upload_subscriptions[upload_id].copy()
        for session_id in subscribed_sessions:
            try:
                if session_id in self._websocket_connections:
                    websocket = self._websocket_connections[session_id]
                    await websocket.send_text(json.dumps(notification))
            except Exception as e:
                logger.warning(f"Failed to send encounter notification to session {session_id}: {e}")

    async def notify_character_metrics(self, upload_id: str, character_data: Dict[str, Any]):
        """Send notification when character metrics are calculated."""
        if upload_id not in self._upload_subscriptions:
            return

        notification = {
            "type": "character_metrics",
            "timestamp": datetime.now().timestamp(),
            "data": {
                "upload_id": upload_id,
                "character": character_data
            }
        }

        subscribed_sessions = self._upload_subscriptions[upload_id].copy()
        for session_id in subscribed_sessions:
            try:
                if session_id in self._websocket_connections:
                    websocket = self._websocket_connections[session_id]
                    await websocket.send_text(json.dumps(notification))
            except Exception as e:
                logger.warning(f"Failed to send character notification to session {session_id}: {e}")

    def get_subscriptions_count(self) -> Dict[str, int]:
        """Get statistics about current subscriptions."""
        return {
            "total_upload_subscriptions": len(self._upload_subscriptions),
            "total_client_subscriptions": len(self._client_subscriptions),
            "active_uploads": list(self._upload_subscriptions.keys()),
            "active_clients": list(self._client_subscriptions.keys())
        }


# Global notifier instance
_websocket_notifier: Optional[WebSocketNotifier] = None


def get_websocket_notifier() -> WebSocketNotifier:
    """Get or create the global WebSocket notifier instance."""
    global _websocket_notifier
    if _websocket_notifier is None:
        _websocket_notifier = WebSocketNotifier()
    return _websocket_notifier