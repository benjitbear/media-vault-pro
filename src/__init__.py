"""
Media Library - Automated digital media library system
"""

__version__ = "0.2.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .app_state import AppState
from .ripper import Ripper
from .metadata import MetadataExtractor
from .disc_monitor import DiscMonitor
from .web_server import MediaServer

__all__ = ["AppState", "Ripper", "MetadataExtractor", "DiscMonitor", "MediaServer"]
