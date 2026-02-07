"""
Tests for the content_downloader module.
"""
import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.app_state import AppState
from src.content_downloader import ContentDownloader


@pytest.fixture
def dl_config(tmp_path):
    """Create a config file for content downloader tests"""
    cfg = {
        "output": {"base_directory": str(tmp_path / "media")},
        "metadata": {"save_to_json": False, "fetch_online_metadata": False,
                      "extract_chapters": False, "extract_subtitles": False,
                      "extract_audio_tracks": False},
        "automation": {"notification_enabled": False},
        "downloads": {
            "download_directory": str(tmp_path / "downloads"),
            "articles_directory": str(tmp_path / "articles"),
            "books_directory": str(tmp_path / "books"),
            "ytdlp_format": "best",
        },
        "podcasts": {
            "enabled": True,
            "download_directory": str(tmp_path / "podcasts"),
            "check_interval_hours": 6,
            "auto_download": False,
            "max_episodes_per_feed": 10,
        },
        "logging": {"debug": False, "progress_indicator": False},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(cfg))
    return config_path


@pytest.fixture
def downloader(tmp_path, dl_config):
    """Create a ContentDownloader with temp DB"""
    AppState.reset()
    state = AppState(db_path=str(tmp_path / 'test.db'))
    dl = ContentDownloader(config_path=str(dl_config), app_state=state)
    yield dl
    AppState.reset()


class TestParseDuration:
    """Tests for _parse_duration static method"""

    def test_hhmmss(self):
        assert ContentDownloader._parse_duration("1:30:00") == 5400.0

    def test_mmss(self):
        assert ContentDownloader._parse_duration("45:30") == 2730.0

    def test_seconds_only(self):
        assert ContentDownloader._parse_duration("3600") == 3600.0

    def test_invalid(self):
        assert ContentDownloader._parse_duration("not-a-duration") is None

    def test_empty(self):
        assert ContentDownloader._parse_duration("") is None


class TestContentDownloader:
    """Tests for ContentDownloader main methods"""

    def test_directories_created(self, downloader, dl_config):
        cfg = json.loads(dl_config.read_text())
        for key in ('download_directory', 'articles_directory', 'books_directory'):
            assert Path(cfg['downloads'][key]).exists()
        assert Path(cfg['podcasts']['download_directory']).exists()

    def test_download_video_no_ytdlp(self, downloader):
        """download_video returns None when yt-dlp is not available"""
        with patch('subprocess.run', side_effect=FileNotFoundError):
            result = downloader.download_video("https://example.com/video")
            assert result is None

    def test_archive_article_no_trafilatura(self, downloader):
        """archive_article returns None when trafilatura is not installed"""
        # Mock import to fail
        import builtins
        original_import = builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == 'trafilatura':
                raise ImportError("No module named 'trafilatura'")
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            result = downloader.archive_article("https://example.com/article")
            assert result is None

    def test_parse_podcast_feed_no_feedparser(self, downloader):
        """parse_podcast_feed returns None when feedparser not installed"""
        import builtins
        original_import = builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == 'feedparser':
                raise ImportError("No module named 'feedparser'")
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            result = downloader.parse_podcast_feed("https://example.com/feed.xml")
            assert result is None

    def test_process_content_job_unknown_type(self, downloader):
        job = {'id': 'test', 'source_path': 'url', 'job_type': 'unknown'}
        result = downloader.process_content_job(job)
        assert result is None


class TestPodcastDB:
    """Tests for podcast database operations via ContentDownloader"""

    def test_subscribe_stores_podcast(self, downloader):
        """Test that subscribe_podcast stores podcast in DB when feed parsing succeeds"""
        mock_feed_info = {
            'title': 'Test Pod',
            'author': 'Tester',
            'description': 'A test podcast',
            'artwork_url': None,
            'episodes': [
                {
                    'title': 'Episode 1',
                    'audio_url': 'https://example.com/ep1.mp3',
                    'duration_seconds': 1800,
                    'published_at': '2024-01-01T00:00:00',
                    'description': 'First episode',
                }
            ]
        }

        with patch.object(downloader, 'parse_podcast_feed', return_value=mock_feed_info):
            pod_id = downloader.subscribe_podcast('https://example.com/feed.xml')
            assert pod_id is not None

            # Verify in database
            pods = downloader.app_state.get_all_podcasts()
            assert len(pods) == 1
            assert pods[0]['title'] == 'Test Pod'

            # Verify episodes stored
            episodes = downloader.app_state.get_episodes(pod_id)
            assert len(episodes) == 1
            assert episodes[0]['title'] == 'Episode 1'

    def test_check_feeds_detects_new_episodes(self, downloader):
        """check_podcast_feeds should detect new episodes"""
        # First subscribe
        mock_feed_1 = {
            'title': 'Feed', 'author': '', 'description': '',
            'artwork_url': None,
            'episodes': [{
                'title': 'Ep 1', 'audio_url': 'https://x.com/1.mp3',
                'duration_seconds': 100, 'published_at': None, 'description': '',
            }]
        }
        with patch.object(downloader, 'parse_podcast_feed', return_value=mock_feed_1):
            pod_id = downloader.subscribe_podcast('https://feed.example.com/rss')

        assert pod_id is not None

        # Now check feeds with a new episode
        mock_feed_2 = {
            'title': 'Feed', 'author': '', 'description': '',
            'artwork_url': None,
            'episodes': [
                {'title': 'Ep 1', 'audio_url': 'https://x.com/1.mp3',
                 'duration_seconds': 100, 'published_at': None, 'description': ''},
                {'title': 'Ep 2', 'audio_url': 'https://x.com/2.mp3',
                 'duration_seconds': 200, 'published_at': None, 'description': ''},
            ]
        }
        with patch.object(downloader, 'parse_podcast_feed', return_value=mock_feed_2):
            downloader.check_podcast_feeds()

        episodes = downloader.app_state.get_episodes(pod_id)
        assert len(episodes) == 2
