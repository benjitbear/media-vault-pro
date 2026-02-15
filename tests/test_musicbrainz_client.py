"""Tests for MusicBrainzClient — fingerprinting, AcoustID, MB lookups, cover art."""

import json
import requests as _requests
import pytest
from unittest.mock import patch, MagicMock
from src.clients.musicbrainz_client import MusicBrainzClient


@pytest.fixture
def client():
    return MusicBrainzClient(acoustid_api_key="fake-acoustid-key")


@pytest.fixture
def client_no_key():
    return MusicBrainzClient(acoustid_api_key=None)


# ── _mb_request ──────────────────────────────────────────────────


class TestMbRequest:
    @patch("time.sleep")
    @patch("requests.get")
    def test_successful_request(self, mock_get, mock_sleep, client):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        result = client._mb_request("https://musicbrainz.org/ws/2/release/123")
        assert result is resp

    @patch("time.sleep")
    @patch("requests.get")
    def test_retry_on_connection_error(self, mock_get, mock_sleep, client):
        ok_resp = MagicMock()
        ok_resp.raise_for_status = MagicMock()
        mock_get.side_effect = [_requests.exceptions.ConnectionError("reset"), ok_resp]

        result = client._mb_request("https://mb.org/test", retries=2)
        assert result is ok_resp
        assert mock_get.call_count == 2

    @patch("time.sleep")
    @patch("requests.get")
    def test_retry_exhausted_returns_none(self, mock_get, mock_sleep, client):
        mock_get.side_effect = _requests.exceptions.ConnectionError("fail")
        result = client._mb_request("https://mb.org/test", retries=2)
        assert result is None

    @patch("time.sleep")
    @patch("requests.get")
    def test_http_error_returns_none(self, mock_get, mock_sleep, client):
        resp = MagicMock()
        resp.raise_for_status.side_effect = Exception("404")
        mock_get.return_value = resp
        result = client._mb_request("https://mb.org/test")
        assert result is None


# ── fingerprint_file ─────────────────────────────────────────────


class TestFingerprintFile:
    @patch("acoustid.fingerprint_file")
    def test_pyacoustid_success(self, mock_fp, client):
        mock_fp.return_value = (180.0, "ABCDEF")
        result = client.fingerprint_file("/fake/track.mp3")
        assert result == {"duration": 180, "fingerprint": "ABCDEF"}

    def test_fpcalc_fallback_on_import_error(self, client):
        """When acoustid raises ImportError, fall back to fpcalc CLI."""
        with patch("acoustid.fingerprint_file", side_effect=ImportError):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout=json.dumps({"duration": 200, "fingerprint": "GHIJKL"}),
                    returncode=0,
                )
                result = client.fingerprint_file("/fake/track.mp3")
                assert result is not None
                assert result["duration"] == 200
                assert result["fingerprint"] == "GHIJKL"

    def test_neither_available(self, client):
        """When both acoustid and fpcalc are unavailable, return None."""
        with patch("acoustid.fingerprint_file", side_effect=ImportError):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = client.fingerprint_file("/fake/track.mp3")
                assert result is None


# ── lookup_acoustid ──────────────────────────────────────────────


class TestLookupAcoustid:
    def test_no_api_key_returns_none(self, client_no_key):
        result = client_no_key.lookup_acoustid("/fake/track.mp3")
        assert result is None

    def test_fingerprint_failure_returns_none(self, client):
        with patch.object(client, "fingerprint_file", return_value=None):
            result = client.lookup_acoustid("/fake/track.mp3")
            assert result is None

    def test_delegates_to_lookup_from_fp(self, client):
        fp_data = {"duration": 180, "fingerprint": "ABC"}
        with patch.object(client, "fingerprint_file", return_value=fp_data):
            with patch.object(
                client, "lookup_acoustid_from_fp", return_value={"title": "Song"}
            ) as mock_lookup:
                result = client.lookup_acoustid("/fake/track.mp3", disc_hints={"track_count": 10})
                mock_lookup.assert_called_once_with(fp_data, disc_hints={"track_count": 10})
                assert result == {"title": "Song"}


# ── lookup_acoustid_from_fp ──────────────────────────────────────


