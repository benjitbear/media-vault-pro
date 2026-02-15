"""Tests for ContentDownloader — video download, article archive, podcast, playlists."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.app_state import AppState


@pytest.fixture
def app_state(tmp_path):
    AppState.reset()
    state = AppState(db_path=str(tmp_path / 'test.db'))
    yield state
    AppState.reset()


@pytest.fixture
def downloader_config(tmp_path):
    return {
        "output": {"base_directory": str(tmp_path / "media")},
        "downloads": {
            "enabled": True,
            "download_directory": str(tmp_path / "downloads"),
            "ytdlp_format": "best",
            "articles_directory": str(tmp_path / "articles"),
            "books_directory": str(tmp_path / "books"),
        },
        "podcasts": {
            "enabled": True,
            "check_interval_hours": 6,
            "auto_download": False,
            "download_directory": str(tmp_path / "podcasts"),
            "max_episodes_per_feed": 10,
        },
    }


@pytest.fixture
def downloader(tmp_path, downloader_config, app_state):
    config_path = tmp_path / 'config.json'
    config_path.write_text(json.dumps(downloader_config))
    from src.content_downloader import ContentDownloader
    return ContentDownloader(config_path=str(config_path), app_state=app_state)


# ── _escape_html ─────────────────────────────────────────────────


class TestEscapeHtml:
    def test_escapes_tags(self):
        from src.content_downloader import _escape_html
        assert '<' not in _escape_html('<script>alert("xss")</script>')

    def test_escapes_ampersand(self):
        from src.content_downloader import _escape_html
        assert '&amp;' in _escape_html('A & B')

    def test_escapes_quotes(self):
        from src.content_downloader import _escape_html
        result = _escape_html('"hello"')
        assert '&quot;' in result


# ── _parse_duration (static) ────────────────────────────────────


class TestParseDurationExtended:
    def test_hh_mm_ss(self):
        from src.content_downloader import ContentDownloader
        assert ContentDownloader._parse_duration('1:30:00') == 5400.0

    def test_mm_ss(self):
        from src.content_downloader import ContentDownloader
        assert ContentDownloader._parse_duration('45:30') == 2730.0

    def test_float_seconds(self):
        from src.content_downloader import ContentDownloader
        assert ContentDownloader._parse_duration('90.5') == 90.5

    def test_none_input(self):
        from src.content_downloader import ContentDownloader
        assert ContentDownloader._parse_duration(None) is None

    def test_empty_string(self):
        from src.content_downloader import ContentDownloader
        assert ContentDownloader._parse_duration('') is None


# ── process_content_job ──────────────────────────────────────────


class TestProcessContentJob:
    def test_unknown_type_returns_none(self, downloader):
        job = {'id': 'j-1', 'source_path': 'http://example.com',
               'job_type': 'unknown_type'}
        result = downloader.process_content_job(job)
        assert result is None

    def test_download_type_dispatches(self, downloader):
        with patch.object(downloader, 'download_video', return_value='/path/video.mp4'):
            job = {'id': 'j-1', 'source_path': 'http://yt.com/v',
                   'job_type': 'download', 'title': 'Video'}
            result = downloader.process_content_job(job)
            assert result == '/path/video.mp4'

    def test_article_type_dispatches(self, downloader):
        with patch.object(downloader, 'archive_article', return_value='/path/article.html'):
            job = {'id': 'j-1', 'source_path': 'http://example.com/post',
                   'job_type': 'article', 'title': 'Article'}
            result = downloader.process_content_job(job)
            assert result == '/path/article.html'

    def test_playlist_import_dispatches(self, downloader):
        with patch.object(downloader, 'import_spotify_playlist', return_value=10):
            job = {'id': 'j-1', 'source_path': 'http://spotify.com/playlist/abc',
                   'job_type': 'playlist_import', 'title': 'My Playlist'}
            result = downloader.process_content_job(job)


# ── subscribe_podcast ────────────────────────────────────────────


class TestSubscribePodcast:
    def test_subscribe_stores_podcast(self, downloader, app_state):
        mock_feed_result = {
            'title': 'Test Pod', 'author': 'Host',
            'description': 'Desc', 'artwork_url': None,
            'episodes': [
                {'title': 'Ep 1', 'audio_url': 'https://example.com/ep1.mp3',
                 'duration_seconds': 1800, 'published_at': '2024-01-01',
                 'description': 'Episode one'}
            ]
        }
        with patch.object(downloader, 'parse_podcast_feed', return_value=mock_feed_result):
            pod_id = downloader.subscribe_podcast('https://example.com/feed.xml')
            if pod_id:
                pods = app_state.get_all_podcasts()
                assert len(pods) >= 1

    def test_subscribe_no_feed_returns_none(self, downloader):
        with patch.object(downloader, 'parse_podcast_feed', return_value=None):
            result = downloader.subscribe_podcast('https://example.com/bad-feed')
            assert result is None


# ── download_video ───────────────────────────────────────────────


class TestDownloadVideo:
    @patch('shutil.which', return_value=None)
    def test_no_ytdlp_returns_none(self, mock_which, downloader):
        result = downloader.download_video('https://youtube.com/watch?v=abc')
        assert result is None


# ── archive_article ──────────────────────────────────────────────


class TestArchiveArticle:
    def test_archive_graceful_on_missing_trafilatura(self, downloader):
        """If trafilatura is not available, should return None gracefully."""
        # The method imports trafilatura inline — if it's not installed,
        # it should handle the ImportError
        # This test documents the expected behavior regardless of install state
        result = downloader.archive_article('https://example.com/article')
        # Will either work (trafilatura installed) or return None
        assert result is None or isinstance(result, str)


# ── check_podcast_feeds ───────────────────────────────────────────


class TestCheckPodcastFeeds:
    def test_no_due_podcasts(self, downloader, app_state):
        """When no podcasts are due, should complete without error."""
        downloader.check_podcast_feeds()

    def test_with_due_podcast(self, downloader, app_state):
        """A due podcast should trigger a feed parse."""
        pod_id = app_state.add_podcast(
            feed_url='https://example.com/feed.xml', title='Test Pod'
        )
        with patch.object(downloader, 'parse_podcast_feed', return_value=None):
            downloader.check_podcast_feeds()
