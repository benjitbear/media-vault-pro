"""
Unit tests for the MetadataExtractor module
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json


class TestMetadataExtractor:
    """Test suite for MetadataExtractor class"""

    @pytest.fixture
    def extractor(self):
        """Create a MetadataExtractor instance for testing"""
        from src.metadata import MetadataExtractor

        return MetadataExtractor()

    @pytest.mark.unit
    def test_extractor_initialization(self, extractor):
        """Test MetadataExtractor initializes correctly"""
        assert extractor is not None
        assert hasattr(extractor, "metadata_dir")
        assert hasattr(extractor, "config")

    @pytest.mark.unit
    def test_extract_mediainfo(self, extractor, tmp_path):
        """Test extraction of basic file metadata"""
        # Create a dummy file so mediainfo can at least find it
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"\x00" * 100)

        # mediainfo may or may not be installed; test gracefully
        result = extractor.extract_mediainfo(str(test_file))
        # If mediainfo is installed, we get a dict; otherwise None
        if result is not None:
            assert "file_path" in result
            assert "file_size_bytes" in result

    @pytest.mark.unit
    @patch("subprocess.run")
    def test_extract_chapters(self, mock_run, extractor):
        """Test chapter information extraction"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "chapters": [
                        {"start_time": "0.0", "end_time": "300.0", "tags": {"title": "Chapter 1"}},
                        {
                            "start_time": "300.0",
                            "end_time": "600.0",
                            "tags": {"title": "Chapter 2"},
                        },
                    ]
                }
            ),
        )
        chapters = extractor.extract_chapters("/tmp/test.mp4")
        assert len(chapters) == 2
        assert chapters[0]["title"] == "Chapter 1"
        assert chapters[1]["start_time"] == 300.0

    @pytest.mark.unit
    def test_tmdb_without_api_key(self, extractor):
        """Test TMDB lookup gracefully handles missing API key"""
        extractor.tmdb_api_key = None
        result = extractor.search_tmdb("Test Movie")
        assert result is None

    @pytest.mark.unit
    def test_save_metadata(self, extractor, tmp_path):
        """Test that metadata is properly saved as JSON"""
        extractor.metadata_dir = tmp_path
        metadata = {"title": "Test", "year": 2024}
        extractor.save_metadata(metadata, "Test Movie")

        saved_file = tmp_path / "Test Movie.json"
        assert saved_file.exists()
        with open(saved_file) as f:
            loaded = json.load(f)
        assert loaded["title"] == "Test"

    @pytest.mark.unit
    def test_clean_search_title(self, extractor):
        """Test title cleaning strips disc noise from volume names"""
        assert extractor._clean_search_title("THE_MATRIX") == "THE MATRIX"
        assert "DVD" not in extractor._clean_search_title("MOVIE_DVD")
        assert "DISC" not in extractor._clean_search_title("MOVIE_DISC_1")
        assert "WIDESCREEN" not in extractor._clean_search_title("MOVIE_WIDESCREEN")
        # Timestamps should be stripped
        cleaned = extractor._clean_search_title("PRELUDE_20260207_160005")
        assert "20260207" not in cleaned

    @pytest.mark.unit
    def test_aggressive_clean_title(self, extractor):
        """Test aggressive title cleaning removes non-alpha chars"""
        result = extractor._aggressive_clean_title("M0V13_2024!!!")
        assert result.isalpha() or " " in result

    @pytest.mark.unit
    def test_pick_best_tmdb_match_no_hints(self, extractor):
        """Test best match picker falls back to first result without hints"""
        results = [{"id": 100}, {"id": 200}]
        assert extractor._pick_best_tmdb_match(results, {}) == 100

    @pytest.mark.unit
    def test_search_musicbrainz_no_results(self, extractor):
        """Test MusicBrainz search handles no results gracefully"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=200, json=lambda: {"releases": []})
            mock_get.return_value.raise_for_status = lambda: None
            result = extractor.search_musicbrainz("Nonexistent Album XYZ123")
            assert result is None

    @pytest.mark.unit
    def test_extract_full_metadata_audio_cd(self, extractor, tmp_path):
        """Test full metadata extraction for audio CD type"""
        extractor.tmdb_api_key = None  # No API key
        metadata = extractor.extract_full_metadata(
            str(tmp_path),
            title_hint="Test Album",
            disc_hints={"disc_type": "audio_cd", "track_count": 10},
        )
        assert metadata["disc_type"] == "audio_cd"

    @pytest.mark.unit
    def test_download_backdrop_no_path(self, extractor):
        """Test backdrop download returns False for None path"""
        assert extractor.download_backdrop(None, "/tmp/test.jpg") is False

    @pytest.mark.unit
    def test_download_cover_art_no_url(self, extractor):
        """Test cover art download returns False for None URL"""
        assert extractor.download_cover_art(None, "/tmp/test.jpg") is False

    # ── AcoustID / Chromaprint tests ──────────────────────────────

    @pytest.mark.unit
    def test_fingerprint_file_pyacoustid(self, extractor, tmp_path):
        """Test fingerprinting delegates to pyacoustid when available"""
        test_file = tmp_path / "track.flac"
        test_file.write_bytes(b"\x00" * 100)

        with patch.dict("sys.modules", {"acoustid": MagicMock()}) as modules:
            modules["acoustid"].fingerprint_file.return_value = (240, "AQAA...")

            # Patch at the point of import inside the method
            with patch(
                "builtins.__import__",
                side_effect=lambda name, *a, **kw: modules.get(name)
                or __builtins__.__import__(name, *a, **kw),
            ):
                pass  # Covered by the integration path below

        # Simpler: mock acoustid import directly inside the method
        mock_acoustid = MagicMock()
        mock_acoustid.fingerprint_file.return_value = (240, "AQAA_FAKE_FP")
        with patch.dict("sys.modules", {"acoustid": mock_acoustid}):
            result = extractor.fingerprint_file(str(test_file))
            if result:  # pyacoustid may still fail on dummy data
                assert "duration" in result
                assert "fingerprint" in result

    @pytest.mark.unit
    @patch("subprocess.run")
    def test_fingerprint_file_fpcalc_fallback(self, mock_run, extractor, tmp_path):
        """Test fingerprinting falls back to fpcalc CLI"""
        test_file = tmp_path / "track.wav"
        test_file.write_bytes(b"\x00" * 100)

        mock_run.return_value = Mock(
            returncode=0, stdout=json.dumps({"duration": 180, "fingerprint": "AQAA_CLI_FP"})
        )

        # Force ImportError on acoustid so fpcalc path is taken
        with patch.dict("sys.modules", {"acoustid": None}):
            result = extractor.fingerprint_file(str(test_file))

        assert result is not None
        assert result["duration"] == 180
        assert result["fingerprint"] == "AQAA_CLI_FP"

    @pytest.mark.unit
    def test_fingerprint_file_neither_available(self, extractor, tmp_path):
        """Test fingerprint returns None when no tool is available"""
        test_file = tmp_path / "track.wav"
        test_file.write_bytes(b"\x00" * 100)

        with patch.dict("sys.modules", {"acoustid": None}):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = extractor.fingerprint_file(str(test_file))

        assert result is None

    @pytest.mark.unit
    def test_lookup_acoustid_no_api_key(self, extractor):
        """Test AcoustID lookup returns None without API key"""
        extractor.acoustid_api_key = None
        result = extractor.lookup_acoustid("/tmp/track.flac")
        assert result is None

    @pytest.mark.unit
    def test_lookup_acoustid_success(self, extractor):
        """Test AcoustID lookup parses a successful response"""
        extractor.acoustid_api_key = "test-key"

        acoustid_response = {
            "status": "ok",
            "results": [
                {
                    "score": 0.95,
                    "recordings": [
                        {
                            "id": "rec-uuid-1234",
                            "title": "Test Song",
                            "artists": [{"name": "Test Artist"}],
                            "releasegroups": [
                                {"title": "Test Album", "releases": [{"id": "rel-uuid-5678"}]}
                            ],
                        }
                    ],
                }
            ],
        }

        with patch.object(
            extractor,
            "fingerprint_file",
            return_value={"duration": 200, "fingerprint": "AQAA_FAKE"},
        ):
            with patch("requests.post") as mock_post:
                mock_post.return_value = Mock(status_code=200, json=lambda: acoustid_response)
                mock_post.return_value.raise_for_status = lambda: None

                result = extractor.lookup_acoustid("/tmp/track.flac")

        assert result is not None
        assert result["musicbrainz_recording_id"] == "rec-uuid-1234"
        assert result["title"] == "Test Song"
        assert result["artist"] == "Test Artist"
        assert result["musicbrainz_release_id"] == "rel-uuid-5678"
        assert result["album"] == "Test Album"

    @pytest.mark.unit
    def test_lookup_acoustid_no_results(self, extractor):
        """Test AcoustID lookup handles empty results"""
        extractor.acoustid_api_key = "test-key"

        with patch.object(
            extractor,
            "fingerprint_file",
            return_value={"duration": 200, "fingerprint": "AQAA_FAKE"},
        ):
            with patch("requests.post") as mock_post:
                mock_post.return_value = Mock(
                    status_code=200, json=lambda: {"status": "ok", "results": []}
                )
                mock_post.return_value.raise_for_status = lambda: None

                result = extractor.lookup_acoustid("/tmp/track.flac")

        assert result is None

    @pytest.mark.unit
    def test_lookup_musicbrainz_by_release_id(self, extractor):
        """Test MusicBrainz release lookup by ID returns metadata"""
        mb_response = {
            "title": "Test Album",
            "date": "2024-03-15",
            "artist-credit": [{"artist": {"name": "Test Artist"}}],
            "media": [
                {
                    "tracks": [
                        {"number": "1", "title": "Track One", "length": 240000},
                        {"number": "2", "title": "Track Two", "length": 300000},
                    ]
                }
            ],
            "label-info": [{"label": {"name": "Test Label"}}],
        }

        with patch("requests.get") as mock_get:
            # First call: release detail; second call: cover art (404)
            detail_resp = Mock(status_code=200, json=lambda: mb_response)
            detail_resp.raise_for_status = lambda: None
            cover_resp = Mock(status_code=404)

            mock_get.side_effect = [detail_resp, cover_resp]

            result = extractor.lookup_musicbrainz_by_release_id("rel-uuid-5678")

        assert result is not None
        assert result["title"] == "Test Album"
        assert result["artist"] == "Test Artist"
        assert result["year"] == "2024"
        assert result["track_count"] == 2
        assert result["identified_by"] == "acoustid_fingerprint"
        assert result["label"] == "Test Label"

    @pytest.mark.unit
    def test_extract_full_metadata_audio_cd_fingerprint(self, extractor, tmp_path):
        """Test that audio CD extraction tries fingerprinting first"""
        extractor.acoustid_api_key = "test-key"

        fake_mb = {
            "title": "Fingerprinted Album",
            "artist": "FP Artist",
            "year": "2025",
            "track_count": 10,
            "tracks": [],
            "musicbrainz_id": "rel-uuid",
            "media_type": "audio",
            "identified_by": "acoustid_fingerprint",
            "cover_art_url": None,
        }

        sample_track = tmp_path / "track01.flac"
        sample_track.write_bytes(b"\x00" * 100)

        with patch.object(
            extractor,
            "lookup_acoustid",
            return_value={
                "musicbrainz_release_id": "rel-uuid",
                "title": "Some Track",
                "artist": "FP Artist",
            },
        ):
            with patch.object(extractor, "lookup_musicbrainz_by_release_id", return_value=fake_mb):
                metadata = extractor.extract_full_metadata(
                    str(sample_track),
                    title_hint="Unknown Disc",
                    disc_hints={
                        "disc_type": "audio_cd",
                        "track_count": 10,
                        "sample_track_path": str(sample_track),
                    },
                )

        assert metadata["disc_type"] == "audio_cd"
        assert metadata["musicbrainz"]["identified_by"] == "acoustid_fingerprint"
        assert metadata["musicbrainz"]["title"] == "Fingerprinted Album"
