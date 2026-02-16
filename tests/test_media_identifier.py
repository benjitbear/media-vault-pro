"""
Tests for the MediaIdentifierService.

Covers: filename parsing, TMDB integration, identify flow, and the
manual identify API endpoint.
"""

import io
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.app_state import AppState
from src.services.media_identifier import MediaIdentifierService


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def identifier_config(tmp_path):
    """Minimal config dict for the identifier."""
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
            "save_to_json": True,
            "extract_chapters": False,
            "extract_subtitles": False,
            "extract_audio_tracks": False,
            "fetch_online_metadata": True,
            "acoustid_fingerprint": False,
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
        "uploads": {"enabled": True, "max_upload_size_mb": 100},
        "downloads": {
            "download_directory": str(tmp_path / "downloads"),
            "articles_directory": str(tmp_path / "articles"),
            "books_directory": str(tmp_path / "books"),
        },
        "podcasts": {"enabled": False},
        "file_naming": {"rename_after_rip": False},
    }


@pytest.fixture
def app_state(tmp_path):
    """Fresh AppState with a temp DB."""
    AppState.reset()
    state = AppState(db_path=str(tmp_path / "test.db"))
    yield state
    AppState.reset()


@pytest.fixture
def mock_metadata_extractor():
    """Mock MetadataExtractor with controllable return values."""
    extractor = MagicMock()
    extractor.extract_mediainfo.return_value = {
        "duration_seconds": 8880.0,  # 148 minutes
        "format": "Matroska",
        "video": {"codec": "H.264", "width": "1920", "height": "1080"},
    }
    extractor.search_tmdb.return_value = {
        "title": "Inception",
        "original_title": "Inception",
        "year": "2010",
        "overview": "A thief who steals corporate secrets through dream-sharing technology.",
        "runtime_minutes": 148,
        "genres": ["Action", "Science Fiction", "Adventure"],
        "rating": 8.4,
        "tmdb_id": 27205,
        "poster_path": "/qmDpIHrmpJINaRKAfWQfftjCdyi.jpg",
        "backdrop_path": "/s3TBrRGB1iav7gFOCNx3H31MoES.jpg",
        "collection_name": None,
        "director": "Christopher Nolan",
        "cast": ["Leonardo DiCaprio", "Joseph Gordon-Levitt", "Elliot Page"],
    }
    extractor.download_poster.return_value = True
    extractor.download_backdrop.return_value = True
    return extractor


@pytest.fixture
def identifier(tmp_path, identifier_config, app_state, mock_metadata_extractor):
    """Build a MediaIdentifierService with mocked external calls."""
    with patch.dict(os.environ, {"MEDIA_ROOT": str(tmp_path / "media_root")}):
        svc = MediaIdentifierService(
            config=identifier_config,
            app_state=app_state,
            metadata_extractor=mock_metadata_extractor,
        )
    return svc


# ── Filename Parsing ─────────────────────────────────────────────


class TestParseFilename:
    """Tests for the guessit-based filename parser."""

    def test_movie_with_year_and_quality(self):
        result = MediaIdentifierService._parse_filename("Inception.2010.1080p.BluRay.x264.mp4")
        assert result["title"] == "Inception"
        assert result["year"] == 2010
        assert result["type"] == "movie"

    def test_movie_with_parenthesized_year(self):
        result = MediaIdentifierService._parse_filename("The Dark Knight (2008).mkv")
        assert result["title"] == "The Dark Knight"
        assert result["year"] == 2008

    def test_movie_minimal_name(self):
        result = MediaIdentifierService._parse_filename("Interstellar.mp4")
        assert result["title"] == "Interstellar"
        assert result["type"] == "movie"

    def test_tv_episode(self):
        result = MediaIdentifierService._parse_filename(
            "Breaking.Bad.S01E01.720p.BluRay.x264.mkv"
        )
        assert result["title"] == "Breaking Bad"
        assert result["season"] == 1
        assert result["episode"] == 1
        assert result["type"] == "episode"

    def test_movie_with_scene_tags(self):
        result = MediaIdentifierService._parse_filename(
            "The.Matrix.1999.Remastered.2160p.UHD.BluRay.REMUX.mkv"
        )
        assert result["title"] == "The Matrix"
        assert result["year"] == 1999

    def test_simple_filename_no_metadata(self):
        result = MediaIdentifierService._parse_filename("vacation_video.mp4")
        assert result["title"] is not None
        assert result["type"] == "movie"

    def test_empty_string_returns_defaults(self):
        result = MediaIdentifierService._parse_filename("")
        # Should not crash
        assert isinstance(result, dict)

    def test_unicode_title(self):
        result = MediaIdentifierService._parse_filename("千と千尋の神隠し.2001.mp4")
        # Should not crash and should extract something
        assert isinstance(result, dict)
        assert result.get("year") == 2001


