"""
Unified entry point for Media Ripper.
Starts the web server, disc monitor, and job worker in a single process.
"""
import argparse
import json
import os
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
from .utils import load_config, setup_logger, configure_notifications, \
    rename_with_metadata, reorganize_audio_album
from .web_server import MediaServer


def job_worker(app_state: AppState, ripper: Ripper,
               metadata_extractor: MetadataExtractor,
               config: dict, logger):
    """
    Background thread that processes the rip job queue.
    Picks up queued jobs one at a time, runs the ripper, then extracts metadata.
    """
    logger.info("Job worker thread started")
    rename_ok = config.get('file_naming', {}).get('rename_after_rip', True)

    while True:
        try:
            job = app_state.get_next_queued_job()
            if not job:
                time.sleep(2)
                continue

            job_id = job['id']
            disc_type = job.get('disc_type', 'dvd')
            disc_hints = json.loads(job.get('disc_hints', '{}'))
            job_type = job.get('job_type', 'rip')
            logger.info(f"Processing job {job_id}: {job['title']} ({disc_type}/{job_type})")

            # Mark as encoding
            app_state.update_job_status(
                job_id, 'encoding',
                started_at=datetime.now().isoformat()
            )

            # Run the appropriate ripper based on disc type
            if disc_type == 'audio_cd':
                output = ripper.rip_audio_cd(
                    source_path=job['source_path'],
                    album_name=job['title'],
                    job_id=job_id
                )
            else:
                output = ripper.rip_disc(
                    source_path=job['source_path'],
                    title_name=job['title'],
                    title_number=job.get('title_number', 1),
                    job_id=job_id
                )

            if output:
                app_state.update_job_status(
                    job_id, 'completed',
                    output_path=output,
                    completed_at=datetime.now().isoformat(),
                    progress=100.0
                )
                logger.info(f"Job {job_id} completed: {output}")

                # Extract and save metadata
                metadata = None
                if config['metadata'].get('save_to_json', True):
                    try:
                        logger.info(f"Extracting metadata for job {job_id}")
                        metadata = metadata_extractor.extract_full_metadata(
                            output, title_hint=job['title'],
                            disc_hints=disc_hints
                        )
                        # Save with output file stem so scan_library can find it
                        output_stem = Path(output).stem
                        metadata_extractor.save_metadata(metadata, output_stem)
                        logger.info(f"Metadata saved for job {job_id}")
                    except Exception as e:
                        logger.error(f"Metadata extraction failed for job {job_id}: {e}")

                # ── Rename output file with metadata ──
                if rename_ok and metadata:
                    try:
                        if disc_type == 'audio_cd':
                            base_output = config['output'].get(
                                'base_directory', '/Users/poppemacmini/Media')
                            new_dir = reorganize_audio_album(
                                output, metadata, base_output, logger)
                            if new_dir:
                                app_state.update_job_status(
                                    job_id, 'completed', output_path=new_dir)
                        else:
                            new_path = rename_with_metadata(
                                output, metadata, logger)
                            if new_path and new_path != output:
                                app_state.update_job_status(
                                    job_id, 'completed', output_path=new_path)
                                # Re-save metadata JSON under new stem
                                new_stem = Path(new_path).stem
                                metadata_extractor.save_metadata(
                                    metadata, new_stem)
                    except Exception as e:
                        logger.error(f"Rename failed for job {job_id}: {e}")

                # Notify clients to refresh library
                app_state.broadcast('library_updated', {})
            else:
                app_state.update_job_status(
                    job_id, 'failed',
                    error_message='Rip process returned no output',
                    completed_at=datetime.now().isoformat()
                )
                logger.error(f"Job {job_id} failed: no output")

        except Exception as e:
            logger.error(f"Job worker error: {e}")
            try:
                active = app_state.get_active_job()
                if active:
                    app_state.update_job_status(
                        active['id'], 'failed',
                        error_message=str(e),
                        completed_at=datetime.now().isoformat()
                    )
            except Exception:
                pass
            time.sleep(5)


