"""
Configuration loader for custom WoW data mappings.

Allows users to provide custom mappings via YAML configuration files.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Optional, Any

from . import wow_data

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Loads and applies custom configuration from YAML files."""

    @staticmethod
    def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to custom config file. If None, looks for:
                        1. wow_config.yaml in current directory
                        2. ~/.loothing/wow_config.yaml
                        3. /etc/loothing/wow_config.yaml

        Returns:
            Configuration dictionary
        """
        # Default search paths
        search_paths = [
            Path("wow_config.yaml"),
            Path("config/wow_config.yaml"),
            Path.home() / ".loothing" / "wow_config.yaml",
            Path("/etc/loothing/wow_config.yaml"),
        ]

        # Add custom path if provided
        if config_path:
            search_paths.insert(0, Path(config_path))

        # Try each path
        for path in search_paths:
            if path.exists():
                try:
                    with open(path, "r") as f:
                        config = yaml.safe_load(f) or {}
                        logger.info(f"Loaded configuration from {path}")
                        return config
                except Exception as e:
                    logger.error(f"Failed to load config from {path}: {e}")

        # No config file found, return empty dict
        logger.debug("No custom configuration file found, using defaults")
        return {}

    @staticmethod
    def apply_config(config: Dict[str, Any]) -> None:
        """
        Apply custom configuration to wow_data module.

        Args:
            config: Configuration dictionary from YAML
        """
        # Apply difficulty mappings
        if "difficulties" in config:
            for diff_id, name in config["difficulties"].items():
                try:
                    diff_id = int(diff_id)
                    wow_data.DIFFICULTY_NAMES[diff_id] = name
                    logger.debug(f"Added custom difficulty: {diff_id} = {name}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid difficulty ID {diff_id}: {e}")

        # Apply specialization mappings
        if "specializations" in config:
            for spec_id, name in config["specializations"].items():
                try:
                    spec_id = int(spec_id)
                    wow_data.ALL_SPECS[spec_id] = name
                    logger.debug(f"Added custom spec: {spec_id} = {name}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid spec ID {spec_id}: {e}")

        # Apply tank specs
        if "tank_specs" in config:
            for spec_id in config["tank_specs"]:
                try:
                    spec_id = int(spec_id)
                    spec_name = wow_data.ALL_SPECS.get(spec_id, f"Unknown ({spec_id})")
                    wow_data.TANK_SPECS[spec_id] = spec_name
                    logger.debug(f"Added tank spec: {spec_id}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid tank spec ID {spec_id}: {e}")

        # Apply healer specs
        if "healer_specs" in config:
            for spec_id in config["healer_specs"]:
                try:
                    spec_id = int(spec_id)
                    spec_name = wow_data.ALL_SPECS.get(spec_id, f"Unknown ({spec_id})")
                    wow_data.HEALER_SPECS[spec_id] = spec_name
                    logger.debug(f"Added healer spec: {spec_id}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid healer spec ID {spec_id}: {e}")

        # Apply affix mappings
        if "affixes" in config:
            for affix_id, name in config["affixes"].items():
                try:
                    affix_id = int(affix_id)
                    wow_data.MYTHIC_PLUS_AFFIXES[affix_id] = name
                    logger.debug(f"Added custom affix: {affix_id} = {name}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid affix ID {affix_id}: {e}")

        # Apply flask IDs
        if "flask_ids" in config:
            for flask_id in config["flask_ids"]:
                try:
                    flask_id = int(flask_id)
                    wow_data.FLASK_IDS.add(flask_id)
                    logger.debug(f"Added flask ID: {flask_id}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid flask ID {flask_id}: {e}")

        # Apply food buff IDs
        if "food_buff_ids" in config:
            for food_id in config["food_buff_ids"]:
                try:
                    food_id = int(food_id)
                    wow_data.FOOD_BUFF_IDS.add(food_id)
                    logger.debug(f"Added food buff ID: {food_id}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid food buff ID {food_id}: {e}")

        # Apply cooldown mappings
        if "major_cooldowns" in config:
            for cd_id, name in config["major_cooldowns"].items():
                try:
                    cd_id = int(cd_id)
                    wow_data.MAJOR_COOLDOWNS[cd_id] = name
                    logger.debug(f"Added major cooldown: {cd_id} = {name}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid cooldown ID {cd_id}: {e}")

        logger.info("Custom configuration applied successfully")


def load_and_apply_config(config_path: Optional[str] = None) -> None:
    """
    Load and apply configuration in one step.

    Args:
        config_path: Optional path to custom config file
    """
    loader = ConfigLoader()
    config = loader.load_config(config_path)
    if config:
        loader.apply_config(config)
