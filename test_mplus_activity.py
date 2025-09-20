#!/usr/bin/env python3
"""Test M+ activity tracking issue."""

from src.parser.parser import CombatLogParser
from src.segmentation.encounters import EncounterSegmenter, FightType

def test_mplus_activity():
    """Test how M+ runs track participant activity."""

    parser = CombatLogParser()
    segmenter = EncounterSegmenter()

    # Process a file with M+ data
    event_count = 0
    for event in parser.parse_file("examples/WoWCombatLog-091525_213021.txt"):
        segmenter.process_event(event)
        event_count += 1
        if event_count > 5000:  # Process enough to get through M+ start
            break

    # Get all fights
    fights = segmenter.finalize()

    # Find M+ runs
    mplus_runs = [f for f in fights if f.fight_type == FightType.MYTHIC_PLUS]

    print(f"Total fights: {len(fights)}")
    print(f"M+ runs found: {len(mplus_runs)}")

    if mplus_runs:
        for i, run in enumerate(mplus_runs):
            print(f"\n--- M+ Run {i+1} ---")
            print(f"Dungeon: {run.encounter_name}")
            print(f"Keystone level: {run.keystone_level}")
            print(f"Duration: {run.get_duration_str()}")
            print(f"Events in run: {len(run.events)}")
            print(f"Participants: {len(run.participants)}")
            print(f"Player count: {run.get_player_count()}")

            # Show participant names
            if run.participants:
                print("Participant list:")
                for guid, info in list(run.participants.items())[:5]:
                    print(f"  - {info['name']} (Player: {info['is_player']})")
            else:
                print("  No participants tracked!")

            # Check if there are events in the run
            if run.events:
                print(f"First event type: {run.events[0].event_type}")
                print(f"Last event type: {run.events[-1].event_type}")

    # Also check trash fights during M+ time window
    if mplus_runs:
        mplus_run = mplus_runs[0]
        trash_during_mplus = []
        for fight in fights:
            if fight.fight_type == FightType.TRASH:
                if fight.start_time >= mplus_run.start_time and (mplus_run.end_time is None or fight.start_time <= mplus_run.end_time):
                    trash_during_mplus.append(fight)

        print(f"\nTrash fights during M+ time window: {len(trash_during_mplus)}")
        if trash_during_mplus:
            total_trash_events = sum(len(f.events) for f in trash_during_mplus)
            total_trash_participants = sum(len(f.participants) for f in trash_during_mplus)
            print(f"Total events in trash fights: {total_trash_events}")
            print(f"Total participants in trash fights: {total_trash_participants}")

if __name__ == "__main__":
    test_mplus_activity()