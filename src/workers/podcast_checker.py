"""
Background thread that periodically checks podcast feeds for new episodes.
"""

import time
from typing import TYPE_CHECKING

from ..observability.errors import ErrorTracker
from ..observability.metrics import MetricsCollector

if TYPE_CHECKING:
    import logging

    from ..app_state import AppState
    from ..content_downloader import ContentDownloader


def podcast_checker(
    app_state: "AppState",
    content_downloader: "ContentDownloader",
    config: dict,
    logger: "logging.Logger",
) -> None:
    """Run forever, periodically checking podcast feeds.

    Args:
        app_state: Shared database singleton.
        content_downloader: ContentDownloader instance.
        config: Application configuration dict.
        logger: Logger instance.
    """
    check_interval = config.get("podcasts", {}).get("check_interval_hours", 6)
    interval_seconds = check_interval * 3600
    logger.info("Podcast checker started (interval: %sh)", check_interval)
    metrics = MetricsCollector()
    error_tracker = ErrorTracker()

    while True:
        try:
            content_downloader.check_podcast_feeds()
            metrics.inc("podcast_feed_checks_total")
        except Exception as e:
            logger.error("Podcast checker error: %s", e)
            error_tracker.capture_exception(extra={"worker": "podcast_checker"})
        time.sleep(interval_seconds)
