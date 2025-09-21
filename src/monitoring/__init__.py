"""
Real-time monitoring package for WoW combat logs.

This package provides:
- File watcher for detecting log file changes
- Stream processor for incremental parsing
- Event callbacks for real-time notifications
"""

from .file_watcher import LogFileWatcher
from .stream_processor import StreamProcessor

__all__ = ["LogFileWatcher", "StreamProcessor"]
