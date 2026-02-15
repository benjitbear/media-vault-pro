"""Tests for MediaInfoClient — mediainfo extraction and chapter parsing."""

import json
import pytest
from unittest.mock import patch, MagicMock
from src.clients.mediainfo_client import MediaInfoClient


@pytest.fixture
def client():
    return MediaInfoClient()


# ── extract_mediainfo ────────────────────────────────────────────


class TestExtractMediainfo:
    @patch("os.path.getsize", return_value=1_000_000)
    @patch("subprocess.run")
    def test_full_extraction(self, mock_run, mock_size, client):
        mock_run.return_value = MagicMock(
            stdout=json.dumps(
                {
                    "media": {
                        "track": [
                            {
                                "@type": "General",
                                "Duration": "120.5",
                                "Format": "MP4",
                                "FileSize": "1000000",
                            },
                            {
                                "@type": "Video",
                                "Format": "AVC",
                                "Width": "1920",
                                "Height": "1080",
                                "FrameRate": "23.976",
                                "BitDepth": "8",
                            },
                            {
                                "@type": "Audio",
                                "Language": "English",
                                "Format": "AAC",
                                "Channels": "6",
                                "SamplingRate": "48000",
                            },
                            {
                                "@type": "Audio",
                                "Language": "Spanish",
                                "Format": "AC3",
                                "Channels": "2",
                                "SamplingRate": "48000",
                            },
                            {"@type": "Text", "Language": "English", "Format": "SRT"},
                        ]
                    }
                }
            )
        )
        result = client.extract_mediainfo("/fake/movie.mp4")

        assert result is not None
        assert result["duration_seconds"] == 120.5
        assert result["format"] == "MP4"
        assert result["video"]["codec"] == "AVC"
        assert result["video"]["width"] == "1920"
        assert result["video"]["height"] == "1080"
        assert len(result["tracks"]) == 3  # 2 audio + 1 subtitle
        assert result["tracks"][0]["type"] == "audio"
        assert result["tracks"][0]["language"] == "English"
        assert result["tracks"][2]["type"] == "subtitle"

    @patch("os.path.getsize", return_value=500)
    @patch("subprocess.run")
    def test_no_tracks(self, mock_run, mock_size, client):
        mock_run.return_value = MagicMock(stdout=json.dumps({"media": {"track": []}}))
        result = client.extract_mediainfo("/fake/file.mp4")
        assert result is not None
        assert result["tracks"] == []
        assert "video" not in result

    @patch("os.path.getsize", return_value=500)
    @patch("subprocess.run")
    def test_missing_media_key(self, mock_run, mock_size, client):
        mock_run.return_value = MagicMock(stdout=json.dumps({}))
        result = client.extract_mediainfo("/fake/file.mp4")
        assert result is not None
        assert result["tracks"] == []

    @patch("subprocess.run")
    def test_called_process_error(self, mock_run, client):
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "mediainfo")
        result = client.extract_mediainfo("/fake/file.mp4")
        assert result is None

    @patch("subprocess.run")
    def test_generic_exception(self, mock_run, client):
        mock_run.side_effect = RuntimeError("unexpected")
        result = client.extract_mediainfo("/fake/file.mp4")
        assert result is None

    @patch("os.path.getsize", return_value=100)
    @patch("subprocess.run")
    def test_general_track_only(self, mock_run, mock_size, client):
        mock_run.return_value = MagicMock(
            stdout=json.dumps(
                {
                    "media": {
                        "track": [
                            {
                                "@type": "General",
                                "Duration": "60.0",
                                "Format": "FLAC",
                                "FileSize": "100",
                            },
                        ]
                    }
                }
            )
        )
        result = client.extract_mediainfo("/fake/song.flac")
        assert result["duration_seconds"] == 60.0
        assert result["format"] == "FLAC"
        assert result["tracks"] == []


# ── extract_chapters ─────────────────────────────────────────────


class TestExtractChapters:
    @patch("subprocess.run")
    def test_chapters_parsed(self, mock_run, client):
        mock_run.return_value = MagicMock(
            stdout=json.dumps(
                {
                    "chapters": [
                        {"tags": {"title": "Intro"}, "start_time": "0.0", "end_time": "120.0"},
                        {"tags": {"title": "Act 1"}, "start_time": "120.0", "end_time": "600.0"},
                        {"start_time": "600.0", "end_time": "900.0"},  # no title tag
                    ]
                }
            )
        )
        chapters = client.extract_chapters("/fake/movie.mkv")
        assert len(chapters) == 3
        assert chapters[0]["title"] == "Intro"
        assert chapters[0]["start_time"] == 0.0
        assert chapters[1]["end_time"] == 600.0
        assert chapters[2]["title"] == "Chapter 3"  # auto-generated

    @patch("subprocess.run")
    def test_no_chapters(self, mock_run, client):
        mock_run.return_value = MagicMock(stdout=json.dumps({"chapters": []}))
        assert client.extract_chapters("/fake/movie.mkv") == []

    @patch("subprocess.run")
    def test_missing_chapters_key(self, mock_run, client):
        mock_run.return_value = MagicMock(stdout=json.dumps({}))
        assert client.extract_chapters("/fake/movie.mkv") == []

    @patch("subprocess.run")
    def test_called_process_error(self, mock_run, client):
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "ffprobe")
        assert client.extract_chapters("/fake/movie.mkv") == []

    @patch("subprocess.run")
    def test_generic_exception(self, mock_run, client):
        mock_run.side_effect = ValueError("bad json")
        assert client.extract_chapters("/fake/movie.mkv") == []
