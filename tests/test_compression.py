"""
Tests for event compression and decompression functionality.

Tests the compression algorithms, performance, and data integrity
of the event storage system.
"""

import pytest
import json
import time
from datetime import datetime

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.compression import EventCompressor, compression_stats
from src.models.character_events import TimestampedEvent, CharacterEventStream
from src.parser.events import BaseEvent, DamageEvent, SpellEvent


@pytest.fixture
def compressor():
    """Create an EventCompressor instance."""
    return EventCompressor()


@pytest.fixture
def sample_events():
    """Create sample events for testing."""
    events = []
    base_time = time.time()

    # Create various event types
    events.append(
        TimestampedEvent(
            timestamp=base_time,
            sequence=0,
            event=SpellEvent(
                timestamp=datetime.fromtimestamp(base_time),
                event_type="SPELL_CAST_START",
                raw_line="test line",
                source_guid="Player-1234-567890AB",
                source_name="Testplayer",
                source_flags=0x512,
                source_raid_flags=0x0,
                dest_guid="Creature-5678-CDEF1234",
                dest_name="Target",
                dest_flags=0x10A28,
                dest_raid_flags=0x0,
                spell_id=1234,
                spell_name="Test Spell",
                spell_school=0x1,
            ),
        )
    )

    events.append(
        TimestampedEvent(
            timestamp=base_time + 1.0,
            sequence=1,
            event=DamageEvent(
                timestamp=datetime.fromtimestamp(base_time + 1.0),
                event_type="SPELL_DAMAGE",
                raw_line="test line",
                source_guid="Player-1234-567890AB",
                source_name="Testplayer",
                source_flags=0x512,
                source_raid_flags=0x0,
                dest_guid="Creature-5678-CDEF1234",
                dest_name="Target",
                dest_flags=0x10A28,
                dest_raid_flags=0x0,
                spell_id=1234,
                spell_name="Test Spell",
                spell_school=0x1,
                amount=5000,
                overkill=0,
                school=0x1,
                resisted=0,
                blocked=0,
                absorbed=0,
                critical=True,
                glancing=False,
                crushing=False,
            ),
        )
    )

    events.append(
        TimestampedEvent(
            timestamp=base_time + 2.0,
            sequence=2,
            event=BaseEvent(
                timestamp=datetime.fromtimestamp(base_time + 2.0),
                event_type="UNIT_DIED",
                raw_line="test line",
                source_guid="nil",
                source_name="nil",
                source_flags=0x0,
                source_raid_flags=0x0,
                dest_guid="Creature-5678-CDEF1234",
                dest_name="Target",
                dest_flags=0x10A28,
                dest_raid_flags=0x0,
            ),
        )
    )

    return events


