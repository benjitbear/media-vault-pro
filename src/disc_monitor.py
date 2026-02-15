"""
Disc detection and automatic ripping daemon
"""

import json
import shutil
import signal
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Set

from .config import load_config
from .constants import AUDIO_CD_EXTENSIONS, IGNORE_VOLUMES
from .metadata import MetadataExtractor
from .ripper import Ripper
from .utils import configure_notifications, send_notification, setup_logger

if TYPE_CHECKING:
    from .app_state import AppState


class DiscMonitor:
    """Monitors for disc insertion and triggers automatic ripping"""

    def __init__(
        self,
        config: Dict[str, Any] = None,
        *,
        config_path: str = None,
        app_state: "AppState" = None,
        ripper: "Ripper" = None,
        metadata_extractor: "MetadataExtractor" = None,
    ):
        """
        Initialize the DiscMonitor

        Args:
            config: Pre-loaded configuration dict (preferred).
            config_path: Path to configuration file (backward compat).
            app_state: Optional shared AppState for job queue integration.
            ripper: Optional pre-built Ripper instance (created if omitted).
            metadata_extractor: Optional pre-built MetadataExtractor (created if omitted).
        """
        self.config = config if config is not None else load_config(config_path or "config.json")
        debug_mode = self.config.get("logging", {}).get("debug", False)
        self.logger = setup_logger("disc_monitor", "disc_monitor.log", debug=debug_mode)

        # Honour notification config
        notify_enabled = self.config.get("automation", {}).get("notification_enabled", True)
        configure_notifications(notify_enabled)

        self.ripper = ripper or Ripper(config=self.config, app_state=app_state)
        self.metadata_extractor = metadata_extractor or MetadataExtractor(config=self.config)
        self.app_state = app_state

        self.mount_path = Path(self.config["disc_detection"]["mount_path"])
        self.check_interval = self.config["disc_detection"]["check_interval_seconds"]
        self.known_volumes: Set[str] = set()
        self.running = False

        # Resolve tool paths for environments with minimal PATH
        self._ffprobe = shutil.which("ffprobe") or "ffprobe"
        self._handbrake = shutil.which("HandBrakeCLI") or "HandBrakeCLI"

        # System volumes to ignore
        self.ignore_volumes = IGNORE_VOLUMES

        self.logger.info("DiscMonitor initialized")

    def get_mounted_volumes(self) -> Set[str]:
        """
        Get list of currently mounted volumes

        Returns:
            Set of volume names
        """
        volumes = set()

        if not self.mount_path.exists():
            return volumes

        try:
            for item in self.mount_path.iterdir():
                if item.is_dir() and item.name not in self.ignore_volumes:
                    # Check if it looks like a disc (has VIDEO_TS or similar)
                    if self.is_disc_volume(item):
                        volumes.add(item.name)
        except Exception as e:
            self.logger.error("Error scanning volumes: %s", e)

        return volumes

    def is_disc_volume(self, volume_path: Path) -> bool:
        """
        Check if a volume appears to be a DVD/CD/Blu-ray

        Args:
            volume_path: Path to volume

        Returns:
            True if it appears to be a disc
        """
        # Check for VIDEO_TS directory (DVD)
        if (volume_path / "VIDEO_TS").exists():
            return True

        # Check for BDMV directory (Blu-ray)
        if (volume_path / "BDMV").exists():
            return True

        # Check for audio CD (.aiff/.cda files directly in volume)
        if self.is_audio_cd(volume_path):
            return True

        return False

    def is_audio_cd(self, volume_path: Path) -> bool:
        """
        Check if a volume is an audio CD.
        macOS mounts audio CDs with .aiff track files.

        Args:
            volume_path: Path to volume

        Returns:
            True if it appears to be an audio CD
        """
        try:
            for item in volume_path.iterdir():
                if item.suffix.lower() in AUDIO_CD_EXTENSIONS:
                    return True
        except (PermissionError, OSError):
            pass
        return False

    def get_disc_type(self, volume_path: Path) -> str:
        """
        Determine the type of disc.

        Args:
            volume_path: Path to volume

        Returns:
            'dvd', 'bluray', 'audio_cd', or 'unknown'
        """
        if (volume_path / "VIDEO_TS").exists():
            return "dvd"
        if (volume_path / "BDMV").exists():
            return "bluray"
        if self.is_audio_cd(volume_path):
            return "audio_cd"
        return "unknown"

    def get_audio_cd_info(self, volume_path: Path) -> dict:
        """
        Extract information from an audio CD for metadata lookup.

        Args:
            volume_path: Path to the mounted audio CD

        Returns:
            Dict with track_count, total_duration, track_durations, etc.
        """
        import subprocess

        info = {
            "track_count": 0,
            "total_duration_seconds": 0,
            "track_durations": [],
            "track_files": [],
        }
        try:
            audio_files = sorted(
                [
                    f
                    for f in volume_path.iterdir()
                    if f.suffix.lower() in {".aiff", ".aif", ".wav", ".cda"}
                ]
            )
            info["track_count"] = len(audio_files)
            info["track_files"] = [str(f) for f in audio_files]
            if audio_files:
                info["sample_track_path"] = str(audio_files[0])

            for audio_file in audio_files:
                try:
                    result = subprocess.run(
                        [
                            self._ffprobe,
                            "-v",
                            "quiet",
                            "-print_format",
                            "json",
                            "-show_format",
                            str(audio_file),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    data = json.loads(result.stdout)
                    duration = float(data.get("format", {}).get("duration", 0))
                    info["track_durations"].append(duration)
                    info["total_duration_seconds"] += duration
                except Exception as e:
                    self.logger.debug("ffprobe failed for %s: %s", audio_file.name, e)

            self.logger.info(
                f"Audio CD info: {info['track_count']} tracks, "
                f"{info['total_duration_seconds']:.0f}s total"
            )
        except Exception as e:
            self.logger.error("Error reading audio CD info: %s", e)
        return info

    def get_dvd_disc_hints(self, volume_path: Path) -> dict:
        """
        Extract hints from a DVD disc for better TMDB matching.
        Parses IFO files, checks for disc label patterns, estimates runtime.

        Args:
            volume_path: Path to DVD volume

        Returns:
            Dict with hints: estimated_runtime_min, title_count, disc_label, etc.
        """
        import subprocess

        hints = {
            "disc_label": volume_path.name,
            "estimated_runtime_min": None,
            "title_count": 0,
        }
        try:
            # Use HandBrake scan to get title info including duration
            result = subprocess.run(
                [self._handbrake, "--scan", "--input", str(volume_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            scan_output = result.stderr or ""

            # Parse title durations from scan output
            import re

            duration_matches = re.findall(r"\+ duration:\s+(\d+):(\d+):(\d+)", scan_output)
            if duration_matches:
                hints["title_count"] = len(duration_matches)
                # Pick the longest title as the main feature
                durations_min = []
                for h, m, s in duration_matches:
                    dur = int(h) * 60 + int(m) + int(s) / 60
                    durations_min.append(dur)
                hints["estimated_runtime_min"] = round(max(durations_min))
                self.logger.info(
                    f"DVD hints: {hints['title_count']} titles, "
                    f"longest ~{hints['estimated_runtime_min']} min"
                )
        except Exception as e:
            self.logger.debug("Could not get DVD hints: %s", e)
        return hints

    def extract_title_from_volume(self, volume_name: str) -> str:
        """
        Extract a clean title from volume name

        Args:
            volume_name: Raw volume name

        Returns:
            Cleaned title
        """
        # Remove common disc markers
        title = volume_name.replace("_", " ")
        title = title.replace("DISC", "").replace("DVD", "").strip()

        # Remove trailing numbers that look like disc numbers (1-4)
        # but keep numbers that could be part of a real title (e.g. "2001")
        parts = title.split()
        if len(parts) > 1 and parts[-1].isdigit():
            num = int(parts[-1])
            if num < 5 and num > 0:
                parts = parts[:-1]
                title = " ".join(parts)

        return title.strip()

    def process_disc(self, volume_name: str):
        """
        Process a newly detected disc.
        Detects disc type (DVD/Blu-ray/Audio CD), collects disc hints,
        and enqueues a job (or falls back to direct ripping).

        Args:
            volume_name: Name of the volume
        """
        volume_path = self.mount_path / volume_name

        self.logger.info("Processing new disc: %s", volume_name)
        send_notification("Disc Detected", f"Found: {volume_name}")

        disc_type = self.get_disc_type(volume_path)
        title_guess = self.extract_title_from_volume(volume_name)
        self.logger.info("Disc type: %s, title guess: %s", disc_type, title_guess)

        # Collect disc hints for better metadata matching
        disc_hints = {"disc_type": disc_type}
        if disc_type == "audio_cd":
            disc_hints.update(self.get_audio_cd_info(volume_path))
        elif disc_type in ("dvd", "bluray"):
            disc_hints.update(self.get_dvd_disc_hints(volume_path))

        # If we have app_state, use the job queue
        if self.app_state:
            job_id = self.app_state.create_job(
                title=title_guess,
                source_path=str(volume_path),
                title_number=1,
                disc_type=disc_type,
                disc_hints=disc_hints,
            )
            self.logger.info("Enqueued rip job %s for: %s (%s)", job_id, volume_name, disc_type)
            self.app_state.broadcast(
                "disc_detected",
                {"volume_name": volume_name, "job_id": job_id, "disc_type": disc_type},
            )
            return

        # Fallback: direct ripping (standalone mode)
        try:
            self.logger.info("Starting direct rip for: %s (%s)", volume_name, disc_type)

            if disc_type == "audio_cd":
                output_file = self.ripper.rip_audio_cd(
                    source_path=str(volume_path), album_name=title_guess
                )
            else:
                output_file = self.ripper.rip_disc(
                    source_path=str(volume_path), title_name=title_guess
                )

            if output_file:
                self.logger.info("Rip successful: %s", output_file)

                if self.config["metadata"]["save_to_json"]:
                    self.logger.info("Extracting metadata...")
                    metadata = self.metadata_extractor.extract_full_metadata(
                        output_file, title_hint=title_guess, disc_hints=disc_hints
                    )
                    self.metadata_extractor.save_metadata(metadata, title_guess)
                    self.logger.info("Metadata extraction complete")

                send_notification("All Done!", f"{title_guess} is ready")
            else:
                self.logger.error("Rip failed for: %s", volume_name)

        except Exception as e:
            self.logger.error("Error processing disc %s: %s", volume_name, e)
            send_notification("Error", f"Failed to process {volume_name}")

    def check_for_new_discs(self):
        """Check for newly inserted discs"""
        current_volumes = self.get_mounted_volumes()

        # Find new volumes
        new_volumes = current_volumes - self.known_volumes

        # Find removed volumes
        removed_volumes = self.known_volumes - current_volumes

        # Update known volumes
        self.known_volumes = current_volumes

        # Log changes
        if removed_volumes:
            for vol in removed_volumes:
                self.logger.info("Disc removed: %s", vol)

        # Process new discs
        if new_volumes:
            for vol in new_volumes:
                self.logger.info("New disc detected: %s", vol)

                if self.config["automation"]["auto_detect_disc"]:
                    # Process in a try block to prevent one failure from stopping monitoring
                    try:
                        self.process_disc(vol)
                    except Exception as e:
                        self.logger.error("Error processing disc: %s", e)
                else:
                    send_notification("Disc Detected", f"{vol} - auto-rip disabled")

    def start(self):
        """Start monitoring for discs"""
        self.logger.info("Starting disc monitoring...")
        self.running = True

        # Initial scan — also process any discs already present
        self.known_volumes = self.get_mounted_volumes()
        self.logger.info("Initial volumes: %s", self.known_volumes)

        if self.known_volumes and self.config["automation"].get("auto_detect_disc", True):
            for vol in self.known_volumes:
                self.logger.info("Processing disc present at startup: %s", vol)
                try:
                    self.process_disc(vol)
                except Exception as e:
                    self.logger.error("Error processing startup disc: %s", e)

        print("🔍 Disc monitor started")
        print(f"📀 Watching: {self.mount_path}")
        print(f"⏱️  Check interval: {self.check_interval} seconds")
        auto_rip = self.config["automation"]["auto_detect_disc"]
        print(f"🤖 Auto-rip: {'Enabled' if auto_rip else 'Disabled'}")
        print("\nWaiting for discs... (Press Ctrl+C to stop)\n")

        send_notification("Disc Monitor Started", "Watching for media")

        try:
            while self.running:
                self.check_for_new_discs()
                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal")
            self.stop()

    def stop(self):
        """Stop monitoring"""
        self.logger.info("Stopping disc monitoring...")
        self.running = False
        send_notification("Disc Monitor Stopped", "No longer watching for media")
        print("\n👋 Disc monitor stopped")


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    print("\nReceived shutdown signal...")
    sys.exit(0)


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Monitor for disc insertion")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    parser.add_argument(
        "--no-auto-rip", action="store_true", help="Disable automatic ripping (notify only)"
    )

    args = parser.parse_args()

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create monitor
    monitor = DiscMonitor(config_path=args.config)

    # Override auto-rip if requested
    if args.no_auto_rip:
        monitor.config["automation"]["auto_detect_disc"] = False

    # Start monitoring
    monitor.start()


if __name__ == "__main__":
    main()
