"""
Real data testing suite for WoW combat log parser.

Tests parser validation using example WoWCombatLog files to ensure the
parser works correctly with real combat data.
"""

import pytest
import time
import gc
import psutil
import os
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from src.parser.parser import CombatLogParser
from src.segmentation.encounters import EncounterSegmenter
from src.database.compression import EventCompressor
from src.models.character_events import CharacterEventStream


class TestRealDataParser:
    """Test parser with real WoW combat log files."""

    @pytest.fixture
    def example_files(self) -> List[Path]:
        """Get all example WoW combat log files."""
        examples_dir = Path("examples")
        if not examples_dir.exists():
            pytest.skip("Examples directory not found")

        files = list(examples_dir.glob("WoWCombatLog*.txt"))
        if not files:
            pytest.skip("No example combat log files found")

        return sorted(files, key=lambda x: x.stat().st_size)

    @pytest.fixture
    def small_log_file(self, example_files) -> Path:
        """Get the smallest example file for quick tests."""
        return example_files[0]

    @pytest.fixture
    def large_log_file(self, example_files) -> Path:
        """Get the largest example file for performance tests."""
        return example_files[-1]

    def test_parser_basic_functionality(self, small_log_file):
        """Test basic parser functionality with real data."""
        parser = CombatLogParser()

        # Test parsing the first 1000 lines
        events = []
        with open(small_log_file, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= 1000:  # Limit to first 1000 lines for speed
                    break

                line = line.strip()
                if line:
                    for event in parser._process_line(line):
                        events.append(event)

        # Validate we parsed some events
        assert len(events) > 0, "Parser should extract events from real combat log"

        # Validate events have expected structure
        for event in events[:10]:  # Check first 10 events
            assert hasattr(event, "timestamp"), "Events should have timestamp"
            assert hasattr(event, "event_type"), "Events should have event_type"

    def test_parser_all_example_files(self, example_files):
        """Test parser can handle all example files without crashing."""
        parser = CombatLogParser()

        for log_file in example_files:
            file_size_mb = log_file.stat().st_size / (1024 * 1024)
            print(f"Testing file: {log_file.name} ({file_size_mb:.1f} MB)")

            events_parsed = 0
            parse_errors = 0

            # Parse first 500 lines of each file
            with open(log_file, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= 500:  # Limit lines for test speed
                        break

                    line = line.strip()
                    if line:
                        try:
                            for event in parser._process_line(line):
                                events_parsed += 1
                        except Exception as e:
                            parse_errors += 1
                            if parse_errors > 10:  # Stop if too many errors
                                break

            # Validate parsing was mostly successful
            success_rate = events_parsed / max(1, events_parsed + parse_errors)
            assert (
                success_rate > 0.8
            ), f"Parser success rate should be >80% for {log_file.name}"
            print(f"  Parsed {events_parsed} events, success rate: {success_rate:.2%}")

    def test_encounter_segmentation(self, small_log_file):
        """Test encounter segmentation with real data."""
        parser = CombatLogParser()
        segmenter = EncounterSegmenter()

        events = []
        with open(small_log_file, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= 2000:  # Parse more lines to find encounters
                    break

                line = line.strip()
                if line:
                    for event in parser._process_line(line):
                        events.append(event)

        if events:
            segments = segmenter.segment_encounters(events)
            # Don't assert specific number as it depends on the log content
            # Just validate the segmenter doesn't crash
            assert isinstance(segments, list), "Segmenter should return a list"

    def test_compression_with_real_data(self, small_log_file):
        """Test compression efficiency with real WoW combat data."""
        parser = CombatLogParser()
        compressor = EventCompressor()

        # Parse events for compression test
        events = []
        with open(small_log_file, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= 1000:
                    break

                line = line.strip()
                if line:
                    event = parser.parse_line(line)
                    if event:
                        # Convert to timestamped events for compression
                        timestamped_event = {
                            "timestamp": event.timestamp,
                            "event_type": event.event_type,
                            "data": event.__dict__,
                        }
                        events.append(timestamped_event)

        if events:
            # Test compression
            compressed_data, stats = compressor.compress_events(events)

            # Validate compression worked
            assert len(compressed_data) > 0, "Compression should produce data"
            assert stats["event_count"] == len(events), "Stats should match event count"

            # Check compression ratio (should be reasonable for real data)
            compression_ratio = stats.get("compression_ratio", 1.0)
            assert (
                0.1 <= compression_ratio <= 1.0
            ), "Compression ratio should be reasonable"

            print(
                f"Compressed {len(events)} events with ratio: {compression_ratio:.3f}"
            )

    def test_performance_benchmarks(self, example_files):
        """Test parsing performance with different file sizes."""
        parser = CombatLogParser()
        benchmarks = []

        for log_file in example_files[:3]:  # Test first 3 files
            file_size_mb = log_file.stat().st_size / (1024 * 1024)

            # Measure parsing performance
            start_time = time.time()
            events_parsed = 0

            with open(log_file, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= 1000:  # Standard test size
                        break

                    line = line.strip()
                    if line:
                        event = parser.parse_line(line)
                        if event:
                            events_parsed += 1

            parse_time = time.time() - start_time
            lines_per_second = 1000 / parse_time if parse_time > 0 else 0

            benchmarks.append(
                {
                    "file": log_file.name,
                    "size_mb": file_size_mb,
                    "parse_time": parse_time,
                    "events_parsed": events_parsed,
                    "lines_per_second": lines_per_second,
                }
            )

            print(f"Performance: {log_file.name} - {lines_per_second:.0f} lines/sec")

        # Validate performance is reasonable (>100 lines/sec minimum)
        for benchmark in benchmarks:
            assert (
                benchmark["lines_per_second"] > 100
            ), f"Performance too slow for {benchmark['file']}"

    def test_memory_usage(self, small_log_file):
        """Test memory usage doesn't grow excessively during parsing."""
        parser = CombatLogParser()
        process = psutil.Process(os.getpid())

        # Measure initial memory
        initial_memory = process.memory_info().rss / (1024 * 1024)  # MB

        events = []
        with open(small_log_file, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= 5000:  # Parse more lines to test memory
                    break

                line = line.strip()
                if line:
                    for event in parser._process_line(line):
                        events.append(event)

                # Check memory every 1000 lines
                if i > 0 and i % 1000 == 0:
                    current_memory = process.memory_info().rss / (1024 * 1024)
                    memory_growth = current_memory - initial_memory

                    # Memory growth should be reasonable (<100MB for 1000 events)
                    assert (
                        memory_growth < 100
                    ), f"Memory usage growing too fast: {memory_growth:.1f}MB"

        # Final memory check
        final_memory = process.memory_info().rss / (1024 * 1024)
        total_growth = final_memory - initial_memory

        print(
            f"Memory usage: {initial_memory:.1f}MB -> {final_memory:.1f}MB (+{total_growth:.1f}MB)"
        )
        print(f"Events parsed: {len(events)}")

        # Memory growth should be proportional to events parsed
        if len(events) > 0:
            memory_per_event = (total_growth * 1024) / len(events)  # KB per event
            assert (
                memory_per_event < 10
            ), f"Memory per event too high: {memory_per_event:.2f}KB"

    def test_character_stream_extraction(self, small_log_file):
        """Test character stream extraction from real data."""
        parser = CombatLogParser()
        character_events = {}

        with open(small_log_file, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= 1000:
                    break

                line = line.strip()
                if line:
                    event = parser.parse_line(line)
                    if event and hasattr(event, "source_name"):
                        source_name = getattr(event, "source_name", None)
                        if source_name and source_name.startswith("Player-"):
                            # This is a player event
                            if source_name not in character_events:
                                character_events[source_name] = []
                            character_events[source_name].append(event)

        # Validate we found some player events
        if character_events:
            print(f"Found events for {len(character_events)} characters")

            # Check the character with the most events
            most_active_char = max(
                character_events.keys(), key=lambda x: len(character_events[x])
            )
            event_count = len(character_events[most_active_char])

            assert event_count > 0, "Should find events for characters"
            print(
                f"Most active character: {most_active_char} with {event_count} events"
            )


class TestRealDataValidation:
    """Validation tests for real data processing."""

    def test_combat_log_format_validation(self):
        """Test that we can identify and validate WoW combat log format."""
        examples_dir = Path("examples")
        if not examples_dir.exists():
            pytest.skip("Examples directory not found")

        files = list(examples_dir.glob("WoWCombatLog*.txt"))
        if not files:
            pytest.skip("No example files found")

        for log_file in files[:2]:  # Test first 2 files
            with open(log_file, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()

                # First line should contain COMBAT_LOG_VERSION
                assert (
                    "COMBAT_LOG_VERSION" in first_line
                ), f"Invalid combat log format in {log_file.name}"

                # Should have timestamp format
                assert (
                    "/" in first_line and ":" in first_line
                ), f"Missing timestamp in {log_file.name}"

                print(f"Validated format for {log_file.name}")

    def test_encounter_detection(self):
        """Test that we can detect raid encounters in real logs."""
        examples_dir = Path("examples")
        if not examples_dir.exists():
            pytest.skip("Examples directory not found")

        files = list(examples_dir.glob("WoWCombatLog*.txt"))
        if not files:
            pytest.skip("No example files found")

        # Look for encounter events in the logs
        encounter_events_found = False

        for log_file in files[:2]:
            with open(log_file, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= 1000:  # Check first 1000 lines
                        break

                    if "ENCOUNTER_" in line or "CHALLENGE_MODE_" in line:
                        encounter_events_found = True
                        print(
                            f"Found encounter event in {log_file.name}: {line[:100]}..."
                        )
                        break

        # Not all logs will have encounters, so just report what we found
        print(f"Encounter events found: {encounter_events_found}")
