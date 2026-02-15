"""
Utility functions for the media ripper application
"""

import logging
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

from .constants import (
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    DEFAULT_MEDIA_ROOT,
    LOG_MAX_BYTES,
    LOG_BACKUP_COUNT,
)
from .config import load_config, validate_config, ConfigError  # noqa: F401 — re-export

load_dotenv()

# Module-level flag for notification suppression
_notifications_enabled = True


def get_media_root() -> Path:
    """Return the media root directory from MEDIA_ROOT env var or config default."""
    return Path(os.environ.get("MEDIA_ROOT", str(DEFAULT_MEDIA_ROOT)))


def get_data_dir() -> Path:
    """Return the data directory (db, metadata, thumbnails) under MEDIA_ROOT."""
    d = get_media_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def configure_notifications(enabled: bool):
    """Enable or disable desktop notifications globally"""
    global _notifications_enabled
    _notifications_enabled = enabled


def setup_logger(name: str, log_file: str, level=None, debug: bool = False) -> logging.Logger:
    """
    Setup a logger with file and console output

    Args:
        name: Logger name
        log_file: Log file path
        level: Logging level (overrides debug flag if provided)
        debug: If True, set level to DEBUG

    Returns:
        Configured logger
    """
    if level is None:
        level = logging.DEBUG if debug else logging.INFO

    base_dir = Path(__file__).parent.parent
    log_path = base_dir / "logs" / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate handlers
    if logger.handlers:
        # Update existing handler levels if debug mode changed
        for handler in logger.handlers:
            handler.setLevel(level)
        return logger

    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
    )
    file_handler.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)

    # Formatter — include function name in debug mode
    if debug:
        fmt = "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
    else:
        fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing invalid characters

    Args:
        filename: Original filename

    Returns:
        Sanitized filename
    """
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, "_")

    # Remove leading/trailing spaces and dots
    filename = filename.strip(". ")

    return filename


def format_size(size_bytes: int) -> str:
    """
    Format byte size to human-readable string

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 GB")
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def format_time(seconds: int) -> str:
    """
    Format seconds to HH:MM:SS

    Args:
        seconds: Time in seconds

    Returns:
        Formatted time string
    """
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def ensure_directory(path: str) -> Path:
    """
    Ensure directory exists, create if it doesn't

    Args:
        path: Directory path

    Returns:
        Path object
    """
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def send_notification(title: str, message: str):
    """
    Send macOS notification (respects notification_enabled config)

    Args:
        title: Notification title
        message: Notification message
    """
    if not _notifications_enabled:
        return
    try:
        import subprocess as _sp

        script = (
            f'display notification "{_escape_applescript(message)}" '
            f'with title "{_escape_applescript(title)}"'
        )
        _sp.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except Exception:
        pass  # Silently fail if notifications don't work