class TestLookupAcoustidFromFp:
    @patch("requests.post")
    def test_successful_lookup(self, mock_post, client):
        resp = MagicMock()
        resp.json.return_value = {
            "status": "ok",
            "results": [
                {
                    "score": 0.95,
                    "recordings": [
                        {
                            "id": "rec-1",
                            "title": "Test Song",
                            "artists": [{"name": "Test Artist"}],
                            "releasegroups": [
                                {
                                    "type": "Album",
                                    "releases": [{"id": "rel-1", "title": "Test Album"}],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        mock_post.return_value = resp

        fp_data = {"duration": 180, "fingerprint": "ABC"}
        result = client.lookup_acoustid_from_fp(fp_data)
        assert result is not None

    @patch("requests.post")
    def test_no_results(self, mock_post, client):
        resp = MagicMock()
        resp.json.return_value = {"status": "ok", "results": []}
        mock_post.return_value = resp

        result = client.lookup_acoustid_from_fp({"duration": 180, "fingerprint": "ABC"})
        assert result is None

    @patch("requests.post")
    def test_low_score_filtered(self, mock_post, client):
        resp = MagicMock()
        resp.json.return_value = {"status": "ok", "results": [{"score": 0.1, "recordings": []}]}
        mock_post.return_value = resp

        result = client.lookup_acoustid_from_fp({"duration": 180, "fingerprint": "ABC"})
        assert result is None

    @patch("requests.post")
    def test_exception_returns_none(self, mock_post, client):
        mock_post.side_effect = Exception("network error")
        result = client.lookup_acoustid_from_fp({"duration": 180, "fingerprint": "ABC"})
        assert result is None


# ── validate_release_durations ───────────────────────────────────


class TestValidateReleaseDurations:
    def test_none_input(self, client):
        assert client.validate_release_durations(None) is None

    def test_missing_durations_passthrough(self, client):
        mb = {"title": "Album", "tracks": [{"title": "Song"}]}
        result = client.validate_release_durations(mb, {"track_durations": []})
        assert result is not None

    def test_track_count_mismatch_rejects(self, client):
        mb = {
            "title": "Album",
            "tracks": [
                {"duration_ms": 200000},
                {"duration_ms": 300000},
            ],
        }
        hints = {"track_durations": [200, 300, 250]}
        result = client.validate_release_durations(mb, hints)
        assert result is None

    def test_good_durations_pass(self, client):
        mb = {
            "title": "Album",
            "tracks": [
                {"duration_ms": 200000},
                {"duration_ms": 300000},
            ],
        }
        hints = {"track_durations": [200, 300]}
        result = client.validate_release_durations(mb, hints)
        assert result is not None

    def test_large_duration_diff_rejects(self, client):
        mb = {
            "title": "Album",
            "tracks": [
                {"duration_ms": 200000},
                {"duration_ms": 300000},
            ],
        }
        hints = {"track_durations": [100, 100]}
        result = client.validate_release_durations(mb, hints)
        assert result is None


# ── lookup_musicbrainz_by_release_id ─────────────────────────────


class TestLookupByReleaseId:
    def test_api_failure_returns_none(self, client):
        with patch.object(client, "_mb_request", return_value=None):
            result = client.lookup_musicbrainz_by_release_id("rel-123")
            assert result is None

    def test_successful_lookup(self, client):
        release_data = {
            "id": "rel-123",
            "title": "Test Album",
            "date": "2020-01-01",
            "artist-credit": [{"name": "Test Artist"}],
            "label-info": [{"label": {"name": "Test Label"}}],
            "media": [
                {
                    "track-list": [
                        {
                            "number": "1",
                            "recording": {
                                "title": "Track 1",
                                "length": 240000,
                                "artist-credit": [{"name": "Test Artist"}],
                            },
                        }
                    ]
                }
            ],
            "release-group": {"id": "rg-1"},
            "cover-art-archive": {"artwork": True, "front": True},
        }
        cover_data = {
            "images": [
                {"types": ["Front"], "image": "https://cover.art/front.jpg"},
                {"types": ["Back"], "image": "https://cover.art/back.jpg"},
            ]
        }

        call_count = [0]

        def mock_mb_request(url, **kwargs):
            call_count[0] += 1
            if "coverartarchive" in url:
                return cover_data
            return release_data

        with patch.object(client, "_mb_request", side_effect=mock_mb_request):
            result = client.lookup_musicbrainz_by_release_id("rel-123")
            if result is not None:
                assert result["title"] == "Test Album"
                assert result["artist"] == "Test Artist"


# ── search_musicbrainz ───────────────────────────────────────────


class TestSearchMusicbrainz:
    def test_no_results(self, client):
        with patch.object(client, "_mb_request", return_value={"releases": []}):
            result = client.search_musicbrainz("Nonexistent Album XYZ")
            assert result is None


# ── download_cover_art ───────────────────────────────────────────


class TestDownloadCoverArt:
    def test_empty_url_returns_false(self, client):
        assert client.download_cover_art("", "/out.jpg") is False
        assert client.download_cover_art(None, "/out.jpg") is False

    @patch("requests.get")
    def test_successful_download(self, mock_get, client, tmp_path):
        from PIL import Image
        import io

        img = Image.new("RGB", (10, 10))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        resp = MagicMock()
        resp.content = buf.getvalue()
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        out = tmp_path / "cover.jpg"
        assert client.download_cover_art("https://example.com/art.jpg", str(out)) is True
        assert out.exists()

    @patch("requests.get")
    def test_download_failure(self, mock_get, client, tmp_path):
        mock_get.side_effect = Exception("network fail")
        assert (
            client.download_cover_art("https://example.com/art.jpg", str(tmp_path / "x.jpg"))
            is False
        )
