"""
Unit tests for combat period detection.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from src.models.combat_periods import CombatPeriod, CombatPeriodDetector
from src.parser.events import BaseEvent


class TestCombatPeriod:
    """Test CombatPeriod dataclass functionality."""

    def test_duration_calculation(self):
        """Test duration property calculation."""
        start = datetime(2024, 1, 1, 10, 0, 0)
        end = datetime(2024, 1, 1, 10, 2, 30)  # 2.5 minutes
        period = CombatPeriod(start_time=start, end_time=end, event_count=10)

        assert period.duration == 150.0  # 2.5 minutes = 150 seconds

    def test_contains_time(self):
        """Test time containment checking."""
        start = datetime(2024, 1, 1, 10, 0, 0)
        end = datetime(2024, 1, 1, 10, 2, 0)
        period = CombatPeriod(start_time=start, end_time=end, event_count=5)

        # Test timestamp within period
        middle = datetime(2024, 1, 1, 10, 1, 0)
        assert period.contains_time(middle) is True

        # Test timestamp at boundaries
        assert period.contains_time(start) is True
        assert period.contains_time(end) is True

        # Test timestamp outside period
        before = datetime(2024, 1, 1, 9, 59, 59)
        after = datetime(2024, 1, 1, 10, 2, 1)
        assert period.contains_time(before) is False
        assert period.contains_time(after) is False

    def test_repr(self):
        """Test string representation."""
        start = datetime(2024, 1, 1, 10, 0, 0)
        end = datetime(2024, 1, 1, 10, 1, 30)
        period = CombatPeriod(start_time=start, end_time=end, event_count=15)

        repr_str = repr(period)
        assert "10:00:00" in repr_str
        assert "10:01:30" in repr_str
        assert "90.0s" in repr_str
        assert "15 events" in repr_str


class TestCombatPeriodDetector:
    """Test CombatPeriodDetector functionality."""

    def create_mock_event(self, timestamp: datetime, event_type: str) -> BaseEvent:
        """Create a mock combat event."""
        event = Mock(spec=BaseEvent)
        event.timestamp = timestamp
        event.event_type = event_type
        return event

    def test_empty_events(self):
        """Test detection with no events."""
        detector = CombatPeriodDetector()
        periods = detector.detect_periods([])
        assert periods == []

    def test_single_combat_event(self):
        """Test detection with single combat event."""
        detector = CombatPeriodDetector()
        start_time = datetime(2024, 1, 1, 10, 0, 0)
        events = [self.create_mock_event(start_time, "SPELL_DAMAGE")]

        periods = detector.detect_periods(events)
        assert len(periods) == 1
        assert periods[0].start_time == start_time
        assert periods[0].end_time == start_time
        assert periods[0].event_count == 1

    def test_continuous_combat(self):
        """Test detection with continuous combat (no gaps)."""
        detector = CombatPeriodDetector(gap_threshold=5.0)
        base_time = datetime(2024, 1, 1, 10, 0, 0)

        # Create events every 2 seconds (within gap threshold)
        events = []
        for i in range(5):
            event_time = base_time + timedelta(seconds=i * 2)
            events.append(self.create_mock_event(event_time, "SPELL_DAMAGE"))

        periods = detector.detect_periods(events)
        assert len(periods) == 1
        assert periods[0].start_time == base_time
        assert periods[0].end_time == base_time + timedelta(seconds=8)
        assert periods[0].event_count == 5
        assert periods[0].duration == 8.0

    def test_combat_with_gap(self):
        """Test detection with gap between combat periods."""
        detector = CombatPeriodDetector(gap_threshold=5.0)
        base_time = datetime(2024, 1, 1, 10, 0, 0)

        # First combat period
        events = [
            self.create_mock_event(base_time, "SPELL_DAMAGE"),
            self.create_mock_event(base_time + timedelta(seconds=2), "SPELL_HEAL"),
        ]

        # 10 second gap (exceeds threshold)
        # Second combat period
        events.extend([
            self.create_mock_event(base_time + timedelta(seconds=12), "SPELL_DAMAGE"),
            self.create_mock_event(base_time + timedelta(seconds=14), "SPELL_CAST_SUCCESS"),
        ])

        periods = detector.detect_periods(events)
        assert len(periods) == 2

        # First period
        assert periods[0].start_time == base_time
        assert periods[0].end_time == base_time + timedelta(seconds=2)
        assert periods[0].event_count == 2
        assert periods[0].duration == 2.0

        # Second period
        assert periods[1].start_time == base_time + timedelta(seconds=12)
        assert periods[1].end_time == base_time + timedelta(seconds=14)
        assert periods[1].event_count == 2
        assert periods[1].duration == 2.0

    def test_custom_gap_threshold(self):
        """Test detection with custom gap threshold."""
        detector = CombatPeriodDetector(gap_threshold=10.0)  # 10 second threshold
        base_time = datetime(2024, 1, 1, 10, 0, 0)

        events = [
            self.create_mock_event(base_time, "SPELL_DAMAGE"),
            self.create_mock_event(base_time + timedelta(seconds=8), "SPELL_DAMAGE"),  # 8s gap < 10s threshold
            self.create_mock_event(base_time + timedelta(seconds=20), "SPELL_DAMAGE"),  # 12s gap > 10s threshold
        ]

        periods = detector.detect_periods(events)
        assert len(periods) == 2

        # First period includes first two events
        assert periods[0].event_count == 2
        assert periods[0].duration == 8.0

        # Second period is single event
        assert periods[1].event_count == 1
        assert periods[1].duration == 0.0

    def test_is_combat_event(self):
        """Test combat event classification."""
        detector = CombatPeriodDetector()

        # Combat events
        combat_events = [
            "SPELL_DAMAGE", "SWING_DAMAGE", "SPELL_HEAL",
            "SPELL_CAST_SUCCESS", "SPELL_CAST_START",
            "SPELL_INTERRUPT", "SPELL_DISPEL",
            "SPELL_AURA_APPLIED", "SPELL_AURA_REMOVED",
            "UNIT_DIED", "SPELL_SUMMON"
        ]

        for event_type in combat_events:
            event = self.create_mock_event(datetime.now(), event_type)
            assert detector._is_combat_event(event) is True, f"{event_type} should be combat event"

        # Non-combat events
        non_combat_events = [
            "ENCOUNTER_START", "ENCOUNTER_END",
            "ZONE_CHANGE", "COMBATANT_INFO",
            "CHALLENGE_MODE_START", "CHALLENGE_MODE_END"
        ]

        for event_type in non_combat_events:
            event = self.create_mock_event(datetime.now(), event_type)
            assert detector._is_combat_event(event) is False, f"{event_type} should not be combat event"

    def test_non_combat_events_filtered(self):
        """Test that non-combat events are filtered out."""
        detector = CombatPeriodDetector()
        base_time = datetime(2024, 1, 1, 10, 0, 0)

        events = [
            self.create_mock_event(base_time, "ENCOUNTER_START"),  # Non-combat
            self.create_mock_event(base_time + timedelta(seconds=1), "SPELL_DAMAGE"),  # Combat
            self.create_mock_event(base_time + timedelta(seconds=2), "COMBATANT_INFO"),  # Non-combat
            self.create_mock_event(base_time + timedelta(seconds=3), "SPELL_HEAL"),  # Combat
            self.create_mock_event(base_time + timedelta(seconds=4), "ENCOUNTER_END"),  # Non-combat
        ]

        periods = detector.detect_periods(events)
        assert len(periods) == 1
        assert periods[0].event_count == 2  # Only 2 combat events
        assert periods[0].duration == 2.0  # From second 1 to second 3

    def test_calculate_total_combat_time(self):
        """Test total combat time calculation."""
        detector = CombatPeriodDetector()

        periods = [
            CombatPeriod(
                start_time=datetime(2024, 1, 1, 10, 0, 0),
                end_time=datetime(2024, 1, 1, 10, 1, 0),  # 60 seconds
                event_count=10
            ),
            CombatPeriod(
                start_time=datetime(2024, 1, 1, 10, 2, 0),
                end_time=datetime(2024, 1, 1, 10, 2, 30),  # 30 seconds
                event_count=5
            )
        ]

        total_time = detector.calculate_total_combat_time(periods)
        assert total_time == 90.0  # 60 + 30 seconds

    def test_get_combat_percentage(self):
        """Test combat percentage calculation."""
        detector = CombatPeriodDetector()

        periods = [
            CombatPeriod(
                start_time=datetime(2024, 1, 1, 10, 0, 0),
                end_time=datetime(2024, 1, 1, 10, 1, 0),  # 60 seconds
                event_count=10
            )
        ]

        # 60 seconds of combat out of 120 second encounter = 50%
        percentage = detector.get_combat_percentage(periods, 120.0)
        assert percentage == 50.0

        # Test edge case with zero duration
        percentage = detector.get_combat_percentage(periods, 0.0)
        assert percentage == 0.0

    def test_is_event_during_combat(self):
        """Test event combat period assignment."""
        detector = CombatPeriodDetector()

        periods = [
            CombatPeriod(
                start_time=datetime(2024, 1, 1, 10, 0, 0),
                end_time=datetime(2024, 1, 1, 10, 1, 0),
                event_count=10
            ),
            CombatPeriod(
                start_time=datetime(2024, 1, 1, 10, 2, 0),
                end_time=datetime(2024, 1, 1, 10, 3, 0),
                event_count=5
            )
        ]

        # Event during first period
        event_time = datetime(2024, 1, 1, 10, 0, 30)
        result = detector.is_event_during_combat(event_time, periods)
        assert result == 0

        # Event during second period
        event_time = datetime(2024, 1, 1, 10, 2, 30)
        result = detector.is_event_during_combat(event_time, periods)
        assert result == 1

        # Event outside any period
        event_time = datetime(2024, 1, 1, 10, 1, 30)
        result = detector.is_event_during_combat(event_time, periods)
        assert result is None

    def test_events_sorted_by_timestamp(self):
        """Test that events are properly sorted before processing."""
        detector = CombatPeriodDetector()
        base_time = datetime(2024, 1, 1, 10, 0, 0)

        # Create events in random order
        events = [
            self.create_mock_event(base_time + timedelta(seconds=5), "SPELL_DAMAGE"),
            self.create_mock_event(base_time + timedelta(seconds=1), "SPELL_HEAL"),
            self.create_mock_event(base_time + timedelta(seconds=3), "SPELL_CAST_SUCCESS"),
        ]

        periods = detector.detect_periods(events)
        assert len(periods) == 1
        assert periods[0].start_time == base_time + timedelta(seconds=1)  # Earliest event
        assert periods[0].end_time == base_time + timedelta(seconds=5)    # Latest event
        assert periods[0].duration == 4.0
        assert periods[0].event_count == 3


if __name__ == "__main__":
    pytest.main([__file__])