"""
Media Library - Automated digital media library system
"""

__version__ = "0.3.0"
__author__ = "Benjamin Poppe"
__email__ = "ben@medialibrary.local"

from .app_state import AppState
from .ripper import Ripper
from .metadata import MetadataExtractor
from .disc_monitor import DiscMonitor
from .web_server import MediaServer
from .content_downloader import ContentDownloader

__all__ = [
    "AppState",
    "Ripper",
    "MetadataExtractor",
    "DiscMonitor",
    "MediaServer",
    "ContentDownloader",
]
