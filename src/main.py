"""
Unified entry point for Media Ripper.
Starts the web server, disc monitor, and job worker in a single process.
"""

import argparse
import json
import os
import shutil
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from .app_state import AppState
from .content_downloader import ContentDownloader
from .disc_monitor import DiscMonitor
from .metadata import MetadataExtractor
from .ripper import Ripper
from .constants import AUDIO_EXTENSIONS
from .config import load_config, validate_config
from .utils import (
    setup_logger,
    configure_notifications,
    rename_with_metadata,
    reorganize_audio_album,
    get_data_dir,
    natural_sort_key,
)
from .web_server import MediaServer


# ── Poster sync helpers ──────────────────────────────────────────


def _sync_video_poster(
    new_path: str, metadata: dict, metadata_extractor: MetadataExtractor, logger
) -> None:
    """
    Ensure a poster exists that matches the renamed video file stem,
    so the web server can find it as ``{stem}_poster.jpg``.
    """
    poster_src = metadata.get("poster_file", "")
    if not poster_src or not os.path.exists(poster_src):
        return

    thumbnails_dir = get_data_dir() / "thumbnails"
    new_stem = Path(new_path).stem
    dest = thumbnails_dir / f"{new_stem}_poster.jpg"

    if dest.exists() or dest == Path(poster_src):
        return

    try:
        shutil.copy2(poster_src, str(dest))
        metadata["poster_file"] = str(dest)
        logger.info("Poster synced: %s", dest.name)
    except Exception as e:
        logger.error("Failed to sync poster: %s", e)


def _sync_album_poster(
    album_dir: str, metadata: dict, metadata_extractor: MetadataExtractor, logger
) -> None:
    """
    Copy the album cover art so each track file has a matching
    ``{track_stem}_poster.jpg`` in the thumbnails directory.
    Also re-saves per-track metadata JSONs with the correct poster_file.
    """
    poster_src = metadata.get("poster_file", "")
    if not poster_src or not os.path.exists(poster_src):
        return

    thumbnails_dir = get_data_dir() / "thumbnails"
    for track_file in sorted(Path(album_dir).iterdir(), key=natural_sort_key):
        if track_file.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        dest = thumbnails_dir / f"{track_file.stem}_poster.jpg"
        try:
            shutil.copy2(poster_src, str(dest))
        except Exception as e:
            logger.error("Failed to copy poster for %s: %s", track_file.name, e)

        # Update per-track metadata JSON with poster path
        track_meta_file = get_data_dir() / "metadata" / f"{track_file.stem}.json"
        if track_meta_file.exists():
            try:
                with open(track_meta_file, "r") as f:
                    track_meta = json.load(f)
                track_meta["poster_file"] = str(dest)
                with open(track_meta_file, "w") as f:
                    json.dump(track_meta, f, indent=2)
            except Exception as e:
                logger.debug("Failed to update track metadata JSON %s: %s", track_meta_file, e)


def job_worker(
    app_state: AppState, ripper: Ripper, metadata_extractor: MetadataExtractor, config: dict, logger
):
    """
    Background thread that processes the rip job queue.
    Picks up queued jobs one at a time, runs the ripper, then extracts metadata.
    """
    logger.info("Job worker thread started")
    rename_ok = config.get("file_naming", {}).get("rename_after_rip", True)

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
                        # Save with output file stem so scan_library can find it
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
                                from .utils import get_media_root

                                base_output = str(get_media_root())
                            new_dir = reorganize_audio_album(output, metadata, base_output, logger)
                            if new_dir:
                                app_state.update_job_status(
                                    job_id, "completed", output_path=new_dir
                                )
                                # Copy album poster for each track so the
                                # web server can find it by file stem.
                                _sync_album_poster(new_dir, metadata, metadata_extractor, logger)
                        else:
                            new_path = rename_with_metadata(output, metadata, logger)
                            if new_path and new_path != output:
                                app_state.update_job_status(
                                    job_id, "completed", output_path=new_path
                                )
                                # Re-save metadata JSON under new stem
                                new_stem = Path(new_path).stem
                                metadata_extractor.save_metadata(metadata, new_stem)
                                # Sync poster to match new file stem
                                _sync_video_poster(new_path, metadata, metadata_extractor, logger)
                    except Exception as e:
                        logger.error("Rename failed for job %s: %s", job_id, e)

                # Notify clients to refresh library
                app_state.broadcast("library_updated", {})
            else:
                app_state.update_job_status(
                    job_id,
                    "failed",
                    error_message="Rip process returned no output",
                    completed_at=datetime.now().isoformat(),
                )
                logger.error("Job %s failed: no output", job_id)

        except Exception as e:
            logger.error("Job worker error: %s", e)
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


