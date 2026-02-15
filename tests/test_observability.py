"""
Tests for the observability package: structured logging, PII scrubbing,
metrics, tracing, and error tracking.
"""

import json
import logging
import threading

# ── Structured Logging ───────────────────────────────────────────


class TestStructuredLogging:
    """Tests for src.observability.logging."""

    def test_setup_structured_logger_returns_logger(self):
        from src.observability.logging import setup_structured_logger

        logger = setup_structured_logger("test_obs_log", "test_obs.log")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_obs_log"

    def test_json_formatter_output(self):
        from src.observability.logging import _JsonFormatter

        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Hello %s",
            args=("world",),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["message"] == "Hello world"
        assert data["level"] == "INFO"
        assert data["logger"] == "test"
        assert "timestamp" in data
        assert "service" in data
        assert "version" in data

    def test_json_formatter_includes_exception(self):
        from src.observability.logging import _JsonFormatter

        formatter = _JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Something broke",
                args=None,
                exc_info=sys.exc_info(),
            )
        output = formatter.format(record)
        data = json.loads(output)
        assert "exception" in data
        assert data["error_type"] == "ValueError"

    def test_set_and_get_log_context(self):
        from src.observability.logging import clear_log_context, get_log_context, set_log_context

        clear_log_context()
        set_log_context(request_id="abc123", user_id="alice")
        ctx = get_log_context()
        assert ctx["request_id"] == "abc123"
        assert ctx["user_id"] == "alice"
        clear_log_context()
        assert get_log_context() == {}

    def test_log_context_is_thread_local(self):
        from src.observability.logging import clear_log_context, get_log_context, set_log_context

        clear_log_context()
        set_log_context(request_id="main_thread")
        results = {}

        def worker():
            results["child"] = get_log_context()

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        # Child thread should not see parent's context
        assert results["child"] == {} or "request_id" not in results["child"]
        clear_log_context()

    def test_dev_formatter_output(self):
        from src.observability.logging import _DevFormatter

        formatter = _DevFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello dev",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        assert "hello dev" in output
        assert "INFO" in output

    def test_structured_logger_debug_mode(self):
        from src.observability.logging import setup_structured_logger

        logger = setup_structured_logger("test_debug_obs", "test_debug_obs.log", debug=True)
        assert logger.level == logging.DEBUG


# ── PII Scrubbing ────────────────────────────────────────────────


class TestPiiScrubber:
    """Tests for src.observability.pii."""

    def test_scrubs_bearer_token(self):
        from src.observability.pii import _scrub_text

        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature"
        result = _scrub_text(text)
        assert "eyJhbGci" not in result
        assert "[REDACTED]" in result

    def test_scrubs_api_key(self):
        from src.observability.pii import _scrub_text

        text = 'api_key="abcdef123456789"'
        result = _scrub_text(text)
        assert "abcdef123456789" not in result
        assert "[REDACTED]" in result

    def test_scrubs_password_in_key_value(self):
        from src.observability.pii import _scrub_text

        text = "password=supersecret123"
        result = _scrub_text(text)
        assert "supersecret123" not in result

    def test_scrubs_email_addresses(self):
        from src.observability.pii import _scrub_text

        text = "User email is john.doe@example.com and he logged in"
        result = _scrub_text(text)
        assert "john.doe@example.com" not in result
        assert "[EMAIL_REDACTED]" in result

    def test_scrubs_credit_card(self):
        from src.observability.pii import _scrub_text

        text = "Card: 4111-1111-1111-1111"
        result = _scrub_text(text)
        assert "4111" not in result
        assert "[CARD_REDACTED]" in result

    def test_scrubs_ssn(self):
        from src.observability.pii import _scrub_text

        text = "SSN: 123-45-6789 on file"
        result = _scrub_text(text)
        assert "123-45-6789" not in result
        assert "[SSN_REDACTED]" in result

    def test_filter_scrubs_log_record(self):
        from src.observability.pii import PiiScrubber

        scrubber = PiiScrubber()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="User token=secret_abc_123 logged in",
            args=None,
            exc_info=None,
        )
        scrubber.filter(record)
        assert "secret_abc_123" not in record.getMessage()

    def test_filter_redacts_sensitive_attributes(self):
        from src.observability.pii import PiiScrubber

        scrubber = PiiScrubber()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="ok",
            args=None,
            exc_info=None,
        )
        record.password = "hunter2"
        record.api_key = "sk-abc123"
        scrubber.filter(record)
        assert record.password == "[REDACTED]"
        assert record.api_key == "[REDACTED]"

    def test_safe_text_passes_through(self):
        from src.observability.pii import _scrub_text

        text = "Job 42 completed in 3.5 seconds"
        assert _scrub_text(text) == text


