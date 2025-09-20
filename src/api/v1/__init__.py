"""
API v1 package for WoW combat log analysis.

This package provides a comprehensive REST API for querying, analyzing, and
exporting World of Warcraft combat log data.

Features:
- Character performance analysis
- Encounter metrics and replay
- Advanced analytics and trends
- Real-time log processing
- Export capabilities
- Guild management tools
"""

from .main import create_v1_app
from .models.responses import *
from .dependencies import *

__version__ = "1.0.0"
__all__ = ["create_v1_app"]