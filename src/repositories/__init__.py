"""
Repository mixins for AppState.

Each mixin encapsulates a logical domain (media, jobs, auth, etc.)
and expects the host class to provide:
    - ``self._get_conn()`` → ``sqlite3.Connection``
    - ``self.logger``       → ``logging.Logger``
    - ``self.broadcast(event, data)`` (optional, for real-time updates)
"""

from .auth_repo import AuthRepositoryMixin
from .collection_repo import CollectionRepositoryMixin
from .job_repo import JobRepositoryMixin
from .media_repo import MediaRepositoryMixin
from .playback_repo import PlaybackRepositoryMixin
from .podcast_repo import PodcastRepositoryMixin

__all__ = [
    "MediaRepositoryMixin",
    "JobRepositoryMixin",
    "CollectionRepositoryMixin",
    "AuthRepositoryMixin",
    "PodcastRepositoryMixin",
    "PlaybackRepositoryMixin",
]
