"""
Media Library - Automated digital media library system
"""

__version__ = "0.3.0"
__author__ = "Benjamin Poppe"
__email__ = "ben@medialibrary.local"

from .app_state import AppState
from .content_downloader import ContentDownloader
from .disc_monitor import DiscMonitor
from .metadata import MetadataExtractor
from .ripper import Ripper
from .web_server import MediaServer

__all__ = [
    "AppState",
    "Ripper",
    "MetadataExtractor",
    "DiscMonitor",
    "MediaServer",
    "ContentDownloader",
]
