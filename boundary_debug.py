#!/usr/bin/env python3
"""
Debug encounter boundary detection issues.
"""

import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parser.tokenizer import LineTokenizer
from src.parser.events import EventFactory, DamageEvent, ChallengeModeEvent, EncounterEvent
from src.segmentation.unified_segmenter import UnifiedSegmenter
from src.config.loader import load_and_apply_config

# Load custom configuration
load_and_apply_config()


def debug_encounter_boundaries():
    """Debug encounter boundary detection."""

    log_path = Path("examples/WoWCombatLog-092025_160322.txt")
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        return

    print("🔍 ENCOUNTER BOUNDARY DEBUG")
    print("=" * 60)

    tokenizer = LineTokenizer()
    event_factory = EventFactory()
    segmenter = UnifiedSegmenter()

    # Track boundary events
    boundary_events = []
    first_event_time = None
    last_event_time = None
    damage_events_by_minute = defaultdict(lambda: {"count": 0, "damage": 0})

    line_count = 0
    events_processed = 0

    print("📊 Phase 1: Finding all boundary events...")

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_count += 1

            if line_count % 100000 == 0:
                print(f"  Processing line {line_count:,}...")

            try:
                parsed = tokenizer.parse_line(line.strip())
                if parsed:
                    event = event_factory.create_event(parsed)
                    if event:
                        events_processed += 1

                        # Track first and last event times
                        if first_event_time is None:
                            first_event_time = event.timestamp
                        last_event_time = event.timestamp

                        # Track boundary events
                        if event.event_type in ["CHALLENGE_MODE_START", "CHALLENGE_MODE_END", "ENCOUNTER_START", "ENCOUNTER_END"]:
                            boundary_events.append({
                                "line": line_count,
                                "timestamp": event.timestamp,
                                "type": event.event_type,
                                "details": {
                                    "zone_name": getattr(event, "zone_name", None),
                                    "challenge_id": getattr(event, "challenge_id", None),
                                    "keystone_level": getattr(event, "keystone_level", None),
                                    "encounter_name": getattr(event, "encounter_name", None),
                                    "encounter_id": getattr(event, "encounter_id", None),
                                    "success": getattr(event, "success", None),
                                }
                            })

                        # Track damage events by minute for Mellow specifically
                        if isinstance(event, DamageEvent):
                            if getattr(event, "source_name", "") == "Mellow":
                                minute_bucket = event.timestamp.replace(second=0, microsecond=0)
                                damage_events_by_minute[minute_bucket]["count"] += 1
                                damage_events_by_minute[minute_bucket]["damage"] += event.amount

                        # Process through segmenter
                        segmenter.process_event(event)

            except Exception as e:
                pass  # Ignore parse errors

    print(f"✅ Processed {line_count:,} lines, {events_processed:,} events")
    print(f"📅 First event: {first_event_time}")
    print(f"📅 Last event: {last_event_time}")
    print(f"🎯 Found {len(boundary_events)} boundary events")

    print(f"\n📋 All Boundary Events:")
    for i, event in enumerate(boundary_events):
        print(f"  {i+1:2}. Line {event['line']:7,} | {event['timestamp']} | {event['type']}")
        if event["details"]["zone_name"]:
            print(f"      Zone: {event['details']['zone_name']}")
        if event["details"]["encounter_name"]:
            print(f"      Boss: {event['details']['encounter_name']}")
        if event["details"]["keystone_level"]:
            print(f"      Key Level: +{event['details']['keystone_level']}")
        if event["details"]["success"] is not None:
            print(f"      Success: {event['details']['success']}")

    # Get the Ara-Kara encounter from segmenter
    encounters = segmenter.get_encounters()
    arakara_encounter = None
    for encounter in encounters:
        if "Ara-Kara" in encounter.encounter_name:
            arakara_encounter = encounter
            break

    if arakara_encounter:
        print(f"\n🏟️ Segmenter Encounter Result:")
        print(f"   Name: {arakara_encounter.encounter_name}")
        print(f"   Start: {arakara_encounter.start_time}")
        print(f"   End: {arakara_encounter.end_time}")
        print(f"   Duration: {arakara_encounter.duration:.1f}s")
        print(f"   Characters: {len(arakara_encounter.characters)}")

        # Show character damage
        print(f"\n   Character Damage:")
        for char_name, char_data in arakara_encounter.characters.items():
            print(f"     {char_data.character_name}: {char_data.total_damage_done/1e9:.2f}B")

        # Analyze Mellow's damage timing
        encounter_start = arakara_encounter.start_time
        encounter_end = arakara_encounter.end_time

        print(f"\n📊 Mellow's Damage Distribution by Time:")
        print(f"   Encounter window: {encounter_start} to {encounter_end}")

        inside_damage = 0
        outside_damage = 0
        inside_count = 0
        outside_count = 0

        for minute_bucket, data in sorted(damage_events_by_minute.items()):
            is_inside = encounter_start <= minute_bucket <= encounter_end
            status = "INSIDE " if is_inside else "OUTSIDE"
            print(f"   {minute_bucket} | {status} | {data['count']:4,} events | {data['damage']/1e6:.1f}M damage")

            if is_inside:
                inside_damage += data["damage"]
                inside_count += data["count"]
            else:
                outside_damage += data["damage"]
                outside_count += data["count"]

        print(f"\n📈 Summary for Mellow:")
        print(f"   Inside encounter:  {inside_count:6,} events, {inside_damage/1e9:.2f}B damage")
        print(f"   Outside encounter: {outside_count:6,} events, {outside_damage/1e9:.2f}B damage")
        print(f"   Total:             {inside_count + outside_count:6,} events, {(inside_damage + outside_damage)/1e9:.2f}B damage")
        print(f"   Inside percentage: {inside_damage/(inside_damage + outside_damage)*100:.1f}%")


if __name__ == "__main__":
    debug_encounter_boundaries()