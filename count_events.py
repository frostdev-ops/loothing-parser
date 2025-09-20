#!/usr/bin/env python3
"""Count all event types in the log."""
from collections import Counter

log_file = "examples/WoWCombatLog-091925_190638.txt"
event_counts = Counter()

with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        if line.strip():
            # Extract event type after timestamp
            parts = line.split('  ', 1)
            if len(parts) > 1:
                event_part = parts[1].split(',')[0]
                event_counts[event_part] += 1

# Print sorted by count
for event, count in event_counts.most_common(50):
    print(f"{count:8} {event}")