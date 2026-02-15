"""Tests for user management routes (/api/users, /api/me)."""

import json

import pytest

from src.app_state import AppState
from src.web_server import MediaServer


@pytest.fixture
def user_config(tmp_path):
    return {
        "output": {
            "base_directory": str(tmp_path / "media"),
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
        "web_server": {"enabled": True, "port": 8098, "host": "127.0.0.1", "library_name": "Test"},
        "disc_detection": {"check_interval_seconds": 5, "mount_path": "/Volumes"},
        "handbrake": {"preset": "Fast 1080p30", "additional_options": []},
        "auth": {"enabled": False, "session_hours": 24},
        "library_cache": {"ttl_seconds": 300},
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
def flask_client(tmp_path, user_config):
    AppState.reset()
    state = AppState(db_path=str(tmp_path / "test.db"))
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(user_config))
    server = MediaServer(config_path=str(config_path), app_state=state)
    server.app.config["TESTING"] = True

    # Seed an admin user
    state.create_user("admin", "admin123", "admin")

    # Middleware helper: inject current_user for requests with X-Test-User header
    @server.app.before_request
    def _inject_test_user():
        from flask import request

        role = request.headers.get("X-Test-Role")
        user = request.headers.get("X-Test-User")
        if role:
            request.current_user = {"username": user or "admin", "role": role}

    with server.app.test_client() as client:
        yield client
    AppState.reset()


def _admin_headers(username="admin"):
    return {"X-Test-Role": "admin", "X-Test-User": username}


def _user_headers(username="bob"):
    return {"X-Test-Role": "user", "X-Test-User": username}


class TestListUsers:
    def test_admin_can_list(self, flask_client):
        resp = flask_client.get("/api/users", headers=_admin_headers())
        assert resp.status_code == 200
        data = resp.get_json()
        assert "users" in data
        assert any(u["username"] == "admin" for u in data["users"])

    def test_non_admin_forbidden(self, flask_client):
        resp = flask_client.get("/api/users", headers=_user_headers())
        assert resp.status_code == 403

    def test_anonymous_forbidden(self, flask_client):
        resp = flask_client.get("/api/users")
        assert resp.status_code == 403


class TestCreateUser:
    def test_create_user(self, flask_client):
        resp = flask_client.post(
            "/api/users",
            headers=_admin_headers(),
            json={"username": "newbie", "password": "pass123"},
        )
        assert resp.status_code == 201
        assert resp.get_json()["username"] == "newbie"

    def test_missing_fields(self, flask_client):
        resp = flask_client.post("/api/users", headers=_admin_headers(), json={"username": "x"})
        assert resp.status_code == 400

    def test_invalid_role(self, flask_client):
        resp = flask_client.post(
            "/api/users",
            headers=_admin_headers(),
            json={"username": "x", "password": "p", "role": "superuser"},
        )
        assert resp.status_code == 400

    def test_duplicate_user(self, flask_client):
        flask_client.post(
            "/api/users", headers=_admin_headers(), json={"username": "dup", "password": "p"}
        )
        resp = flask_client.post(
            "/api/users", headers=_admin_headers(), json={"username": "dup", "password": "p"}
        )
        assert resp.status_code == 409

    def test_non_admin_cannot_create(self, flask_client):
        resp = flask_client.post(
            "/api/users", headers=_user_headers(), json={"username": "x", "password": "p"}
        )
        assert resp.status_code == 403


class TestDeleteUser:
    def test_delete_user(self, flask_client):
        flask_client.post(
            "/api/users", headers=_admin_headers(), json={"username": "victim", "password": "p"}
        )
        resp = flask_client.delete("/api/users/victim", headers=_admin_headers())
        assert resp.status_code == 200

    def test_cannot_delete_self(self, flask_client):
        resp = flask_client.delete("/api/users/admin", headers=_admin_headers())
        assert resp.status_code == 400

    def test_user_not_found(self, flask_client):
        resp = flask_client.delete("/api/users/ghost", headers=_admin_headers())
        assert resp.status_code == 404


class TestUpdatePassword:
    def test_admin_changes_password(self, flask_client):
        flask_client.post(
            "/api/users", headers=_admin_headers(), json={"username": "bob", "password": "old"}
        )
        resp = flask_client.put(
            "/api/users/bob/password", headers=_admin_headers(), json={"password": "new123"}
        )
        assert resp.status_code == 200

    def test_user_changes_own_password(self, flask_client):
        flask_client.post(
            "/api/users", headers=_admin_headers(), json={"username": "bob", "password": "old"}
        )
        resp = flask_client.put(
            "/api/users/bob/password", headers=_user_headers("bob"), json={"password": "new123"}
        )
        assert resp.status_code == 200

    def test_user_cannot_change_others_password(self, flask_client):
        resp = flask_client.put(
            "/api/users/admin/password", headers=_user_headers("eve"), json={"password": "hacked"}
        )
        assert resp.status_code == 403

    def test_missing_password_field(self, flask_client):
        resp = flask_client.put("/api/users/admin/password", headers=_admin_headers(), json={})
        assert resp.status_code == 400


class TestMe:
    def test_authenticated_user(self, flask_client):
        resp = flask_client.get("/api/me", headers=_admin_headers())
        data = resp.get_json()
        assert data["username"] == "admin"
        assert data["role"] == "admin"

    def test_anonymous_user(self, flask_client):
        resp = flask_client.get("/api/me")
        data = resp.get_json()
        assert data["username"] is None
        assert data["role"] == "anonymous"
