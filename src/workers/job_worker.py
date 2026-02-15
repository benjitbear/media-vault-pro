"""
Background thread that processes the rip-job queue.

Picks up queued jobs one at a time, runs the ripper, extracts metadata,
optionally renames output files, and syncs poster artwork.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..constants import AUDIO_EXTENSIONS
from ..observability.errors import ErrorTracker
from ..observability.metrics import MetricsCollector
from ..observability.tracing import end_background_trace, trace_background_job
from ..utils import (
    get_media_root,
    natural_sort_key,
    rename_with_metadata,
    reorganize_audio_album,
)
from .poster_sync import sync_album_poster, sync_video_poster

if TYPE_CHECKING:
    import logging

    from ..app_state import AppState
    from ..metadata import MetadataExtractor
    from ..ripper import Ripper


def job_worker(
    app_state: "AppState",
    ripper: "Ripper",
    metadata_extractor: "MetadataExtractor",
    config: dict,
    logger: "logging.Logger",
) -> None:
    """Run forever, draining the rip-job queue.

    Args:
        app_state: Shared database singleton.
        ripper: Ripper instance for disc encoding.
        metadata_extractor: For post-rip metadata enrichment.
        config: Application configuration dict.
        logger: Logger instance.
    """
    logger.info("Job worker thread started")
    rename_ok = config.get("file_naming", {}).get("rename_after_rip", True)
    metrics = MetricsCollector()
    error_tracker = ErrorTracker()

    while True:
        try:
            job = app_state.get_next_queued_job()
            if not job:
                time.sleep(2)
                continue

            job_id = job["id"]
            disc_type = job.get("disc_type", "dvd")
            disc_hints = json.loads(job.get("disc_hints", "{}"))
            job_type = job.get("job_type", "rip")

            # Start a trace span for this job
            trace_background_job(job_type, job_id)
            metrics.inc("rip_jobs_created_total", labels={"type": disc_type})

            logger.info("Processing job %s: %s (%s/%s)", job_id, job["title"], disc_type, job_type)

            # Mark as encoding
            app_state.update_job_status(job_id, "encoding", started_at=datetime.now().isoformat())

            # Run the appropriate ripper based on disc type
            if disc_type == "audio_cd":
                output = ripper.rip_audio_cd(
                    source_path=job["source_path"], album_name=job["title"], job_id=job_id
                )
            else:
                output = ripper.rip_disc(
                    source_path=job["source_path"],
                    title_name=job["title"],
                    title_number=job.get("title_number", 1),
                    job_id=job_id,
                )

            if output:
                app_state.update_job_status(
                    job_id,
                    "completed",
                    output_path=output,
                    completed_at=datetime.now().isoformat(),
                    progress=100.0,
                )
                logger.info("Job %s completed: %s", job_id, output)

                # For audio CDs, inject a sample track path so AcoustID
                # fingerprinting can identify the album.
                if disc_type == "audio_cd" and Path(output).is_dir():
                    sample = next(
                        (
                            f
                            for f in sorted(Path(output).iterdir(), key=natural_sort_key)
                            if f.suffix.lower() in AUDIO_EXTENSIONS
                        ),
                        None,
                    )
                    if sample:
                        disc_hints["sample_track_path"] = str(sample)
                        logger.info("Set sample_track_path: %s", sample)

                # Extract and save metadata
                metadata = None
                if config["metadata"].get("save_to_json", True):
                    try:
                        logger.info("Extracting metadata for job %s", job_id)
                        metadata = metadata_extractor.extract_full_metadata(
                            output, title_hint=job["title"], disc_hints=disc_hints
                        )
                        output_stem = Path(output).stem
                        metadata_extractor.save_metadata(metadata, output_stem)
                        logger.info("Metadata saved for job %s", job_id)
                    except Exception as e:
                        logger.error("Metadata extraction failed for job %s: %s", job_id, e)

                # ── Rename output file with metadata ──
                if rename_ok and metadata:
                    try:
                        if disc_type == "audio_cd":
                            base_output = config["output"].get("base_directory", "")
                            if not base_output or base_output.startswith("${"):
                                base_output = str(get_media_root())
                            new_dir = reorganize_audio_album(output, metadata, base_output, logger)
                            if new_dir:
                                app_state.update_job_status(
                                    job_id, "completed", output_path=new_dir
                                )
                                sync_album_poster(new_dir, metadata, metadata_extractor, logger)
                        else:
                            new_path = rename_with_metadata(output, metadata, logger)
                            if new_path and new_path != output:
                                app_state.update_job_status(
                                    job_id, "completed", output_path=new_path
                                )
                                new_stem = Path(new_path).stem
                                metadata_extractor.save_metadata(metadata, new_stem)
                                sync_video_poster(new_path, metadata, metadata_extractor, logger)
                    except Exception as e:
                        logger.error("Rename failed for job %s: %s", job_id, e)

                # Notify clients to refresh library
                app_state.broadcast("library_updated", {})
                metrics.inc("rip_jobs_completed_total", labels={"type": disc_type})
            else:
                app_state.update_job_status(
                    job_id,
                    "failed",
                    error_message="Rip process returned no output",
                    completed_at=datetime.now().isoformat(),
                )
                logger.error("Job %s failed: no output", job_id)
                metrics.inc("rip_jobs_failed_total", labels={"type": disc_type})

            # End the trace span and record duration
            duration_ms = end_background_trace()
            if duration_ms is not None:
                metrics.observe("job_duration_ms", duration_ms, labels={"job_type": job_type})

        except Exception as e:
            logger.error("Job worker error: %s", e)
            error_tracker.capture_exception(extra={"worker": "job_worker"})
            metrics.inc("rip_jobs_failed_total")
            end_background_trace()
            try:
                active = app_state.get_active_job()
                if active:
                    app_state.update_job_status(
                        active["id"],
                        "failed",
                        error_message=str(e),
                        completed_at=datetime.now().isoformat(),
                    )
            except Exception as exc:
                logger.warning("Failed to mark job as failed: %s", exc)
