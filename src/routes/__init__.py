"""
Flask Blueprints organised by domain.

Each blueprint accesses the ``MediaServer`` instance via
``current_app.config['server']``, keeping the same runtime behaviour
as the old closure-based ``_setup_routes()``.
"""

from .collections_bp import collections_bp
from .content_bp import content_bp
from .jobs_bp import jobs_bp
from .media_bp import media_bp
from .playback_bp import playback_bp
from .podcasts_bp import podcasts_bp
from .users_bp import users_bp

__all__ = [
    "media_bp",
    "jobs_bp",
    "collections_bp",
    "users_bp",
    "content_bp",
    "podcasts_bp",
    "playback_bp",
]