def _escape_applescript(text: str) -> str:
    """Escape a string for safe use inside AppleScript double-quotes."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def print_progress(
    percent: float, eta: str = None, fps: float = None, title: str = "", width: int = 40
):
    """
    Print a progress bar to the terminal (overwrites current line).

    Args:
        percent: Progress 0-100
        eta: Estimated time remaining
        fps: Frames per second
        title: Current title being processed
        width: Width of the progress bar in characters
    """
    filled = int(width * percent / 100)
    bar = "█" * filled + "░" * (width - filled)
    parts = [f"\r  [{bar}] {percent:5.1f}%"]
    if fps:
        parts.append(f" {fps:.1f} fps")
    if eta:
        parts.append(f" ETA {eta}")
    if title:
        # Truncate long titles
        short = title[:25] + "…" if len(title) > 25 else title
        parts.append(f" | {short}")
    line = "".join(parts)
    sys.stdout.write(line.ljust(100))
    sys.stdout.flush()
    if percent >= 100:
        sys.stdout.write("\n")


# ── Natural (numeric-aware) sorting ──────────────────────────────


def natural_sort_key(path: Path):
    """
    Sort key that orders embedded numbers numerically so that
    'Track 2' sorts before 'Track 10'.

    Args:
        path: A Path object whose *name* is used for ordering

    Returns:
        A list of alternating str/int chunks suitable for sorted().
    """
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", path.name)]


# ── File Renaming with Metadata ──────────────────────────────────


def rename_with_metadata(file_path: str, metadata: Dict[str, Any], logger=None) -> Optional[str]:
    """
    Rename a media file using verified metadata.
    Video: 'Title (Year).ext'
    Falls back to original name if metadata is insufficient.

    Args:
        file_path: Current file path
        metadata: Metadata dict (with 'tmdb' or 'musicbrainz' key)
        logger: Optional logger

    Returns:
        New file path, or original if rename not possible/needed
    """
    path = Path(file_path)
    if not path.exists():
        return file_path

    tmdb = metadata.get("tmdb", {})
    title = tmdb.get("title")
    year = tmdb.get("year")

    if not title:
        if logger:
            logger.debug("No metadata title for rename: %s", file_path)
        return file_path

    # Build new filename: Title (Year).ext
    if year:
        new_stem = f"{sanitize_filename(title)} ({year})"
    else:
        new_stem = sanitize_filename(title)

    new_name = f"{new_stem}{path.suffix}"

    # Files are already ripped into movies/ — rename in place
    new_path = path.parent / new_name

    # Handle collision
    new_path = _resolve_collision(new_path)

    if new_path == path:
        return file_path

    try:
        shutil.move(str(path), str(new_path))
        if logger:
            logger.info("Renamed: %s -> %s", path.name, new_path.name)
        return str(new_path)
    except Exception as e:
        if logger:
            logger.error("Rename failed: %s", e)
        return file_path


def reorganize_audio_album(
    album_dir: str, metadata: Dict[str, Any], base_output_dir: str, logger=None
) -> Optional[str]:
    """
    Reorganize audio album tracks using MusicBrainz metadata.
    Creates: Artist/Album (Year)/## - Title.mp3

    Args:
        album_dir: Current album directory path
        metadata: Metadata dict with 'musicbrainz' key
        base_output_dir: Root output directory
        logger: Optional logger

    Returns:
        New album directory path, or original if reorganize not possible
    """
    mb = metadata.get("musicbrainz", {})
    album_title = mb.get("title")
    artist = mb.get("artist", "Unknown Artist")
    year = mb.get("year")
    tracks = mb.get("tracks", [])

    if not album_title:
        if logger:
            logger.debug("No MusicBrainz title for audio rename: %s", album_dir)
        return album_dir

    src = Path(album_dir)
    if not src.is_dir():
        return album_dir

    # Build new directory: Artist/Album (Year)/
    safe_artist = sanitize_filename(artist)
    if year:
        safe_album = f"{sanitize_filename(album_title)} ({year})"
    else:
        safe_album = sanitize_filename(album_title)

    new_dir = Path(base_output_dir) / "music" / safe_artist / safe_album
    new_dir.mkdir(parents=True, exist_ok=True)

    # Rename each track – use natural sort so '02 - …' < '10 - …'
    track_files = sorted(
        [f for f in src.iterdir() if f.suffix.lower() in AUDIO_EXTENSIONS],
        key=natural_sort_key,
    )

    for i, track_file in enumerate(track_files):
        # Use MusicBrainz track title if available
        if i < len(tracks) and tracks[i].get("title"):
            track_title = sanitize_filename(tracks[i]["title"])
            raw_track_title = tracks[i]["title"]
        else:
            track_title = track_file.stem
            raw_track_title = track_file.stem

        track_num = i + 1
        new_name = f"{track_num:02d} - {track_title}{track_file.suffix}"
        dest = new_dir / new_name
        dest = _resolve_collision(dest)

        try:
            shutil.move(str(track_file), str(dest))
            # Update ID3 tags with real metadata
            if dest.suffix.lower() == ".mp3" and album_title:
                _update_mp3_tags(
                    dest,
                    artist,
                    album_title,
                    raw_track_title,
                    track_num,
                    len(track_files),
                    year,
                    logger,
                )
        except Exception as e:
            if logger:
                logger.error("Failed to move track %s: %s", track_file.name, e)

    # Remove old empty directory
    try:
        if src != new_dir and not any(src.iterdir()):
            src.rmdir()
    except Exception:
        pass

    if logger:
        logger.info("Reorganized album: %s/%s", safe_artist, safe_album)
    return str(new_dir)


def _resolve_collision(path: Path) -> Path:
    """Append (2), (3), etc. if file/dir already exists"""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _update_mp3_tags(
    file_path: Path,
    artist: str,
    album: str,
    title: str,
    track_num: int,
    total_tracks: int,
    year: Optional[str] = None,
    logger=None,
):
    """
    Rewrite ID3 tags on an MP3 file using ffmpeg.
    Creates a temp copy with updated tags, then replaces the original.
    """
    import subprocess
    import tempfile

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
    os.close(tmp_fd)

    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(file_path),
            "-codec",
            "copy",
            "-id3v2_version",
            "3",
            "-metadata",
            f"artist={artist}",
            "-metadata",
            f"album={album}",
            "-metadata",
            f"title={title}",
            "-metadata",
            f"track={track_num}/{total_tracks}",
        ]
        if year:
            cmd.extend(["-metadata", f"date={year}"])
        cmd.append(tmp_path)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            shutil.move(tmp_path, str(file_path))
        else:
            if logger:
                logger.warning("ffmpeg tag update failed for %s", file_path.name)
            os.unlink(tmp_path)
    except Exception as e:
        if logger:
            logger.warning("Failed to update ID3 tags for %s: %s", file_path.name, e)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def generate_media_id(file_path: str) -> str:
    """Generate a stable, deterministic media ID from file path.

    Args:
        file_path: Absolute path to the media file

    Returns:
        A 12-character hex digest string
    """
    import hashlib

    return hashlib.sha256(file_path.encode()).hexdigest()[:12]


def detect_media_type(filename: str) -> str:
    """
    Detect media type from file extension.

    Returns one of: video, audio, image, document, other
    """
    ext = Path(filename).suffix.lower()

    if ext in VIDEO_EXTENSIONS:
        return "video"
    elif ext in AUDIO_EXTENSIONS:
        return "audio"
    elif ext in IMAGE_EXTENSIONS:
        return "image"
    elif ext in DOCUMENT_EXTENSIONS:
        return "document"
    return "other"
