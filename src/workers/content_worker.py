"""
Background thread that processes content-download jobs.

Handles: video download, article archiving, podcast subscription,
and playlist import job types.
"""

import time
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging

    from ..app_state import AppState
    from ..content_downloader import ContentDownloader


def content_worker(
    app_state: "AppState",
    content_downloader: "ContentDownloader",
    config: dict,
    logger: "logging.Logger",
) -> None:
    """Run forever, draining the content-download job queue.

    Args:
        app_state: Shared database singleton.
        content_downloader: ContentDownloader instance.
        config: Application configuration dict.
        logger: Logger instance.
    """
    logger.info("Content worker thread started")

    while True:
        try:
            row = app_state.get_next_queued_content_job()
            if not row:
                time.sleep(3)
                continue

            job = row
            job_id = job["id"]
            logger.info("Content job %s: %s (%s)", job_id, job["title"], job.get("job_type"))

            app_state.update_job_status(job_id, "encoding", started_at=datetime.now().isoformat())

            output = content_downloader.process_content_job(job)

            if output:
                app_state.update_job_status(
                    job_id,
                    "completed",
                    output_path=output,
                    completed_at=datetime.now().isoformat(),
                    progress=100.0,
                )
                logger.info("Content job %s completed: %s", job_id, output)
                app_state.broadcast("library_updated", {})
            else:
                app_state.update_job_status(
                    job_id,
                    "failed",
                    error_message="Content processing returned no output",
                    completed_at=datetime.now().isoformat(),
                )
                logger.error("Content job %s failed", job_id)

        except Exception as e:
            logger.error("Content worker error: %s", e)
            time.sleep(5)
