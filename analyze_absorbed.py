#!/usr/bin/env python3
"""Analyze SPELL_ABSORBED event structure."""

log_file = "examples/WoWCombatLog-091925_190638.txt"

print("SPELL_ABSORBED Event Structure Analysis")
print("=" * 60)

with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
    count = 0
    for line in f:
        if 'SPELL_ABSORBED' in line and count < 10:
            parts = line.strip().split(',')

            # Extract timestamp and event type
            timestamp_event = parts[0].split('  ')
            event_type = timestamp_event[1] if len(timestamp_event) > 1 else ""

            print(f"\nEvent #{count + 1}:")
            print(f"Event type: {event_type}")

            if len(parts) >= 14:
                print(f"1. Attacker GUID: {parts[1]}")
                print(f"2. Attacker Name: {parts[2]}")
                print(f"3. Attacker Flags: {parts[3]}")
                print(f"4. Target GUID: {parts[5]}")
                print(f"5. Target Name: {parts[6]}")
                print(f"6. Target Flags: {parts[7]}")

                # The absorber info starts at position 9
                if event_type == "SPELL_ABSORBED":
                    print(f"--- ABSORBER INFO ---")
                    print(f"9. Absorber GUID: {parts[9]}")
                    print(f"10. Absorber Name: {parts[10]}")
                    print(f"11. Absorber Flags: {parts[11]}")
                    print(f"13. Spell ID: {parts[13]}")
                    print(f"14. Spell Name: {parts[14]}")
                    print(f"15. Spell School: {parts[15]}")

                    # Amount absorbed
                    if len(parts) > 16:
                        print(f"16. Amount Absorbed: {parts[16]}")
                    if len(parts) > 17:
                        print(f"17. Total Absorbed(?): {parts[17]}")

            count += 1
            if count >= 10:
                break

print(f"\nTotal SPELL_ABSORBED events analyzed: {count}")
print("\nStructure Summary:")
print("- Attacker (source) -> Target (dest)")
print("- Absorber (who cast the shield) info at positions 9-12")
print("- Spell info (shield spell) at positions 13-15")
print("- Amount absorbed at position 16")
print("- The ABSORBER should get credit for damage prevented!")