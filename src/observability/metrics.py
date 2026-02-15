"""
In-process metrics collection — golden signals + business metrics.

Provides counters, gauges, and histograms that are stored in memory and
exposed via a ``/metrics`` endpoint in Prometheus exposition format and
a ``/api/healthz`` JSON endpoint for dashboards.

No external dependency (Prometheus client library) is required — the
collector is self-contained.  If you later adopt ``prometheus_client``,
the metric names are compatible.
"""

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ── Metric types ─────────────────────────────────────────────────


@dataclass
class _Counter:
    """Monotonically increasing counter."""

    value: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def inc(self, amount: float = 1.0) -> None:
        with self.lock:
            self.value += amount


@dataclass
class _Gauge:
    """Value that can go up and down."""

    value: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def set(self, value: float) -> None:
        with self.lock:
            self.value = value

    def inc(self, amount: float = 1.0) -> None:
        with self.lock:
            self.value += amount

    def dec(self, amount: float = 1.0) -> None:
        with self.lock:
            self.value -= amount


@dataclass
class _Histogram:
    """Collect observations and expose count / sum / quantile buckets."""

    count: int = 0
    total: float = 0.0
    buckets: Dict[float, int] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    # Default latency buckets (ms)
    DEFAULT_BUCKETS: tuple = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)

    def __post_init__(self):
        if not self.buckets:
            self.buckets = {b: 0 for b in self.DEFAULT_BUCKETS}
            self.buckets[float("inf")] = 0

    def observe(self, value: float) -> None:
        with self.lock:
            self.count += 1
            self.total += value
            for boundary in self.buckets:
                if value <= boundary:
                    self.buckets[boundary] += 1


def _labels_key(labels: Optional[Dict[str, str]]) -> str:
    """Convert a labels dict to a deterministic hashable string."""
    if not labels:
        return ""
    return ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))


# ── Collector singleton ──────────────────────────────────────────


class MetricsCollector:
    """Thread-safe in-process metrics store.

    Usage::

        mc = MetricsCollector()
        mc.inc("http_requests_total", labels={"method": "GET"})
        mc.observe("http_request_duration_ms", 42.5, labels={"path": "/api/library"})
        mc.gauge_set("active_jobs", 3)
    """

    _instance: Optional["MetricsCollector"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "MetricsCollector":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._counters: Dict[str, _Counter] = defaultdict(_Counter)
        self._gauges: Dict[str, _Gauge] = defaultdict(_Gauge)
        self._histograms: Dict[str, _Histogram] = defaultdict(_Histogram)
        self._start_time = time.time()

    # ── Counters ─────────────────────────────────────────────────

    def inc(
        self, name: str, amount: float = 1.0,
        *, labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Increment a counter metric."""
        key = f"{name}{{{_labels_key(labels)}}}" if labels else name
        self._counters[key].inc(amount)

    # ── Gauges ───────────────────────────────────────────────────

    def gauge_set(
        self, name: str, value: float,
        *, labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Set a gauge to an absolute value."""
        key = f"{name}{{{_labels_key(labels)}}}" if labels else name
        self._gauges[key].set(value)

    def gauge_inc(
        self, name: str, amount: float = 1.0,
        *, labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Increment a gauge."""
        key = f"{name}{{{_labels_key(labels)}}}" if labels else name
        self._gauges[key].inc(amount)

    def gauge_dec(
        self, name: str, amount: float = 1.0,
        *, labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Decrement a gauge."""
        key = f"{name}{{{_labels_key(labels)}}}" if labels else name
        self._gauges[key].dec(amount)

    # ── Histograms ───────────────────────────────────────────────

    def observe(self, name: str, value: float, *, labels: Optional[Dict[str, str]] = None) -> None:
        """Record an observation in a histogram (e.g. latency in ms)."""
        key = f"{name}{{{_labels_key(labels)}}}" if labels else name
        self._histograms[key].observe(value)

    # ── Snapshot / export ────────────────────────────────────────

    def snapshot(self) -> Dict[str, Any]:
        """Return a JSON-friendly snapshot of all metrics."""
        data: Dict[str, Any] = {
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "counters": {},
            "gauges": {},
            "histograms": {},
        }
        for k, c in self._counters.items():
            data["counters"][k] = c.value
        for k, g in self._gauges.items():
            data["gauges"][k] = g.value
        for k, h in self._histograms.items():
            data["histograms"][k] = {
                "count": h.count,
                "sum": round(h.total, 2),
                "avg": round(h.total / h.count, 2) if h.count else 0,
                "buckets": {str(b): v for b, v in sorted(h.buckets.items())},
            }
        return data

    def prometheus_exposition(self) -> str:
        """Return metrics in Prometheus text exposition format."""
        lines: List[str] = []

        lines.append("# HELP uptime_seconds Process uptime in seconds")
        lines.append("# TYPE uptime_seconds gauge")
        lines.append(f"uptime_seconds {time.time() - self._start_time:.1f}")

        for key, c in sorted(self._counters.items()):
            lines.append(f"{key} {c.value}")

        for key, g in sorted(self._gauges.items()):
            lines.append(f"{key} {g.value}")

        for key, h in sorted(self._histograms.items()):
            base = key.split("{")[0]
            labels_part = "{" + key.split("{")[1] if "{" in key else ""
            for boundary, count in sorted(h.buckets.items()):
                le = "+Inf" if boundary == float("inf") else str(boundary)
                if labels_part:
                    lbl = labels_part.rstrip("}") + f',le="{le}"}}'
                else:
                    lbl = f'{{le="{le}"}}'
                lines.append(f"{base}_bucket{lbl} {count}")
            lines.append(f"{base}_sum{labels_part or ''} {h.total:.2f}")
            lines.append(f"{base}_count{labels_part or ''} {h.count}")

        return "\n".join(lines) + "\n"

    # ── Reset (testing) ──────────────────────────────────────────

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for tests)."""
        with cls._lock:
            cls._instance = None
