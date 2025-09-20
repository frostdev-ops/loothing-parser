"""
Parallel combat log processor for multi-threaded encounter analysis.
"""

import os
import mmap
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import logging

from ..parser.parser import CombatLogParser
from ..segmentation.encounters import EncounterSegmenter, Fight
from ..segmentation.enhanced import EnhancedSegmenter

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


class ParallelLogProcessor:
    """
    Processes combat logs using parallel processing for improved performance.

    Uses a two-pass approach:
    1. Fast scan to identify encounter boundaries
    2. Parallel processing of each encounter segment
    """

    def __init__(self, max_workers: Optional[int] = None):
        """
        Initialize the parallel processor.

        Args:
            max_workers: Maximum number of worker threads (defaults to CPU count)
        """
        self.max_workers = max_workers or os.cpu_count()
        self.parse_errors: List[str] = []

    def process_file(self, log_path: Path) -> Tuple[List[Fight], Dict[str, Any]]:
        """
        Process a combat log file using parallel processing.

        Args:
            log_path: Path to the combat log file

        Returns:
            Tuple of (fights, enhanced_data)
        """
        logger.info(f"Starting parallel processing of {log_path}")

        # Phase 1: Fast encounter boundary detection
        boundaries = self._detect_encounter_boundaries(log_path)
        logger.info(f"Detected {len(boundaries)} encounter segments")

        if not boundaries:
            logger.warning("No encounters found, falling back to sequential processing")
            return self._fallback_sequential_processing(log_path)

        # Phase 2: Parallel processing of encounter segments
        fights, enhanced_data = self._process_encounters_parallel(log_path, boundaries)

        logger.info(f"Parallel processing completed: {len(fights)} fights processed")
        return fights, enhanced_data

    def _detect_encounter_boundaries(self, log_path: Path) -> List[EncounterBoundary]:
        """
        Fast scan to detect encounter boundaries in the log file.

        Args:
            log_path: Path to the combat log file

        Returns:
            List of encounter boundaries
        """
        boundaries = []
        current_encounter = None
        current_challenge_mode = None

        with open(log_path, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                file_size = len(mm)
                current_pos = 0

                while current_pos < file_size:
                    # Find next line
                    line_start = current_pos
                    line_end = mm.find(b'\n', current_pos)
                    if line_end == -1:
                        line_end = file_size

                    try:
                        line = mm[line_start:line_end].decode('utf-8', errors='ignore')

                        # Check for encounter events
                        if ',ENCOUNTER_START,' in line:
                            # End previous encounter if exists
                            if current_encounter:
                                current_encounter.end_byte = line_start
                                boundaries.append(current_encounter)

                            # Start new encounter
                            parts = line.split(',')
                            encounter_name = parts[4] if len(parts) > 4 else "Unknown"
                            encounter_id = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None

                            current_encounter = EncounterBoundary(
                                start_byte=line_start,
                                end_byte=file_size,  # Will be updated when encounter ends
                                encounter_type="ENCOUNTER",
                                encounter_name=encounter_name,
                                encounter_id=encounter_id
                            )

                        elif ',ENCOUNTER_END,' in line and current_encounter:
                            current_encounter.end_byte = line_end
                            boundaries.append(current_encounter)
                            current_encounter = None

                        elif ',CHALLENGE_MODE_START,' in line:
                            # End previous challenge mode if exists
                            if current_challenge_mode:
                                current_challenge_mode.end_byte = line_start
                                boundaries.append(current_challenge_mode)

                            # Start new challenge mode
                            parts = line.split(',')
                            zone_name = parts[4] if len(parts) > 4 else "Mythic+"

                            current_challenge_mode = EncounterBoundary(
                                start_byte=line_start,
                                end_byte=file_size,  # Will be updated when challenge ends
                                encounter_type="CHALLENGE_MODE",
                                encounter_name=zone_name
                            )

                        elif ',CHALLENGE_MODE_END,' in line and current_challenge_mode:
                            current_challenge_mode.end_byte = line_end
                            boundaries.append(current_challenge_mode)
                            current_challenge_mode = None

                    except (UnicodeDecodeError, ValueError) as e:
                        logger.debug(f"Error parsing line at position {current_pos}: {e}")

                    current_pos = line_end + 1

                # Handle unclosed encounters
                if current_encounter:
                    current_encounter.end_byte = file_size
                    boundaries.append(current_encounter)
                if current_challenge_mode:
                    current_challenge_mode.end_byte = file_size
                    boundaries.append(current_challenge_mode)

        return boundaries

    def _process_encounters_parallel(
        self, log_path: Path, boundaries: List[EncounterBoundary]
    ) -> Tuple[List[Fight], Dict[str, Any]]:
        """
        Process encounters in parallel using thread pool.

        Args:
            log_path: Path to the combat log file
            boundaries: List of encounter boundaries to process

        Returns:
            Tuple of (fights, enhanced_data)
        """
        all_fights = []
        all_raid_encounters = []
        all_mythic_plus_runs = []

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
                    fights, raid_encounters, mythic_plus_runs, errors = future.result()
                    all_fights.extend(fights)
                    all_raid_encounters.extend(raid_encounters)
                    all_mythic_plus_runs.extend(mythic_plus_runs)
                    self.parse_errors.extend(errors)

                except Exception as e:
                    logger.error(f"Error processing encounter {boundary.encounter_name}: {e}")
                    self.parse_errors.append(f"Encounter {boundary.encounter_name}: {str(e)}")

        # Sort fights by start time
        all_fights.sort(key=lambda f: f.start_time if f.start_time else datetime.min)

        # Prepare enhanced data
        enhanced_data = {
            "raid_encounters": all_raid_encounters,
            "mythic_plus_runs": all_mythic_plus_runs
        }

        return all_fights, enhanced_data

    def _process_encounter_chunk(
        self, log_path: Path, boundary: EncounterBoundary
    ) -> Tuple[List[Fight], List[Any], List[Any], List[str]]:
        """
        Process a single encounter chunk.

        Args:
            log_path: Path to the combat log file
            boundary: Encounter boundary to process

        Returns:
            Tuple of (fights, raid_encounters, mythic_plus_runs, errors)
        """
        # Create independent parser and segmenter instances for this thread
        parser = CombatLogParser()
        segmenter = EncounterSegmenter()
        enhanced_segmenter = EnhancedSegmenter()

        chunk_errors = []
        event_count = 0

        try:
            with open(log_path, 'rb') as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    # Process lines in the boundary range
                    current_pos = boundary.start_byte

                    while current_pos < boundary.end_byte and current_pos < len(mm):
                        # Find next line
                        line_end = mm.find(b'\n', current_pos)
                        if line_end == -1 or line_end > boundary.end_byte:
                            line_end = min(boundary.end_byte, len(mm))

                        try:
                            line = mm[current_pos:line_end].decode('utf-8', errors='ignore')
                            if line.strip():
                                parsed_line = parser.tokenizer.parse_line(line)
                                event = parser.event_factory.create_event(parsed_line)
                                segmenter.process_event(event)
                                enhanced_segmenter.process_event(event)
                                event_count += 1

                        except Exception as e:
                            chunk_errors.append(f"Line {current_pos}: {str(e)}")

                        current_pos = line_end + 1

            # Finalize the segmenters
            fights = segmenter.finalize()
            raid_encounters, mythic_plus_runs = enhanced_segmenter.finalize()

            logger.debug(
                f"Processed encounter {boundary.encounter_name}: "
                f"{event_count} events, {len(fights)} fights"
            )

            return fights, raid_encounters, mythic_plus_runs, chunk_errors

        except Exception as e:
            logger.error(f"Failed to process encounter chunk {boundary.encounter_name}: {e}")
            chunk_errors.append(f"Chunk processing failed: {str(e)}")
            return [], [], [], chunk_errors

    def _fallback_sequential_processing(self, log_path: Path) -> Tuple[List[Fight], Dict[str, Any]]:
        """
        Fallback to sequential processing if no encounters are detected.

        Args:
            log_path: Path to the combat log file

        Returns:
            Tuple of (fights, enhanced_data)
        """
        logger.info("Using sequential processing fallback")

        parser = CombatLogParser()
        segmenter = EncounterSegmenter()
        enhanced_segmenter = EnhancedSegmenter()

        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    try:
                        parsed_line = parser.tokenizer.parse_line(line)
                        event = parser.event_factory.create_event(parsed_line)
                        segmenter.process_event(event)
                        enhanced_segmenter.process_event(event)
                    except Exception as e:
                        self.parse_errors.append(f"Line {line_num}: {str(e)}")

        fights = segmenter.finalize()
        raid_encounters, mythic_plus_runs = enhanced_segmenter.finalize()

        enhanced_data = {
            "raid_encounters": raid_encounters,
            "mythic_plus_runs": mythic_plus_runs
        }

        return fights, enhanced_data

    def get_stats(self) -> Dict[str, Any]:
        """
        Get processing statistics.

        Returns:
            Dictionary of processing stats
        """
        return {
            "max_workers": self.max_workers,
            "parse_errors": len(self.parse_errors),
            "errors": self.parse_errors
        }