# ── Identify File ────────────────────────────────────────────────


class TestIdentifyFile:
    """Tests for the full identification flow."""

    def test_identify_video_success(self, identifier, tmp_path, app_state, mock_metadata_extractor):
        """Full identify flow with a video file → TMDB match."""
        video = tmp_path / "Inception.2010.1080p.BluRay.x264.mp4"
        video.write_bytes(b"\x00" * 1024)

        result = identifier.identify_file(str(video))

        assert result["title"] == "Inception"
        assert result["year"] == "2010"
        assert result["has_metadata"] is True
        assert result["tmdb_id"] == 27205
        assert result["director"] == "Christopher Nolan"
        assert "Action" in result["genres"]
        assert result["duration_seconds"] == 8880.0

        # Verify DB was updated
        db_item = app_state.get_media(result["id"])
        assert db_item is not None
        assert db_item["title"] == "Inception"
        assert db_item["tmdb_id"] == 27205

        # Verify TMDB search was called with correct title + year
        mock_metadata_extractor.search_tmdb.assert_called_once()
        call_args = mock_metadata_extractor.search_tmdb.call_args
        assert call_args[0][0] == "Inception"
        assert call_args[1]["year"] == 2010

    def test_identify_with_title_override(self, identifier, tmp_path, mock_metadata_extractor):
        """User-supplied title overrides filename parsing."""
        video = tmp_path / "random_file_name_1234.mp4"
        video.write_bytes(b"\x00" * 512)

        result = identifier.identify_file(str(video), title_override="Inception", year_override=2010)

        assert result["title"] == "Inception"
        mock_metadata_extractor.search_tmdb.assert_called_once()
        call_args = mock_metadata_extractor.search_tmdb.call_args
        assert call_args[0][0] == "Inception"
        assert call_args[1]["year"] == 2010

    def test_identify_no_tmdb_match(self, identifier, tmp_path, mock_metadata_extractor):
        """When TMDB returns nothing, the item is still stored with parsed data."""
        mock_metadata_extractor.search_tmdb.return_value = None

        video = tmp_path / "My Home Movie 2024.mp4"
        video.write_bytes(b"\x00" * 256)

        result = identifier.identify_file(str(video))

        assert result["title"] == "My Home Movie"
        assert result["has_metadata"] is False
        assert result["tmdb_id"] is None

    def test_identify_nonexistent_file(self, identifier):
        """Should return empty dict for missing file."""
        result = identifier.identify_file("/nonexistent/path/movie.mp4")
        assert result == {}

    def test_identify_saves_sidecar_json(self, identifier, tmp_path, mock_metadata_extractor):
        """Verify that a metadata JSON sidecar is written to disk."""
        video = tmp_path / "Inception.2010.mp4"
        video.write_bytes(b"\x00" * 256)

        identifier.identify_file(str(video))

        # Check that a sidecar exists in the metadata dir
        sidecar_path = identifier.metadata_dir / "Inception.json"
        assert sidecar_path.exists()

        with open(sidecar_path) as f:
            data = json.load(f)
        assert "tmdb" in data
        assert data["tmdb"]["title"] == "Inception"
        assert "identification" in data
        assert data["identification"]["method"] == "guessit"

    def test_identify_downloads_poster(self, identifier, tmp_path, mock_metadata_extractor):
        """Poster and backdrop download methods are called."""
        video = tmp_path / "Inception.2010.mp4"
        video.write_bytes(b"\x00" * 256)

        result = identifier.identify_file(str(video))

        mock_metadata_extractor.download_poster.assert_called_once()
        mock_metadata_extractor.download_backdrop.assert_called_once()
        # poster_path should be set
        assert result.get("poster_path") is not None

    def test_identify_uses_runtime_hint(self, identifier, tmp_path, mock_metadata_extractor):
        """Duration from MediaInfo is passed as estimated_runtime_min to TMDB."""
        video = tmp_path / "Inception.2010.mp4"
        video.write_bytes(b"\x00" * 256)

        identifier.identify_file(str(video))

        call_kwargs = mock_metadata_extractor.search_tmdb.call_args[1]
        disc_hints = call_kwargs["disc_hints"]
        assert "estimated_runtime_min" in disc_hints
        assert abs(disc_hints["estimated_runtime_min"] - 148.0) < 0.1

    def test_identify_non_video_file(self, identifier, tmp_path, mock_metadata_extractor):
        """Non-video files skip MediaInfo but still try TMDB."""
        doc = tmp_path / "Inception Script.pdf"
        doc.write_bytes(b"%PDF-1.4")

        result = identifier.identify_file(str(doc))

        # MediaInfo should NOT be called for non-video
        mock_metadata_extractor.extract_mediainfo.assert_not_called()
        # But TMDB is still called (based on parsed filename)
        mock_metadata_extractor.search_tmdb.assert_called_once()

    def test_identify_skips_tmdb_when_disabled(self, identifier, tmp_path, mock_metadata_extractor):
        """When fetch_online_metadata is False, TMDB is skipped."""
        identifier.config["metadata"]["fetch_online_metadata"] = False

        video = tmp_path / "Inception.2010.mp4"
        video.write_bytes(b"\x00" * 256)

        result = identifier.identify_file(str(video))

        mock_metadata_extractor.search_tmdb.assert_not_called()
        assert result["has_metadata"] is False


