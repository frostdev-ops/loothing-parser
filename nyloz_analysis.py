#!/usr/bin/env python3
"""
Focused analysis of Nyloz's damage events to identify the 9.2% overcount issue.
"""

import sys
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parser.tokenizer import LineTokenizer
from src.parser.events import EventFactory, DamageEvent
from src.segmentation.unified_segmenter import UnifiedSegmenter
from src.config.loader import load_and_apply_config

# Load custom configuration
load_and_apply_config()

# Game reference value for Nyloz
NYLOZ_GAME_VALUE = 10.83e9


def analyze_nyloz_damage():
    """Focused analysis of Nyloz's damage to identify the overcount source."""

    log_path = Path("examples/WoWCombatLog-092025_160322.txt")
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        return

    print("🎯 FOCUSED NYLOZ DAMAGE ANALYSIS")
    print("=" * 60)

    tokenizer = LineTokenizer()
    event_factory = EventFactory()
    segmenter = UnifiedSegmenter()

    # Get encounter boundaries first
    print("📊 Phase 1: Getting encounter boundaries...")

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            try:
                parsed = tokenizer.parse_line(line.strip())
                if parsed:
                    event = event_factory.create_event(parsed)
                    if event:
                        segmenter.process_event(event)
            except Exception:
                pass

    # Get the Ara-Kara encounter
    encounters = segmenter.get_encounters()
    arakara_encounter = None
    for encounter in encounters:
        if "Ara-Kara" in encounter.encounter_name:
            arakara_encounter = encounter
            break

    if not arakara_encounter:
        print("❌ Ara-Kara encounter not found!")
        return

    encounter_start = arakara_encounter.start_time
    encounter_end = arakara_encounter.end_time

    print(f"✅ Ara-Kara encounter found:")
    print(f"   Start: {encounter_start}")
    print(f"   End: {encounter_end}")
    print(f"   Duration: {arakara_encounter.duration:.1f}s")

    # Get Nyloz's total damage from segmenter
    nyloz_segmenter_damage = 0
    for char_name, char_data in arakara_encounter.characters.items():
        if char_data.character_name == "Nyloz":
            nyloz_segmenter_damage = char_data.total_damage_done
            break

    print(f"   Nyloz damage (segmenter): {nyloz_segmenter_damage/1e9:.2f}B")
    print(f"   Nyloz damage (game): {NYLOZ_GAME_VALUE/1e9:.2f}B")
    print(f"   Difference: {(nyloz_segmenter_damage - NYLOZ_GAME_VALUE)/1e9:.2f}B ({(nyloz_segmenter_damage - NYLOZ_GAME_VALUE)/NYLOZ_GAME_VALUE*100:.1f}%)")

    # Now analyze Nyloz's events in detail
    print(f"\n📊 Phase 2: Analyzing Nyloz's events...")

    nyloz_events = []
    nyloz_pets = {}
    line_count = 0
    seen_swings = set()
    duplicate_events = []

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_count += 1

            if line_count % 200000 == 0:
                print(f"  Processing line {line_count:,}...")

            try:
                parsed = tokenizer.parse_line(line.strip())
                if parsed:
                    event = event_factory.create_event(parsed)
                    if event:
                        # Track pet summons for Nyloz
                        if event.event_type == "SPELL_SUMMON":
                            if hasattr(event, "source_name") and event.source_name == "Nyloz":
                                nyloz_pets[event.dest_guid] = {
                                    "pet_name": getattr(event, "dest_name", "Unknown"),
                                    "summoned_at": event.timestamp
                                }

                        # Track damage events by Nyloz or Nyloz's pets
                        if isinstance(event, DamageEvent):
                            is_nyloz_damage = False
                            source_type = "unknown"

                            # Check if it's Nyloz directly
                            if hasattr(event, "source_name") and event.source_name == "Nyloz":
                                is_nyloz_damage = True
                                source_type = "player"
                            # Check if it's Nyloz's pet
                            elif event.source_guid in nyloz_pets:
                                is_nyloz_damage = True
                                source_type = "pet"

                            if is_nyloz_damage:
                                # Check if within encounter window
                                if encounter_start <= event.timestamp <= encounter_end:
                                    # Check for swing duplicates
                                    is_duplicate = False
                                    if event.event_type in ["SWING_DAMAGE", "SWING_DAMAGE_LANDED"]:
                                        swing_sig = f"{event.timestamp}_{event.source_guid}_{event.dest_guid}"
                                        if swing_sig in seen_swings:
                                            is_duplicate = True
                                            duplicate_events.append({
                                                "event_type": event.event_type,
                                                "damage": event.amount,
                                                "timestamp": event.timestamp,
                                                "source_type": source_type
                                            })
                                        else:
                                            seen_swings.add(swing_sig)

                                    nyloz_events.append({
                                        "event_type": event.event_type,
                                        "damage": event.amount,
                                        "timestamp": event.timestamp,
                                        "source_type": source_type,
                                        "source_name": getattr(event, "source_name", "Unknown"),
                                        "dest_name": getattr(event, "dest_name", "Unknown"),
                                        "spell_name": getattr(event, "spell_name", "Unknown"),
                                        "is_duplicate": is_duplicate,
                                        "line": line_count
                                    })

            except Exception:
                pass

    print(f"✅ Found {len(nyloz_events):,} Nyloz damage events in encounter")
    print(f"🐾 Found {len(nyloz_pets)} pets summoned by Nyloz")
    print(f"⚔️ Found {len(duplicate_events)} duplicate swing events")

    # Analyze events by type
    print(f"\n📊 Phase 3: Event analysis...")

    non_duplicate_events = [e for e in nyloz_events if not e["is_duplicate"]]
    total_damage = sum(e["damage"] for e in non_duplicate_events)
    duplicate_damage = sum(e["damage"] for e in nyloz_events if e["is_duplicate"])

    print(f"📈 Damage Summary:")
    print(f"   Total events (non-duplicate): {len(non_duplicate_events):,}")
    print(f"   Total damage (non-duplicate): {total_damage/1e9:.2f}B")
    print(f"   Duplicate events: {len([e for e in nyloz_events if e['is_duplicate']]):,}")
    print(f"   Duplicate damage (excluded): {duplicate_damage/1e9:.2f}B")

    # Event type breakdown
    event_types = Counter()
    damage_by_type = defaultdict(int)
    for event in non_duplicate_events:
        event_types[event["event_type"]] += 1
        damage_by_type[event["event_type"]] += event["damage"]

    print(f"\n📊 Event Type Breakdown:")
    for event_type, count in event_types.most_common():
        damage = damage_by_type[event_type]
        print(f"   {event_type:<25}: {count:5,} events, {damage/1e9:6.2f}B damage ({damage/total_damage*100:5.1f}%)")

    # Source type breakdown
    source_types = Counter()
    damage_by_source = defaultdict(int)
    for event in non_duplicate_events:
        source_types[event["source_type"]] += 1
        damage_by_source[event["source_type"]] += event["damage"]

    print(f"\n👤 Source Type Breakdown:")
    for source_type, count in source_types.most_common():
        damage = damage_by_source[source_type]
        print(f"   {source_type:<10}: {count:5,} events, {damage/1e9:6.2f}B damage ({damage/total_damage*100:5.1f}%)")

    # Pet breakdown
    if nyloz_pets:
        print(f"\n🐾 Pet Breakdown:")
        for pet_guid, pet_info in nyloz_pets.items():
            pet_events = [e for e in non_duplicate_events if e.get("source_name") == pet_info["pet_name"]]
            if pet_events:
                pet_damage = sum(e["damage"] for e in pet_events)
                print(f"   {pet_info['pet_name']:<20}: {len(pet_events):4,} events, {pet_damage/1e9:6.2f}B damage")

    # Top damage spells
    spell_damage = defaultdict(int)
    spell_counts = defaultdict(int)
    for event in non_duplicate_events:
        spell_name = event["spell_name"]
        spell_damage[spell_name] += event["damage"]
        spell_counts[spell_name] += 1

    print(f"\n🔮 Top Damage Spells:")
    for spell_name, damage in sorted(spell_damage.items(), key=lambda x: x[1], reverse=True)[:10]:
        count = spell_counts[spell_name]
        print(f"   {spell_name:<30}: {count:4,} casts, {damage/1e9:6.2f}B damage ({damage/total_damage*100:5.1f}%)")

    # Look for potential issues
    print(f"\n🔍 Phase 4: Issue detection...")

    potential_issues = []

    # Check for unusual event types
    unusual_events = [et for et in event_types if et not in ["SPELL_DAMAGE", "SPELL_PERIODIC_DAMAGE", "SWING_DAMAGE", "SWING_DAMAGE_LANDED", "RANGE_DAMAGE"]]
    if unusual_events:
        potential_issues.append(f"Unusual event types found: {unusual_events}")

    # Check for high-damage single events
    high_damage_events = [e for e in non_duplicate_events if e["damage"] > 100e6]  # >100M damage
    if high_damage_events:
        potential_issues.append(f"Found {len(high_damage_events)} very high damage events (>100M)")
        for event in sorted(high_damage_events, key=lambda x: x["damage"], reverse=True)[:5]:
            print(f"     High damage: {event['damage']/1e6:.1f}M from {event['spell_name']} ({event['event_type']})")

    # Check for timing anomalies
    events_by_second = defaultdict(lambda: {"count": 0, "damage": 0})
    for event in non_duplicate_events:
        second = event["timestamp"].replace(microsecond=0)
        events_by_second[second]["count"] += 1
        events_by_second[second]["damage"] += event["damage"]

    high_activity_seconds = [(sec, data) for sec, data in events_by_second.items() if data["count"] > 50]
    if high_activity_seconds:
        potential_issues.append(f"Found {len(high_activity_seconds)} seconds with >50 events")

    if potential_issues:
        print(f"\n⚠️ Potential Issues:")
        for issue in potential_issues:
            print(f"   • {issue}")
    else:
        print(f"\n✅ No obvious issues detected")

    # Compare to game value
    difference = total_damage - NYLOZ_GAME_VALUE
    print(f"\n🎯 Final Analysis:")
    print(f"   Calculated damage: {total_damage/1e9:.2f}B")
    print(f"   Game damage: {NYLOZ_GAME_VALUE/1e9:.2f}B")
    print(f"   Difference: {difference/1e9:.2f}B ({difference/NYLOZ_GAME_VALUE*100:.1f}%)")
    print(f"   Extra damage per second: {difference/arakara_encounter.duration/1e6:.1f}M DPS")

    if abs(difference/NYLOZ_GAME_VALUE) < 0.05:  # Within 5%
        print(f"   ✅ Difference is within acceptable range (<5%)")
    else:
        print(f"   ⚠️ Difference exceeds acceptable range (>5%)")

    return {
        "calculated_damage": total_damage,
        "game_damage": NYLOZ_GAME_VALUE,
        "difference": difference,
        "events_analyzed": len(non_duplicate_events),
        "duplicate_events": len([e for e in nyloz_events if e["is_duplicate"]]),
        "event_types": dict(event_types),
        "potential_issues": potential_issues
    }


if __name__ == "__main__":
    analyze_nyloz_damage()