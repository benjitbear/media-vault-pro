"""
Background thread that periodically checks podcast feeds for new episodes.
"""

import time
from typing import TYPE_CHECKING

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

    while True:
        try:
            content_downloader.check_podcast_feeds()
        except Exception as e:
            logger.error("Podcast checker error: %s", e)
        time.sleep(interval_seconds)