# ── Identify by Media ID ─────────────────────────────────────────


class TestIdentifyByMediaId:
    """Tests for re-identifying an existing media item."""

    def test_reidentify_existing_item(self, identifier, tmp_path, app_state, mock_metadata_extractor):
        """Re-identify updates an existing DB record."""
        video = tmp_path / "unknown_movie.mp4"
        video.write_bytes(b"\x00" * 512)

        # First, register as an unidentified item
        from src.utils import generate_media_id

        media_id = generate_media_id(str(video))
        app_state.upsert_media({
            "id": media_id,
            "title": "unknown_movie",
            "filename": video.name,
            "file_path": str(video),
            "file_size": 512,
            "media_type": "video",
        })

        # Now re-identify with a title override
        result = identifier.identify_by_media_id(
            media_id, title_override="Inception", year_override=2010
        )

        assert result["title"] == "Inception"
        assert result["tmdb_id"] == 27205

        # DB should be updated
        db_item = app_state.get_media(media_id)
        assert db_item["title"] == "Inception"

    def test_reidentify_missing_id(self, identifier):
        """Non-existent media ID returns empty dict."""
        result = identifier.identify_by_media_id("nonexistent_id")
        assert result == {}

    def test_reidentify_missing_file(self, identifier, app_state):
        """If the file was deleted from disk, returns empty dict."""
        app_state.upsert_media({
            "id": "test123",
            "title": "Deleted Movie",
            "filename": "deleted.mp4",
            "file_path": "/nonexistent/deleted.mp4",
            "file_size": 0,
            "media_type": "video",
        })

        result = identifier.identify_by_media_id("test123")
        assert result == {}


# ── Upload Integration ────────────────────────────────────────────


class TestUploadIdentifyIntegration:
    """Tests that upload correctly queues identify jobs for video files."""

    @pytest.fixture
    def flask_client(self, tmp_path, identifier_config):
        """Flask test client wired with full config."""
        from src.web_server import MediaServer

        AppState.reset()
        state = AppState(db_path=str(tmp_path / "test.db"))

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        identifier_config["uploads"]["upload_directory"] = str(upload_dir)

        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(identifier_config))

        with patch.dict(os.environ, {"MEDIA_ROOT": str(tmp_path / "media_root")}):
            server = MediaServer(config_path=str(config_path), app_state=state)
            server.app.config["TESTING"] = True

            with server.app.test_client() as client:
                yield client, state

        AppState.reset()

    def test_upload_video_queues_identify_job(self, flask_client):
        """Uploading a video file should queue an identify job."""
        client, state = flask_client

        data = {"files": (io.BytesIO(b"\x00" * 100), "Inception.2010.1080p.mp4")}
        resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 201

        result = resp.get_json()
        assert result["uploaded"][0]["media_type"] == "video"

        # Check that an identify job was queued
        jobs = state.get_all_jobs()
        identify_jobs = [j for j in jobs if j["job_type"] == "identify"]
        assert len(identify_jobs) == 1
        assert "Inception" in identify_jobs[0]["title"]

    def test_upload_text_does_not_queue_identify(self, flask_client):
        """Non-video uploads should NOT queue an identify job."""
        client, state = flask_client

        data = {"files": (io.BytesIO(b"hello world"), "notes.txt")}
        resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 201

        jobs = state.get_all_jobs()
        identify_jobs = [j for j in jobs if j["job_type"] == "identify"]
        assert len(identify_jobs) == 0

    def test_upload_multiple_videos_queues_multiple_jobs(self, flask_client):
        """Each video upload gets its own identify job."""
        client, state = flask_client

        data = {
            "files": [
                (io.BytesIO(b"\x00" * 100), "Movie1.mp4"),
                (io.BytesIO(b"\x00" * 100), "Movie2.mkv"),
                (io.BytesIO(b"text"), "readme.txt"),
            ]
        }
        resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
        assert resp.status_code == 201

        jobs = state.get_all_jobs()
        identify_jobs = [j for j in jobs if j["job_type"] == "identify"]
        assert len(identify_jobs) == 2


