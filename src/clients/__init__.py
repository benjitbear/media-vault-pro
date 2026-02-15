"""
External service clients for metadata extraction.

Each module encapsulates a single API / CLI tool:
- ``mediainfo_client``  – MediaInfo / ffprobe wrappers
- ``tmdb_client``       – TMDB movie search & poster download
- ``musicbrainz_client``– MusicBrainz + AcoustID + CoverArtArchive
"""

from .mediainfo_client import MediaInfoClient
from .tmdb_client import TMDBClient
from .musicbrainz_client import MusicBrainzClient

__all__ = [
    "MediaInfoClient",
    "TMDBClient",
    "MusicBrainzClient",
]
