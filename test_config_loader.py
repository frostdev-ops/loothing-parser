#!/usr/bin/env python3
"""Test configuration loading system."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import wow_data
from src.config.loader import ConfigLoader


def test_default_mappings():
    """Test that default mappings work."""
    print("Testing default mappings...")

    # Test difficulty mapping
    assert wow_data.get_difficulty_name(8) == "Challenge Mode"
    assert wow_data.get_difficulty_name(14) == "Normal"
    assert wow_data.get_difficulty_name(999) == "Unknown (999)"
    print("✓ Difficulty mappings working")

    # Test spec detection
    assert wow_data.is_tank_spec(250)  # Blood DK
    assert wow_data.is_healer_spec(105)  # Resto Druid
    assert not wow_data.is_tank_spec(251)  # Frost DK (DPS)
    print("✓ Spec detection working")

    # Test affix names
    assert wow_data.get_affix_name(9) == "Tyrannical"
    assert wow_data.get_affix_name(10) == "Fortified"
    print("✓ Affix mappings working")

    # Test consumable detection
    assert wow_data.is_flask_buff(431972)  # TWW flask
    assert wow_data.is_food_buff(462854)  # TWW food
    print("✓ Consumable detection working")

    print("\nAll default mappings tests passed!")


def test_config_loading():
    """Test loading custom configuration."""
    print("\nTesting configuration loading...")

    # Create a test config
    test_config = {
        "difficulties": {
            "999": "Test Difficulty",
            "8": "Custom Challenge Mode"  # Override existing
        },
        "specializations": {
            "9999": "Test Spec"
        },
        "tank_specs": [9999],  # Add our test spec as tank
        "affixes": {
            "888": "Test Affix"
        },
        "flask_ids": [777777],
        "food_buff_ids": [666666]
    }

    # Apply the config
    loader = ConfigLoader()
    loader.apply_config(test_config)

    # Test that custom mappings were applied
    assert wow_data.get_difficulty_name(999) == "Test Difficulty"
    assert wow_data.get_difficulty_name(8) == "Custom Challenge Mode"  # Override worked
    print("✓ Custom difficulty mappings applied")

    assert wow_data.get_spec_name(9999) == "Test Spec"
    assert wow_data.is_tank_spec(9999)  # Our custom tank spec
    print("✓ Custom spec mappings applied")

    assert wow_data.get_affix_name(888) == "Test Affix"
    print("✓ Custom affix mappings applied")

    assert wow_data.is_flask_buff(777777)
    assert wow_data.is_food_buff(666666)
    print("✓ Custom consumable IDs applied")

    print("\nConfiguration loading tests passed!")


def test_file_search():
    """Test configuration file search paths."""
    print("\nTesting file search paths...")

    loader = ConfigLoader()

    # Test with non-existent file (should return empty dict)
    config = loader.load_config("non_existent_file.yaml")
    assert config == {}
    print("✓ Returns empty dict for missing files")

    # Test with example file if it exists
    example_path = Path("config/wow_config.yaml.example")
    if example_path.exists():
        config = loader.load_config(str(example_path))
        assert "difficulties" in config
        print("✓ Can load example configuration file")

    print("\nFile search tests passed!")


def main():
    """Run all tests."""
    print("=" * 50)
    print("Configuration System Test")
    print("=" * 50)

    test_default_mappings()
    test_config_loading()
    test_file_search()

    print("\n" + "=" * 50)
    print("All tests passed successfully!")
    print("=" * 50)
    print("\nThe configuration system is working correctly.")
    print("Users can now customize WoW data mappings by creating")
    print("a wow_config.yaml file based on the provided examples.")


if __name__ == "__main__":
    main()