# ── Manual Identify API Endpoint ──────────────────────────────────


class TestIdentifyEndpoint:
    """Tests for POST /api/media/<id>/identify."""

    @pytest.fixture
    def flask_client_with_media(self, tmp_path, identifier_config):
        """Flask test client with a pre-registered media item."""
        from src.web_server import MediaServer

        AppState.reset()
        state = AppState(db_path=str(tmp_path / "test.db"))

        video = tmp_path / "uploads" / "unknown_movie.mp4"
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"\x00" * 1024)

        from src.utils import generate_media_id

        media_id = generate_media_id(str(video))
        state.upsert_media({
            "id": media_id,
            "title": "unknown_movie",
            "filename": video.name,
            "file_path": str(video),
            "file_size": 1024,
            "media_type": "video",
        })

        identifier_config["uploads"]["upload_directory"] = str(tmp_path / "uploads")

        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(identifier_config))

        with patch.dict(os.environ, {"MEDIA_ROOT": str(tmp_path / "media_root")}):
            server = MediaServer(config_path=str(config_path), app_state=state)
            server.app.config["TESTING"] = True

            with server.app.test_client() as client:
                yield client, state, media_id

        AppState.reset()

    @patch("src.services.media_identifier.MediaIdentifierService")
    def test_identify_endpoint_success(self, MockIdentifier, flask_client_with_media):
        """POST /api/media/<id>/identify returns enriched item."""
        client, state, media_id = flask_client_with_media

        # Mock the identifier to return a known result
        mock_instance = MockIdentifier.return_value
        mock_instance.identify_file.return_value = {
            "id": media_id,
            "title": "Inception",
            "year": "2010",
            "tmdb_id": 27205,
            "has_metadata": True,
            "director": "Christopher Nolan",
            "genres": ["Action"],
            "cast": ["Leonardo DiCaprio"],
            "poster_path": "/some/path.jpg",
            "file_path": "/some/file.mp4",
        }

        resp = client.post(
            f"/api/media/{media_id}/identify",
            json={"title": "Inception", "year": 2010},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "identified"
        assert data["item"]["title"] == "Inception"
        assert data["item"]["tmdb_id"] == 27205
        # file_path should be stripped from response
        assert "file_path" not in data["item"]
        # has_poster derived from poster_path
        assert data["item"]["has_poster"] is True

    def test_identify_endpoint_not_found(self, flask_client_with_media):
        """Non-existent media ID returns 404."""
        client, _, _ = flask_client_with_media
        resp = client.post("/api/media/nonexistent/identify", json={})
        assert resp.status_code == 404

    @patch("src.services.media_identifier.MediaIdentifierService")
    def test_identify_endpoint_no_body(self, MockIdentifier, flask_client_with_media):
        """Calling without JSON body should still work (auto-detect from filename)."""
        client, state, media_id = flask_client_with_media

        mock_instance = MockIdentifier.return_value
        mock_instance.identify_file.return_value = {
            "id": media_id,
            "title": "unknown_movie",
            "year": None,
            "has_metadata": False,
        }

        resp = client.post(f"/api/media/{media_id}/identify")
        assert resp.status_code == 200

    @patch("src.services.media_identifier.MediaIdentifierService")
    def test_identify_endpoint_with_string_year(self, MockIdentifier, flask_client_with_media):
        """Year as string should be converted to int."""
        client, state, media_id = flask_client_with_media

        mock_instance = MockIdentifier.return_value
        mock_instance.identify_file.return_value = {
            "id": media_id,
            "title": "Test",
            "year": "2020",
            "has_metadata": True,
        }

        resp = client.post(
            f"/api/media/{media_id}/identify",
            json={"year": "2020"},
        )
        assert resp.status_code == 200
        call_kwargs = mock_instance.identify_file.call_args[1]
        assert call_kwargs["year_override"] == 2020
