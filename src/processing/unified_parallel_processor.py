"""
Unified parallel combat log processor using the new UnifiedSegmenter.

This processor uses the modern unified data model with enhanced character tracking,
death analysis, and proper M+ hierarchical structure.
"""

import os
import mmap
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import logging

from ..parser.tokenizer import LineTokenizer
from ..parser.events import EventFactory
from ..segmentation.unified_segmenter import UnifiedSegmenter
from ..models.unified_encounter import UnifiedEncounter, EncounterType

logger = logging.getLogger(__name__)


@dataclass
class EncounterBoundary:
    """Represents the boundaries of an encounter in the log file."""

    start_byte: int
    end_byte: int
    encounter_type: str  # "ENCOUNTER", "CHALLENGE_MODE", or "TRASH"
    encounter_name: Optional[str] = None
    encounter_id: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class UnifiedParallelProcessor:
    """
    Processes combat logs using parallel processing with the unified data model.

    Uses a two-pass approach:
    1. Fast scan to identify encounter boundaries
    2. Parallel processing of each encounter segment using UnifiedSegmenter

    Features:
    - Enhanced character tracking with ability breakdowns
    - Death analysis with recent events
    - Proper M+ hierarchical structure
    - Talent/equipment data integration
    """

    def __init__(self, max_workers: Optional[int] = None):
        """
        Initialize the unified parallel processor.

        Args:
            max_workers: Maximum number of worker threads (defaults to CPU count)
        """
        self.max_workers = max_workers or os.cpu_count()
        self.parse_errors: List[str] = []
        self.total_events = 0

    def process_file(self, log_path: Path) -> List[UnifiedEncounter]:
        """
        Process a combat log file using parallel processing with unified segmentation.

        Args:
            log_path: Path to the combat log file

        Returns:
            List of UnifiedEncounter objects
        """
        logger.info(f"Starting unified parallel processing of {log_path}")

        # Phase 1: Fast encounter boundary detection
        boundaries = self._detect_encounter_boundaries(log_path)
        logger.info(f"Detected {len(boundaries)} top-level encounter segments")

        if not boundaries:
            logger.warning("No encounters found, falling back to sequential processing")
            return self._fallback_sequential_processing(log_path)

        # Phase 2: Parallel processing of encounter segments
        encounters = self._process_encounters_parallel(log_path, boundaries)

        logger.info(f"Parallel processing completed: {len(encounters)} encounters processed")
        return encounters

    def _detect_encounter_boundaries(self, log_path: Path) -> List[EncounterBoundary]:
        """
        Detect top-level boundaries: M+ runs and standalone raid encounters.

        This creates boundaries for the largest logical units:
        - Each complete Mythic+ run (CHALLENGE_MODE_START to END)
        - Each standalone raid encounter (ENCOUNTER_START to END not within M+)

        Args:
            log_path: Path to the combat log file

        Returns:
            List of top-level encounter boundaries
        """
        challenge_mode_ranges = []
        encounter_ranges = []

        with open(log_path, "rb") as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                file_size = len(mm)

                # Pass 1: Collect CHALLENGE_MODE ranges
                current_pos = 0
                current_challenge_mode = None

                while current_pos < file_size:
                    line_end = mm.find(b"\n", current_pos)
                    if line_end == -1:
                        line_end = file_size

                    try:
                        line = mm[current_pos:line_end].decode("utf-8", errors="ignore")

                        if "CHALLENGE_MODE_START" in line and not line.strip().startswith("#"):
                            if current_challenge_mode:
                                challenge_mode_ranges.append(current_challenge_mode)

                            parts = line.split(",")
                            # Extract zone name from the event
                            zone_name = "Mythic+"
                            for i, part in enumerate(parts):
                                if "CHALLENGE_MODE_START" in part and i + 1 < len(parts):
                                    zone_name = parts[i + 1].strip('"')
                                    break

                            current_challenge_mode = {
                                "start_byte": current_pos,
                                "end_byte": file_size,
                                "name": zone_name,
                            }

                        elif (
                            "CHALLENGE_MODE_END" in line
                            and not line.strip().startswith("#")
                            and current_challenge_mode
                        ):
                            current_challenge_mode["end_byte"] = line_end
                            challenge_mode_ranges.append(current_challenge_mode)
                            current_challenge_mode = None

                    except (UnicodeDecodeError, ValueError):
                        pass

                    current_pos = line_end + 1

                # Handle unclosed challenge mode
                if current_challenge_mode:
                    challenge_mode_ranges.append(current_challenge_mode)

                # Pass 2: Collect ENCOUNTER ranges
                current_pos = 0
                current_encounter = None

                while current_pos < file_size:
                    line_end = mm.find(b"\n", current_pos)
                    if line_end == -1:
                        line_end = file_size

                    try:
                        line = mm[current_pos:line_end].decode("utf-8", errors="ignore")

                        if "ENCOUNTER_START" in line and not line.strip().startswith("#"):
                            if current_encounter:
                                encounter_ranges.append(current_encounter)

                            parts = line.split(",")
                            # Find the encounter name and ID in the event
                            encounter_name = "Unknown"
                            encounter_id = None

                            for i, part in enumerate(parts):
                                if "ENCOUNTER_START" in part:
                                    # Encounter ID is usually 2 positions after ENCOUNTER_START
                                    if i + 2 < len(parts):
                                        try:
                                            encounter_id = int(parts[i + 2])
                                        except ValueError:
                                            pass
                                    # Encounter name is usually 3 positions after
                                    if i + 3 < len(parts):
                                        encounter_name = parts[i + 3].strip('"')
                                    break

                            current_encounter = {
                                "start_byte": current_pos,
                                "end_byte": file_size,
                                "name": encounter_name,
                                "id": encounter_id,
                            }

                        elif (
                            "ENCOUNTER_END" in line
                            and not line.strip().startswith("#")
                            and current_encounter
                        ):
                            current_encounter["end_byte"] = line_end
                            encounter_ranges.append(current_encounter)
                            current_encounter = None

                    except (UnicodeDecodeError, ValueError):
                        pass

                    current_pos = line_end + 1

                # Handle unclosed encounter
                if current_encounter:
                    encounter_ranges.append(current_encounter)

        # Create boundaries from top-level segments
        boundaries = []

        # Add all M+ runs as boundaries (these contain their boss encounters)
        for cm in challenge_mode_ranges:
            boundaries.append(
                EncounterBoundary(
                    start_byte=cm["start_byte"],
                    end_byte=cm["end_byte"],
                    encounter_type="CHALLENGE_MODE",
                    encounter_name=cm["name"],
                )
            )

        # Add only standalone encounters (not within any M+ run)
        for enc in encounter_ranges:
            is_within_challenge_mode = False

            for cm in challenge_mode_ranges:
                if enc["start_byte"] >= cm["start_byte"] and enc["end_byte"] <= cm["end_byte"]:
                    is_within_challenge_mode = True
                    break

            if not is_within_challenge_mode:
                boundaries.append(
                    EncounterBoundary(
                        start_byte=enc["start_byte"],
                        end_byte=enc["end_byte"],
                        encounter_type="ENCOUNTER",
                        encounter_name=enc["name"],
                        encounter_id=enc["id"],
                    )
                )

        # Sort boundaries by start position
        boundaries.sort(key=lambda b: b.start_byte)

        logger.info(
            f"Detected {len(boundaries)} top-level boundaries: "
            f"{len([b for b in boundaries if b.encounter_type == 'CHALLENGE_MODE'])} M+ runs, "
            f"{len([b for b in boundaries if b.encounter_type == 'ENCOUNTER'])} standalone raids"
        )

        return boundaries

    def _process_encounters_parallel(
        self, log_path: Path, boundaries: List[EncounterBoundary]
    ) -> List[UnifiedEncounter]:
        """
        Process encounters in parallel using thread pool.

        Args:
            log_path: Path to the combat log file
            boundaries: List of encounter boundaries to process

        Returns:
            List of UnifiedEncounter objects
        """
        all_encounters = []

        # Process encounters in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all encounter processing tasks
            future_to_boundary = {
                executor.submit(self._process_encounter_chunk, log_path, boundary): boundary
                for boundary in boundaries
            }

            # Collect results as they complete
            for future in as_completed(future_to_boundary):
                boundary = future_to_boundary[future]
                try:
                    encounters, events_processed, errors = future.result()
                    all_encounters.extend(encounters)
                    self.total_events += events_processed
                    self.parse_errors.extend(errors)

                    logger.debug(
                        f"Processed {boundary.encounter_name}: "
                        f"{len(encounters)} encounters, {events_processed} events"
                    )

                except Exception as e:
                    logger.error(f"Error processing encounter {boundary.encounter_name}: {e}")
                    self.parse_errors.append(f"Encounter {boundary.encounter_name}: {str(e)}")

        # Sort encounters by start time
        all_encounters.sort(
            key=lambda e: e.start_time if e.start_time else datetime.min
        )

        # Post-process: Calculate metrics for all encounters
        logger.info("Calculating metrics for all encounters...")
        for encounter in all_encounters:
            try:
                encounter.calculate_metrics()
                logger.debug(
                    f"Calculated metrics for {encounter.encounter_name} "
                    f"({encounter.encounter_type.value})"
                )
            except Exception as e:
                logger.error(f"Error calculating metrics for {encounter.encounter_name}: {e}")
                self.parse_errors.append(f"Metrics calculation failed: {str(e)}")

        return all_encounters

    def _process_encounter_chunk(
        self, log_path: Path, boundary: EncounterBoundary
    ) -> Tuple[List[UnifiedEncounter], int, List[str]]:
        """
        Process a single encounter chunk using UnifiedSegmenter.

        Args:
            log_path: Path to the combat log file
            boundary: Encounter boundary to process

        Returns:
            Tuple of (encounters, events_processed, errors)
        """
        # Create independent tokenizer, event factory, and segmenter for this thread
        tokenizer = LineTokenizer()
        event_factory = EventFactory()
        segmenter = UnifiedSegmenter()

        chunk_errors = []
        event_count = 0

        try:
            with open(log_path, "rb") as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    # Process lines in the boundary range
                    current_pos = boundary.start_byte

                    while current_pos < boundary.end_byte and current_pos < len(mm):
                        # Find next line
                        line_end = mm.find(b"\n", current_pos)
                        if line_end == -1 or line_end > boundary.end_byte:
                            line_end = min(boundary.end_byte, len(mm))

                        try:
                            line = mm[current_pos:line_end].decode("utf-8", errors="ignore")
                            if line.strip() and not line.strip().startswith("#"):
                                parsed_line = tokenizer.parse_line(line)
                                if parsed_line:
                                    event = event_factory.create_event(parsed_line)
                                    if event:
                                        segmenter.process_event(event)
                                        event_count += 1

                        except Exception as e:
                            if len(chunk_errors) < 100:  # Limit error collection
                                chunk_errors.append(f"Line {current_pos}: {str(e)}")

                        current_pos = line_end + 1

            # Get the completed encounters from this chunk
            encounters = segmenter.get_encounters()

            logger.debug(
                f"Chunk {boundary.encounter_name}: "
                f"{event_count} events, {len(encounters)} encounters"
            )

            return encounters, event_count, chunk_errors

        except Exception as e:
            logger.error(f"Failed to process encounter chunk {boundary.encounter_name}: {e}")
            chunk_errors.append(f"Chunk processing failed: {str(e)}")
            return [], 0, chunk_errors

    def _fallback_sequential_processing(self, log_path: Path) -> List[UnifiedEncounter]:
        """
        Fallback to sequential processing if no encounters are detected.

        Args:
            log_path: Path to the combat log file

        Returns:
            List of UnifiedEncounter objects
        """
        logger.info("Using sequential processing fallback with UnifiedSegmenter")

        tokenizer = LineTokenizer()
        event_factory = EventFactory()
        segmenter = UnifiedSegmenter()

        event_count = 0

        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line_num, line in enumerate(f, 1):
                if line.strip() and not line.strip().startswith("#"):
                    try:
                        parsed_line = tokenizer.parse_line(line)
                        if parsed_line:
                            event = event_factory.create_event(parsed_line)
                            if event:
                                segmenter.process_event(event)
                                event_count += 1

                                # Log progress
                                if event_count % 10000 == 0:
                                    logger.debug(f"Processed {event_count} events...")

                    except Exception as e:
                        if len(self.parse_errors) < 1000:  # Limit error collection
                            self.parse_errors.append(f"Line {line_num}: {str(e)}")

        self.total_events = event_count

        # Get all encounters
        encounters = segmenter.get_encounters()

        # Calculate metrics
        logger.info(f"Calculating metrics for {len(encounters)} encounters...")
        for encounter in encounters:
            try:
                encounter.calculate_metrics()
            except Exception as e:
                logger.error(f"Error calculating metrics for {encounter.encounter_name}: {e}")
                self.parse_errors.append(f"Metrics calculation failed: {str(e)}")

        return encounters

    def get_stats(self) -> Dict[str, Any]:
        """
        Get processing statistics.

        Returns:
            Dictionary of processing stats
        """
        return {
            "max_workers": self.max_workers,
            "total_events": self.total_events,
            "parse_errors": len(self.parse_errors),
            "errors": self.parse_errors[:100] if self.parse_errors else [],  # Limit errors shown
        }