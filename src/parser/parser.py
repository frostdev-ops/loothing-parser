"""
Main combat log parser that coordinates tokenization, event creation, and processing.
"""

import os
from pathlib import Path
from typing import Iterator, List, Optional, Dict, Any
from datetime import datetime
import logging

from .tokenizer import LineTokenizer, ParsedLine
from .events import BaseEvent, EventFactory
from .schemas import EventSchema


logger = logging.getLogger(__name__)


class CombatLogParser:
    """
    Main parser for WoW combat log files.

    Handles file reading, line tokenization, and event creation.
    """

    def __init__(self, buffer_size: int = 8192):
        """
        Initialize the combat log parser.

        Args:
            buffer_size: Size of read buffer for file streaming
        """
        self.tokenizer = LineTokenizer()
        self.event_factory = EventFactory()
        self.buffer_size = buffer_size
        self.current_file = None
        self.events_processed = 0
        self.parse_errors = []

    def parse_file(self, file_path: str, progress_callback=None) -> Iterator[BaseEvent]:
        """
        Parse a combat log file and yield events.

        Args:
            file_path: Path to the combat log file
            progress_callback: Optional callback for progress updates

        Yields:
            BaseEvent objects
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Combat log file not found: {file_path}")

        self.current_file = file_path
        file_size = file_path.stat().st_size
        bytes_read = 0

        logger.info(f"Starting parse of {file_path.name} ({file_size / 1024 / 1024:.1f} MB)")

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            line_buffer = ""
            chunk_count = 0

            while True:
                chunk = f.read(self.buffer_size)
                if not chunk:
                    # Process any remaining line
                    if line_buffer:
                        yield from self._process_line(line_buffer)
                    break

                bytes_read += len(chunk.encode('utf-8'))
                chunk_count += 1

                # Add chunk to buffer
                line_buffer += chunk

                # Process complete lines
                lines = line_buffer.split('\n')
                line_buffer = lines[-1]  # Keep incomplete line for next iteration

                for line in lines[:-1]:
                    yield from self._process_line(line)

                # Update progress
                if progress_callback and chunk_count % 100 == 0:
                    progress = bytes_read / file_size
                    progress_callback(progress, bytes_read, file_size)

        logger.info(f"Completed parsing {self.current_file.name}: "
                   f"{self.events_processed} events, {len(self.parse_errors)} errors")

    def _process_line(self, line: str) -> Iterator[BaseEvent]:
        """
        Process a single line and yield event if valid.

        Args:
            line: Raw line from combat log

        Yields:
            BaseEvent if line parses successfully
        """
        if not line.strip():
            return

        try:
            # Tokenize the line
            parsed_line = self.tokenizer.parse_line(line)
            if not parsed_line:
                return

            # Create event object
            event = self.event_factory.create_event(parsed_line)
            if event:
                self.events_processed += 1
                yield event

        except Exception as e:
            self.parse_errors.append({
                'line': line[:100],  # Store first 100 chars
                'error': str(e),
                'line_number': self.tokenizer.line_count
            })
            logger.debug(f"Parse error on line {self.tokenizer.line_count}: {e}")

    def parse_lines(self, lines: List[str]) -> List[BaseEvent]:
        """
        Parse a list of lines and return events.

        Args:
            lines: List of raw combat log lines

        Returns:
            List of BaseEvent objects
        """
        events = []
        for line in lines:
            for event in self._process_line(line):
                events.append(event)
        return events

    def get_stats(self) -> Dict[str, Any]:
        """
        Get parsing statistics.

        Returns:
            Dictionary with parsing stats
        """
        return {
            'file': str(self.current_file) if self.current_file else None,
            'events_processed': self.events_processed,
            'parse_errors': len(self.parse_errors),
            'tokenizer_stats': self.tokenizer.get_stats()
        }

    def reset(self):
        """Reset parser state for new file."""
        self.tokenizer = LineTokenizer()
        self.events_processed = 0
        self.parse_errors = []
        self.current_file = None


class StreamingParser:
    """
    Streaming parser for processing very large combat log files.

    Processes events in chunks to minimize memory usage.
    """

    def __init__(self, chunk_size: int = 10000):
        """
        Initialize streaming parser.

        Args:
            chunk_size: Number of events to process at once
        """
        self.parser = CombatLogParser()
        self.chunk_size = chunk_size

    def process_file(self, file_path: str, event_handler, progress_callback=None):
        """
        Process a file with a callback for each chunk of events.

        Args:
            file_path: Path to combat log file
            event_handler: Callback function for processing event chunks
            progress_callback: Optional progress callback
        """
        chunk = []

        for event in self.parser.parse_file(file_path, progress_callback):
            chunk.append(event)

            if len(chunk) >= self.chunk_size:
                event_handler(chunk)
                chunk = []

        # Process remaining events
        if chunk:
            event_handler(chunk)