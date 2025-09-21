"""
Segmentation module for identifying and grouping combat encounters.
"""

from .encounters import EncounterSegmenter, Fight
from .aggregator import EventAggregator
from .enhanced import EnhancedSegmenter

__all__ = ["EncounterSegmenter", "Fight", "EventAggregator", "EnhancedSegmenter"]
