#!/usr/bin/env python3
"""Test ACL detection from log file."""

from src.parser.tokenizer import LineTokenizer
from src.parser.events import EventFactory

def test_acl_detection():
    """Test that ACL is properly detected from log file."""

    tokenizer = LineTokenizer()

    # First, parse the COMBAT_LOG_VERSION line to detect ACL
    version_line = '9/15/2025 21:30:21.462-4  COMBAT_LOG_VERSION,22,ADVANCED_LOG_ENABLED,1,BUILD_VERSION,11.2.0,PROJECT_ID,1'
    version_parsed = tokenizer.parse_line(version_line)
    print(f"ACL enabled after version line: {tokenizer.advanced_logging_enabled}")

    # Now test a damage line
    damage_line = '9/15/2025 21:37:10.071-4  SPELL_DAMAGE,Player-64-0F629762,"Felbane-Duskwood-US",0x511,0x80000020,Creature-0-3886-2649-25903-206705-000148BF39,"Arathi Footman",0xa48,0x80000000,320334,"Infernal Armor",0x4,Creature-0-3886-2649-25903-206705-000148BF39,0000000000000000,300650464,300724176,0,0,42857,0,0,0,1,0,0,0,3007.57,1074.27,2308,4.8249,80,73712,36745,-1,4,0,0,0,1,nil,nil,ST'

    damage_parsed = tokenizer.parse_line(damage_line)

    if damage_parsed:
        print(f"Event type: {damage_parsed.event_type}")
        print(f"Suffix params count: {len(damage_parsed.suffix_params)}")
        print(f"First few suffix params: {damage_parsed.suffix_params[:5]}")

        # Create event
        event = EventFactory.create_event(damage_parsed)

        if hasattr(event, 'amount'):
            print(f"Damage amount: {event.amount}")
            print(f"Overkill: {event.overkill}")
            print(f"Success: Damage amount is {'non-zero' if event.amount > 0 else 'zero'}")
        else:
            print("Event doesn't have amount attribute")
    else:
        print("Failed to parse damage line")

if __name__ == "__main__":
    test_acl_detection()