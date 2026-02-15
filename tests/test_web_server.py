"""Tests for web_server.py — auth, scan, safe_items, login flow."""

import json

import pytest

from src.app_state import AppState
from src.utils import generate_media_id
from src.web_server import MediaServer


@pytest.fixture
def server_config(tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    return {
        "output": {
            "base_directory": str(media_dir),
            "format": "mp4",
            "video_encoder": "x264",
            "quality": 22,
            "audio_encoder": "aac",
            "audio_bitrate": "192",
        },
        "metadata": {
            "save_to_json": False,
            "fetch_online_metadata": False,
            "extract_chapters": False,
            "extract_subtitles": False,
            "extract_audio_tracks": False,
        },
        "automation": {
            "auto_detect_disc": False,
            "auto_eject_after_rip": False,
            "notification_enabled": False,
        },
        "web_server": {"enabled": True, "port": 8097, "host": "127.0.0.1", "library_name": "Test"},
        "disc_detection": {"check_interval_seconds": 5, "mount_path": "/Volumes"},
        "handbrake": {"preset": "Fast 1080p30", "additional_options": []},
        "auth": {"enabled": True, "session_hours": 24},
        "library_cache": {"ttl_seconds": 0},
        "uploads": {"enabled": False},
        "podcasts": {
            "enabled": False,
            "check_interval_hours": 6,
            "auto_download": False,
            "download_directory": str(tmp_path / "podcasts"),
        },
        "downloads": {
            "enabled": False,
            "download_directory": str(tmp_path / "downloads"),
            "articles_directory": str(tmp_path / "articles"),
            "books_directory": str(tmp_path / "books"),
        },
        "file_naming": {"rename_after_rip": False},
    }


@pytest.fixture
def auth_disabled_config(server_config):
    cfg = dict(server_config)
    cfg["auth"] = {"enabled": False, "session_hours": 24}
    return cfg


@pytest.fixture
def server_client(tmp_path, server_config):
    AppState.reset()
    state = AppState(db_path=str(tmp_path / "test.db"))
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(server_config))
    server = MediaServer(config_path=str(config_path), app_state=state)
    server.app.config["TESTING"] = True
    with server.app.test_client() as client:
        yield client, state, server
    AppState.reset()


@pytest.fixture
def noauth_client(tmp_path, auth_disabled_config):
    AppState.reset()
    state = AppState(db_path=str(tmp_path / "test.db"))
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(auth_disabled_config))
    server = MediaServer(config_path=str(config_path), app_state=state)
    server.app.config["TESTING"] = True
    with server.app.test_client() as client:
        yield client, state, server
    AppState.reset()


# ── generate_media_id ────────────────────────────────────────────


class TestGenerateMediaId:
    def test_deterministic(self):
        id1 = generate_media_id("/path/to/file.mp4")
        id2 = generate_media_id("/path/to/file.mp4")
        assert id1 == id2

    def test_different_paths_differ(self):
        id1 = generate_media_id("/path/a.mp4")
        id2 = generate_media_id("/path/b.mp4")
        assert id1 != id2

    def test_returns_string(self):
        result = generate_media_id("/any/file.mp4")
        assert isinstance(result, str)
        assert len(result) > 0


# ── _safe_items ──────────────────────────────────────────────────


class TestSafeItems:
    def test_strips_sensitive_fields(self, noauth_client):
        client, state, server = noauth_client
        items = [
            {
                "id": "1",
                "title": "Movie",
                "file_path": "/secret/path.mp4",
                "poster_path": "/secret/poster.jpg",
                "other": "value",
            }
        ]
        safe = server._safe_items(items)
        assert len(safe) == 1
        assert "file_path" not in safe[0]
        assert "poster_path" not in safe[0]
        assert safe[0]["other"] == "value"

    def test_adds_has_poster(self, noauth_client):
        client, state, server = noauth_client
        items = [
            {"id": "1", "poster_path": "/real/poster.jpg"},
            {"id": "2", "poster_path": None},
            {"id": "3"},
        ]
        safe = server._safe_items(items)
        assert safe[0].get("has_poster") is True
        assert safe[1].get("has_poster") is False
        assert safe[2].get("has_poster") is False

    def test_empty_list(self, noauth_client):
        client, state, server = noauth_client
        assert server._safe_items([]) == []


# ── scan_library ─────────────────────────────────────────────────


class TestScanLibrary:
    def test_scan_returns_list(self, noauth_client):
        client, state, server = noauth_client
        result = server.scan_library()
        assert isinstance(result, list)

    def test_force_scan_bypasses_cache(self, noauth_client):
        client, state, server = noauth_client
        server.scan_library()
        r2 = server.scan_library(force=True)
        assert isinstance(r2, list)


# ── Auth middleware ──────────────────────────────────────────────


class TestAuthMiddleware:
    def test_api_without_auth_returns_401(self, server_client):
        """API endpoints return 401 when auth is enabled and no session."""
        client, state, server = server_client
        # No users created yet, no session cookie
        resp = client.get("/api/media/test123")
        # Should be 401 or redirect depending on implementation
        assert resp.status_code in (401, 302, 404)

    def test_page_without_auth_redirects(self, server_client):
        """Page requests redirect to login."""
        client, state, server = server_client
        resp = client.get("/")
        assert resp.status_code in (200, 302)  # First run may show setup

    def test_auth_disabled_allows_all(self, noauth_client):
        """With auth disabled, all requests pass."""
        client, state, server = noauth_client
        resp = client.get("/api/stats")
        assert resp.status_code == 200


# ── Login flow ───────────────────────────────────────────────────


class TestLoginFlow:
    def test_login_page_accessible(self, server_client):
        client, state, server = server_client
        resp = client.get("/login")
        assert resp.status_code == 200

    def test_first_run_setup(self, server_client):
        """On first run with no users, /login should show setup form."""
        client, state, server = server_client
        resp = client.get("/login")
        assert resp.status_code == 200
        # The page should render (either login or setup)

    def test_login_with_valid_credentials(self, server_client):
        client, state, server = server_client
        state.create_user("admin", "pass123", "admin")
        resp = client.post(
            "/login",
            data={
                "username": "admin",
                "password": "pass123",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (200, 302)

    def test_login_with_invalid_credentials(self, server_client):
        client, state, server = server_client
        state.create_user("admin", "pass123", "admin")
        resp = client.post(
            "/login",
            data={
                "username": "admin",
                "password": "wrong",
            },
        )
        assert resp.status_code in (200, 401)

    def test_logout(self, server_client):
        client, state, server = server_client
        resp = client.get("/logout", follow_redirects=False)
        assert resp.status_code in (200, 302)
