"""
Efficient line buffering for streaming combat log data.

Provides thread-safe buffering, batching, and overflow protection
for high-throughput log streaming.
"""

import asyncio
import time
import logging
from typing import List, Optional, Callable, Dict, Any
from dataclasses import dataclass
from collections import deque
import threading

logger = logging.getLogger(__name__)


@dataclass
class BufferedLine:
    """A buffered log line with metadata."""

    sequence: int
    timestamp: float
    line: str
    received_at: float


class LineBuffer:
    """
    High-performance line buffer for streaming combat logs.

    Features:
    - Thread-safe operation
    - Automatic batching based on size or time
    - Overflow protection with oldest-first eviction
    - Statistics tracking
    - Configurable flush triggers
    """

    def __init__(
        self,
        max_size: int = 5000,
        batch_size: int = 1000,
        flush_interval: float = 1.0,
        on_batch_ready: Optional[Callable[[List[BufferedLine]], None]] = None,
    ):
        """
        Initialize line buffer.

        Args:
            max_size: Maximum buffer size before overflow
            batch_size: Lines per batch when flushing
            flush_interval: Maximum seconds between flushes
            on_batch_ready: Callback for when batch is ready
        """
        self.max_size = max_size
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.on_batch_ready = on_batch_ready

        # Thread-safe buffer
        self._buffer: deque[BufferedLine] = deque(maxlen=max_size)
        self._lock = threading.RLock()

        # State tracking
        self._last_flush = time.time()
        self._sequence_counter = 0
        self._total_added = 0
        self._total_flushed = 0
        self._overflows = 0

        # Flush timer
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start the buffer's background flush timer."""
        if self._running:
            return

        self._running = True
        self._flush_task = asyncio.create_task(self._flush_timer())
        logger.info(
            f"Line buffer started (max_size={self.max_size}, batch_size={self.batch_size})"
        )

    async def stop(self):
        """Stop the buffer and flush remaining lines."""
        self._running = False

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Flush any remaining lines
        await self.flush()
        logger.info("Line buffer stopped")

    def add_line(
        self,
        line: str,
        timestamp: Optional[float] = None,
        sequence: Optional[int] = None,
    ) -> int:
        """
        Add a line to the buffer.

        Args:
            line: Combat log line
            timestamp: Event timestamp (defaults to current time)
            sequence: Sequence number (auto-assigned if None)

        Returns:
            Assigned sequence number
        """
        if timestamp is None:
            timestamp = time.time()

        with self._lock:
            if sequence is None:
                sequence = self._sequence_counter
                self._sequence_counter += 1

            buffered_line = BufferedLine(
                sequence=sequence,
                timestamp=timestamp,
                line=line,
                received_at=time.time(),
            )

            # Check for overflow
            if len(self._buffer) >= self.max_size:
                self._overflows += 1
                logger.warning(
                    f"Buffer overflow! Dropping oldest line (total overflows: {self._overflows})"
                )

            self._buffer.append(buffered_line)
            self._total_added += 1

            # Check if we should flush immediately
            if len(self._buffer) >= self.batch_size:
                asyncio.create_task(self.flush())

        return sequence

    async def flush(self, force: bool = False) -> int:
        """
        Flush buffered lines in batches.

        Args:
            force: Force flush even if batch size not reached

        Returns:
            Number of lines flushed
        """
        if not self.on_batch_ready:
            return 0

        lines_flushed = 0

        with self._lock:
            # Determine how many lines to flush
            available = len(self._buffer)
            if available == 0:
                return 0

            if not force and available < self.batch_size:
                # Check time-based flush
                if time.time() - self._last_flush < self.flush_interval:
                    return 0

            # Extract lines for flushing
            batch_size = min(available, self.batch_size) if not force else available
            batch = []

            for _ in range(batch_size):
                if self._buffer:
                    batch.append(self._buffer.popleft())

            if not batch:
                return 0

            lines_flushed = len(batch)
            self._total_flushed += lines_flushed
            self._last_flush = time.time()

        # Process batch outside of lock
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self.on_batch_ready, batch
            )
            logger.debug(f"Flushed batch of {lines_flushed} lines")
        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            # Return lines to buffer on error
            with self._lock:
                for line in reversed(batch):
                    self._buffer.appendleft(line)
                self._total_flushed -= lines_flushed

        return lines_flushed

    async def _flush_timer(self):
        """Background task for periodic flushing."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                if self._running:  # Check again after sleep
                    await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in flush timer: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get buffer statistics."""
        with self._lock:
            current_size = len(self._buffer)
            utilization = (current_size / self.max_size) * 100

            # Calculate lag
            lag_seconds = 0.0
            if self._buffer:
                oldest = self._buffer[0]
                lag_seconds = time.time() - oldest.received_at

            return {
                "current_size": current_size,
                "max_size": self.max_size,
                "utilization_percent": round(utilization, 1),
                "total_added": self._total_added,
                "total_flushed": self._total_flushed,
                "pending": self._total_added - self._total_flushed,
                "overflows": self._overflows,
                "lag_seconds": round(lag_seconds, 3),
                "last_flush": self._last_flush,
                "sequence_counter": self._sequence_counter,
            }

    def clear(self):
        """Clear all buffered lines."""
        with self._lock:
            self._buffer.clear()
            logger.info("Buffer cleared")

    @property
    def size(self) -> int:
        """Get current buffer size."""
        with self._lock:
            return len(self._buffer)

    @property
    def is_full(self) -> bool:
        """Check if buffer is at capacity."""
        with self._lock:
            return len(self._buffer) >= self.max_size

    @property
    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        with self._lock:
            return len(self._buffer) == 0