def content_worker(app_state: AppState, content_downloader: ContentDownloader,
                   config: dict, logger):
    """
    Background thread that processes content download jobs (non-rip jobs).
    Handles: download, article, podcast, playlist_import job types.
    """
    logger.info("Content worker thread started")

    while True:
        try:
            # Look for content jobs specifically
            conn = app_state._get_conn()
            row = conn.execute(
                "SELECT * FROM jobs WHERE status = 'queued' "
                "AND job_type != 'rip' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if not row:
                time.sleep(3)
                continue

            job = dict(row)
            job_id = job['id']
            logger.info(f"Content job {job_id}: {job['title']} ({job.get('job_type')})")

            app_state.update_job_status(
                job_id, 'encoding',
                started_at=datetime.now().isoformat()
            )

            output = content_downloader.process_content_job(job)

            if output:
                app_state.update_job_status(
                    job_id, 'completed',
                    output_path=output,
                    completed_at=datetime.now().isoformat(),
                    progress=100.0
                )
                logger.info(f"Content job {job_id} completed: {output}")
                app_state.broadcast('library_updated', {})
            else:
                app_state.update_job_status(
                    job_id, 'failed',
                    error_message='Content processing returned no output',
                    completed_at=datetime.now().isoformat()
                )
                logger.error(f"Content job {job_id} failed")

        except Exception as e:
            logger.error(f"Content worker error: {e}")
            time.sleep(5)


def podcast_checker(app_state: AppState, content_downloader: ContentDownloader,
                    config: dict, logger):
    """
    Background thread that periodically checks podcast feeds for new episodes.
    """
    check_interval = config.get('podcasts', {}).get('check_interval_hours', 6)
    interval_seconds = check_interval * 3600
    logger.info(f"Podcast checker started (interval: {check_interval}h)")

    while True:
        try:
            content_downloader.check_podcast_feeds()
        except Exception as e:
            logger.error(f"Podcast checker error: {e}")
        time.sleep(interval_seconds)


def main():
    """Main entry point - starts all services"""
    parser = argparse.ArgumentParser(description='Media Ripper Server')
    parser.add_argument('--config', default='config.json', help='Path to config file')
    parser.add_argument('--host', help='Host address (overrides config)')
    parser.add_argument('--port', type=int, help='Port number (overrides config)')
    parser.add_argument('--no-monitor', action='store_true',
                        help='Disable disc monitoring')
    parser.add_argument('--no-worker', action='store_true',
                        help='Disable job worker (no automatic ripping)')
    parser.add_argument('--background', action='store_true',
                        help='Run in background mode with suppressed output')
    args = parser.parse_args()

    # Suppress console output if running in background mode
    if args.background:
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')

    config = load_config(args.config)
    debug_mode = config.get('logging', {}).get('debug', False)
    logger = setup_logger('main', 'main.log', debug=debug_mode)
    logger.info("=" * 60)
    logger.info("Media Ripper Server starting")
    logger.info("=" * 60)

    # Configure notification suppression
    notify_enabled = config.get('automation', {}).get('notification_enabled', True)
    configure_notifications(notify_enabled)

    # Initialize shared state (SQLite-backed singleton)
    app_state = AppState()

    # Initialize components with shared state
    ripper = Ripper(config_path=args.config, app_state=app_state)
    metadata_extractor = MetadataExtractor(config_path=args.config)
    content_dl = ContentDownloader(config_path=args.config, app_state=app_state)

    # Start job worker thread (disc ripping)
    if not args.no_worker:
        worker_thread = threading.Thread(
            target=job_worker,
            args=(app_state, ripper, metadata_extractor, config, logger),
            daemon=True,
            name='job-worker'
        )
        worker_thread.start()
        logger.info("Job worker thread started")

        # Start content worker thread (downloads, articles, playlists)
        content_thread = threading.Thread(
            target=content_worker,
            args=(app_state, content_dl, config, logger),
            daemon=True,
            name='content-worker'
        )
        content_thread.start()
        logger.info("Content worker thread started")
    else:
        logger.info("Job worker disabled")

    # Start podcast checker thread
    if config.get('podcasts', {}).get('enabled', True):
        pod_thread = threading.Thread(
            target=podcast_checker,
            args=(app_state, content_dl, config, logger),
            daemon=True,
            name='podcast-checker'
        )
        pod_thread.start()
        logger.info("Podcast checker thread started")

    # Start disc monitor thread
    if not args.no_monitor and config['automation'].get('auto_detect_disc', True):
        monitor = DiscMonitor(config_path=args.config, app_state=app_state)
        monitor_thread = threading.Thread(
            target=monitor.start,
            daemon=True,
            name='disc-monitor'
        )
        monitor_thread.start()
        logger.info("Disc monitor thread started")
    else:
        logger.info("Disc monitoring disabled")

    # Start web server (blocking - runs in main thread)
    server = MediaServer(config_path=args.config, app_state=app_state)

    def shutdown(signum, frame):
        logger.info("Shutdown signal received")
        if not args.background:
            print("\n👋 Shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    server.run(host=args.host, port=args.port)


if __name__ == '__main__':
    main()
