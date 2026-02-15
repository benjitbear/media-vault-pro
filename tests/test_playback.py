"""
Tests for playback progress, chunked streaming, and collection shuffle features.
"""

import io
import json
from pathlib import Path

import pytest

from src.app_state import AppState
from src.web_server import MediaServer

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def playback_config(tmp_path):
    """Config for playback tests"""
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
        "web_server": {"enabled": True, "port": 8098, "host": "127.0.0.1", "library_name": "Test"},
        "disc_detection": {"check_interval_seconds": 5, "mount_path": "/Volumes"},
        "handbrake": {"preset": "Fast 1080p30", "additional_options": []},
        "auth": {"enabled": False, "session_hours": 24},
        "library_cache": {"ttl_seconds": 300},
        "uploads": {
            "enabled": True,
            "max_upload_size_mb": 10,
            "upload_directory": str(tmp_path / "uploads"),
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
def flask_client(tmp_path, playback_config):
    """Create a Flask test client"""
    AppState.reset()
    state = AppState(db_path=str(tmp_path / "test.db"))

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(playback_config))

    server = MediaServer(config_path=str(config_path), app_state=state)
    server.app.config["TESTING"] = True

    with server.app.test_client() as client:
        yield client

    AppState.reset()


@pytest.fixture
def state_with_media(tmp_path):
    """AppState pre-populated with sample media"""
    AppState.reset()
    state = AppState(db_path=str(tmp_path / "test.db"))
    # Insert two test media items
    state.upsert_media(
        {
            "id": "media_001",
            "title": "Test Video",
            "filename": "test.mp4",
            "file_path": "/tmp/test.mp4",
            "file_size": 1024,
            "media_type": "video",
        }
    )
    state.upsert_media(
        {
            "id": "media_002",
            "title": "Test Song",
            "filename": "song.mp3",
            "file_path": "/tmp/song.mp3",
            "file_size": 512,
            "media_type": "audio",
        }
    )
    state.upsert_media(
        {
            "id": "media_003",
            "title": "Another Song",
            "filename": "song2.mp3",
            "file_path": "/tmp/song2.mp3",
            "file_size": 256,
            "media_type": "audio",
        }
    )
    yield state
    AppState.reset()


# ── Playback Progress DB Tests ───────────────────────────────────