# ── Metrics ──────────────────────────────────────────────────────


class TestMetricsCollector:
    """Tests for src.observability.metrics."""

    def setup_method(self):
        from src.observability.metrics import MetricsCollector

        MetricsCollector.reset()

    def teardown_method(self):
        from src.observability.metrics import MetricsCollector

        MetricsCollector.reset()

    def test_counter_increment(self):
        from src.observability.metrics import MetricsCollector

        mc = MetricsCollector()
        mc.inc("test_counter")
        mc.inc("test_counter")
        snap = mc.snapshot()
        assert snap["counters"]["test_counter"] == 2.0

    def test_counter_with_labels(self):
        from src.observability.metrics import MetricsCollector

        mc = MetricsCollector()
        mc.inc("http_requests", labels={"method": "GET"})
        mc.inc("http_requests", labels={"method": "POST"})
        mc.inc("http_requests", labels={"method": "GET"})
        snap = mc.snapshot()
        assert snap["counters"]['http_requests{method="GET"}'] == 2.0
        assert snap["counters"]['http_requests{method="POST"}'] == 1.0

    def test_gauge_set_inc_dec(self):
        from src.observability.metrics import MetricsCollector

        mc = MetricsCollector()
        mc.gauge_set("active_jobs", 5)
        snap = mc.snapshot()
        assert snap["gauges"]["active_jobs"] == 5.0

        mc.gauge_inc("active_jobs")
        snap = mc.snapshot()
        assert snap["gauges"]["active_jobs"] == 6.0

        mc.gauge_dec("active_jobs", 2)
        snap = mc.snapshot()
        assert snap["gauges"]["active_jobs"] == 4.0

    def test_histogram_observe(self):
        from src.observability.metrics import MetricsCollector

        mc = MetricsCollector()
        mc.observe("latency", 15.0)
        mc.observe("latency", 150.0)
        mc.observe("latency", 1500.0)
        snap = mc.snapshot()
        h = snap["histograms"]["latency"]
        assert h["count"] == 3
        assert h["sum"] == 1665.0
        assert h["avg"] == 555.0

    def test_prometheus_exposition(self):
        from src.observability.metrics import MetricsCollector

        mc = MetricsCollector()
        mc.inc("test_total")
        mc.gauge_set("test_gauge", 42)
        text = mc.prometheus_exposition()
        assert "uptime_seconds" in text
        assert "test_total 1.0" in text
        assert "test_gauge 42" in text

    def test_snapshot_includes_uptime(self):
        from src.observability.metrics import MetricsCollector

        mc = MetricsCollector()
        snap = mc.snapshot()
        assert "uptime_seconds" in snap
        assert snap["uptime_seconds"] >= 0

    def test_singleton_pattern(self):
        from src.observability.metrics import MetricsCollector

        mc1 = MetricsCollector()
        mc2 = MetricsCollector()
        assert mc1 is mc2

    def test_thread_safety(self):
        from src.observability.metrics import MetricsCollector

        mc = MetricsCollector()
        errors = []

        def increment():
            try:
                for _ in range(1000):
                    mc.inc("thread_counter")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=increment) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        snap = mc.snapshot()
        assert snap["counters"]["thread_counter"] == 5000.0


# ── Tracing ──────────────────────────────────────────────────────