class MultiClientBuffer:
    """
    Manages separate buffers for multiple clients.

    Provides isolation between clients while sharing processing
    resources efficiently.
    """

    def __init__(
        self,
        default_buffer_config: Optional[Dict[str, Any]] = None,
        max_clients: int = 100,
    ):
        """
        Initialize multi-client buffer manager.

        Args:
            default_buffer_config: Default buffer configuration
            max_clients: Maximum number of concurrent clients
        """
        self.default_config = default_buffer_config or {
            "max_size": 5000,
            "batch_size": 1000,
            "flush_interval": 1.0,
        }
        self.max_clients = max_clients

        self._buffers: Dict[str, LineBuffer] = {}
        self._lock = threading.RLock()

    def get_buffer(
        self, client_id: str, on_batch_ready: Optional[Callable] = None
    ) -> LineBuffer:
        """
        Get or create buffer for client.

        Args:
            client_id: Unique client identifier
            on_batch_ready: Callback for batch processing

        Returns:
            LineBuffer for the client
        """
        with self._lock:
            if client_id not in self._buffers:
                if len(self._buffers) >= self.max_clients:
                    raise ValueError(
                        f"Maximum client limit reached ({self.max_clients})"
                    )

                # Create new buffer
                buffer = LineBuffer(
                    on_batch_ready=on_batch_ready, **self.default_config
                )
                self._buffers[client_id] = buffer
                logger.info(f"Created buffer for client {client_id}")

            return self._buffers[client_id]

    async def start_buffer(self, client_id: str):
        """Start buffer for client."""
        with self._lock:
            if client_id in self._buffers:
                await self._buffers[client_id].start()

    async def stop_buffer(self, client_id: str):
        """Stop and remove buffer for client."""
        with self._lock:
            if client_id in self._buffers:
                await self._buffers[client_id].stop()
                del self._buffers[client_id]
                logger.info(f"Removed buffer for client {client_id}")

    async def stop_all(self):
        """Stop all client buffers."""
        with self._lock:
            clients = list(self._buffers.keys())

        for client_id in clients:
            await self.stop_buffer(client_id)

        logger.info("All client buffers stopped")

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all client buffers."""
        with self._lock:
            return {
                client_id: buffer.get_stats()
                for client_id, buffer in self._buffers.items()
            }

    @property
    def client_count(self) -> int:
        """Get number of active clients."""
        with self._lock:
            return len(self._buffers)
