"""
Centralised constants for the MediaLibrary application.

All magic numbers, extension sets, thresholds and default values live here
so they can be imported by any module without circular dependencies.
"""

from pathlib import Path

# ── Version ──────────────────────────────────────────────────────
APP_VERSION = "0.3.0"
APP_USER_AGENT = f"MediaLibrary/{APP_VERSION} (https://github.com/bpoppe/MediaLibrary)"

# ── Default paths ────────────────────────────────────────────────
DEFAULT_MEDIA_ROOT = Path.home() / "Media"
DEFAULT_CONFIG_PATH = "config.json"

# ── File extension sets ──────────────────────────────────────────
VIDEO_EXTENSIONS = frozenset(
    {
        ".mp4",
        ".mkv",
        ".avi",
        ".m4v",
        ".mov",
        ".webm",
        ".flv",
        ".wmv",
    }
)
AUDIO_EXTENSIONS = frozenset(
    {
        ".mp3",
        ".flac",
        ".wav",
        ".aac",
        ".m4a",
        ".ogg",
        ".wma",
        ".aiff",
        ".opus",
    }
)
IMAGE_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".bmp",
        ".tiff",
        ".svg",
    }
)
DOCUMENT_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".html",
        ".htm",
        ".txt",
        ".md",
        ".epub",
        ".mobi",
    }
)
# Audio CD source formats (macOS / Linux mounts)
AUDIO_CD_EXTENSIONS = frozenset({".aiff", ".aif", ".wav", ".cda"})
# All extensions the library scanner should index
ALL_MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS

# ── MIME type mapping ────────────────────────────────────────────
MIME_TYPES: dict[str, str] = {
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".flv": "video/x-flv",
    ".wmv": "video/x-ms-wmv",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".opus": "audio/opus",
    ".wma": "audio/x-ms-wma",
    ".aiff": "audio/aiff",
}

# ── Streaming / HTTP ─────────────────────────────────────────────
STREAM_CHUNK_SIZE = 256 * 1024  # 256 KB — used for range-request streaming

# ── Logging ──────────────────────────────────────────────────────
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per log file
LOG_BACKUP_COUNT = 5

# ── Auth ─────────────────────────────────────────────────────────
# Use pbkdf2 instead of scrypt — Python 3.9 + LibreSSL lacks hashlib.scrypt
PW_HASH_METHOD = "pbkdf2:sha256"
DEFAULT_SESSION_HOURS = 24

# ── Playback ─────────────────────────────────────────────────────
PLAYBACK_FINISH_THRESHOLD = 0.95  # mark as finished when 95 % watched

# ── AcoustID / MusicBrainz ───────────────────────────────────────
MIN_ACOUSTID_SCORE = 0.6
MB_RATE_LIMIT_SECONDS = 1.1  # MusicBrainz requires ≤ 1 request/second
MB_DURATION_TOLERANCE_SECONDS = 15  # avg seconds diff before rejecting a match

# ── Library scanner ──────────────────────────────────────────────
LIBRARY_SKIP_DIRS = frozenset({"data", ".cache"})

# ── macOS system volumes to ignore during disc detection ─────────
IGNORE_VOLUMES = frozenset(
    {
        "Macintosh HD",
        "Macintosh HD - Data",
        "Preboot",
        "Recovery",
        "VM",
        "com.apple.TimeMachine.localsnapshots",
    }
)
