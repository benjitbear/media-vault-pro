"""
Background thread that processes content-download jobs.

Handles: video download, article archiving, podcast subscription,
playlist import, and media identification job types.
"""

import time
from datetime import datetime
from typing import TYPE_CHECKING

from ..observability.errors import ErrorTracker
from ..observability.metrics import MetricsCollector
from ..observability.tracing import end_background_trace, trace_background_job

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
    metrics = MetricsCollector()
    error_tracker = ErrorTracker()

    # Lazy-init identifier only when first identify job arrives
    _identifier = None

    def _get_identifier():
        nonlocal _identifier
        if _identifier is None:
            from ..services.media_identifier import MediaIdentifierService

            _identifier = MediaIdentifierService(
                config=config,
                app_state=app_state,
            )
        return _identifier

    while True:
        try:
            row = app_state.get_next_queued_content_job()
            if not row:
                time.sleep(3)
                continue

            job = row
            job_id = job["id"]
            job_type = job.get("job_type", "download")
            logger.info("Content job %s: %s (%s)", job_id, job["title"], job_type)

            trace_background_job(job_type, job_id)

            app_state.update_job_status(job_id, "encoding", started_at=datetime.now().isoformat())

            # ── Identify jobs are handled here, not by ContentDownloader ──
            if job_type == "identify":
                try:
                    identifier = _get_identifier()
                    file_path = job.get("source_path", "")
                    result = identifier.identify_file(file_path)
                    if result:
                        app_state.update_job_status(
                            job_id,
                            "completed",
                            output_path=file_path,
                            completed_at=datetime.now().isoformat(),
                            progress=100.0,
                        )
                        logger.info("Identify job %s completed: %s", job_id, result.get("title"))
                        metrics.inc(
                            "content_downloads_completed_total", labels={"type": job_type}
                        )
                    else:
                        app_state.update_job_status(
                            job_id,
                            "completed",
                            output_path=file_path,
                            completed_at=datetime.now().isoformat(),
                            progress=100.0,
                        )
                        logger.info(
                            "Identify job %s: no TMDB match found (file kept as-is)", job_id
                        )
                        metrics.inc(
                            "content_downloads_completed_total", labels={"type": job_type}
                        )
                except Exception as e:
                    app_state.update_job_status(
                        job_id,
                        "failed",
                        error_message=str(e),
                        completed_at=datetime.now().isoformat(),
                    )
                    logger.error("Identify job %s failed: %s", job_id, e)
                    metrics.inc("content_downloads_failed_total", labels={"type": job_type})

                duration_ms = end_background_trace()
                if duration_ms is not None:
                    metrics.observe("job_duration_ms", duration_ms, labels={"job_type": job_type})
                continue

            # ── All other job types go through ContentDownloader ──
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
                metrics.inc("content_downloads_completed_total", labels={"type": job_type})
            else:
                app_state.update_job_status(
                    job_id,
                    "failed",
                    error_message="Content processing returned no output",
                    completed_at=datetime.now().isoformat(),
                )
                logger.error("Content job %s failed", job_id)
                metrics.inc("content_downloads_failed_total", labels={"type": job_type})

            duration_ms = end_background_trace()
            if duration_ms is not None:
                metrics.observe("job_duration_ms", duration_ms, labels={"job_type": job_type})

        except Exception as e:
            logger.error("Content worker error: %s", e)
            error_tracker.capture_exception(extra={"worker": "content_worker"})
            end_background_trace()
            time.sleep(5)