class TestEventCompressor:
    """Test the EventCompressor class."""

    def test_compression_basic(self, compressor, sample_events):
        """Test basic compression functionality."""
        # Compress events
        compressed_data = compressor.compress_events(sample_events)

        # Should return bytes
        assert isinstance(compressed_data, bytes)
        assert len(compressed_data) > 0

        # Decompress
        decompressed_events = compressor.decompress_events(compressed_data)

        # Should have same number of events
        assert len(decompressed_events) == len(sample_events)

        # Events should be equivalent
        for original, decompressed in zip(sample_events, decompressed_events):
            assert original.timestamp == decompressed.timestamp
            assert original.sequence == decompressed.sequence
            assert original.event.event_type == decompressed.event.event_type

    def test_empty_event_list(self, compressor):
        """Test compression of empty event list."""
        compressed_data = compressor.compress_events([])
        assert isinstance(compressed_data, bytes)

        decompressed_events = compressor.decompress_events(compressed_data)
        assert decompressed_events == []

    def test_single_event(self, compressor, sample_events):
        """Test compression of single event."""
        single_event = [sample_events[0]]

        compressed_data = compressor.compress_events(single_event)
        decompressed_events = compressor.decompress_events(compressed_data)

        assert len(decompressed_events) == 1
        assert (
            decompressed_events[0].event.event_type == single_event[0].event.event_type
        )

    def test_large_event_list(self, compressor):
        """Test compression of large event list."""
        # Create many similar events (should compress well)
        base_time = time.time()
        large_event_list = []

        for i in range(1000):
            event = TimestampedEvent(
                timestamp=base_time + i * 0.1,
                sequence=i,
                event=DamageEvent(
                    timestamp=datetime.fromtimestamp(base_time + i * 0.1),
                    event_type="SPELL_DAMAGE",
                    raw_line="test line",
                    source_guid="Player-1234-567890AB",
                    source_name="Testplayer",
                    source_flags=0x512,
                    source_raid_flags=0x0,
                    dest_guid="Creature-5678-CDEF1234",
                    dest_name="Target",
                    dest_flags=0x10A28,
                    dest_raid_flags=0x0,
                    spell_id=1234,
                    spell_name="Test Spell",
                    spell_school=0x1,
                    amount=5000 + (i % 100),  # Slight variation
                    overkill=0,
                    school=0x1,
                    resisted=0,
                    blocked=0,
                    absorbed=0,
                    critical=i % 5 == 0,  # Some variation
                    glancing=False,
                    crushing=False,
                ),
            )
            large_event_list.append(event)

        # Compress
        compressed_data = compressor.compress_events(large_event_list)

        # Should achieve good compression
        # Estimate uncompressed size (this is rough)
        uncompressed_estimate = len(
            json.dumps([e.model_dump() for e in large_event_list]).encode()
        )
        compression_ratio = len(compressed_data) / uncompressed_estimate

        # Should compress to less than 50% of original
        assert compression_ratio < 0.5

        # Verify decompression
        decompressed_events = compressor.decompress_events(compressed_data)
        assert len(decompressed_events) == len(large_event_list)

    def test_compression_ratio_calculation(self, compressor, sample_events):
        """Test compression ratio calculation."""
        # Test with known data
        compressed_data = compressor.compress_events(sample_events)

        # Calculate sizes
        uncompressed_size = compressor._estimate_uncompressed_size(sample_events)
        compressed_size = len(compressed_data)

        ratio = compressed_size / uncompressed_size
        assert 0.0 < ratio <= 1.0  # Should be between 0 and 1

    def test_error_handling_invalid_data(self, compressor):
        """Test error handling with invalid compressed data."""
        # Try to decompress invalid data
        with pytest.raises(Exception):  # Should raise some kind of decompression error
            compressor.decompress_events(b"invalid compressed data")

    def test_error_handling_none_input(self, compressor):
        """Test error handling with None input."""
        with pytest.raises((TypeError, AttributeError)):
            compressor.compress_events(None)

    def test_different_event_types_compression(self, compressor):
        """Test compression with different event types."""
        base_time = time.time()
        mixed_events = []

        # Create events of different types
        event_types = [
            "SPELL_CAST_START",
            "SPELL_DAMAGE",
            "SPELL_HEAL",
            "UNIT_DIED",
            "SWING_DAMAGE",
        ]

        for i, event_type in enumerate(event_types * 20):  # Repeat to get more data
            if event_type == "SPELL_DAMAGE":
                event = SpellDamageEvent(
                    event_type=event_type,
                    timestamp=datetime.fromtimestamp(base_time + i * 0.1),
                    source_guid=f"Player-{i % 5}-567890AB",
                    source_name=f"Player{i % 5}",
                    source_flags=0x512,
                    source_raid_flags=0x0,
                    dest_guid="Creature-5678-CDEF1234",
                    dest_name="Target",
                    dest_flags=0x10A28,
                    dest_raid_flags=0x0,
                    spell_id=1234 + (i % 10),
                    spell_name=f"Spell {i % 10}",
                    spell_school=0x1,
                    amount=1000 + (i * 100),
                    overkill=0,
                    school=0x1,
                    resisted=0,
                    blocked=0,
                    absorbed=0,
                    critical=i % 5 == 0,
                    glancing=False,
                    crushing=False,
                    is_off_hand=False,
                )
            else:
                # Create a basic event for other types (simplified for testing)
                event = SpellCastStartEvent(
                    event_type=event_type,
                    timestamp=datetime.fromtimestamp(base_time + i * 0.1),
                    source_guid=f"Player-{i % 5}-567890AB",
                    source_name=f"Player{i % 5}",
                    source_flags=0x512,
                    source_raid_flags=0x0,
                    dest_guid="Creature-5678-CDEF1234",
                    dest_name="Target",
                    dest_flags=0x10A28,
                    dest_raid_flags=0x0,
                    spell_id=1234 + (i % 10),
                    spell_name=f"Spell {i % 10}",
                    spell_school=0x1,
                )

            timestamped_event = TimestampedEvent(
                timestamp=base_time + i * 0.1, sequence=i, event=event
            )
            mixed_events.append(timestamped_event)

        # Compress and decompress
        compressed_data = compressor.compress_events(mixed_events)
        decompressed_events = compressor.decompress_events(compressed_data)

        # Verify integrity
        assert len(decompressed_events) == len(mixed_events)

        # Check that different event types are preserved
        original_types = {e.event.event_type for e in mixed_events}
        decompressed_types = {e.event.event_type for e in decompressed_events}
        assert original_types == decompressed_types


