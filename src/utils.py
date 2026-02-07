"""
Utility functions for the media ripper application
"""
import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from logging.handlers import RotatingFileHandler

# Module-level flag for notification suppression
_notifications_enabled = True


def configure_notifications(enabled: bool):
    """Enable or disable desktop notifications globally"""
    global _notifications_enabled
    _notifications_enabled = enabled


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """
    Load configuration from JSON file
    
    Args:
        config_path: Path to config file
        
    Returns:
        Configuration dictionary
    """
    base_dir = Path(__file__).parent.parent
    full_path = base_dir / config_path
    
    with open(full_path, 'r') as f:
        return json.load(f)


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
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(level)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    
    # Formatter — include function name in debug mode
    if debug:
        fmt = '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    else:
        fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    formatter = logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S')
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
        filename = filename.replace(char, '_')
    
    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')
    
    return filename


def format_size(size_bytes: int) -> str:
    """
    Format byte size to human-readable string
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted string (e.g., "1.5 GB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
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
        os.system(f"""
            osascript -e 'display notification "{message}" with title "{title}"'
        """)
    except Exception:
        pass  # Silently fail if notifications don't work


def print_progress(percent: float, eta: str = None, fps: float = None,
                   title: str = '', width: int = 40):
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
    bar = '█' * filled + '░' * (width - filled)
    parts = [f'\r  [{bar}] {percent:5.1f}%']
    if fps:
        parts.append(f' {fps:.1f} fps')
    if eta:
        parts.append(f' ETA {eta}')
    if title:
        # Truncate long titles
        short = title[:25] + '…' if len(title) > 25 else title
        parts.append(f' | {short}')
    line = ''.join(parts)
    sys.stdout.write(line.ljust(100))
    sys.stdout.flush()
    if percent >= 100:
        sys.stdout.write('\n')


# ── File Renaming with Metadata ──────────────────────────────────

def rename_with_metadata(file_path: str, metadata: Dict[str, Any],
                         logger=None) -> Optional[str]:
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

    tmdb = metadata.get('tmdb', {})
    title = tmdb.get('title')
    year = tmdb.get('year')

    if not title:
        if logger:
            logger.debug(f"No metadata title for rename: {file_path}")
        return file_path

    # Build new filename: Title (Year).ext
    if year:
        new_stem = f"{sanitize_filename(title)} ({year})"
    else:
        new_stem = sanitize_filename(title)

    new_name = f"{new_stem}{path.suffix}"
    new_path = path.parent / new_name

    # Handle collision
    new_path = _resolve_collision(new_path)

    if new_path == path:
        return file_path

    try:
        shutil.move(str(path), str(new_path))
        if logger:
            logger.info(f"Renamed: {path.name} -> {new_path.name}")
        return str(new_path)
    except Exception as e:
        if logger:
            logger.error(f"Rename failed: {e}")
        return file_path


def reorganize_audio_album(album_dir: str, metadata: Dict[str, Any],
                           base_output_dir: str,
                           logger=None) -> Optional[str]:
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
    mb = metadata.get('musicbrainz', {})
    album_title = mb.get('title')
    artist = mb.get('artist', 'Unknown Artist')
    year = mb.get('year')
    tracks = mb.get('tracks', [])

    if not album_title:
        if logger:
            logger.debug(f"No MusicBrainz title for audio rename: {album_dir}")
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

    new_dir = Path(base_output_dir) / safe_artist / safe_album
    new_dir.mkdir(parents=True, exist_ok=True)

    # Rename each track
    audio_exts = {'.mp3', '.flac', '.wav', '.aac', '.m4a', '.ogg', '.aiff'}
    track_files = sorted([
        f for f in src.iterdir()
        if f.suffix.lower() in audio_exts
    ])

    for i, track_file in enumerate(track_files):
        # Use MusicBrainz track title if available
        if i < len(tracks) and tracks[i].get('title'):
            track_title = sanitize_filename(tracks[i]['title'])
        else:
            track_title = track_file.stem

        track_num = i + 1
        new_name = f"{track_num:02d} - {track_title}{track_file.suffix}"
        dest = new_dir / new_name
        dest = _resolve_collision(dest)

        try:
            shutil.move(str(track_file), str(dest))
        except Exception as e:
            if logger:
                logger.error(f"Failed to move track {track_file.name}: {e}")

    # Remove old empty directory
    try:
        if src != new_dir and not any(src.iterdir()):
            src.rmdir()
    except Exception:
        pass

    if logger:
        logger.info(f"Reorganized album: {safe_artist}/{safe_album}")
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


def detect_media_type(filename: str) -> str:
    """
    Detect media type from file extension.

    Returns one of: video, audio, image, document, other
    """
    ext = Path(filename).suffix.lower()
    video_exts = {'.mp4', '.mkv', '.avi', '.m4v', '.mov', '.webm', '.flv', '.wmv'}
    audio_exts = {'.mp3', '.flac', '.wav', '.aac', '.m4a', '.ogg', '.wma', '.aiff', '.opus'}
    image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.svg'}
    doc_exts = {'.pdf', '.html', '.htm', '.txt', '.md', '.epub', '.mobi'}

    if ext in video_exts:
        return 'video'
    elif ext in audio_exts:
        return 'audio'
    elif ext in image_exts:
        return 'image'
    elif ext in doc_exts:
        return 'document'
    return 'other'

