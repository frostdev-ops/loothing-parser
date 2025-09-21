#!/usr/bin/env python3
"""
Quick test to verify SWING_DAMAGE_LANDED processing.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parser.tokenizer import LineTokenizer
from src.parser.events import EventFactory, DamageEvent
from src.config.loader import load_and_apply_config

# Load custom configuration
load_and_apply_config()

def test_swing_processing():
    """Test if SWING_DAMAGE_LANDED is being processed."""

    log_path = Path("examples/WoWCombatLog-092025_160322.txt")
    tokenizer = LineTokenizer()
    event_factory = EventFactory()

    swing_damage_processed = 0
    swing_damage_landed_processed = 0

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            if line_num > 10000:  # Test first 10k lines
                break

            try:
                parsed = tokenizer.parse_line(line.strip())
                if parsed:
                    event = event_factory.create_event(parsed)

                    if isinstance(event, DamageEvent):
                        if event.event_type == "SWING_DAMAGE":
                            swing_damage_processed += 1
                            if swing_damage_processed == 1:
                                print(f"First SWING_DAMAGE processed: {event.amount:,} damage")
                        elif event.event_type == "SWING_DAMAGE_LANDED":
                            swing_damage_landed_processed += 1
                            if swing_damage_landed_processed == 1:
                                print(f"First SWING_DAMAGE_LANDED processed: {event.amount:,} damage")

            except Exception:
                continue

    print(f"\nProcessing Summary:")
    print(f"SWING_DAMAGE events processed: {swing_damage_processed}")
    print(f"SWING_DAMAGE_LANDED events processed: {swing_damage_landed_processed}")

if __name__ == "__main__":
    test_swing_processing()