class TestTracing:
    """Tests for src.observability.tracing."""

    def test_trace_context_lifecycle(self):
        from src.observability.tracing import (
            TraceContext,
            clear_trace_context,
            get_trace_context,
            set_trace_context,
        )

        clear_trace_context()
        assert get_trace_context() is None

        ctx = TraceContext(trace_id="abc", span_id="def", operation="test")
        set_trace_context(ctx)
        assert get_trace_context() is ctx
        assert get_trace_context().trace_id == "abc"

        clear_trace_context()
        assert get_trace_context() is None

    def test_background_job_tracing(self):
        from src.observability.logging import get_log_context
        from src.observability.tracing import (
            clear_trace_context,
            end_background_trace,
            get_trace_context,
            trace_background_job,
        )

        clear_trace_context()
        ctx = trace_background_job("rip", "job-42")
        assert ctx.trace_id
        assert ctx.span_id
        assert ctx.operation == "job:rip"
        assert ctx.attributes["job_id"] == "job-42"

        # Log context should have the trace info
        log_ctx = get_log_context()
        assert log_ctx["trace_id"] == ctx.trace_id
        assert log_ctx["job_id"] == "job-42"

        # End trace returns duration
        duration = end_background_trace()
        assert duration is not None
        assert duration >= 0
        assert get_trace_context() is None

    def test_new_id_generates_correct_length(self):
        from src.observability.tracing import _new_id

        assert len(_new_id(32)) == 32
        assert len(_new_id(16)) == 16

    def test_request_tracer_with_flask_app(self):
        """Test that RequestTracer installs hooks on a Flask app."""
        from flask import Flask

        from src.observability.tracing import RequestTracer

        app = Flask(__name__)

        @app.route("/test")
        def test_route():
            from flask import g

            return {"trace_id": g.trace_id}

        RequestTracer(app)

        with app.test_client() as client:
            resp = client.get("/test")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "trace_id" in data
            assert len(data["trace_id"]) == 32

            # Response should have trace headers
            assert "X-Request-ID" in resp.headers
            assert "X-Trace-ID" in resp.headers

    def test_request_id_propagation(self):
        """Test X-Request-ID header is respected."""
        from flask import Flask

        from src.observability.tracing import RequestTracer

        app = Flask(__name__)

        @app.route("/test")
        def test_route():
            from flask import g

            return {"trace_id": g.trace_id}

        RequestTracer(app)

        with app.test_client() as client:
            resp = client.get("/test", headers={"X-Request-ID": "my-custom-id"})
            data = resp.get_json()
            assert data["trace_id"] == "my-custom-id"

    def test_traceparent_header_parsing(self):
        """Test W3C traceparent header parsing."""
        from flask import Flask

        from src.observability.tracing import RequestTracer

        app = Flask(__name__)

        @app.route("/test")
        def test_route():
            from flask import g

            return {"trace_id": g.trace_id, "span_id": g.span_id}

        RequestTracer(app)
        trace_id = "0af7651916cd43dd8448eb211c80319c"

        with app.test_client() as client:
            resp = client.get(
                "/test",
                headers={"traceparent": f"00-{trace_id}-b7ad6b7169203331-01"},
            )
            data = resp.get_json()
            assert data["trace_id"] == trace_id


# ── Error Tracking ───────────────────────────────────────────────


class TestErrorTracker:
    """Tests for src.observability.errors."""

    def setup_method(self):
        from src.observability.errors import ErrorTracker

        ErrorTracker.reset()

    def teardown_method(self):
        from src.observability.errors import ErrorTracker

        ErrorTracker.reset()

    def test_capture_exception(self):
        from src.observability.errors import ErrorTracker

        tracker = ErrorTracker()
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            record = tracker.capture_exception()

        assert record is not None
        assert record.error_type == "RuntimeError"
        assert record.message == "boom"
        assert "RuntimeError" in record.traceback

    def test_capture_with_explicit_exc(self):
        from src.observability.errors import ErrorTracker

        tracker = ErrorTracker()
        exc = ValueError("bad value")
        try:
            raise exc
        except ValueError:
            record = tracker.capture_exception(exc=exc)

        assert record.error_type == "ValueError"

    def test_capture_with_extra_context(self):
        from src.observability.errors import ErrorTracker

        tracker = ErrorTracker()
        try:
            raise TypeError("type mismatch")
        except TypeError:
            record = tracker.capture_exception(extra={"job_id": "j-99", "worker": "test"})

        assert record.context["job_id"] == "j-99"
        assert record.context["worker"] == "test"

    def test_recent_errors(self):
        from src.observability.errors import ErrorTracker

        tracker = ErrorTracker()
        for i in range(5):
            try:
                raise RuntimeError(f"error {i}")
            except RuntimeError:
                tracker.capture_exception()

        recent = tracker.recent_errors(limit=3)
        assert len(recent) == 3
        # Most recent first
        assert "error 4" in recent[0]["message"]

    def test_error_summary_dedup(self):
        from src.observability.errors import ErrorTracker

        tracker = ErrorTracker()
        # Same error location = same fingerprint
        for _ in range(5):
            try:
                raise RuntimeError("same error")
            except RuntimeError:
                tracker.capture_exception()

        summary = tracker.error_summary()
        assert summary["total_captured"] == 5
        # All have the same fingerprint so unique should be 1
        assert summary["unique_errors"] == 1

    def test_on_error_callback(self):
        from src.observability.errors import ErrorTracker

        tracker = ErrorTracker()
        captured = []
        tracker.on_error(lambda r: captured.append(r))

        try:
            raise RuntimeError("callback test")
        except RuntimeError:
            tracker.capture_exception()

        assert len(captured) == 1
        assert captured[0].message == "callback test"

    def test_singleton_pattern(self):
        from src.observability.errors import ErrorTracker

        t1 = ErrorTracker()
        t2 = ErrorTracker()
        assert t1 is t2

    def test_install_flask_error_handler(self):
        """Test that install_flask catches unhandled route exceptions."""
        from flask import Flask

        from src.observability.errors import ErrorTracker

        tracker = ErrorTracker()
        app = Flask(__name__)

        @app.route("/explode")
        def explode():
            raise RuntimeError("kaboom")

        tracker.install_flask(app)

        with app.test_client() as client:
            resp = client.get("/explode")
            assert resp.status_code == 500
            data = resp.get_json()
            assert data["error"] == "Internal Server Error"

        recent = tracker.recent_errors(1)
        assert len(recent) == 1
        assert "kaboom" in recent[0]["message"]


