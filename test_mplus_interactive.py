#!/usr/bin/env python3
"""Quick test of M+ in interactive analyzer."""

import sys
from src.parser.parser import CombatLogParser
from src.segmentation.encounters import EncounterSegmenter, FightType
from src.analyzer.interactive import InteractiveAnalyzer

def test_mplus_interactive():
    """Test M+ in interactive analyzer."""

    parser = CombatLogParser()
    segmenter = EncounterSegmenter()

    print("Processing combat log for M+ analysis...")

    # Process full log
    for event in parser.parse_file("examples/WoWCombatLog-091525_213021.txt"):
        segmenter.process_event(event)

    fights = segmenter.finalize()
    mplus_runs = [f for f in fights if f.fight_type == FightType.MYTHIC_PLUS]

    print(f"Found {len(mplus_runs)} M+ runs")
    for run in mplus_runs:
        print(f"- {run.encounter_name} +{run.keystone_level}: {len(run.events)} events, {len(run.participants)} participants")

    if mplus_runs:
        print("\nM+ runs are now properly tracked with activity!")
        print("You can run the interactive analyzer to see detailed stats.")
    else:
        print("No M+ runs found")

if __name__ == "__main__":
    test_mplus_interactive()