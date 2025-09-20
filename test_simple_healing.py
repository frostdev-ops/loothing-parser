#!/usr/bin/env python3
"""
Simple test to verify healing is calculated correctly.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.parser.parser import CombatLogParser
from src.parser.categorizer import EventCategorizer
from src.models.character_events import CharacterEventStream
from src.parser.events import HealEvent

def test_simple_healing():
    """Test healing calculation on a few events."""
    log_file = "examples/WoWCombatLog-091925_190638.txt"

    print(f"Testing healing calculation on: {log_file}")
    print("=" * 60)

    parser = CombatLogParser()
    categorizer = EventCategorizer()

    # Create a character stream manually
    character_guid = "Player-64-0E9A3428"  # Nootloops
    character_stream = CharacterEventStream(
        character_guid=character_guid,
        character_name="Nootloops-Duskwood-US"
    )

    categorizer.set_character_streams({character_guid: character_stream})

    healing_events_processed = 0
    absorbed_events_processed = 0

    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            if line.strip() and healing_events_processed < 50:
                try:
                    parsed_line = parser.tokenizer.parse_line(line)
                    event = parser.event_factory.create_event(parsed_line)

                    # Only process events for our test character
                    if (hasattr(event, 'source_guid') and event.source_guid == character_guid):

                        if "HEAL" in event.event_type:
                            if event.event_type == "SPELL_HEAL_ABSORBED":
                                absorbed_events_processed += 1
                                print(f"SPELL_HEAL_ABSORBED #{absorbed_events_processed}: {type(event)}")

                                # Test categorization
                                categories = categorizer.categorize_event(event)
                                print(f"  Categories: {categories}")

                            elif isinstance(event, HealEvent):
                                healing_events_processed += 1
                                print(f"Heal event #{healing_events_processed}: {event.event_type}")
                                print(f"  Amount: {event.amount}, Overheal: {event.overhealing}, Effective: {event.effective_healing}")

                                # Test categorization and routing
                                categories = categorizer.categorize_event(event)
                                print(f"  Categories: {categories}")

                                # Route the event
                                categorizer.route_event(event)

                except Exception as e:
                    continue

            if healing_events_processed >= 20:
                break

    print(f"\nProcessed {healing_events_processed} healing events")
    print(f"Processed {absorbed_events_processed} SPELL_HEAL_ABSORBED events")

    print(f"\nCharacter healing totals:")
    print(f"  Total healing done: {character_stream.total_healing_done}")
    print(f"  Total overhealing: {character_stream.total_overhealing}")
    print(f"  Healing events: {len(character_stream.healing_done)}")

if __name__ == "__main__":
    test_simple_healing()