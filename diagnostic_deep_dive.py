#!/usr/bin/env python3
"""
Comprehensive diagnostic script to identify and resolve ALL remaining damage calculation issues.
"""

import sys
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parser.tokenizer import LineTokenizer
from src.parser.events import EventFactory, DamageEvent
from src.segmentation.unified_segmenter import UnifiedSegmenter
from src.config.loader import load_and_apply_config

# Load custom configuration
load_and_apply_config()

# Game reference values for Ara-Kara
GAME_VALUES = {
    "Mellow": 12.25e9,      # Nootlay in game
    "Felica": 11.15e9,
    "Nyloz": 10.83e9,
    "Ivanovich": 6.55e9,
    "Nootloops": 1.08e9,
}

def analyze_damage_discrepancies():
    """Comprehensive analysis of damage calculation discrepancies."""

    log_path = Path("examples/WoWCombatLog-092025_160322.txt")
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        return

    print("🔍 COMPREHENSIVE DAMAGE DISCREPANCY ANALYSIS")
    print("=" * 80)

    tokenizer = LineTokenizer()
    event_factory = EventFactory()
    segmenter = UnifiedSegmenter()

    # Diagnostic tracking
    character_events = defaultdict(list)
    character_event_types = defaultdict(Counter)
    duplicate_events = defaultdict(list)
    pet_mappings = {}
    encounter_boundaries = []
    line_count = 0
    events_processed = 0

    # Track swing deduplication like the categorizer does
    seen_swings = set()
    swing_duplicates_found = defaultdict(int)

    print("📊 Phase 1: Parsing log and tracking all events...")

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

                        # Track encounter boundaries
                        if event.event_type in ["ENCOUNTER_START", "ENCOUNTER_END", "CHALLENGE_MODE_START", "CHALLENGE_MODE_END"]:
                            encounter_boundaries.append({
                                "timestamp": event.timestamp,
                                "type": event.event_type,
                                "line": line_count
                            })

                        # Track pet summons
                        if event.event_type == "SPELL_SUMMON":
                            if event.source_guid and event.dest_guid:
                                pet_mappings[event.dest_guid] = {
                                    "owner_guid": event.source_guid,
                                    "owner_name": getattr(event, "source_name", "Unknown"),
                                    "pet_name": getattr(event, "dest_name", "Unknown")
                                }

                        # Track damage events with detailed analysis
                        if isinstance(event, DamageEvent):
                            # Resolve pet ownership
                            source_guid = event.source_guid
                            source_name = getattr(event, "source_name", "Unknown")

                            if source_guid in pet_mappings:
                                source_guid = pet_mappings[source_guid]["owner_guid"]
                                source_name = pet_mappings[source_guid]["owner_name"]

                            # Check for swing duplicates
                            is_duplicate = False
                            if event.event_type in ["SWING_DAMAGE", "SWING_DAMAGE_LANDED"]:
                                swing_sig = f"{event.timestamp}_{event.source_guid}_{event.dest_guid}"
                                if swing_sig in seen_swings:
                                    is_duplicate = True
                                    swing_duplicates_found[source_name] += 1
                                    duplicate_events[source_name].append({
                                        "event_type": event.event_type,
                                        "damage": event.amount,
                                        "timestamp": event.timestamp,
                                        "line": line_count
                                    })
                                else:
                                    seen_swings.add(swing_sig)

                            # Track all damage events by character
                            character_events[source_name].append({
                                "event_type": event.event_type,
                                "damage": event.amount,
                                "timestamp": event.timestamp,
                                "line": line_count,
                                "is_duplicate": is_duplicate,
                                "source_guid": event.source_guid,
                                "original_source_name": getattr(event, "source_name", "Unknown")
                            })

                            character_event_types[source_name][event.event_type] += 1

                        # Process through segmenter
                        segmenter.process_event(event)

            except Exception as e:
                pass  # Ignore parse errors

    print(f"✅ Processed {line_count:,} lines, {events_processed:,} events")
    print(f"🎯 Found {len(encounter_boundaries)} encounter boundary events")
    print(f"🐾 Tracked {len(pet_mappings)} pet summons")

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

    print(f"\n🏟️ Ara-Kara Encounter Found:")
    print(f"   Duration: {arakara_encounter.duration:.1f}s")
    print(f"   Start: {arakara_encounter.start_time}")
    print(f"   End: {arakara_encounter.end_time}")

    # Analyze encounter timing boundaries
    encounter_start = arakara_encounter.start_time
    encounter_end = arakara_encounter.end_time

    print(f"\n📅 Phase 2: Analyzing timing boundaries...")
    events_outside_encounter = defaultdict(lambda: {"count": 0, "damage": 0})

    for char_name, events in character_events.items():
        for event in events:
            if event["timestamp"] < encounter_start or event["timestamp"] > encounter_end:
                events_outside_encounter[char_name]["count"] += 1
                events_outside_encounter[char_name]["damage"] += event["damage"]

    # Get parser results
    parser_results = {}
    for char_name, char_data in arakara_encounter.characters.items():
        parser_results[char_data.character_name] = char_data.total_damage_done

    print(f"\n📊 Phase 3: Damage discrepancy analysis...")
    print(f"{'Character':<12} {'Game Value':<12} {'Parser Value':<14} {'Difference':<12} {'% Diff':<8}")
    print("-" * 70)

    discrepancy_analysis = {}
    for char_name in GAME_VALUES:
        game_value = GAME_VALUES[char_name]
        parser_value = parser_results.get(char_name, 0)
        difference = parser_value - game_value
        pct_diff = (difference / game_value) * 100 if game_value > 0 else 0

        discrepancy_analysis[char_name] = {
            "game_value": game_value,
            "parser_value": parser_value,
            "difference": difference,
            "pct_diff": pct_diff
        }

        print(f"{char_name:<12} {game_value/1e9:<11.2f}B {parser_value/1e9:<13.2f}B {difference/1e9:<11.2f}B {pct_diff:<7.1f}%")

    # Detailed character analysis
    print(f"\n🔬 Phase 4: Character-specific analysis...")

    for char_name in GAME_VALUES:
        if char_name not in character_events:
            print(f"\n❌ {char_name}: No events found")
            continue

        char_events = character_events[char_name]
        total_damage = sum(e["damage"] for e in char_events if not e["is_duplicate"])
        duplicate_damage = sum(e["damage"] for e in char_events if e["is_duplicate"])

        print(f"\n👤 {char_name} Analysis:")
        print(f"   Total Events: {len(char_events):,}")
        print(f"   Duplicate Events: {len([e for e in char_events if e['is_duplicate']]):,}")
        print(f"   Non-duplicate Damage: {total_damage/1e9:.2f}B")
        print(f"   Duplicate Damage (excluded): {duplicate_damage/1e9:.2f}B")
        print(f"   Events Outside Encounter: {events_outside_encounter[char_name]['count']:,}")
        print(f"   Damage Outside Encounter: {events_outside_encounter[char_name]['damage']/1e9:.2f}B")

        # Event type breakdown
        print(f"   Event Type Breakdown:")
        for event_type, count in character_event_types[char_name].most_common(10):
            type_damage = sum(e["damage"] for e in char_events if e["event_type"] == event_type and not e["is_duplicate"])
            print(f"     {event_type}: {count:,} events, {type_damage/1e9:.2f}B damage")

    # Look for specific issues
    print(f"\n🔍 Phase 5: Specific issue detection...")

    # Check for pet attribution issues
    print(f"\n🐾 Pet Attribution Analysis:")
    pet_damage_by_owner = defaultdict(lambda: {"damage": 0, "events": 0})

    for char_name, events in character_events.items():
        for event in events:
            if event["source_guid"] != event.get("original_source_name", event["source_guid"]):
                # This was a pet event attributed to owner
                pet_damage_by_owner[char_name]["damage"] += event["damage"]
                pet_damage_by_owner[char_name]["events"] += 1

    for char_name, pet_data in pet_damage_by_owner.items():
        if pet_data["events"] > 0:
            print(f"   {char_name}: {pet_data['events']:,} pet events, {pet_data['damage']/1e9:.2f}B pet damage")

    # Check for swing duplication effectiveness
    print(f"\n⚔️ Swing Duplication Analysis:")
    for char_name, duplicate_count in swing_duplicates_found.items():
        if duplicate_count > 0:
            print(f"   {char_name}: {duplicate_count:,} swing duplicates found and excluded")

    # Final recommendations
    print(f"\n🎯 Phase 6: Issue identification and recommendations...")

    major_issues = []
    for char_name, analysis in discrepancy_analysis.items():
        if abs(analysis["pct_diff"]) > 5:  # >5% difference is significant
            major_issues.append({
                "character": char_name,
                "issue": f"{analysis['pct_diff']:.1f}% {'overcount' if analysis['pct_diff'] > 0 else 'undercount'}",
                "difference": analysis["difference"]
            })

    if major_issues:
        print(f"\n⚠️ MAJOR ISSUES DETECTED:")
        for issue in major_issues:
            print(f"   {issue['character']}: {issue['issue']} ({issue['difference']/1e9:.2f}B)")

            # Provide specific recommendations
            char_events = character_events.get(issue["character"], [])
            if char_events:
                # Look for patterns in the problematic character's events
                event_pattern_analysis = Counter()
                for event in char_events:
                    if not event["is_duplicate"]:
                        event_pattern_analysis[event["event_type"]] += 1

                print(f"     Top event types for {issue['character']}:")
                for event_type, count in event_pattern_analysis.most_common(5):
                    type_damage = sum(e["damage"] for e in char_events if e["event_type"] == event_type and not e["is_duplicate"])
                    print(f"       {event_type}: {count:,} events, {type_damage/1e9:.2f}B")
    else:
        print(f"\n✅ No major issues detected (all within 5%)")

    # Save detailed analysis
    analysis_output = {
        "summary": discrepancy_analysis,
        "encounter_info": {
            "duration": arakara_encounter.duration,
            "start_time": str(arakara_encounter.start_time),
            "end_time": str(arakara_encounter.end_time)
        },
        "character_event_counts": dict(character_event_types),
        "duplicate_analysis": dict(swing_duplicates_found),
        "pet_attribution": dict(pet_damage_by_owner),
        "major_issues": major_issues
    }

    with open("damage_analysis_detailed.json", "w") as f:
        json.dump(analysis_output, f, indent=2, default=str)

    print(f"\n💾 Detailed analysis saved to: damage_analysis_detailed.json")

    return major_issues

if __name__ == "__main__":
    analyze_damage_discrepancies()