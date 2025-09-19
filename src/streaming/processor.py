"""
Stream processor for real-time combat log processing.

Handles incoming log lines from streaming clients, processes them through
the existing parser and segmentation systems, and stores results to database.
"""

import asyncio
import time
import logging
from typing import List, Dict, Any, Optional, Callable, Set
from datetime import datetime
from dataclasses import dataclass
import uuid

from .buffer import BufferedLine, LineBuffer
from .session import StreamSession, SessionStatus
from parser.parser import CombatLogParser
from parser.tokenizer import CombatLogTokenizer
from segmentation.enhanced import EnhancedSegmenter
from database.storage import EventStorage
from database.schema import DatabaseManager
from api.models import EncounterUpdate, StreamStats

logger = logging.getLogger(__name__)


@dataclass
class ProcessingContext:
    """Context for processing a client's stream."""

    session: StreamSession
    parser: CombatLogParser
    segmenter: EnhancedSegmenter
    storage: EventStorage
    buffer: LineBuffer

    # State tracking
    total_processed: int = 0
    parse_errors: int = 0
    last_encounter_update: Optional[EncounterUpdate] = None

    # Performance metrics
    processing_start_time: float = 0.0
    last_metrics_update: float = 0.0


class StreamProcessor:
    """
    High-performance stream processor for combat log data.

    Features:
    - Real-time parsing and segmentation
    - Per-client processing isolation
    - Automatic database storage
    - Performance monitoring
    - Event callbacks for real-time notifications
    """

    def __init__(
        self,
        db: DatabaseManager,
        on_encounter_update: Optional[Callable[[EncounterUpdate], None]] = None,
        on_character_update: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        metrics_update_interval: float = 5.0
    ):
        """
        Initialize stream processor.

        Args:
            db: Database manager instance
            on_encounter_update: Callback for encounter state changes
            on_character_update: Callback for character metric updates
            metrics_update_interval: Seconds between metrics updates
        """
        self.db = db
        self.on_encounter_update = on_encounter_update
        self.on_character_update = on_character_update
        self.metrics_update_interval = metrics_update_interval

        # Processing contexts per client
        self._contexts: Dict[str, ProcessingContext] = {}

        # Global tokenizer (thread-safe)
        self._tokenizer = CombatLogTokenizer()

        # Performance tracking
        self._global_stats = {
            "total_lines_processed": 0,
            "total_events_generated": 0,
            "total_parse_errors": 0,
            "processing_start_time": time.time(),
            "contexts_active": 0,
        }

        # Background tasks
        self._metrics_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start the stream processor."""
        if self._running:
            return

        self._running = True
        self._metrics_task = asyncio.create_task(self._metrics_update_loop())
        logger.info("Stream processor started")

    async def stop(self):
        """Stop the stream processor and cleanup all contexts."""
        self._running = False

        if self._metrics_task:
            self._metrics_task.cancel()
            try:
                await self._metrics_task
            except asyncio.CancelledError:
                pass

        # Stop all processing contexts
        context_ids = list(self._contexts.keys())
        for context_id in context_ids:
            await self.stop_processing_context(context_id)

        logger.info("Stream processor stopped")

    async def create_processing_context(
        self,
        session: StreamSession,
        buffer_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a processing context for a client session.

        Args:
            session: Client session
            buffer_config: Optional buffer configuration

        Returns:
            Context ID
        """
        context_id = f"{session.client_id}:{session.session_id}"

        if context_id in self._contexts:
            # Clean up existing context
            await self.stop_processing_context(context_id)

        # Create processing components
        parser = CombatLogParser()
        segmenter = EnhancedSegmenter()
        storage = EventStorage(self.db)

        # Create buffer with callback
        buffer_config = buffer_config or {}
        buffer = LineBuffer(
            on_batch_ready=lambda batch: self._process_batch(context_id, batch),
            **buffer_config
        )

        # Create context
        context = ProcessingContext(
            session=session,
            parser=parser,
            segmenter=segmenter,
            storage=storage,
            buffer=buffer,
            processing_start_time=time.time(),
            last_metrics_update=time.time()
        )

        self._contexts[context_id] = context
        await buffer.start()

        session.status = SessionStatus.ACTIVE
        self._global_stats["contexts_active"] = len(self._contexts)

        logger.info(f"Created processing context for {context_id}")
        return context_id

    async def stop_processing_context(self, context_id: str) -> bool:
        """
        Stop and remove a processing context.

        Args:
            context_id: Context to stop

        Returns:
            True if context was stopped
        """
        if context_id not in self._contexts:
            return False

        context = self._contexts[context_id]

        # Stop buffer first
        await context.buffer.stop()

        # Finalize any active encounters
        raids, mplus = context.segmenter.finalize()

        if raids or mplus:
            # Store final encounters
            try:
                context.storage.store_encounters(raids, mplus, f"stream:{context_id}")
                logger.info(f"Stored final encounters for {context_id}: {len(raids)} raids, {len(mplus)} M+")
            except Exception as e:
                logger.error(f"Error storing final encounters for {context_id}: {e}")

        # Update session status
        context.session.status = SessionStatus.DISCONNECTED

        # Remove context
        del self._contexts[context_id]
        self._global_stats["contexts_active"] = len(self._contexts)

        logger.info(f"Stopped processing context for {context_id}")
        return True

    async def process_line(self, context_id: str, line: str, timestamp: Optional[float] = None, sequence: Optional[int] = None) -> bool:
        """
        Process a single log line for a client.

        Args:
            context_id: Processing context ID
            line: Combat log line
            timestamp: Event timestamp
            sequence: Sequence number

        Returns:
            True if line was accepted for processing
        """
        if context_id not in self._contexts:
            logger.warning(f"No processing context for {context_id}")
            return False

        context = self._contexts[context_id]

        # Check rate limits
        if not context.session.check_rate_limit():
            logger.warning(f"Rate limit exceeded for {context_id}")
            return False

        # Add to buffer for batch processing
        assigned_sequence = context.buffer.add_line(line, timestamp, sequence)

        # Update session metrics
        context.session.add_event(assigned_sequence, len(line.encode('utf-8')))

        return True

    def _process_batch(self, context_id: str, batch: List[BufferedLine]):
        """
        Process a batch of lines (called by buffer callback).

        Args:
            context_id: Processing context ID
            batch: Batch of buffered lines
        """
        if context_id not in self._contexts:
            return

        context = self._contexts[context_id]
        processed_count = 0
        error_count = 0

        try:
            for buffered_line in batch:
                try:
                    # Tokenize line
                    tokens = self._tokenizer.tokenize_line(buffered_line.line)
                    if not tokens:
                        continue

                    # Parse event
                    event = context.parser.parse_tokens(tokens)
                    if event:
                        # Process through segmenter
                        context.segmenter.process_event(event)
                        processed_count += 1

                        # Acknowledge processing
                        context.session.acknowledge_sequence(buffered_line.sequence)

                        # Check for encounter updates
                        self._check_encounter_updates(context)

                except Exception as e:
                    logger.debug(f"Error processing line: {e}")
                    context.session.add_parse_error()
                    error_count += 1

            # Update context metrics
            context.total_processed += processed_count
            context.parse_errors += error_count

            # Update global stats
            self._global_stats["total_lines_processed"] += len(batch)
            self._global_stats["total_events_generated"] += processed_count
            self._global_stats["total_parse_errors"] += error_count

            # Periodically store encounters
            self._maybe_store_encounters(context)

            logger.debug(f"Processed batch for {context_id}: {processed_count}/{len(batch)} successful")

        except Exception as e:
            logger.error(f"Critical error processing batch for {context_id}: {e}")

    def _check_encounter_updates(self, context: ProcessingContext):
        """Check for encounter state changes and emit updates."""
        current_raid = context.segmenter.current_raid
        current_mplus = context.segmenter.current_mythic_plus

        # Create encounter update if state changed
        encounter_update = None

        if current_raid:
            encounter_update = EncounterUpdate(
                encounter_type="raid",
                boss_name=current_raid.boss_name,
                difficulty=current_raid.difficulty.name if current_raid.difficulty else None,
                status="in_progress",
                start_time=current_raid.start_time.timestamp() if current_raid.start_time else time.time(),
                duration=current_raid.combat_length,
                participants=len(current_raid.characters),
                top_dps={
                    char.character_name: char.get_dps(current_raid.combat_length)
                    for char in list(current_raid.characters.values())[:5]  # Top 5
                    if char.total_damage_done > 0
                }
            )

        elif current_mplus:
            encounter_update = EncounterUpdate(
                encounter_type="mythic_plus",
                boss_name=current_mplus.dungeon_name,
                difficulty=f"+{current_mplus.keystone_level}",
                status="in_progress",
                start_time=current_mplus.start_time.timestamp() if current_mplus.start_time else time.time(),
                duration=current_mplus.actual_time_seconds,
                participants=len(current_mplus.overall_characters),
                top_dps={
                    char.character_name: char.get_dps(current_mplus.actual_time_seconds)
                    for char in list(current_mplus.overall_characters.values())[:5]
                    if char.total_damage_done > 0
                }
            )

        # Emit update if significant change
        if encounter_update and encounter_update != context.last_encounter_update:
            context.last_encounter_update = encounter_update
            if self.on_encounter_update:
                try:
                    self.on_encounter_update(encounter_update)
                except Exception as e:
                    logger.error(f"Error in encounter update callback: {e}")

    def _maybe_store_encounters(self, context: ProcessingContext):
        """Periodically store completed encounters to database."""
        # Get completed encounters
        raids, mplus = context.segmenter.finalize()

        if raids or mplus:
            try:
                # Store to database
                result = context.storage.store_encounters(
                    raids, mplus, f"stream:{context.session.client_id}"
                )
                logger.info(f"Stored encounters for {context.session.client_id}: {result}")

                # Update session context
                for raid in raids:
                    if raid.characters:
                        context.session.character_context.update(raid.characters.keys())

                for run in mplus:
                    if run.overall_characters:
                        context.session.character_context.update(run.overall_characters.keys())

            except Exception as e:
                logger.error(f"Error storing encounters: {e}")

    async def _metrics_update_loop(self):
        """Background task for updating metrics."""
        while self._running:
            try:
                await asyncio.sleep(self.metrics_update_interval)
                if not self._running:
                    break

                # Update buffer utilization for all contexts
                for context in self._contexts.values():
                    buffer_stats = context.buffer.get_stats()
                    context.session.set_buffer_utilization(buffer_stats["utilization_percent"])
                    context.session.set_lag(buffer_stats["lag_seconds"] * 1000)  # Convert to ms

                    # Update last metrics time
                    context.last_metrics_update = time.time()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics update loop: {e}")

    def get_context_stats(self, context_id: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a specific processing context."""
        if context_id not in self._contexts:
            return None

        context = self._contexts[context_id]
        current_time = time.time()

        return {
            "context_id": context_id,
            "uptime_seconds": current_time - context.processing_start_time,
            "total_processed": context.total_processed,
            "parse_errors": context.parse_errors,
            "buffer_stats": context.buffer.get_stats(),
            "session_stats": context.session.get_stats().dict(),
            "segmenter_stats": context.segmenter.get_stats(),
            "encounters": {
                "raids": len(context.segmenter.raid_encounters),
                "mythic_plus": len(context.segmenter.mythic_plus_runs),
                "current_raid": bool(context.segmenter.current_raid),
                "current_mplus": bool(context.segmenter.current_mythic_plus),
            }
        }

    def get_global_stats(self) -> Dict[str, Any]:
        """Get global processor statistics."""
        current_time = time.time()
        uptime = current_time - self._global_stats["processing_start_time"]

        return {
            "uptime_seconds": uptime,
            "active_contexts": len(self._contexts),
            "total_lines_processed": self._global_stats["total_lines_processed"],
            "total_events_generated": self._global_stats["total_events_generated"],
            "total_parse_errors": self._global_stats["total_parse_errors"],
            "lines_per_second": self._global_stats["total_lines_processed"] / max(uptime, 1.0),
            "events_per_second": self._global_stats["total_events_generated"] / max(uptime, 1.0),
            "error_rate": (
                self._global_stats["total_parse_errors"] / max(self._global_stats["total_lines_processed"], 1)
            ) * 100,
            "contexts": {
                context_id: {
                    "client_id": context.session.client_id,
                    "total_processed": context.total_processed,
                    "parse_errors": context.parse_errors,
                    "status": context.session.status.value,
                    "last_activity": context.session.last_activity,
                }
                for context_id, context in self._contexts.items()
            }
        }