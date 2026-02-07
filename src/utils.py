"""
Utility functions for the media ripper application
"""
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any
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

