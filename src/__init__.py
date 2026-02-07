"""
Media Ripper - Automated DVD/CD ripping and digital library system
"""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .ripper import Ripper
from .metadata import MetadataExtractor
from .disc_monitor import DiscMonitor
from .web_server import MediaServer

__all__ = ["Ripper", "MetadataExtractor", "DiscMonitor", "MediaServer"]
