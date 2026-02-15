"""
Tests for file upload functionality via web API.
"""

import io
import json
from pathlib import Path

import pytest

from src.app_state import AppState
from src.web_server import MediaServer


@pytest.fixture
def upload_config(tmp_path):
    """Config with upload settings pointing to tmp_path"""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
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
        "web_server": {"enabled": True, "port": 8099, "host": "127.0.0.1", "library_name": "Test"},
        "disc_detection": {"check_interval_seconds": 5, "mount_path": "/Volumes"},
        "handbrake": {"preset": "Fast 1080p30", "additional_options": []},
        "auth": {"enabled": False, "session_hours": 24},
        "library_cache": {"ttl_seconds": 300},
        "uploads": {
            "enabled": True,
            "max_upload_size_mb": 10,
            "upload_directory": str(upload_dir),
        },
        "podcasts": {
            "enabled": False,
            "check_interval_hours": 6,
            "auto_download": False,
            "download_directory": str(tmp_path / "podcasts"),
        },
        "downloads": {
            "enabled": True,
            "download_directory": str(tmp_path / "downloads"),
            "articles_directory": str(tmp_path / "articles"),
            "books_directory": str(tmp_path / "books"),
        },
        "file_naming": {"rename_after_rip": False},
    }


@pytest.fixture
def flask_client(tmp_path, upload_config):
    """Create a Flask test client with AppState"""
    AppState.reset()
    state = AppState(db_path=str(tmp_path / "test.db"))

    # Write config to temp file
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(upload_config))

    server = MediaServer(config_path=str(config_path), app_state=state)
    server.app.config["TESTING"] = True

    with server.app.test_client() as client:
        yield client

    AppState.reset()


class TestUploadEndpoint:
    """Tests for POST /api/upload"""

    def test_upload_single_file(self, flask_client, tmp_path, upload_config):
        data = {"files": (io.BytesIO(b"hello world"), "test.txt")}
        resp = flask_client.post("/api/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 201
        result = resp.get_json()
        assert "uploaded" in result
        assert len(result["uploaded"]) == 1
        assert result["uploaded"][0]["file"] == "test.txt"
        assert result["uploaded"][0]["media_type"] == "document"

    def test_upload_video_file(self, flask_client):
        data = {"files": (io.BytesIO(b"\x00" * 100), "video.mp4")}
        resp = flask_client.post("/api/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 201
        result = resp.get_json()
        assert result["uploaded"][0]["media_type"] == "video"

    def test_upload_audio_file(self, flask_client):
        data = {"files": (io.BytesIO(b"\x00" * 100), "song.mp3")}
        resp = flask_client.post("/api/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 201
        result = resp.get_json()
        assert result["uploaded"][0]["media_type"] == "audio"

    def test_upload_no_files(self, flask_client):
        resp = flask_client.post("/api/upload", content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_upload_collision_handling(self, flask_client, upload_config):
        """Upload same filename twice should not overwrite"""
        for _ in range(2):
            data = {"files": (io.BytesIO(b"data"), "dup.txt")}
            resp = flask_client.post("/api/upload", data=data, content_type="multipart/form-data")
            assert resp.status_code == 201

        # Both should have been saved (second with collision suffix)
        upload_dir = Path(upload_config["uploads"]["upload_directory"])
        files = list(upload_dir.iterdir())
        assert len(files) == 2


class TestContentEndpoints:
    """Tests for content ingestion API endpoints"""

    def test_download_endpoint_requires_url(self, flask_client):
        resp = flask_client.post(
            "/api/downloads", data=json.dumps({}), content_type="application/json"
        )
        assert resp.status_code == 400

    def test_download_endpoint_queues_job(self, flask_client):
        resp = flask_client.post(
            "/api/downloads",
            data=json.dumps({"url": "https://youtube.com/watch?v=test"}),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "queued"
        assert "id" in data

    def test_article_endpoint_requires_url(self, flask_client):
        resp = flask_client.post(
            "/api/articles", data=json.dumps({}), content_type="application/json"
        )
        assert resp.status_code == 400

    def test_article_endpoint_queues_job(self, flask_client):
        resp = flask_client.post(
            "/api/articles",
            data=json.dumps({"url": "https://example.com/article"}),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "queued"

    def test_book_endpoint_requires_title(self, flask_client):
        resp = flask_client.post("/api/books", data=json.dumps({}), content_type="application/json")
        assert resp.status_code == 400

    def test_book_endpoint_adds_item(self, flask_client):
        resp = flask_client.post(
            "/api/books",
            data=json.dumps(
                {
                    "title": "The Great Gatsby",
                    "author": "F. Scott Fitzgerald",
                    "year": "1925",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "added"

    def test_playlist_import_requires_url(self, flask_client):
        resp = flask_client.post(
            "/api/import/playlist", data=json.dumps({}), content_type="application/json"
        )
        assert resp.status_code == 400

    def test_stats_endpoint(self, flask_client):
        resp = flask_client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_items" in data
        assert "by_type" in data
        assert "total_size_formatted" in data


class TestPodcastEndpoints:
    """Tests for podcast API endpoints"""

    def test_list_podcasts_empty(self, flask_client):
        resp = flask_client.get("/api/podcasts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["podcasts"] == []

    def test_add_podcast_requires_feed_url(self, flask_client):
        resp = flask_client.post(
            "/api/podcasts", data=json.dumps({}), content_type="application/json"
        )
        assert resp.status_code == 400

    def test_add_and_delete_podcast(self, flask_client):
        # Add
        resp = flask_client.post(
            "/api/podcasts",
            data=json.dumps(
                {
                    "feed_url": "https://example.com/feed.xml",
                    "title": "Test Podcast",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        pod_id = resp.get_json()["id"]

        # Verify listed
        resp = flask_client.get("/api/podcasts")
        assert len(resp.get_json()["podcasts"]) == 1

        # Delete
        resp = flask_client.delete(f"/api/podcasts/{pod_id}")
        assert resp.status_code == 200

        # Verify gone
        resp = flask_client.get("/api/podcasts")
        assert len(resp.get_json()["podcasts"]) == 0

    def test_duplicate_podcast_rejected(self, flask_client):
        body = json.dumps({"feed_url": "https://example.com/dup.xml", "title": "Dup"})
        flask_client.post("/api/podcasts", data=body, content_type="application/json")
        resp = flask_client.post("/api/podcasts", data=body, content_type="application/json")
        assert resp.status_code == 409
