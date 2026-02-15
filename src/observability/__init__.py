"""
Observability package — structured logging, metrics, tracing, and error tracking.

Provides:
- ``StructuredLogger`` / ``setup_structured_logger``: JSON-formatted logging
- ``RequestTracer``: Flask middleware for request-id propagation & tracing
- ``MetricsCollector``: In-process golden-signal & business metrics
- ``ErrorTracker``: Centralised error tracking with context enrichment
- ``PiiScrubber``: Filters sensitive data from log records
"""

from .errors import ErrorTracker
from .logging import StructuredLogger, setup_structured_logger
from .metrics import MetricsCollector
from .pii import PiiScrubber
from .tracing import RequestTracer, get_trace_context

__all__ = [
    "StructuredLogger",
    "setup_structured_logger",
    "RequestTracer",
    "get_trace_context",
    "MetricsCollector",
    "ErrorTracker",
    "PiiScrubber",
]
