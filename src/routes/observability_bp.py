"""
Observability routes — health checks, metrics, error dashboard.

Endpoints:
    GET /api/healthz       — JSON health status  (liveness + readiness)
    GET /api/metrics       — Prometheus exposition format
    GET /api/metrics/json  — JSON metrics snapshot
    GET /api/errors/recent — Recent captured errors
    GET /api/errors/summary — Error dedup summary
"""

import os
import time
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify

from ..observability.errors import ErrorTracker
from ..observability.metrics import MetricsCollector

observability_bp = Blueprint("observability", __name__)


def _server():
    return current_app.config["server"]


# ── Health ───────────────────────────────────────────────────────


@observability_bp.route("/api/healthz")
def healthz():
    """Liveness + readiness probe.

    Returns 200 when the service is healthy, 503 otherwise.
    JSON body includes component statuses for dashboards.
    """
    checks = {}
    healthy = True

    # 1. Database connectivity
    try:
        srv = _server()
        conn = srv.app_state._get_conn()
        conn.execute("SELECT 1")
        checks["database"] = {"status": "ok"}
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)}
        healthy = False

    # 2. Disk space on MEDIA_ROOT
    try:
        media_root = os.environ.get("MEDIA_ROOT", str(Path.home() / "Media"))
        stat = os.statvfs(media_root)
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        total_gb = (stat.f_blocks * stat.f_frsize) / (1024 ** 3)
        used_pct = round((1 - stat.f_bavail / stat.f_blocks) * 100, 1) if stat.f_blocks else 0
        disk_ok = free_gb > 1.0  # warn if <1GB free
        checks["disk"] = {
            "status": "ok" if disk_ok else "warning",
            "free_gb": round(free_gb, 2),
            "total_gb": round(total_gb, 2),
            "used_percent": used_pct,
        }
        if not disk_ok:
            healthy = False
    except Exception as e:
        checks["disk"] = {"status": "error", "message": str(e)}

    # 3. Uptime
    mc = MetricsCollector()
    uptime = time.time() - mc._start_time

    payload = {
        "status": "healthy" if healthy else "degraded",
        "uptime_seconds": round(uptime, 1),
        "checks": checks,
    }
    return jsonify(payload), 200 if healthy else 503


# ── Metrics ──────────────────────────────────────────────────────


@observability_bp.route("/api/metrics")
def metrics_prometheus():
    """Prometheus text exposition format."""
    mc = MetricsCollector()
    return Response(mc.prometheus_exposition(), mimetype="text/plain; charset=utf-8")


@observability_bp.route("/api/metrics/json")
def metrics_json():
    """JSON metrics snapshot for custom dashboards."""
    mc = MetricsCollector()

    # Supplement with resource gauges
    try:
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF)
        mc.gauge_set("process_cpu_user_seconds", ru.ru_utime)
        mc.gauge_set("process_cpu_system_seconds", ru.ru_stime)
        mc.gauge_set("process_max_rss_bytes", ru.ru_maxrss)
    except Exception:
        pass

    # Active job count
    try:
        srv = _server()
        active = srv.app_state.get_active_job()
        mc.gauge_set("active_jobs", 1 if active else 0)
    except Exception:
        pass

    return jsonify(mc.snapshot())


# ── Errors ───────────────────────────────────────────────────────


@observability_bp.route("/api/errors/recent")
def errors_recent():
    """Return the most recent captured errors."""
    tracker = ErrorTracker()
    limit = int(current_app.config.get("ERROR_DISPLAY_LIMIT", 50))
    return jsonify(tracker.recent_errors(limit))


@observability_bp.route("/api/errors/summary")
def errors_summary():
    """Return deduplicated error counts."""
    tracker = ErrorTracker()
    return jsonify(tracker.error_summary())
