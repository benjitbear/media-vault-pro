"""
Unified entry point for Media Ripper.
Starts the web server, disc monitor, and job worker in a single process.
"""
import argparse
import os
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from .app_state import AppState
from .disc_monitor import DiscMonitor
from .metadata import MetadataExtractor
from .ripper import Ripper
from .utils import load_config, setup_logger, configure_notifications
from .web_server import MediaServer


def job_worker(app_state: AppState, ripper: Ripper,
               metadata_extractor: MetadataExtractor,
               config: dict, logger):
    """
    Background thread that processes the rip job queue.
    Picks up queued jobs one at a time, runs the ripper, then extracts metadata.
    """
    logger.info("Job worker thread started")

    while True:
        try:
            job = app_state.get_next_queued_job()
            if not job:
                time.sleep(2)
                continue

            job_id = job['id']
            logger.info(f"Processing job {job_id}: {job['title']}")

            # Mark as encoding
            app_state.update_job_status(
                job_id, 'encoding',
                started_at=datetime.now().isoformat()
            )

            # Run the ripper
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
                if config['metadata'].get('save_to_json', True):
                    try:
                        logger.info(f"Extracting metadata for job {job_id}")
                        metadata = metadata_extractor.extract_full_metadata(
                            output, title_hint=job['title']
                        )
                        # Save with output file stem so scan_library can find it
                        output_stem = Path(output).stem
                        metadata_extractor.save_metadata(metadata, output_stem)
                        logger.info(f"Metadata saved for job {job_id}")
                    except Exception as e:
                        logger.error(f"Metadata extraction failed for job {job_id}: {e}")

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
            # If we have a current job, mark it failed
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

    # Start job worker thread
    if not args.no_worker:
        worker_thread = threading.Thread(
            target=job_worker,
            args=(app_state, ripper, metadata_extractor, config, logger),
            daemon=True,
            name='job-worker'
        )
        worker_thread.start()
        logger.info("Job worker thread started")
    else:
        logger.info("Job worker disabled")

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
