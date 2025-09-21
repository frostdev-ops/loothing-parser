"""
Real-time combat log streaming package.

This package provides:
- Stream processing pipeline for incoming log data
- Buffering and batching for performance
- Integration with parser and database systems
"""

from .processor import StreamProcessor
from .buffer import LineBuffer
from .session import StreamSession

__all__ = ["StreamProcessor", "LineBuffer", "StreamSession"]
