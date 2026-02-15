"""
Centralised error tracking with context enrichment.

Captures unhandled exceptions at every boundary — Flask routes, background
workers, WebSocket handlers — and enriches them with trace context,
user info, and breadcrumbs.

Errors are:
1. Logged via the structured logger.
2. Stored in a bounded in-memory ring buffer for the dashboard.
3. Optionally forwarded to an external service (Sentry DSN via env var).
"""

import os
import sys
import threading
import traceback
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from flask import Flask, request

from .logging import get_log_context, setup_structured_logger
from .tracing import get_trace_context

# ── Error record ─────────────────────────────────────────────────


@dataclass
class ErrorRecord:
    """A single captured error event."""

    timestamp: str
    error_type: str
    message: str
    traceback: str
    context: Dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""  # for dedup grouping

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "error_type": self.error_type,
            "message": self.message,
            "traceback": self.traceback,
            "context": self.context,
            "fingerprint": self.fingerprint,
        }


# ── Error Tracker ────────────────────────────────────────────────

# Maximum number of recent errors kept in memory
_MAX_ERROR_BUFFER = 200


class ErrorTracker:
    """Singleton that captures, deduplicates, and stores errors.

    Usage::

        tracker = ErrorTracker()
        tracker.install_flask(app)

        # In a background worker:
        try:
            do_work()
        except Exception:
            tracker.capture_exception(extra={"job_id": jid})
    """

    _instance: Optional["ErrorTracker"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ErrorTracker":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._buffer: deque[ErrorRecord] = deque(maxlen=_MAX_ERROR_BUFFER)
        self._counts: Dict[str, int] = {}  # fingerprint -> count
        self._logger = setup_structured_logger("error_tracker", "errors.log")
        self._sentry_dsn = os.environ.get("SENTRY_DSN", "")
        self._callbacks: List[Callable[[ErrorRecord], None]] = []

        # Attempt Sentry SDK init if DSN is present
        if self._sentry_dsn:
            try:
                import sentry_sdk  # type: ignore[import-untyped]

                sentry_sdk.init(dsn=self._sentry_dsn, traces_sample_rate=0.1)
                self._logger.info("Sentry SDK initialised")
            except ImportError:
                self._logger.warning("SENTRY_DSN set but sentry-sdk not installed")

    # ── Flask integration ────────────────────────────────────────

    def install_flask(self, app: Flask) -> None:
        """Register a Flask error handler that captures all unhandled exceptions."""

        @app.errorhandler(Exception)
        def _handle_exception(exc: Exception):
            from werkzeug.exceptions import HTTPException

            # Let Flask handle HTTP exceptions (400, 404, etc.) normally
            if isinstance(exc, HTTPException):
                self.capture_exception(exc=exc)
                return exc

            self.capture_exception(exc=exc)
            # Return a JSON error to the client
            from flask import jsonify

            return (
                jsonify(
                    {
                        "error": "Internal Server Error",
                        "request_id": getattr(request, "trace_id", None) or "",
                    }
                ),
                500,
            )

        # Also hook into 404 etc. for tracking
        @app.errorhandler(404)
        def _handle_404(exc):
            return {"error": "Not found"}, 404

    # ── Capture methods ──────────────────────────────────────────

    def capture_exception(
        self,
        exc: Optional[BaseException] = None,
        *,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Optional[ErrorRecord]:
        """Capture an exception with full context.

        Args:
            exc: The exception. If ``None``, uses ``sys.exc_info()``.
            extra: Additional context to attach.

        Returns:
            The ``ErrorRecord``, or ``None`` if nothing to capture.
        """
        if exc is None:
            exc_info = sys.exc_info()
            if exc_info[0] is None:
                return None
            exc = exc_info[1]
        else:
            exc_info = (type(exc), exc, exc.__traceback__)

        tb = "".join(traceback.format_exception(*exc_info))
        fingerprint = f"{type(exc).__name__}:{_extract_location(exc_info)}"

        ctx: Dict[str, Any] = {}
        # Merge trace context
        trace = get_trace_context()
        if trace:
            ctx["trace_id"] = trace.trace_id
            ctx["span_id"] = trace.span_id
            ctx["operation"] = trace.operation
            ctx.update(trace.attributes)

        # Merge log context (request_id, user_id, etc.)
        ctx.update(get_log_context())

        # Merge caller-supplied extras
        if extra:
            ctx.update(extra)

        # Flask request context
        try:
            if request:
                ctx.setdefault("method", request.method)
                ctx.setdefault("path", request.path)
                ctx.setdefault("remote_addr", request.remote_addr)
                if hasattr(request, "current_user") and request.current_user:
                    ctx.setdefault("user_id", request.current_user.get("username"))
        except RuntimeError:
            pass  # Outside request context

        record = ErrorRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            error_type=type(exc).__name__,
            message=str(exc),
            traceback=tb,
            context=ctx,
            fingerprint=fingerprint,
        )

        self._buffer.append(record)
        self._counts[fingerprint] = self._counts.get(fingerprint, 0) + 1

        # Log the error
        self._logger.error(
            "Captured %s: %s",
            record.error_type,
            record.message,
            extra={"error_type": record.error_type, "fingerprint": fingerprint, **ctx},
        )

        # Forward to Sentry if available
        if self._sentry_dsn:
            try:
                import sentry_sdk

                sentry_sdk.capture_exception(exc)
            except Exception:
                pass

        # Invoke registered callbacks
        for cb in self._callbacks:
            try:
                cb(record)
            except Exception:
                pass

        return record

    def on_error(self, callback: Callable[[ErrorRecord], None]) -> None:
        """Register a callback invoked on every captured error."""
        self._callbacks.append(callback)

    # ── Query methods ────────────────────────────────────────────

    def recent_errors(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent errors as dicts."""
        items = list(self._buffer)[-limit:]
        items.reverse()
        return [e.to_dict() for e in items]

    def error_summary(self) -> Dict[str, Any]:
        """Return dedup counts and totals."""
        return {
            "total_captured": sum(self._counts.values()),
            "unique_errors": len(self._counts),
            "top_errors": sorted(
                [{"fingerprint": fp, "count": c} for fp, c in self._counts.items()],
                key=lambda x: x["count"],
                reverse=True,
            )[:20],
        }

    # ── Reset (testing) ──────────────────────────────────────────

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None


def _extract_location(exc_info) -> str:
    """Extract file:line from the innermost traceback frame."""
    tb = exc_info[2]
    if tb is None:
        return "unknown"
    while tb.tb_next:
        tb = tb.tb_next
    return f"{tb.tb_frame.f_code.co_filename}:{tb.tb_lineno}"
