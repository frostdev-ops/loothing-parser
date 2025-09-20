#!/usr/bin/env python3
"""Test M+ DPS/HPS calculations after activity tracking fix."""

from src.parser.parser import CombatLogParser
from src.segmentation.encounters import EncounterSegmenter, FightType
from src.models.character_events import CharacterEventStream


def test_mplus_performance():
    """Test M+ DPS/HPS calculations."""

    parser = CombatLogParser()
    segmenter = EncounterSegmenter()

    # Process M+ data
    event_count = 0
    for event in parser.parse_file("examples/WoWCombatLog-091525_213021.txt"):
        segmenter.process_event(event)
        event_count += 1
        if event_count > 10000:  # Process more to get through the full M+
            break

    fights = segmenter.finalize()
    mplus_runs = [f for f in fights if f.fight_type == FightType.MYTHIC_PLUS]

    if mplus_runs:
        run = mplus_runs[0]
        print(f"=== M+ Performance Analysis ===")
        print(f"Dungeon: {run.encounter_name}")
        print(f"Keystone Level: {run.keystone_level}")
        print(f"Duration: {run.get_duration_str()}")
        print(f"Total Events: {len(run.events)}")
        print(f"Success: {run.success}")

        # Create character streams for players
        characters = {}
        for guid, participant in run.participants.items():
            if participant.get("is_player", False):
                characters[guid] = CharacterEventStream(
                    character_guid=guid, character_name=participant["name"]
                )

        # Add events to character streams
        damage_events = 0
        heal_events = 0

        for event in run.events:
            # Track damage done
            if hasattr(event, "amount") and "DAMAGE" in event.event_type:
                damage_events += 1
                if hasattr(event, "source_guid") and event.source_guid in characters:
                    characters[event.source_guid].total_damage_done += event.amount

            # Track healing done
            elif hasattr(event, "amount") and "HEAL" in event.event_type:
                heal_events += 1
                if hasattr(event, "source_guid") and event.source_guid in characters:
                    characters[event.source_guid].total_healing_done += event.amount

        print(f"\nEvent Breakdown:")
        print(f"  Damage Events: {damage_events}")
        print(f"  Healing Events: {heal_events}")

        # Calculate and display performance metrics
        print(f"\n=== Player Performance ===")
        for guid, char in characters.items():
            dps = char.get_dps()
            hps = char.get_hps()
            total_damage = char.total_damage
            total_healing = char.total_healing

            print(f"{char.player_name}:")
            print(f"  DPS: {dps:,.0f}")
            print(f"  HPS: {hps:,.0f}")
            print(f"  Total Damage: {total_damage:,}")
            print(f"  Total Healing: {total_healing:,}")
            print(f"  Events: {len(char.events)}")
            print()

        # Overall run metrics
        total_run_damage = sum(char.total_damage for char in characters.values())
        total_run_healing = sum(char.total_healing for char in characters.values())

        print(f"=== Run Totals ===")
        print(f"Total Damage Done: {total_run_damage:,}")
        print(f"Total Healing Done: {total_run_healing:,}")
        print(f"Average Group DPS: {total_run_damage/max(run.duration or 1, 1):,.0f}")
        print(f"Average Group HPS: {total_run_healing/max(run.duration or 1, 1):,.0f}")


if __name__ == "__main__":
    test_mplus_performance()
