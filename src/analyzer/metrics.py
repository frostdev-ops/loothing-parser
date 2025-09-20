"""
Metric calculation helpers for the interactive analyzer.
"""

from typing import List, Dict, Any, Optional, Tuple
from ..segmentation.encounters import Fight, FightType
from ..models.character_events import CharacterEventStream


class MetricsCalculator:
    """Calculates various performance metrics for encounters and players."""

    @staticmethod
    def calculate_encounter_metrics(
        fight: Fight, characters: Dict[str, CharacterEventStream]
    ) -> Dict[str, Any]:
        """Calculate comprehensive metrics for a single encounter."""
        if not characters or not fight.duration:
            return {}

        metrics = {
            "total_damage": sum(char.total_damage_done for char in characters.values()),
            "total_healing": sum(char.total_healing_done for char in characters.values()),
            "total_overhealing": sum(char.total_overhealing for char in characters.values()),
            "total_deaths": sum(char.death_count for char in characters.values()),
            "raid_dps": 0,
            "raid_hps": 0,
            "player_count": len(characters),
            "activity_avg": 0,
        }

        # Calculate raid-wide DPS/HPS using combat duration if available
        duration_for_metrics = fight.combat_duration if fight.combat_duration and fight.combat_duration > 0 else fight.duration
        if duration_for_metrics and duration_for_metrics > 0:
            metrics["raid_dps"] = metrics["total_damage"] / duration_for_metrics
            metrics["raid_hps"] = metrics["total_healing"] / duration_for_metrics
            metrics["combat_duration"] = fight.combat_duration
            metrics["combat_percentage"] = (fight.combat_duration / fight.duration * 100) if fight.duration and fight.combat_duration else 0

        # Calculate average activity
        active_chars = [char for char in characters.values() if char.activity_percentage > 0]
        if active_chars:
            metrics["activity_avg"] = sum(char.activity_percentage for char in active_chars) / len(
                active_chars
            )

        return metrics

    @staticmethod
    def get_dps_rankings(
        characters: Dict[str, CharacterEventStream], duration: float, use_combat_time: bool = True
    ) -> List[Tuple[str, float, CharacterEventStream]]:
        """Get DPS rankings for characters."""
        rankings = []
        for char in characters.values():
            if char.total_damage_done > 0:
                if use_combat_time and char.combat_time > 0:
                    dps = char.get_combat_dps()
                else:
                    dps = char.get_dps(duration) if duration > 0 else 0
                rankings.append((char.character_name, dps, char))

        return sorted(rankings, key=lambda x: x[1], reverse=True)

    @staticmethod
    def get_hps_rankings(
        characters: Dict[str, CharacterEventStream], duration: float, use_combat_time: bool = True
    ) -> List[Tuple[str, float, CharacterEventStream]]:
        """Get HPS rankings for characters."""
        rankings = []
        for char in characters.values():
            if char.total_healing_done > 0:
                if use_combat_time and char.combat_time > 0:
                    hps = char.get_combat_hps()
                else:
                    hps = char.get_hps(duration) if duration > 0 else 0
                rankings.append((char.character_name, hps, char))

        return sorted(rankings, key=lambda x: x[1], reverse=True)

    @staticmethod
    def get_survival_stats(characters: Dict[str, CharacterEventStream]) -> Dict[str, Any]:
        """Calculate survival statistics."""
        total_deaths = sum(char.death_count for char in characters.values())
        total_players = len(characters)

        deaths_by_player = [
            (char.character_name, char.death_count)
            for char in characters.values()
            if char.death_count > 0
        ]
        deaths_by_player.sort(key=lambda x: x[1], reverse=True)

        return {
            "total_deaths": total_deaths,
            "death_rate": total_deaths / total_players if total_players > 0 else 0,
            "players_died": len(deaths_by_player),
            "survival_rate": (
                (total_players - len(deaths_by_player)) / total_players if total_players > 0 else 0
            ),
            "deaths_by_player": deaths_by_player[:10],  # Top 10 deaths
        }

    @staticmethod
    def analyze_performance_trends(fights: List[Fight]) -> Dict[str, Any]:
        """Analyze performance trends across multiple fights."""
        if not fights:
            return {}

        successful_fights = [f for f in fights if f.success is True]
        failed_fights = [f for f in fights if f.success is False]

        trends = {
            "total_encounters": len(fights),
            "success_rate": len(successful_fights) / len(fights) if fights else 0,
            "avg_duration_success": 0,
            "avg_duration_wipe": 0,
            "encounter_types": {},
            "difficulty_distribution": {},
        }

        # Calculate average durations
        if successful_fights:
            valid_success = [f for f in successful_fights if f.duration]
            if valid_success:
                trends["avg_duration_success"] = sum(f.duration for f in valid_success) / len(
                    valid_success
                )

        if failed_fights:
            valid_failed = [f for f in failed_fights if f.duration]
            if valid_failed:
                trends["avg_duration_wipe"] = sum(f.duration for f in valid_failed) / len(
                    valid_failed
                )

        # Count encounter types
        for fight in fights:
            fight_type = fight.fight_type.value
            trends["encounter_types"][fight_type] = trends["encounter_types"].get(fight_type, 0) + 1

        # Count difficulties (for raid encounters)
        for fight in fights:
            if fight.difficulty:
                diff = str(fight.difficulty)
                trends["difficulty_distribution"][diff] = (
                    trends["difficulty_distribution"].get(diff, 0) + 1
                )

        return trends

    @staticmethod
    def calculate_fight_efficiency(
        fight: Fight, characters: Dict[str, CharacterEventStream]
    ) -> Dict[str, float]:
        """Calculate various efficiency metrics for a fight."""
        if not characters or not fight.duration:
            return {}

        efficiency = {}

        # DPS efficiency (actual vs theoretical max)
        total_damage = sum(char.total_damage_done for char in characters.values())
        dps_players = len([char for char in characters.values() if char.total_damage_done > 0])

        if dps_players > 0 and fight.duration > 0:
            avg_dps = total_damage / (dps_players * fight.duration)
            efficiency["avg_dps_per_player"] = avg_dps

        # Healing efficiency (effective healing vs overhealing)
        total_healing = sum(char.total_healing_done for char in characters.values())
        total_overhealing = sum(char.total_overhealing for char in characters.values())

        if total_healing + total_overhealing > 0:
            efficiency["healing_efficiency"] = total_healing / (total_healing + total_overhealing)

        # Activity efficiency
        active_chars = [char for char in characters.values() if char.activity_percentage > 0]
        if active_chars:
            efficiency["avg_activity"] = sum(
                char.activity_percentage for char in active_chars
            ) / len(active_chars)

        # Survival efficiency
        total_players = len(characters)
        deaths = sum(char.death_count for char in characters.values())
        efficiency["survival_rate"] = (
            (total_players * 1.0 - deaths) / total_players if total_players > 0 else 0
        )

        return efficiency

    @staticmethod
    def get_top_abilities(
        characters: Dict[str, CharacterEventStream], ability_type: str = "damage"
    ) -> List[Tuple[str, str, int]]:
        """Get top abilities by damage or healing."""
        ability_totals = {}

        for char in characters.values():
            if ability_type == "damage":
                events = char.damage_done
            elif ability_type == "healing":
                events = char.healing_done
            else:
                continue

            for event in events:
                if hasattr(event, "spell_name") and event.spell_name:
                    key = f"{char.character_name}:{event.spell_name}"
                    if key not in ability_totals:
                        ability_totals[key] = 0
                    ability_totals[key] += getattr(event, "amount", 0)

        # Sort and return top abilities
        sorted_abilities = sorted(ability_totals.items(), key=lambda x: x[1], reverse=True)
        result = []
        for ability_key, total in sorted_abilities[:20]:
            character_name, spell_name = ability_key.split(":", 1)
            result.append((character_name, spell_name, total))

        return result
