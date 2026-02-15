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

from .app_state import AppState
from .config import load_config, validate_config
from .content_downloader import ContentDownloader
from .disc_monitor import DiscMonitor
from .metadata import MetadataExtractor
from .observability import (
    ErrorTracker,
    MetricsCollector,
    PiiScrubber,
    setup_structured_logger,
)
from .ripper import Ripper
from .utils import configure_notifications
from .web_server import MediaServer
from .workers import content_worker, job_worker, podcast_checker


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
    logger = setup_structured_logger("main", "main.log", debug=debug_mode)
    logger.addFilter(PiiScrubber())
    logger.info("=" * 60)
    logger.info("Media Ripper Server starting")
    logger.info("=" * 60)

    # Initialise global observability singletons early
    MetricsCollector()
    ErrorTracker()

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
