"""Tests for job queue routes (/api/jobs)."""

import json

import pytest

from src.app_state import AppState
from src.web_server import MediaServer


@pytest.fixture
def job_config(tmp_path):
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
        "web_server": {"enabled": True, "port": 8097, "host": "127.0.0.1", "library_name": "Test"},
        "disc_detection": {"check_interval_seconds": 5, "mount_path": "/Volumes"},
        "handbrake": {"preset": "Fast 1080p30", "additional_options": []},
        "auth": {"enabled": False, "session_hours": 24},
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
def flask_client(tmp_path, job_config):
    AppState.reset()
    state = AppState(db_path=str(tmp_path / "test.db"))
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(job_config))
    server = MediaServer(config_path=str(config_path), app_state=state)
    server.app.config["TESTING"] = True
    with server.app.test_client() as client:
        yield client, state
    AppState.reset()


class TestGetJobs:
    def test_empty_list(self, flask_client):
        client, state = flask_client
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["jobs"] == []

    def test_list_with_jobs(self, flask_client):
        client, state = flask_client
        state.create_job(title="Movie 1", source_path="/dev/disc0")
        state.create_job(title="Movie 2", source_path="/dev/disc1")
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["jobs"]) == 2


class TestCreateJob:
    def test_success(self, flask_client):
        client, state = flask_client
        resp = client.post(
            "/api/jobs",
            json={
                "source_path": "/Volumes/DISC",
                "title": "My Movie",
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert "id" in data
        assert data["status"] == "queued"

    def test_missing_source_path(self, flask_client):
        client, state = flask_client
        resp = client.post("/api/jobs", json={"title": "No path"})
        assert resp.status_code == 400
        assert "source_path" in resp.get_json()["error"]

    def test_no_body(self, flask_client):
        client, state = flask_client
        resp = client.post("/api/jobs", content_type="application/json", data="null")
        assert resp.status_code == 400

    def test_default_title_from_path(self, flask_client):
        client, state = flask_client
        resp = client.post(
            "/api/jobs",
            json={
                "source_path": "/Volumes/MY_MOVIE_DVD",
            },
        )
        assert resp.status_code == 201


class TestCancelJob:
    def test_cancel_queued(self, flask_client):
        client, state = flask_client
        job_id = state.create_job(title="Movie", source_path="/dev/disc0")
        resp = client.delete(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "cancelled"

    def test_cancel_completed_fails(self, flask_client):
        client, state = flask_client
        job_id = state.create_job(title="Movie", source_path="/dev/disc0")
        state.update_job_status(job_id, "encoding")
        state.update_job_status(job_id, "completed")
        resp = client.delete(f"/api/jobs/{job_id}")
        assert resp.status_code == 400


class TestRetryJob:
    def test_retry_failed(self, flask_client):
        client, state = flask_client
        job_id = state.create_job(title="Movie", source_path="/dev/disc0")
        state.update_job_status(job_id, "encoding")
        state.update_job_status(job_id, "failed")
        resp = client.post(f"/api/jobs/{job_id}/retry")
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "queued"
        assert data["id"] != job_id  # new job ID

    def test_retry_queued_fails(self, flask_client):
        client, state = flask_client
        job_id = state.create_job(title="Movie", source_path="/dev/disc0")
        resp = client.post(f"/api/jobs/{job_id}/retry")
        assert resp.status_code == 400