class TestPlaybackProgressDB:
    """Tests for playback progress CRUD in AppState"""

    def test_save_and_get_progress(self, state_with_media):
        state = state_with_media
        state.save_playback_progress("media_001", 120.5, 3600.0, "alice")
        prog = state.get_playback_progress("media_001", "alice")
        assert prog is not None
        assert prog["position_seconds"] == 120.5
        assert prog["duration_seconds"] == 3600.0
        assert prog["finished"] == 0

    def test_progress_not_found(self, state_with_media):
        prog = state_with_media.get_playback_progress("media_001", "bob")
        assert prog is None

    def test_progress_upsert(self, state_with_media):
        state = state_with_media
        state.save_playback_progress("media_001", 60.0, 3600.0)
        state.save_playback_progress("media_001", 120.0, 3600.0)
        prog = state.get_playback_progress("media_001", "anonymous")
        assert prog["position_seconds"] == 120.0

    def test_auto_finish_at_95_percent(self, state_with_media):
        state = state_with_media
        # 96% through a 100-second video -> should mark finished
        state.save_playback_progress("media_001", 96.0, 100.0)
        prog = state.get_playback_progress("media_001", "anonymous")
        assert prog["finished"] == 1

    def test_not_finished_at_90_percent(self, state_with_media):
        state = state_with_media
        state.save_playback_progress("media_001", 90.0, 100.0)
        prog = state.get_playback_progress("media_001", "anonymous")
        assert prog["finished"] == 0

    def test_clear_progress(self, state_with_media):
        state = state_with_media
        state.save_playback_progress("media_001", 60.0, 100.0)
        assert state.clear_playback_progress("media_001", "anonymous")
        assert state.get_playback_progress("media_001", "anonymous") is None

    def test_clear_nonexistent(self, state_with_media):
        assert not state_with_media.clear_playback_progress("nope", "anonymous")

    def test_per_user_isolation(self, state_with_media):
        state = state_with_media
        state.save_playback_progress("media_001", 30.0, 100.0, "alice")
        state.save_playback_progress("media_001", 80.0, 100.0, "bob")
        assert state.get_playback_progress("media_001", "alice")["position_seconds"] == 30.0
        assert state.get_playback_progress("media_001", "bob")["position_seconds"] == 80.0

    def test_get_in_progress_media(self, state_with_media):
        state = state_with_media
        state.save_playback_progress("media_001", 60.0, 3600.0, "alice")
        state.save_playback_progress("media_002", 15.0, 200.0, "alice")
        # media_003 finished
        state.save_playback_progress("media_003", 98.0, 100.0, "alice")
        result = state.get_in_progress_media("alice")
        ids = [r["id"] for r in result]
        assert "media_001" in ids
        assert "media_002" in ids
        assert "media_003" not in ids  # finished

    def test_in_progress_excludes_short_position(self, state_with_media):
        """Progress < 5 seconds should not appear (accidental click)"""
        state = state_with_media
        state.save_playback_progress("media_001", 3.0, 3600.0)
        result = state.get_in_progress_media("anonymous")
        assert len(result) == 0

    def test_in_progress_sorted_by_recent(self, state_with_media):
        state = state_with_media
        import time

        state.save_playback_progress("media_001", 60.0, 3600.0)
        time.sleep(0.05)
        state.save_playback_progress("media_002", 30.0, 200.0)
        result = state.get_in_progress_media("anonymous")
        # media_002 should be first (most recently updated)
        assert result[0]["id"] == "media_002"


# ── Playback Progress API Tests ──────────────────────────────────


