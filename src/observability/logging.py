"""
Structured JSON logging with context enrichment.

Replaces the plain-text ``setup_logger`` for production use while keeping
backward-compatible signatures.  Every log line is a single JSON object with
guaranteed keys: ``timestamp``, ``level``, ``logger``, ``message``,
``service``, and optional contextual fields (``request_id``, ``user_id``,
``thread``, ``func``, ``line``).
"""

import json
import logging
import os
import sys
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

from ..constants import APP_VERSION, LOG_BACKUP_COUNT, LOG_MAX_BYTES

# Thread-local storage for per-request context (request_id, user_id, etc.)
_context = threading.local()

# Default service name — overridable via LOG_SERVICE_NAME env var
SERVICE_NAME: str = os.environ.get("LOG_SERVICE_NAME", "medialibrary")


def set_log_context(**kwargs: Any) -> None:
    """Attach key-value pairs to the current thread's log context.

    Typical usage inside Flask ``before_request``::

        set_log_context(request_id=rid, user_id=uid)
    """
    if not hasattr(_context, "data"):
        _context.data = {}
    _context.data.update(kwargs)


def clear_log_context() -> None:
    """Remove all per-request context from the current thread."""
    _context.data = {}


def get_log_context() -> Dict[str, Any]:
    """Return a *copy* of the current thread's context dict."""
    return dict(getattr(_context, "data", {}))


# ── JSON Formatter ───────────────────────────────────────────────


class _JsonFormatter(logging.Formatter):
    """Emit each record as a single-line JSON object."""

    # Keys that are promoted from ``extra`` to the top-level JSON.
    _PROMOTE_KEYS = frozenset(
        {
            "request_id",
            "user_id",
            "trace_id",
            "span_id",
            "operation",
            "duration_ms",
            "status_code",
            "method",
            "path",
            "error_type",
            "job_id",
            "media_id",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        entry: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": SERVICE_NAME,
            "version": APP_VERSION,
            "thread": record.threadName,
        }

        # Add source location for DEBUG / ERROR+
        if record.levelno <= logging.DEBUG or record.levelno >= logging.ERROR:
            entry["func"] = record.funcName
            entry["line"] = record.lineno
            entry["file"] = record.pathname

        # Merge thread-local context
        ctx = get_log_context()
        if ctx:
            entry.update(ctx)

        # Promote well-known extra keys
        for key in self._PROMOTE_KEYS:
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val

        # Exception info
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
            entry["error_type"] = record.exc_info[0].__name__

        return json.dumps(entry, default=str, ensure_ascii=False)


# ── Plain Formatter (dev / console) ─────────────────────────────


class _DevFormatter(logging.Formatter):
    """Human-readable coloured output for local development."""

    _COLORS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[35m",  # magenta
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self._COLORS.get(record.levelname, "")
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
        ctx = get_log_context()
        rid = ctx.get("request_id", "")
        prefix = f"[{rid[:8]}] " if rid else ""
        base = (
            f"{color}{ts} {record.levelname:<8}{self._RESET} "
            f"{record.name} {prefix}{record.getMessage()}"
        )
        if record.exc_info and record.exc_info[0] is not None:
            base += "\n" + self.formatException(record.exc_info)
        return base


# ── Logger Factory ───────────────────────────────────────────────


class StructuredLogger:
    """Thin wrapper that returns a stdlib ``logging.Logger`` with JSON output."""

    def __init__(self, name: str, log_file: str, *, level: int = None, debug: bool = False):
        self._logger = _build_logger(name, log_file, level=level, debug=debug)

    def __getattr__(self, item: str):
        return getattr(self._logger, item)


def setup_structured_logger(
    name: str,
    log_file: str,
    *,
    level: Optional[int] = None,
    debug: bool = False,
) -> logging.Logger:
    """Create (or retrieve) a structured JSON logger.

    Signature mirrors ``utils.setup_logger`` so callers can switch with a
    one-line import change.

    Args:
        name: Logger name.
        log_file: Filename under ``logs/``.
        level: Explicit level (overrides *debug*).
        debug: If ``True``, sets level to ``DEBUG``.

    Returns:
        A configured ``logging.Logger``.
    """
    return _build_logger(name, log_file, level=level, debug=debug)


def _build_logger(
    name: str,
    log_file: str,
    *,
    level: Optional[int] = None,
    debug: bool = False,
) -> logging.Logger:
    if level is None:
        level = logging.DEBUG if debug else logging.INFO

    base_dir = Path(__file__).parent.parent.parent
    log_path = base_dir / "logs" / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        for h in logger.handlers:
            h.setLevel(level)
        return logger

    # ── JSON file handler ────────────────────────────────────────
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(_JsonFormatter())

    # ── Console handler — JSON in prod, coloured in dev ──────────
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)

    use_json_console = os.environ.get("LOG_FORMAT", "").lower() == "json"
    if use_json_console:
        console_handler.setFormatter(_JsonFormatter())
    else:
        console_handler.setFormatter(_DevFormatter())

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
