"""
Database package for WoW combat log storage and retrieval.

This package provides:
- SQLite schema for efficient event storage
- Event compression for 70-80% size reduction
- High-speed query API with caching
- Real-time data ingestion
"""

from .schema import DatabaseManager, create_tables
from .compression import EventCompressor
from .storage import EventStorage
from .query import QueryAPI

__all__ = [
    "DatabaseManager",
    "create_tables",
    "EventCompressor",
    "EventStorage",
    "QueryAPI",
]
