"""
Distributed tracing — request-ID propagation and span tracking.

Provides Flask middleware that:
1. Extracts or generates a ``X-Request-ID`` / ``traceparent`` header.
2. Stores trace context in thread-local storage accessible everywhere.
3. Injects trace IDs into the structured log context.
4. Measures request latency and records it as a span.

The implementation is intentionally lightweight (no OpenTelemetry SDK
dependency) but produces W3C Trace Context-compatible ``trace_id`` /
``span_id`` pairs so traces can be correlated with external systems if
one is later adopted.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from flask import Flask, g, request

from .logging import clear_log_context, set_log_context

# ── Trace context ────────────────────────────────────────────────

_trace_local = threading.local()


@dataclass
class TraceContext:
    """Immutable trace context for the current operation."""

    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    operation: str = ""
    start_time: float = field(default_factory=time.monotonic)
    attributes: Dict[str, Any] = field(default_factory=dict)


def get_trace_context() -> Optional[TraceContext]:
    """Return the active ``TraceContext`` for the current thread, or ``None``."""
    return getattr(_trace_local, "ctx", None)


def set_trace_context(ctx: TraceContext) -> None:
    """Set the trace context for the current thread."""
    _trace_local.ctx = ctx


def clear_trace_context() -> None:
    """Remove the trace context from the current thread."""
    _trace_local.ctx = None


def _new_id(length: int = 32) -> str:
    """Generate a random hex ID (32 chars = 128-bit trace id, 16 = 64-bit span)."""
    return uuid.uuid4().hex[:length]


# ── Flask Middleware ─────────────────────────────────────────────


class RequestTracer:
    """Flask middleware: assigns trace/request IDs and measures latency.

    Usage::

        tracer = RequestTracer(app)
    """

    # Header used for request-id propagation
    REQUEST_ID_HEADER = "X-Request-ID"
    TRACEPARENT_HEADER = "traceparent"

    def __init__(self, app: Flask, *, logger=None, metrics=None):
        """
        Args:
            app: The Flask application.
            logger: Optional logger for per-request logs.
            metrics: Optional ``MetricsCollector`` to record latency/traffic.
        """
        self.app = app
        self.logger = logger
        self.metrics = metrics
        self._install(app)

    # ── installation ─────────────────────────────────────────────

    def _install(self, app: Flask) -> None:
        app.before_request(self._before)
        app.after_request(self._after)
        app.teardown_request(self._teardown)

    # ── hooks ────────────────────────────────────────────────────

    def _before(self) -> None:
        trace_id, parent_span = self._extract_trace_id()
        span_id = _new_id(16)

        ctx = TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span,
            operation=f"{request.method} {request.path}",
            start_time=time.monotonic(),
        )
        set_trace_context(ctx)

        # Also inject into Flask ``g`` for easy template/route access
        g.trace_id = trace_id
        g.request_id = trace_id  # alias
        g.span_id = span_id

        # Push into structured log context
        user_id = (
            getattr(request, "current_user", {}).get("username")
            if hasattr(request, "current_user")
            else None
        )
        set_log_context(
            request_id=trace_id,
            trace_id=trace_id,
            span_id=span_id,
            user_id=user_id or "anonymous",
            method=request.method,
            path=request.path,
        )

        # Record traffic metric
        if self.metrics:
            self.metrics.inc(
                "http_requests_total",
                labels={"method": request.method, "path": request.path},
            )

    def _after(self, response):
        ctx = get_trace_context()
        if ctx:
            duration_ms = (time.monotonic() - ctx.start_time) * 1000

            # Inject trace ID into response headers for client correlation
            response.headers[self.REQUEST_ID_HEADER] = ctx.trace_id
            response.headers["X-Trace-ID"] = ctx.trace_id

            # Set the user_id after auth middleware has run
            user_id = None
            if hasattr(request, "current_user") and request.current_user:
                user_id = request.current_user.get("username")
                set_log_context(user_id=user_id)

            # Record latency metric
            if self.metrics:
                self.metrics.observe(
                    "http_request_duration_ms",
                    duration_ms,
                    labels={
                        "method": request.method,
                        "path": request.path,
                        "status": str(response.status_code),
                    },
                )
                # Record error metric
                if response.status_code >= 400:
                    self.metrics.inc(
                        "http_errors_total",
                        labels={
                            "method": request.method,
                            "path": request.path,
                            "status": str(response.status_code),
                        },
                    )

            # Log the request
            if self.logger:
                log_method = (
                    self.logger.warning if response.status_code >= 400 else self.logger.info
                )
                log_method(
                    "%s %s %s %.1fms",
                    request.method,
                    request.path,
                    response.status_code,
                    duration_ms,
                    extra={
                        "duration_ms": round(duration_ms, 2),
                        "status_code": response.status_code,
                        "user_id": user_id or "anonymous",
                    },
                )

        return response

    def _teardown(self, exc=None) -> None:
        clear_trace_context()
        clear_log_context()

    # ── header parsing ───────────────────────────────────────────

    def _extract_trace_id(self) -> tuple[str, Optional[str]]:
        """Extract trace ID from incoming headers or generate a new one.

        Supports:
        * ``X-Request-ID`` (simple propagation)
        * ``traceparent`` (W3C Trace Context)

        Returns:
            (trace_id, parent_span_id | None)
        """
        # W3C traceparent: 00-<trace_id>-<parent_span_id>-<flags>
        tp = request.headers.get(self.TRACEPARENT_HEADER, "")
        if tp:
            parts = tp.split("-")
            if len(parts) >= 4 and len(parts[1]) == 32:
                return parts[1], parts[2]

        # Simple X-Request-ID
        rid = request.headers.get(self.REQUEST_ID_HEADER, "")
        if rid:
            return rid, None

        # Generate fresh
        return _new_id(32), None


# ── Background-job tracing helper ────────────────────────────────


def trace_background_job(job_type: str, job_id: str) -> TraceContext:
    """Create and activate a ``TraceContext`` for a background job.

    Args:
        job_type: E.g. ``"rip"``, ``"download"``, ``"podcast_check"``.
        job_id: The unique job identifier.

    Returns:
        The active ``TraceContext`` (also stored in thread-local).
    """
    ctx = TraceContext(
        trace_id=_new_id(32),
        span_id=_new_id(16),
        operation=f"job:{job_type}",
        attributes={"job_id": job_id, "job_type": job_type},
    )
    set_trace_context(ctx)
    set_log_context(
        trace_id=ctx.trace_id,
        span_id=ctx.span_id,
        job_id=job_id,
        operation=ctx.operation,
    )
    return ctx


def end_background_trace() -> Optional[float]:
    """End the current background trace and return duration in ms."""
    ctx = get_trace_context()
    duration_ms = None
    if ctx:
        duration_ms = (time.monotonic() - ctx.start_time) * 1000
    clear_trace_context()
    clear_log_context()
    return duration_ms