def content_worker(
    app_state: AppState, content_downloader: ContentDownloader, config: dict, logger
):
    """
    Background thread that processes content download jobs (non-rip jobs).
    Handles: download, article, podcast, playlist_import job types.
    """
    logger.info("Content worker thread started")

    while True:
        try:
            # Look for content jobs via public API
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


def podcast_checker(
    app_state: AppState, content_downloader: ContentDownloader, config: dict, logger
):
    """
    Background thread that periodically checks podcast feeds for new episodes.
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


def main():
    """Main entry point - starts all services"""
    parser = argparse.ArgumentParser(description="Media Ripper Server")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    parser.add_argument("--host", help="Host address (overrides config)")
    parser.add_argument("--port", type=int, help="Port number (overrides config)")
    parser.add_argument(
        "--mode",
        choices=["full", "server", "monitor"],
        default="full",
        help="Run mode: full (all services), server (web+downloads only), "
        "monitor (disc ripping only)",
    )
    parser.add_argument(
        "--no-monitor",
        action="store_true",
        help="Disable disc monitoring (deprecated, use --mode server)",
    )
    parser.add_argument(
        "--no-worker", action="store_true", help="Disable job worker (no automatic ripping)"
    )
    parser.add_argument(
        "--background", action="store_true", help="Run in background mode with suppressed output"
    )
    args = parser.parse_args()

    # Suppress console output if running in background mode
    if args.background:
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")

    config = load_config(args.config)

    # Validate configuration at startup
    config_errors = validate_config(config)
    if config_errors:
        for err in config_errors:
            print(f"  Config error: {err}", file=sys.stderr)
        sys.exit(1)

    debug_mode = config.get("logging", {}).get("debug", False)
    logger = setup_logger("main", "main.log", debug=debug_mode)
    logger.info("=" * 60)
    logger.info("Media Ripper Server starting")
    logger.info("=" * 60)

    # Configure notification suppression
    notify_enabled = config.get("automation", {}).get("notification_enabled", True)
    configure_notifications(notify_enabled)

    # Determine effective mode
    mode = args.mode
    if args.no_monitor and mode == "full":
        mode = "server"

    # Initialize shared state (SQLite-backed singleton)
    app_state = AppState()

    # Initialize components with shared state — config loaded once above
    ripper = Ripper(config=config, app_state=app_state)
    metadata_extractor = MetadataExtractor(config=config)
    content_dl = ContentDownloader(config=config, app_state=app_state)

    # Track threads for graceful shutdown
    _shutdown_event = threading.Event()

    # Start job worker thread (disc ripping) — full and monitor modes
    if not args.no_worker and mode in ("full", "monitor"):
        worker_thread = threading.Thread(
            target=job_worker,
            args=(app_state, ripper, metadata_extractor, config, logger),
            daemon=True,
            name="job-worker",
        )
        worker_thread.start()
        logger.info("Job worker thread started")

        # Start content worker thread (downloads, articles, playlists)
        content_thread = threading.Thread(
            target=content_worker,
            args=(app_state, content_dl, config, logger),
            daemon=True,
            name="content-worker",
        )
        content_thread.start()
        logger.info("Content worker thread started")
    else:
        logger.info("Job worker disabled")

    # Start podcast checker thread
    if config.get("podcasts", {}).get("enabled", True):
        pod_thread = threading.Thread(
            target=podcast_checker,
            args=(app_state, content_dl, config, logger),
            daemon=True,
            name="podcast-checker",
        )
        pod_thread.start()
        logger.info("Podcast checker thread started")

    # Start disc monitor thread — full and monitor modes only
    if mode in ("full", "monitor") and config["automation"].get("auto_detect_disc", True):
        monitor = DiscMonitor(
            config=config,
            app_state=app_state,
            ripper=ripper,
            metadata_extractor=metadata_extractor,
        )
        monitor_thread = threading.Thread(target=monitor.start, daemon=True, name="disc-monitor")
        monitor_thread.start()
        logger.info("Disc monitor thread started")
    else:
        logger.info("Disc monitoring disabled")

    # Start web server (blocking - runs in main thread) — full and server modes
    if mode in ("full", "server"):
        server = MediaServer(config=config, app_state=app_state)

        def shutdown(signum, frame):
            logger.info("Shutdown signal received")
            _shutdown_event.set()
            if not args.background:
                print("\n Shutting down...")
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        server.run(host=args.host, port=args.port)
    elif mode == "monitor":
        # Monitor-only mode: block on disc monitor
        def shutdown(signum, frame):
            logger.info("Shutdown signal received")
            _shutdown_event.set()
            if not args.background:
                print("\n Shutting down...")
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        logger.info("Running in monitor-only mode (no web server)")
        try:
            while not _shutdown_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