# ── Integration ──────────────────────────────────────────────────


class TestObservabilityIntegration:
    """Integration tests verifying components work together."""

    def setup_method(self):
        from src.observability.errors import ErrorTracker
        from src.observability.metrics import MetricsCollector

        MetricsCollector.reset()
        ErrorTracker.reset()

    def teardown_method(self):
        from src.observability.errors import ErrorTracker
        from src.observability.metrics import MetricsCollector

        MetricsCollector.reset()
        ErrorTracker.reset()

    def test_tracer_records_metrics(self):
        """RequestTracer should record request count and latency metrics."""
        from flask import Flask

        from src.observability.metrics import MetricsCollector
        from src.observability.tracing import RequestTracer

        app = Flask(__name__)
        mc = MetricsCollector()

        @app.route("/hello")
        def hello():
            return "ok"

        RequestTracer(app, metrics=mc)

        with app.test_client() as client:
            client.get("/hello")
            client.get("/hello")

        snap = mc.snapshot()
        # Should have recorded traffic
        assert any("http_requests_total" in k for k in snap["counters"])
        # Should have recorded latency
        assert any("http_request_duration_ms" in k for k in snap["histograms"])

    def test_tracer_records_error_metrics(self):
        """RequestTracer should record error count for 4xx/5xx responses."""
        from flask import Flask

        from src.observability.metrics import MetricsCollector
        from src.observability.tracing import RequestTracer

        app = Flask(__name__)
        mc = MetricsCollector()

        @app.route("/notfound")
        def notfound():
            return "nope", 404

        RequestTracer(app, metrics=mc)

        with app.test_client() as client:
            client.get("/notfound")

        snap = mc.snapshot()
        assert any("http_errors_total" in k for k in snap["counters"])

    def test_pii_scrubber_on_structured_logger(self):
        """PII scrubber should work as a filter on the structured logger."""
        from src.observability.logging import setup_structured_logger
        from src.observability.pii import PiiScrubber

        logger = setup_structured_logger("pii_test", "pii_test.log")
        logger.addFilter(PiiScrubber())
        # Should not raise
        logger.info("password=supersecret token=abc123def")

    def test_full_request_lifecycle(self):
        """Test a complete request through tracer + metrics + error tracker."""
        from flask import Flask

        from src.observability.errors import ErrorTracker
        from src.observability.logging import setup_structured_logger
        from src.observability.metrics import MetricsCollector
        from src.observability.tracing import RequestTracer

        app = Flask(__name__)
        mc = MetricsCollector()
        et = ErrorTracker()
        logger = setup_structured_logger("lifecycle_test", "lifecycle_test.log")

        @app.route("/ok")
        def ok():
            return "fine"

        @app.route("/fail")
        def fail():
            raise ValueError("lifecycle fail")

        RequestTracer(app, logger=logger, metrics=mc)
        et.install_flask(app)

        with app.test_client() as client:
            resp = client.get("/ok")
            assert resp.status_code == 200
            assert "X-Request-ID" in resp.headers

            resp = client.get("/fail")
            assert resp.status_code == 500

        snap = mc.snapshot()
        assert any("http_requests_total" in k for k in snap["counters"])

        recent = et.recent_errors()
        assert any("lifecycle fail" in e["message"] for e in recent)
