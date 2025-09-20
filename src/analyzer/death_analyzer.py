"""
Death analyzer for comprehensive death event analysis.
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import logging

from src.parser.events import BaseEvent, DamageEvent, HealEvent
from src.models.enhanced_character import EnhancedCharacter, EnhancedDeathEvent

logger = logging.getLogger(__name__)


class DeathAnalyzer:
    """
    Analyzes death events to provide insights into what killed players.

    This analyzer tracks recent damage and healing events to understand
    the circumstances around each death, helping identify dangerous
    mechanics and healing deficiencies.
    """

    def __init__(self, recent_event_window: float = 10.0):
        """
        Initialize the death analyzer.

        Args:
            recent_event_window: Time window (seconds) before death to consider events
        """
        self.recent_event_window = recent_event_window
        self.death_events: List[EnhancedDeathEvent] = []

    def analyze_character_death(
        self,
        character: EnhancedCharacter,
        death_time: datetime,
        killing_blow: Optional[DamageEvent] = None
    ) -> EnhancedDeathEvent:
        """
        Analyze a character's death and return detailed information.

        Args:
            character: The character that died
            death_time: Time of death
            killing_blow: Optional killing blow event

        Returns:
            EnhancedDeathEvent with full analysis
        """
        # Get recent events from character's deques
        recent_damage = list(character.recent_damage_taken)
        recent_healing = list(character.recent_healing_received)

        # Create enhanced death event
        death_event = EnhancedDeathEvent(
            timestamp=death_time.timestamp(),
            datetime=death_time,
            killing_blow=killing_blow,
            overkill=killing_blow.overkill if killing_blow else 0,
            recent_damage_taken=recent_damage,
            recent_healing_received=recent_healing
        )

        # Analyze death contributors
        death_event.analyze_death_contributors()

        # Additional analysis
        self._analyze_death_timing(death_event)
        self._analyze_preventability(death_event)

        self.death_events.append(death_event)
        return death_event

    def _analyze_death_timing(self, death_event: EnhancedDeathEvent):
        """Analyze the timing of damage leading to death."""
        if not death_event.recent_damage_taken:
            return

        # Calculate damage spikes
        damage_by_second = {}
        for event in death_event.recent_damage_taken:
            second = int(event.timestamp.timestamp())
            if second not in damage_by_second:
                damage_by_second[second] = 0
            damage_by_second[second] += event.amount

        # Find the highest spike
        if damage_by_second:
            max_spike = max(damage_by_second.values())
            death_event.damage_spike = max_spike

    def _analyze_preventability(self, death_event: EnhancedDeathEvent):
        """Analyze if the death could have been prevented."""
        total_recent_damage = sum(death_event.damage_sources.values())
        total_recent_healing = sum(death_event.healing_sources.values())

        # Check if healing was insufficient
        if total_recent_damage > 0:
            healing_coverage = (total_recent_healing / total_recent_damage) * 100
            death_event.healing_coverage = healing_coverage

            # Death is potentially preventable if healing coverage was low
            if healing_coverage < 50:
                death_event.preventable = "Low healing coverage"
            elif death_event.damage_spike and death_event.damage_spike > 100000:
                death_event.preventable = "One-shot mechanic"
            else:
                death_event.preventable = "Sustained damage"

    def get_death_summary(self, characters: Dict[str, EnhancedCharacter]) -> Dict[str, any]:
        """
        Get a summary of all deaths in an encounter.

        Args:
            characters: Dictionary of character streams

        Returns:
            Death summary statistics
        """
        total_deaths = sum(char.death_count for char in characters.values())

        # Group deaths by source
        death_sources = {}
        for char in characters.values():
            for death in char.enhanced_deaths:
                for source, damage in death.damage_sources.items():
                    if source not in death_sources:
                        death_sources[source] = {"count": 0, "total_damage": 0}
                    death_sources[source]["count"] += 1
                    death_sources[source]["total_damage"] += damage

        # Sort by frequency
        top_killers = sorted(
            death_sources.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )[:10]

        # Deaths over time
        death_timeline = []
        for char in characters.values():
            for death in char.enhanced_deaths:
                death_timeline.append({
                    "character": char.character_name,
                    "time": death.timestamp,
                    "killing_blow": death.killing_blow.spell_name if death.killing_blow and death.killing_blow.spell_name else "Melee"
                })

        death_timeline.sort(key=lambda x: x["time"])

        return {
            "total_deaths": total_deaths,
            "deaths_by_character": {
                char.character_name: char.death_count
                for char in characters.values()
                if char.death_count > 0
            },
            "top_death_causes": top_killers,
            "death_timeline": death_timeline,
            "average_deaths_per_player": total_deaths / len(characters) if characters else 0
        }

    def identify_wipe_mechanics(self, characters: Dict[str, EnhancedCharacter]) -> List[str]:
        """
        Identify mechanics that caused raid wipes.

        Args:
            characters: Dictionary of character streams

        Returns:
            List of identified wipe mechanics
        """
        wipe_mechanics = []

        # Look for multiple deaths within a short window
        death_windows = {}
        for char in characters.values():
            for death in char.enhanced_deaths:
                window = int(death.timestamp / 5)  # 5-second windows
                if window not in death_windows:
                    death_windows[window] = []
                death_windows[window].append(death)

        # Find windows with many deaths
        for window, deaths in death_windows.items():
            if len(deaths) >= len(characters) * 0.5:  # 50% of raid died
                # Find common damage source
                common_sources = {}
                for death in deaths:
                    for source in death.damage_sources:
                        common_sources[source] = common_sources.get(source, 0) + 1

                if common_sources:
                    most_common = max(common_sources.items(), key=lambda x: x[1])
                    wipe_mechanics.append(f"{most_common[0]} (killed {most_common[1]} players)")

        return wipe_mechanics

    def analyze_survival_issues(self, character: EnhancedCharacter) -> Dict[str, any]:
        """
        Analyze survival issues for a specific character.

        Args:
            character: Character to analyze

        Returns:
            Analysis of survival problems
        """
        if not character.enhanced_deaths:
            return {"deaths": 0, "issues": []}

        issues = []
        total_damage_taken = 0
        total_healing_received = 0

        for death in character.enhanced_deaths:
            total_damage_taken += sum(death.damage_sources.values())
            total_healing_received += sum(death.healing_sources.values())

            # Check for repeated death causes
            if death.damage_sources:
                top_source = max(death.damage_sources.items(), key=lambda x: x[1])
                issues.append({
                    "time": death.timestamp,
                    "cause": top_source[0],
                    "damage": top_source[1],
                    "preventable": getattr(death, "preventable", "Unknown")
                })

        # Calculate survival metrics
        avg_damage_per_death = total_damage_taken / len(character.enhanced_deaths)
        avg_healing_per_death = total_healing_received / len(character.enhanced_deaths)

        return {
            "deaths": character.death_count,
            "total_damage_leading_to_death": total_damage_taken,
            "total_healing_attempted": total_healing_received,
            "avg_damage_per_death": avg_damage_per_death,
            "avg_healing_per_death": avg_healing_per_death,
            "healing_deficit": avg_damage_per_death - avg_healing_per_death,
            "death_causes": issues
        }