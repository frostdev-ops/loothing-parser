#!/usr/bin/env python3
"""Test ACL parameter parsing fix."""

from src.parser.tokenizer import LineTokenizer
from src.parser.events import EventFactory

def test_acl_parsing():
    """Test that ACL parameters are properly handled."""

    # Sample SPELL_DAMAGE line with ACL
    test_line = '9/15/2025 21:37:10.071-4  SPELL_DAMAGE,Player-64-0F629762,"Felbane-Duskwood-US",0x511,0x80000020,Creature-0-3886-2649-25903-206705-000148BF39,"Arathi Footman",0xa48,0x80000000,320334,"Infernal Armor",0x4,Creature-0-3886-2649-25903-206705-000148BF39,0000000000000000,300650464,300724176,0,0,42857,0,0,0,1,0,0,0,3007.57,1074.27,2308,4.8249,80,73712,36745,-1,4,0,0,0,1,nil,nil,ST'

    # Parse the line
    tokenizer = LineTokenizer()
    parsed = tokenizer.parse_line(test_line)

    if parsed:
        print(f"Event type: {parsed.event_type}")
        print(f"Base params count: {len(parsed.base_params)}")
        print(f"Prefix params count: {len(parsed.prefix_params)}")
        print(f"Suffix params count: {len(parsed.suffix_params)}")
        print(f"First few suffix params: {parsed.suffix_params[:5]}")

        # Create event from parsed line
        event = EventFactory.create_event(parsed)

        if hasattr(event, 'amount'):
            print(f"Damage amount: {event.amount}")
            print(f"Overkill: {event.overkill}")
            print(f"Success: Damage amount is {'non-zero' if event.amount > 0 else 'zero'}")
        else:
            print("Event doesn't have amount attribute")
    else:
        print("Failed to parse line")

if __name__ == "__main__":
    test_acl_parsing()