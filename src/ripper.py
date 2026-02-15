"""
Main DVD/CD ripping functionality using HandBrake
"""

import platform
import re
import shutil
import subprocess
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from .config import load_config
from .constants import AUDIO_CD_EXTENSIONS
from .utils import (
    configure_notifications,
    format_time,
    natural_sort_key,
    print_progress,
    sanitize_filename,
    send_notification,
    setup_logger,
)

if TYPE_CHECKING:
    from .app_state import AppState


class Ripper:
    """Handles DVD/CD ripping operations"""

    def __init__(
        self,
        config: Dict[str, Any] = None,
        *,
        config_path: str = None,
        app_state: "AppState" = None,
    ):
        """
        Initialize the Ripper

        Args:
            config: Pre-loaded configuration dict (preferred).
            config_path: Path to configuration file (backward compat).
            app_state: Optional shared AppState for progress reporting.
        """
        self.config = config if config is not None else load_config(config_path or "config.json")
        debug_mode = self.config.get("logging", {}).get("debug", False)
        self.logger = setup_logger("ripper", "ripper.log", debug=debug_mode)
        self.output_dir = Path(self.config["output"]["base_directory"])
        self.app_state = app_state
        self.show_progress = self.config.get("logging", {}).get("progress_indicator", True)

        # Resolve tool paths — use shutil.which so they work even
        # when launched from contexts with a minimal PATH (e.g. launchd)
        self._ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        self._ffprobe = shutil.which("ffprobe") or "ffprobe"
        self._handbrake = shutil.which("HandBrakeCLI") or "HandBrakeCLI"

        # Honour notification config
        notify_enabled = self.config.get("automation", {}).get("notification_enabled", True)
        configure_notifications(notify_enabled)

        self.logger.info("Ripper initialized")

    def check_handbrake_installed(self) -> bool:
        """
        Check if HandBrakeCLI is installed

        Returns:
            True if installed, False otherwise
        """
        try:
            result = subprocess.run([self._handbrake, "--version"], capture_output=True, text=True)
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def detect_disc_info(self, source_path: str) -> Optional[Dict[str, Any]]:
        """
        Detect information about the disc

        Args:
            source_path: Path to disc mount point

        Returns:
            Dictionary with disc information or None
        """
        self.logger.info("Detecting disc info for: %s", source_path)

        try:
            # Use HandBrake to scan the disc
            result = subprocess.run(
                [self._handbrake, "--scan", "--input", source_path],
                capture_output=True,
                text=True,
                timeout=60,
            )

            output = result.stderr  # HandBrake outputs scan to stderr

            # Parse output for basic info
            disc_info = {"source": source_path, "detected": True, "scan_output": output}

            # Try to extract title count
            if "title(s)" in output.lower():
                # Basic parsing - can be enhanced
                disc_info["has_content"] = True

            self.logger.info("Disc detected successfully: %s", source_path)
            return disc_info

        except subprocess.TimeoutExpired:
            self.logger.error("Timeout while scanning disc: %s", source_path)
            return None
        except Exception as e:
            self.logger.error("Error detecting disc: %s", e)
            return None

    def build_handbrake_command(self, source: str, output: str, title: int = 1) -> list:
        """
        Build HandBrakeCLI command

        Args:
            source: Source disc path
            output: Output file path
            title: Title number to rip (default: 1 for main feature)

        Returns:
            Command as list of arguments
        """
        config = self.config["output"]
        hb_config = self.config.get("handbrake", {})

        cmd = [
            self._handbrake,
            "--input",
            source,
            "--output",
            output,
            "--title",
            str(title),
            "--format",
            config["format"],
            "--encoder",
            config["video_encoder"],
            "--quality",
            str(config["quality"]),
            "--aencoder",
            config["audio_encoder"],
            "--ab",
            config["audio_bitrate"],
        ]

        # Add preset if specified
        if "preset" in hb_config:
            cmd.extend(["--preset", hb_config["preset"]])

        # Add subtitle extraction
        if self.config["metadata"]["extract_subtitles"]:
            cmd.extend(["--subtitle", "scan", "--subtitle-burned=none"])

        # Add additional options
        for option in hb_config.get("additional_options", []):
            cmd.append(option)

        return cmd

    def rip_disc(
        self,
        source_path: str,
        title_name: Optional[str] = None,
        title_number: int = 1,
        job_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Rip a DVD/CD to the output directory

        Args:
            source_path: Path to mounted disc
            title_name: Custom name for the output file
            title_number: Title number to rip (1 for main feature)
            job_id: Optional job ID for progress reporting via AppState

        Returns:
            Path to output file if successful, None otherwise
        """
        self.logger.info("Starting rip process for: %s", source_path)

        # Check HandBrake is installed
        if not self.check_handbrake_installed():
            self.logger.error("HandBrakeCLI not found. Please install HandBrake.")
            send_notification("Rip Failed", "HandBrakeCLI not installed")
            return None

        # Warn if libdvdcss is missing (needed for CSS-encrypted DVDs)
        if platform.system() == "Darwin":
            dvdcss_paths = [
                "/usr/local/lib/libdvdcss.dylib",
                "/opt/homebrew/lib/libdvdcss.dylib",
            ]
            if not any(Path(p).exists() for p in dvdcss_paths):
                self.logger.warning(
                    "libdvdcss not found — CSS-protected DVDs will fail to rip. "
                    "Install with: brew install libdvdcss"
                )

        # Detect disc info
        disc_info = self.detect_disc_info(source_path)
        if not disc_info:
            self.logger.error("Failed to detect disc information")
            send_notification("Rip Failed", "Could not read disc")
            return None

        # Generate output filename
        if not title_name:
            # Extract volume name from path
            title_name = Path(source_path).name

        sanitized_name = sanitize_filename(title_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{sanitized_name}_{timestamp}.{self.config['output']['format']}"
        movies_dir = self.output_dir / "movies"
        output_path = movies_dir / output_filename

        # Ensure output directory exists
        movies_dir.mkdir(parents=True, exist_ok=True)

        # Build command
        cmd = self.build_handbrake_command(source_path, str(output_path), title_number)

        self.logger.info("Ripping to: %s", output_path)
        self.logger.debug("Command: %s", " ".join(cmd))

        send_notification("Ripping Started", f"Processing: {title_name}")

        try:
            # Start ripping process
            start_time = time.time()

            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
            )

            # Keep a ring buffer of recent output for error diagnostics
            recent_output = deque(maxlen=30)

            # Monitor progress
            for line in process.stdout:
                line = line.strip()
                if line:
                    recent_output.append(line)
                    # Parse and report progress
                    if "Encoding:" in line or "ETA" in line:
                        # Parse HandBrake progress: "Encoding: task 1 of 1, 45.23 %"
                        pct_match = re.search(r"(\d+\.\d+)\s*%", line)
                        eta_match = re.search(r"ETA\s+(\S+)", line)
                        fps_match = re.search(r"(\d+\.\d+)\s*fps", line)
                        pct = float(pct_match.group(1)) if pct_match else 0.0
                        eta = eta_match.group(1) if eta_match else None
                        fps = float(fps_match.group(1)) if fps_match else None

                        # Console progress bar
                        if self.show_progress:
                            print_progress(pct, eta=eta, fps=fps, title=title_name or "")

                        # WebSocket progress updates
                        if job_id and self.app_state:
                            if pct_match:
                                self.app_state.update_job_progress(
                                    job_id, pct, eta=eta, fps=fps, title=title_name
                                )
                    self.logger.debug(line)

            process.wait()

            elapsed_time = int(time.time() - start_time)

            if process.returncode == 0:
                self.logger.info("Rip completed successfully in %s", format_time(elapsed_time))
                self.logger.info("Output: %s", output_path)
                send_notification("Rip Completed", f"{title_name} finished!")

                # Auto-eject if configured
                if self.config["automation"].get("auto_eject_after_rip", True):
                    self.eject_disc(source_path)

                return str(output_path)
            else:
                self.logger.error("Rip failed with return code: %s", process.returncode)
                if recent_output:
                    tail = "\n".join(recent_output)
                    self.logger.error(
                        f"HandBrake output (last {len(recent_output)} lines):\n{tail}"
                    )
                send_notification("Rip Failed", f"{title_name} encountered an error")
                return None

        except Exception as e:
            self.logger.error("Error during rip process: %s", e)
            send_notification("Rip Failed", str(e))
            return None

    def eject_disc(self, disc_path: str):
        """
        Eject the disc

        Args:
            disc_path: Path to mounted disc
        """
        try:
            subprocess.run(["diskutil", "eject", disc_path], check=True)
            self.logger.info("Ejected disc: %s", disc_path)
        except subprocess.CalledProcessError as e:
            self.logger.warning("Failed to eject disc: %s", e)

    def rip_audio_cd(
        self, source_path: str, album_name: Optional[str] = None, job_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Rip an audio CD to individual track files using ffmpeg.
        macOS mounts audio CDs as .aiff files in /Volumes/<disc>.

        Args:
            source_path: Path to mounted audio CD volume
            album_name: Album name for organising output
            job_id: Optional job ID for progress reporting

        Returns:
            Path to the output directory containing ripped tracks, or None
        """
        self.logger.info("Starting audio CD rip for: %s", source_path)

        volume = Path(source_path)
        if not volume.exists():
            self.logger.error("Source path does not exist: %s", source_path)
            return None

        # Collect audio track files – use natural sort so that
        # 'Track 2' sorts before 'Track 10' (lexicographic sort fails
        # for non-zero-padded filenames on macOS audio CD mounts).
        audio_files = sorted(
            [f for f in volume.iterdir() if f.suffix.lower() in AUDIO_CD_EXTENSIONS],
            key=natural_sort_key,
        )

        if not audio_files:
            self.logger.error("No audio tracks found on disc")
            send_notification("Rip Failed", "No audio tracks found on CD")
            return None

        # Create output directory
        safe_album = sanitize_filename(album_name or volume.name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        music_dir = self.output_dir / "music"
        album_dir = music_dir / f"{safe_album}_{timestamp}"
        album_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info("Ripping %s tracks to: %s", len(audio_files), album_dir)
        send_notification("Ripping Started", f"Audio CD: {album_name or volume.name}")

        total = len(audio_files)
        ripped = 0

        for idx, track_file in enumerate(audio_files, 1):
            track_name = track_file.stem
            output_file = album_dir / f"{idx:02d} - {sanitize_filename(track_name)}.mp3"

            self.logger.info("  Track %s/%s: %s", idx, total, track_name)
            try:
                cmd = [
                    self._ffmpeg,
                    "-y",
                    "-i",
                    str(track_file),
                    "-codec:a",
                    "libmp3lame",
                    "-qscale:a",
                    "2",
                    "-id3v2_version",
                    "3",
                    "-metadata",
                    f"track={idx}/{total}",
                    "-metadata",
                    f"album={album_name or volume.name}",
                    "-metadata",
                    f"title={track_name}",
                    str(output_file),
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode == 0:
                    ripped += 1
                else:
                    stderr_tail = result.stderr.strip().splitlines()[-10:]
                    self.logger.error(
                        f"  ffmpeg failed for track {idx} (exit {result.returncode}):\n"
                        + "\n".join(stderr_tail)
                    )
            except Exception as e:
                self.logger.error("  Error ripping track %s: %s", idx, e)

            # Progress reporting
            pct = (idx / total) * 100
            if self.show_progress:
                print_progress(pct, title=track_name)
            if job_id and self.app_state:
                self.app_state.update_job_progress(job_id, pct, title=track_name)

        if ripped > 0:
            self.logger.info("Audio CD rip completed: %s/%s tracks", ripped, total)
            send_notification("Rip Completed", f"{album_name}: {ripped} tracks")

            if self.config["automation"].get("auto_eject_after_rip", True):
                self.eject_disc(source_path)

            return str(album_dir)
        else:
            self.logger.error("Audio CD rip failed — no tracks ripped")
            send_notification("Rip Failed", f"{album_name}: no tracks ripped")
            return None

    def get_title_list(self, source_path: str) -> list:
        """
        Get list of all titles on the disc

        Args:
            source_path: Path to disc

        Returns:
            List of title numbers
        """
        # This is a simplified version - can be enhanced with proper parsing
        disc_info = self.detect_disc_info(source_path)
        if disc_info:
            # Parse scan output for title count
            # For now, return [1] as main title
            return [1]
        return []


def main():
    """Main entry point for command-line usage"""
    import argparse

    parser = argparse.ArgumentParser(description="Rip DVD/CD media")
    parser.add_argument("--source", required=True, help="Path to disc mount point")
    parser.add_argument("--title", default=None, help="Custom title name")
    parser.add_argument("--title-number", type=int, default=1, help="Title number to rip")
    parser.add_argument("--config", default="config.json", help="Path to config file")

    args = parser.parse_args()

    ripper = Ripper(config_path=args.config)
    output = ripper.rip_disc(args.source, args.title, args.title_number)

    if output:
        print(f"\n✓ Successfully ripped to: {output}")
        return 0
    else:
        print("\n✗ Rip failed. Check logs for details.")
        return 1


if __name__ == "__main__":
    exit(main())
