"""Tests for media blueprint routes (/api/media, /api/search, /api/scan, etc.)."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch
from src.app_state import AppState
from src.web_server import MediaServer


@pytest.fixture
def media_config(tmp_path):
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
        "web_server": {"enabled": True, "port": 8096, "host": "127.0.0.1", "library_name": "Test"},
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
def flask_client(tmp_path, media_config):
    AppState.reset()
    state = AppState(db_path=str(tmp_path / "test.db"))
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(media_config))
    server = MediaServer(config_path=str(config_path), app_state=state)
    server.app.config["TESTING"] = True
    with server.app.test_client() as client:
        yield client, state, tmp_path
    AppState.reset()


def _insert_media(state, media_id, title="Test Movie", file_path=None, **kw):
    item = {
        "id": media_id,
        "title": title,
        "filename": Path(file_path).name if file_path else f"{title}.mp4",
        "file_path": file_path or "",
        "file_size": 100,
        "size_formatted": "100 B",
        "created_at": "2024-01-01",
        "modified_at": "2024-01-01",
        "media_type": "video",
    }
    item.update(kw)
    state.upsert_media(item)


class TestApiMedia:
    def test_get_existing(self, flask_client):
        client, state, _ = flask_client
        _insert_media(state, "abc123", title="Big Movie")
        resp = client.get("/api/media/abc123")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["title"] == "Big Movie"
        assert "file_path" not in data  # stripped
        assert "has_poster" in data

    def test_not_found(self, flask_client):
        client, state, _ = flask_client
        resp = client.get("/api/media/nonexistent")
        assert resp.status_code == 404


class TestApiSearch:
    def test_search_by_query(self, flask_client):
        client, state, _ = flask_client
        _insert_media(state, "s1", title="Alpha")
        _insert_media(state, "s2", title="Beta")
        with patch.object(
            type(client.application.config["server"]), "scan_library", return_value=[]
        ):
            resp = client.get("/api/search?q=alpha")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["query"] == "alpha"
        assert data["items"][0]["title"] == "Alpha"

    def test_query_no_results(self, flask_client):
        client, state, _ = flask_client
        _insert_media(state, "s1", title="Star Wars")
        with patch.object(
            type(client.application.config["server"]), "scan_library", return_value=[]
        ):
            resp = client.get("/api/search?q=titanic")
        data = resp.get_json()
        assert data["count"] == 0


class TestApiScan:
    def test_force_scan(self, flask_client):
        client, _, _ = flask_client
        resp = client.post("/api/scan")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "completed"
        assert "count" in data


class TestApiStream:
    def test_stream_existing_file(self, flask_client):
        client, state, tmp = flask_client
        media_dir = tmp / "media"
        media_dir.mkdir(exist_ok=True)
        test_file = media_dir / "test.mp4"
        test_file.write_bytes(b"\x00" * 1024)
        _insert_media(state, "vid1", file_path=str(test_file))
        resp = client.get("/api/stream/vid1")
        assert resp.status_code in (200, 206)

    def test_stream_missing_file(self, flask_client):
        client, state, _ = flask_client
        _insert_media(state, "vid2", file_path="/nonexistent/file.mp4")
        resp = client.get("/api/stream/vid2")
        assert resp.status_code == 404


class TestApiDownload:
    def test_download_file(self, flask_client):
        client, state, tmp = flask_client
        media_dir = tmp / "media"
        media_dir.mkdir(exist_ok=True)
        test_file = media_dir / "movie.mp4"
        test_file.write_bytes(b"fakevideo")
        _insert_media(state, "dl1", file_path=str(test_file), filename="movie.mp4")
        resp = client.get("/api/download/dl1")
        assert resp.status_code == 200
        assert b"fakevideo" in resp.data

    def test_download_not_found(self, flask_client):
        client, _, _ = flask_client
        resp = client.get("/api/download/nofile")
        assert resp.status_code == 404


class TestApiPoster:
    def test_poster_found(self, flask_client):
        client, state, tmp = flask_client
        poster_file = tmp / "poster.jpg"
        poster_file.write_bytes(b"\xff\xd8\xff\xe0")  # JPEG header
        _insert_media(state, "p1", poster_path=str(poster_file))
        resp = client.get("/api/poster/p1")
        assert resp.status_code == 200

    def test_poster_not_found(self, flask_client):
        client, _, _ = flask_client
        resp = client.get("/api/poster/nope")
        assert resp.status_code == 404


class TestApiUpdateMetadata:
    def test_update(self, flask_client):
        client, state, _ = flask_client
        _insert_media(state, "ed1", title="Old Title")
        resp = client.put("/api/media/ed1/metadata", json={"title": "New Title", "year": "2025"})
        assert resp.status_code == 200
        item = state.get_media("ed1")
        assert item["title"] == "New Title"

    def test_no_data(self, flask_client):
        client, state, _ = flask_client
        _insert_media(state, "ed2")
        resp = client.put("/api/media/ed2/metadata", content_type="application/json", data="")
        assert resp.status_code == 400

    def test_not_found(self, flask_client):
        client, _, _ = flask_client
        resp = client.put("/api/media/ghost/metadata", json={"title": "X"})
        assert resp.status_code == 404


class TestApiStats:
    def test_stats(self, flask_client):
        client, state, _ = flask_client
        _insert_media(state, "st1", media_type="video", file_size=5000)
        _insert_media(state, "st2", media_type="audio", file_size=3000)
        resp = client.get("/api/stats")
        data = resp.get_json()
        assert data["total_items"] == 2
        assert data["by_type"]["video"] == 1
        assert data["by_type"]["audio"] == 1
        assert data["total_size"] == 8000
