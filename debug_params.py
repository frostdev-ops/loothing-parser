#!/usr/bin/env python3
"""Debug parameter positions."""

from src.parser.tokenizer import LineTokenizer

def debug_parameters():
    """Debug the parameter positions."""

    # Sample SPELL_DAMAGE line with ACL - damage should be 73712
    test_line = '9/15/2025 21:37:10.071-4  SPELL_DAMAGE,Player-64-0F629762,"Felbane-Duskwood-US",0x511,0x80000020,Creature-0-3886-2649-25903-206705-000148BF39,"Arathi Footman",0xa48,0x80000000,320334,"Infernal Armor",0x4,Creature-0-3886-2649-25903-206705-000148BF39,0000000000000000,300650464,300724176,0,0,42857,0,0,0,1,0,0,0,3007.57,1074.27,2308,4.8249,80,73712,36745,-1,4,0,0,0,1,nil,nil,ST'

    # Split manually to understand structure
    parts = test_line.split(',')
    print(f"Total parts: {len(parts)}")

    # Find where damage values should be
    for i, part in enumerate(parts):
        if part.strip() == '73712':
            print(f"Found 73712 at position {i}")
        if part.strip() == '36745':
            print(f"Found 36745 at position {i}")

    # Show last 15 parts
    print("\nLast 15 parts:")
    for i, part in enumerate(parts[-15:], len(parts)-15):
        print(f"  {i}: {part}")

    # Parse with tokenizer
    tokenizer = LineTokenizer()
    parsed = tokenizer.parse_line(test_line)

    if parsed:
        print(f"\nAfter base params (8): {len(parsed.base_params)}")
        print(f"After prefix params (3): {len(parsed.prefix_params)}")
        print(f"Suffix params: {parsed.suffix_params}")
        print(f"Expected damage (73712) at suffix index: ?")

if __name__ == "__main__":
    debug_parameters()