class TestPlaybackProgressAPI:
    """Tests for playback progress REST endpoints"""

    def _seed_media(self, client, tmp_path, playback_config):
        """Helper: seed a media item via upload"""
        upload_dir = Path(playback_config["uploads"]["upload_directory"])
        upload_dir.mkdir(parents=True, exist_ok=True)
        data = {"files": (io.BytesIO(b"\x00" * 100), "test_vid.mp4")}
        resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
        return resp.get_json()["uploaded"][0]["id"]

    def test_get_progress_empty(self, flask_client):
        resp = flask_client.get("/api/media/nonexistent/progress")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["position_seconds"] == 0
        assert data["finished"] == 0

    def test_save_and_get_progress(self, flask_client, tmp_path, playback_config):
        media_id = self._seed_media(flask_client, tmp_path, playback_config)
        # Save progress
        resp = flask_client.put(
            f"/api/media/{media_id}/progress",
            data=json.dumps({"position": 45.2, "duration": 120.0}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        # Retrieve
        resp = flask_client.get(f"/api/media/{media_id}/progress")
        data = resp.get_json()
        assert data["position_seconds"] == 45.2
        assert data["duration_seconds"] == 120.0

    def test_delete_progress(self, flask_client, tmp_path, playback_config):
        media_id = self._seed_media(flask_client, tmp_path, playback_config)
        flask_client.put(
            f"/api/media/{media_id}/progress",
            data=json.dumps({"position": 30.0, "duration": 100.0}),
            content_type="application/json",
        )
        resp = flask_client.delete(f"/api/media/{media_id}/progress")
        assert resp.status_code == 200
        # Should be cleared
        data = flask_client.get(f"/api/media/{media_id}/progress").get_json()
        assert data["position_seconds"] == 0

    def test_continue_watching_endpoint(self, flask_client, tmp_path, playback_config):
        media_id = self._seed_media(flask_client, tmp_path, playback_config)
        flask_client.put(
            f"/api/media/{media_id}/progress",
            data=json.dumps({"position": 60.0, "duration": 300.0}),
            content_type="application/json",
        )
        resp = flask_client.get("/api/continue-watching")
        assert resp.status_code == 200
        items = resp.get_json()["items"]
        assert len(items) >= 1
        assert items[0]["progress_position"] == 60.0

    def test_save_progress_no_data(self, flask_client):
        resp = flask_client.put("/api/media/fake/progress", content_type="application/json")
        assert resp.status_code == 400


# ── Chunked Streaming Tests ──────────────────────────────────────


class TestChunkedStreaming:
    """Tests for HTTP range request streaming"""

    def _create_test_file(self, tmp_path, playback_config, name, size):
        """Create a test media file and register it"""
        upload_dir = Path(playback_config["uploads"]["upload_directory"])
        upload_dir.mkdir(parents=True, exist_ok=True)
        content = bytes(range(256)) * (size // 256 + 1)
        content = content[:size]
        data = {"files": (io.BytesIO(content), name)}
        return content, data

    def test_stream_accepts_range(self, flask_client, tmp_path, playback_config):
        """Verify Accept-Ranges header is returned"""
        content, data = self._create_test_file(tmp_path, playback_config, "range_test.mp4", 1024)
        resp = flask_client.post("/api/upload", data=data, content_type="multipart/form-data")
        media_id = resp.get_json()["uploaded"][0]["id"]

        resp = flask_client.get(f"/api/stream/{media_id}")
        assert resp.status_code == 200
        assert resp.headers.get("Accept-Ranges") == "bytes"

    def test_stream_partial_range(self, flask_client, tmp_path, playback_config):
        """Request a specific byte range and verify 206 response"""
        content, data = self._create_test_file(tmp_path, playback_config, "partial.mp4", 2048)
        resp = flask_client.post("/api/upload", data=data, content_type="multipart/form-data")
        media_id = resp.get_json()["uploaded"][0]["id"]

        resp = flask_client.get(f"/api/stream/{media_id}", headers={"Range": "bytes=0-99"})
        assert resp.status_code == 206
        assert resp.headers.get("Content-Length") == "100"
        assert "bytes 0-99/" in resp.headers.get("Content-Range", "")

    def test_stream_full_has_content_length(self, flask_client, tmp_path, playback_config):
        """Full download should have Content-Length set"""
        content, data = self._create_test_file(tmp_path, playback_config, "full.mp4", 512)
        resp = flask_client.post("/api/upload", data=data, content_type="multipart/form-data")
        media_id = resp.get_json()["uploaded"][0]["id"]

        resp = flask_client.get(f"/api/stream/{media_id}")
        assert resp.status_code == 200
        assert int(resp.headers.get("Content-Length", 0)) == 512


# ── Collection Items Endpoint Test ───────────────────────────────


class TestCollectionPlayback:
    """Tests for collection items endpoint used by queue player"""

    def test_collection_items_endpoint(self, flask_client, tmp_path, playback_config):
        """Verify GET /api/collections/<id>/items returns ordered items"""
        upload_dir = Path(playback_config["uploads"]["upload_directory"])
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Upload two files
        ids = []
        for name in ["track1.mp3", "track2.mp3"]:
            data = {"files": (io.BytesIO(b"\x00" * 50), name)}
            resp = flask_client.post("/api/upload", data=data, content_type="multipart/form-data")
            ids.append(resp.get_json()["uploaded"][0]["id"])

        # Create collection
        flask_client.put(
            "/api/collections/Test%20Playlist",
            data=json.dumps({"media_ids": ids, "collection_type": "playlist"}),
            content_type="application/json",
        )

        # Get collections to find ID
        resp = flask_client.get("/api/collections")
        col = resp.get_json()["collections"][0]

        # Fetch items via the new endpoint
        resp = flask_client.get(f'/api/collections/{col["id"]}/items')
        assert resp.status_code == 200
        items = resp.get_json()["items"]
        assert len(items) == 2
        assert items[0]["id"] == ids[0]
        assert items[1]["id"] == ids[1]
