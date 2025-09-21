#!/usr/bin/env python3
"""
Quick focused analysis of Nyloz's damage events.
"""

import sys
from pathlib import Path
from collections import defaultdict, Counter

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parser.tokenizer import LineTokenizer
from src.parser.events import EventFactory, DamageEvent
from src.config.loader import load_and_apply_config

# Load custom configuration
load_and_apply_config()

def quick_nyloz_analysis():
    """Quick analysis of Nyloz's damage in Ara-Kara."""

    log_path = Path("examples/WoWCombatLog-092025_160322.txt")

    print("🎯 QUICK NYLOZ ANALYSIS")
    print("=" * 50)

    tokenizer = LineTokenizer()
    event_factory = EventFactory()

    # Ara-Kara encounter boundaries from previous analysis
    encounter_start_str = "2025-09-20 17:32:12.928000"
    encounter_end_str = "2025-09-20 17:59:29.668000"

    from datetime import datetime
    encounter_start = datetime.fromisoformat(encounter_start_str)
    encounter_end = datetime.fromisoformat(encounter_end_str)

    print(f"📅 Encounter window: {encounter_start} to {encounter_end}")

    nyloz_events = []
    nyloz_pets = set()
    line_count = 0
    seen_swings = set()

    print(f"📊 Processing log file...")

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_count += 1

            if line_count % 250000 == 0:
                print(f"  Line {line_count:,}...")

            try:
                parsed = tokenizer.parse_line(line.strip())
                if parsed:
                    event = event_factory.create_event(parsed)
                    if event:
                        # Track Nyloz pet summons
                        if event.event_type == "SPELL_SUMMON":
                            if hasattr(event, "source_name") and event.source_name == "Nyloz":
                                pet_name = getattr(event, "dest_name", "")
                                if pet_name:
                                    nyloz_pets.add(pet_name)

                        # Track damage events within encounter window
                        if isinstance(event, DamageEvent) and encounter_start <= event.timestamp <= encounter_end:
                            source_name = getattr(event, "source_name", "")

                            # Check if it's Nyloz or Nyloz's pet
                            if source_name == "Nyloz" or source_name in nyloz_pets:
                                # Check for swing duplicates
                                is_duplicate = False
                                if event.event_type in ["SWING_DAMAGE", "SWING_DAMAGE_LANDED"]:
                                    swing_sig = f"{event.timestamp}_{event.source_guid}_{event.dest_guid}"
                                    if swing_sig in seen_swings:
                                        is_duplicate = True
                                    else:
                                        seen_swings.add(swing_sig)

                                if not is_duplicate:
                                    nyloz_events.append({
                                        "event_type": event.event_type,
                                        "damage": event.amount,
                                        "source_name": source_name,
                                        "spell_name": getattr(event, "spell_name", "Unknown"),
                                        "dest_name": getattr(event, "dest_name", "Unknown")
                                    })

            except Exception:
                pass

    print(f"✅ Processed {line_count:,} lines")
    print(f"🐾 Found {len(nyloz_pets)} Nyloz pets: {list(nyloz_pets)}")
    print(f"⚔️ Found {len(nyloz_events):,} Nyloz damage events")

    if not nyloz_events:
        print("❌ No Nyloz events found!")
        return

    # Calculate total damage
    total_damage = sum(e["damage"] for e in nyloz_events)
    game_value = 10.83e9

    print(f"\n📊 DAMAGE ANALYSIS:")
    print(f"   Calculated: {total_damage/1e9:.2f}B")
    print(f"   Game value: {game_value/1e9:.2f}B")
    print(f"   Difference: {(total_damage - game_value)/1e9:.2f}B ({(total_damage - game_value)/game_value*100:.1f}%)")

    # Event type breakdown
    event_types = Counter()
    damage_by_type = defaultdict(int)
    for event in nyloz_events:
        event_types[event["event_type"]] += 1
        damage_by_type[event["event_type"]] += event["damage"]

    print(f"\n📋 Event Types:")
    for event_type, count in event_types.most_common():
        damage = damage_by_type[event_type]
        print(f"   {event_type:<25}: {count:4,} events, {damage/1e9:5.2f}B ({damage/total_damage*100:4.1f}%)")

    # Source breakdown
    source_damage = defaultdict(int)
    source_counts = defaultdict(int)
    for event in nyloz_events:
        source = event["source_name"]
        source_damage[source] += event["damage"]
        source_counts[source] += 1

    print(f"\n👤 Source Breakdown:")
    for source, damage in sorted(source_damage.items(), key=lambda x: x[1], reverse=True):
        count = source_counts[source]
        print(f"   {source:<20}: {count:4,} events, {damage/1e9:5.2f}B ({damage/total_damage*100:4.1f}%)")

    # Top spells
    spell_damage = defaultdict(int)
    for event in nyloz_events:
        spell_damage[event["spell_name"]] += event["damage"]

    print(f"\n🔮 Top Spells:")
    for spell, damage in sorted(spell_damage.items(), key=lambda x: x[1], reverse=True)[:8]:
        print(f"   {spell:<25}: {damage/1e9:5.2f}B ({damage/total_damage*100:4.1f}%)")

    # Look for outliers
    high_damage_events = [e for e in nyloz_events if e["damage"] > 50e6]  # >50M
    if high_damage_events:
        print(f"\n⚠️ High damage events (>50M):")
        for event in sorted(high_damage_events, key=lambda x: x["damage"], reverse=True)[:5]:
            print(f"   {event['damage']/1e6:5.1f}M: {event['spell_name']} -> {event['dest_name']}")

if __name__ == "__main__":
    quick_nyloz_analysis()