#!/usr/bin/env python3
"""
Debug script to analyze damage parsing issues.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parser.tokenizer import LineTokenizer
from src.parser.events import EventFactory

def analyze_damage_line():
    """Analyze a specific damage line to understand parsing."""

    # Real damage line from Mellow in the log
    line = '9/20/2025 16:52:36.249-4  SPELL_DAMAGE,Player-64-0F3A503D,"Mellow-Bloodhoof-US",0x512,0x80000000,Creature-0-4229-2773-25620-229250-0006CF13FF,"Venture Co. Contractor",0xa48,0x80000000,429951,"Blade Flurry",0x1,Creature-0-4229-2773-25620-229250-0006CF13FF,0000000000000000,272624269,273385615,0,0,42857,0,0,0,1,0,0,0,1821.40,-2771.31,2387,1.7075,80,442823,632603,-1,1,0,0,0,nil,nil,nil,AOE'

    print("Analyzing damage line:")
    print("-" * 80)
    print(f"Raw line: {line[:150]}...")
    print()

    # Tokenize the line
    tokenizer = LineTokenizer()
    parsed = tokenizer.parse_line(line)

    if not parsed:
        print("Failed to parse line!")
        return

    print(f"Timestamp: {parsed['timestamp']}")
    print(f"Event type: {parsed['event_type']}")
    print(f"Base params count: {len(parsed['base_params'])}")
    print(f"Prefix params count: {len(parsed.get('prefix_params', []))}")
    print(f"Suffix params count: {len(parsed.get('suffix_params', []))}")
    print()

    # Show the suffix params (where damage should be)
    if 'suffix_params' in parsed:
        print("Suffix parameters (damage info):")
        for i, param in enumerate(parsed['suffix_params'][:15]):  # First 15 params
            print(f"  [{i}]: {param}")
        print()

    # Create event using factory
    factory = EventFactory()
    event = factory.create_event(parsed)

    if event:
        print(f"Event created: {type(event).__name__}")
        if hasattr(event, 'amount'):
            print(f"Damage amount extracted: {event.amount:,}")
        if hasattr(event, 'overkill'):
            print(f"Overkill: {event.overkill}")
        if hasattr(event, 'absorbed'):
            print(f"Absorbed: {event.absorbed}")
        print()

    # Analyze the actual damage values in the line
    print("Manual analysis of damage parameters:")
    print("-" * 40)

    # After the ACL params (19 fields), we have damage params
    # From the line: 442823,632603,-1,1,0,0,0,nil,nil,nil,AOE
    suffix = parsed.get('suffix_params', [])
    if len(suffix) > 20:
        # ACL detected (19 ACL params before damage)
        damage_start = 19
        print(f"ACL detected, damage params start at index {damage_start}")
        print(f"  Pre-mitigation damage: {suffix[damage_start]} (index {damage_start})")
        print(f"  Actual damage: {suffix[damage_start + 1]} (index {damage_start + 1})")
        print(f"  Overkill: {suffix[damage_start + 2]} (index {damage_start + 2})")
        print(f"  School: {suffix[damage_start + 3]} (index {damage_start + 3})")
    else:
        print("Standard combat log format")
        if len(suffix) > 0:
            print(f"  Damage amount: {suffix[0]} (index 0)")
            if len(suffix) > 1:
                print(f"  Overkill: {suffix[1]} (index 1)")

    print()
    print("ISSUE IDENTIFIED:")
    print("-" * 40)
    print("The parser is extracting damage from the WRONG parameter index!")
    print(f"Should extract: 442823 (pre-mitigation/base damage)")
    print(f"Currently extracting: 632603 (appears to be something else)")
    print()
    print("The damage value 442823 is the actual damage dealt.")
    print("The value 632603 might be a damage cap or some other value.")

if __name__ == "__main__":
    analyze_damage_line()