class TestCompressionPerformance:
    """Test compression performance characteristics."""

    def test_compression_speed(self, compressor, sample_events):
        """Test compression and decompression speed."""
        # Multiply events to get more data
        large_event_list = sample_events * 100

        # Time compression
        start_time = time.time()
        compressed_data = compressor.compress_events(large_event_list)
        compression_time = time.time() - start_time

        # Time decompression
        start_time = time.time()
        decompressed_events = compressor.decompress_events(compressed_data)
        decompression_time = time.time() - start_time

        # Should complete reasonably quickly
        assert compression_time < 5.0  # Less than 5 seconds
        assert decompression_time < 5.0  # Less than 5 seconds

        # Verify correctness
        assert len(decompressed_events) == len(large_event_list)

    def test_memory_efficiency(self, compressor):
        """Test memory efficiency of compression."""
        # Create a large dataset
        base_time = time.time()
        large_event_list = []

        for i in range(5000):
            event = TimestampedEvent(
                timestamp=base_time + i * 0.1,
                sequence=i,
                event=SpellDamageEvent(
                    event_type="SPELL_DAMAGE",
                    timestamp=datetime.fromtimestamp(base_time + i * 0.1),
                    source_guid="Player-1234-567890AB",
                    source_name="Testplayer",
                    source_flags=0x512,
                    source_raid_flags=0x0,
                    dest_guid="Creature-5678-CDEF1234",
                    dest_name="Target",
                    dest_flags=0x10A28,
                    dest_raid_flags=0x0,
                    spell_id=1234,
                    spell_name="Test Spell",
                    spell_school=0x1,
                    amount=5000,
                    overkill=0,
                    school=0x1,
                    resisted=0,
                    blocked=0,
                    absorbed=0,
                    critical=False,
                    glancing=False,
                    crushing=False,
                    is_off_hand=False,
                ),
            )
            large_event_list.append(event)

        # Compress
        compressed_data = compressor.compress_events(large_event_list)

        # Should achieve significant compression
        uncompressed_estimate = compressor._estimate_uncompressed_size(large_event_list)
        compression_ratio = len(compressed_data) / uncompressed_estimate

        # Should compress to less than 30% for repetitive data
        assert compression_ratio < 0.3

    def test_incremental_compression_patterns(self, compressor):
        """Test compression efficiency with different data patterns."""
        base_time = time.time()

        # Test 1: Highly repetitive data (should compress very well)
        repetitive_events = []
        for i in range(1000):
            event = TimestampedEvent(
                timestamp=base_time + i * 0.1,
                sequence=i,
                event=SpellDamageEvent(
                    event_type="SPELL_DAMAGE",
                    timestamp=datetime.fromtimestamp(base_time + i * 0.1),
                    source_guid="Player-1234-567890AB",
                    source_name="Testplayer",
                    source_flags=0x512,
                    source_raid_flags=0x0,
                    dest_guid="Creature-5678-CDEF1234",
                    dest_name="Target",
                    dest_flags=0x10A28,
                    dest_raid_flags=0x0,
                    spell_id=1234,
                    spell_name="Test Spell",
                    spell_school=0x1,
                    amount=5000,  # Same amount every time
                    overkill=0,
                    school=0x1,
                    resisted=0,
                    blocked=0,
                    absorbed=0,
                    critical=False,
                    glancing=False,
                    crushing=False,
                    is_off_hand=False,
                ),
            )
            repetitive_events.append(event)

        # Test 2: Highly random data (should compress less well)
        import random

        random_events = []
        for i in range(1000):
            event = TimestampedEvent(
                timestamp=base_time + i * 0.1,
                sequence=i,
                event=SpellDamageEvent(
                    event_type="SPELL_DAMAGE",
                    timestamp=datetime.fromtimestamp(base_time + i * 0.1),
                    source_guid=f"Player-{random.randint(1000, 9999)}-567890AB",
                    source_name=f"Player{random.randint(1, 100)}",
                    source_flags=0x512,
                    source_raid_flags=0x0,
                    dest_guid=f"Creature-{random.randint(1000, 9999)}-CDEF1234",
                    dest_name=f"Target{random.randint(1, 100)}",
                    dest_flags=0x10A28,
                    dest_raid_flags=0x0,
                    spell_id=random.randint(1000, 9999),
                    spell_name=f"Spell {random.randint(1, 1000)}",
                    spell_school=random.choice([0x1, 0x2, 0x4, 0x8]),
                    amount=random.randint(1000, 10000),
                    overkill=random.randint(0, 1000),
                    school=random.choice([0x1, 0x2, 0x4, 0x8]),
                    resisted=random.randint(0, 500),
                    blocked=random.randint(0, 500),
                    absorbed=random.randint(0, 500),
                    critical=random.choice([True, False]),
                    glancing=random.choice([True, False]),
                    crushing=random.choice([True, False]),
                    is_off_hand=random.choice([True, False]),
                ),
            )
            random_events.append(event)

        # Compress both
        repetitive_compressed = compressor.compress_events(repetitive_events)
        random_compressed = compressor.compress_events(random_events)

        # Calculate ratios
        rep_uncompressed = compressor._estimate_uncompressed_size(repetitive_events)
        rand_uncompressed = compressor._estimate_uncompressed_size(random_events)

        rep_ratio = len(repetitive_compressed) / rep_uncompressed
        rand_ratio = len(random_compressed) / rand_uncompressed

        # Repetitive data should compress better than random data
        assert rep_ratio < rand_ratio

        # Both should still achieve some compression
        assert rep_ratio < 0.5
        assert rand_ratio < 0.9


class TestCompressionStats:
    """Test compression statistics functionality."""

    def test_compression_stats_collection(self, compressor, sample_events):
        """Test that compression statistics are collected properly."""
        # Reset stats
        compression_stats.clear()

        # Perform compression operations
        compressed_data = compressor.compress_events(sample_events)
        decompressed_events = compressor.decompress_events(compressed_data)

        # Check that stats were collected
        stats = compression_stats.get_stats()
        assert stats["total_compressions"] > 0
        assert stats["total_decompressions"] > 0
        assert stats["total_compressed_bytes"] > 0
        assert stats["total_uncompressed_bytes"] > 0

    def test_compression_stats_accuracy(self, compressor, sample_events):
        """Test that compression statistics are accurate."""
        # Reset stats
        compression_stats.clear()

        # Perform known operations
        compressed_data = compressor.compress_events(sample_events)

        stats = compression_stats.get_stats()
        assert stats["total_compressions"] == 1
        assert stats["total_compressed_bytes"] == len(compressed_data)

        # Decompress
        decompressed_events = compressor.decompress_events(compressed_data)

        stats = compression_stats.get_stats()
        assert stats["total_decompressions"] == 1


if __name__ == "__main__":
    pytest.main([__file__])
