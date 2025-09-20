#!/usr/bin/env python3
"""Analyze combat periods in logs to understand activity tracking."""

from datetime import datetime, timedelta
from src.parser.parser import CombatLogParser

def analyze_combat_periods(file_path: str, gap_threshold: float = 3.0):
    """
    Analyze combat periods by detecting event clusters.

    Args:
        file_path: Path to combat log
        gap_threshold: Seconds of inactivity to consider combat ended
    """
    parser = CombatLogParser()

    combat_events = []
    last_timestamp = None
    combat_periods = []
    current_period_start = None
    current_period_events = 0

    for event in parser.parse_file(file_path):
        # Only consider combat events
        if any(keyword in event.event_type for keyword in ["DAMAGE", "HEAL", "CAST_SUCCESS", "CAST_START", "AURA_APPLIED"]):
            combat_events.append(event.timestamp)

            if last_timestamp is None:
                # First combat event - start new period
                current_period_start = event.timestamp
                current_period_events = 1
            else:
                gap = (event.timestamp - last_timestamp).total_seconds()

                if gap > gap_threshold:
                    # Gap too large - end current period and start new
                    if current_period_start:
                        duration = (last_timestamp - current_period_start).total_seconds()
                        combat_periods.append({
                            'start': current_period_start,
                            'end': last_timestamp,
                            'duration': duration,
                            'events': current_period_events
                        })

                    # Start new period
                    current_period_start = event.timestamp
                    current_period_events = 1
                else:
                    # Continue current period
                    current_period_events += 1

            last_timestamp = event.timestamp

    # Close final period
    if current_period_start and last_timestamp:
        duration = (last_timestamp - current_period_start).total_seconds()
        combat_periods.append({
            'start': current_period_start,
            'end': last_timestamp,
            'duration': duration,
            'events': current_period_events
        })

    # Analyze results
    print(f"Combat Period Analysis (gap threshold: {gap_threshold}s)")
    print("=" * 60)
    print(f"Total combat periods detected: {len(combat_periods)}")

    if combat_periods:
        total_combat_time = sum(p['duration'] for p in combat_periods)
        total_time = (combat_periods[-1]['end'] - combat_periods[0]['start']).total_seconds()

        print(f"Total time span: {total_time:.1f}s ({total_time/60:.1f} min)")
        print(f"Time in combat: {total_combat_time:.1f}s ({total_combat_time/60:.1f} min)")
        print(f"Combat uptime: {(total_combat_time/total_time)*100:.1f}%")

        print(f"\nFirst 10 combat periods:")
        for i, period in enumerate(combat_periods[:10], 1):
            print(f"  {i}. {period['start'].strftime('%H:%M:%S')} - {period['end'].strftime('%H:%M:%S')} "
                  f"({period['duration']:.1f}s, {period['events']} events)")

        # Find gaps between combat
        if len(combat_periods) > 1:
            gaps = []
            for i in range(1, len(combat_periods)):
                gap = (combat_periods[i]['start'] - combat_periods[i-1]['end']).total_seconds()
                gaps.append(gap)

            print(f"\nGaps between combat periods:")
            print(f"  Average: {sum(gaps)/len(gaps):.1f}s")
            print(f"  Min: {min(gaps):.1f}s")
            print(f"  Max: {max(gaps):.1f}s")

if __name__ == "__main__":
    # Test with different gap thresholds
    for threshold in [2.0, 3.0, 5.0, 10.0]:
        print(f"\n{'='*80}")
        analyze_combat_periods("examples/WoWCombatLog-091525_213021.txt", threshold)
        print()
        if threshold == 3.0:
            break  # Just test 3s for now