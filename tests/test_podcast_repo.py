"""Tests for podcast repository mixin — CRUD for podcasts and episodes."""
import pytest
from src.app_state import AppState


@pytest.fixture
def app_state(tmp_path):
    AppState.reset()
    state = AppState(db_path=str(tmp_path / 'test.db'))
    yield state
    AppState.reset()


# ── add_podcast / get_podcast ────────────────────────────────────


class TestAddPodcast:
    def test_add_and_retrieve(self, app_state):
        pod_id = app_state.add_podcast(
            feed_url='https://example.com/feed.xml',
            title='My Podcast',
            author='Host',
            description='A podcast about things',
            artwork_url='https://example.com/art.jpg'
        )
        assert pod_id is not None

        pod = app_state.get_podcast(pod_id)
        assert pod is not None
        assert pod['title'] == 'My Podcast'
        assert pod['author'] == 'Host'
        assert pod['feed_url'] == 'https://example.com/feed.xml'

    def test_duplicate_feed_url(self, app_state):
        app_state.add_podcast(feed_url='https://example.com/feed.xml', title='First')
        dup_id = app_state.add_podcast(feed_url='https://example.com/feed.xml', title='Second')
        assert dup_id is None

    def test_defaults(self, app_state):
        pod_id = app_state.add_podcast(feed_url='https://example.com/feed2.xml')
        pod = app_state.get_podcast(pod_id)
        assert pod['title'] == ''
        assert pod['author'] == ''

    def test_get_nonexistent(self, app_state):
        assert app_state.get_podcast('nonexistent-id') is None


# ── get_all_podcasts ─────────────────────────────────────────────


class TestGetAllPodcasts:
    def test_empty(self, app_state):
        assert app_state.get_all_podcasts() == []

    def test_ordered_by_title(self, app_state):
        app_state.add_podcast(feed_url='https://b.com/feed', title='Beta Pod')
        app_state.add_podcast(feed_url='https://a.com/feed', title='Alpha Pod')
        pods = app_state.get_all_podcasts()
        assert len(pods) == 2
        assert pods[0]['title'] == 'Alpha Pod'
        assert pods[1]['title'] == 'Beta Pod'


# ── update_podcast ───────────────────────────────────────────────


class TestUpdatePodcast:
    def test_update_allowed_fields(self, app_state):
        pod_id = app_state.add_podcast(
            feed_url='https://example.com/feed.xml', title='Original'
        )
        app_state.update_podcast(pod_id, title='Updated', author='New Author')
        pod = app_state.get_podcast(pod_id)
        assert pod['title'] == 'Updated'
        assert pod['author'] == 'New Author'

    def test_update_artwork_path(self, app_state):
        pod_id = app_state.add_podcast(
            feed_url='https://example.com/feed.xml', title='Pod'
        )
        app_state.update_podcast(pod_id, artwork_path='/art/cover.jpg')
        pod = app_state.get_podcast(pod_id)
        assert pod['artwork_path'] == '/art/cover.jpg'


# ── delete_podcast ───────────────────────────────────────────────


class TestDeletePodcast:
    def test_delete_existing(self, app_state):
        pod_id = app_state.add_podcast(
            feed_url='https://example.com/feed.xml', title='To Delete'
        )
        assert app_state.delete_podcast(pod_id) is True
        assert app_state.get_podcast(pod_id) is None

    def test_delete_nonexistent(self, app_state):
        assert app_state.delete_podcast('fake-id') is False


# ── get_due_podcasts ─────────────────────────────────────────────


class TestGetDuePodcasts:
    def test_never_checked_is_due(self, app_state):
        app_state.add_podcast(
            feed_url='https://example.com/feed.xml', title='New Pod'
        )
        due = app_state.get_due_podcasts()
        assert len(due) >= 1

    def test_recently_checked_not_due(self, app_state):
        import datetime
        pod_id = app_state.add_podcast(
            feed_url='https://example.com/feed.xml', title='Checked Pod'
        )
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        app_state.update_podcast(pod_id, last_checked=now)
        due = app_state.get_due_podcasts()
        due_ids = [p['id'] for p in due]
        assert pod_id not in due_ids


# ── add_episode / get_episodes ───────────────────────────────────


class TestEpisodes:
    def test_add_and_get(self, app_state):
        pod_id = app_state.add_podcast(
            feed_url='https://example.com/feed.xml', title='Pod'
        )
        ep_id = app_state.add_episode(
            podcast_id=pod_id,
            title='Episode 1',
            audio_url='https://example.com/ep1.mp3',
            duration_seconds=3600,
            published_at='2024-01-15',
            description='First episode'
        )
        assert ep_id is not None

        episodes = app_state.get_episodes(pod_id)
        assert len(episodes) == 1
        assert episodes[0]['title'] == 'Episode 1'
        assert episodes[0]['duration_seconds'] == 3600

    def test_episodes_ordered_newest_first(self, app_state):
        pod_id = app_state.add_podcast(
            feed_url='https://example.com/feed.xml', title='Pod'
        )
        app_state.add_episode(podcast_id=pod_id, title='Ep 1',
                               audio_url='https://example.com/ep1.mp3',
                               published_at='2024-01-01')
        app_state.add_episode(podcast_id=pod_id, title='Ep 2',
                               audio_url='https://example.com/ep2.mp3',
                               published_at='2024-06-01')
        episodes = app_state.get_episodes(pod_id)
        assert episodes[0]['title'] == 'Ep 2'

    def test_empty_episodes(self, app_state):
        pod_id = app_state.add_podcast(
            feed_url='https://example.com/feed.xml', title='Pod'
        )
        assert app_state.get_episodes(pod_id) == []


# ── update_episode ───────────────────────────────────────────────


class TestUpdateEpisode:
    def test_update_file_path(self, app_state):
        pod_id = app_state.add_podcast(
            feed_url='https://example.com/feed.xml', title='Pod'
        )
        ep_id = app_state.add_episode(podcast_id=pod_id, title='Ep 1',
                                       audio_url='https://example.com/ep1.mp3')
        app_state.update_episode(ep_id, file_path='/podcasts/ep1.mp3',
                                  is_downloaded=True)
        episodes = app_state.get_episodes(pod_id)
        assert episodes[0]['file_path'] == '/podcasts/ep1.mp3'
        assert episodes[0]['is_downloaded'] == 1


# ── episode_exists ───────────────────────────────────────────────


class TestEpisodeExists:
    def test_exists(self, app_state):
        pod_id = app_state.add_podcast(
            feed_url='https://example.com/feed.xml', title='Pod'
        )
        app_state.add_episode(podcast_id=pod_id, title='Ep 1',
                               audio_url='https://example.com/ep1.mp3')
        assert app_state.episode_exists(pod_id, 'https://example.com/ep1.mp3') is True

    def test_not_exists(self, app_state):
        pod_id = app_state.add_podcast(
            feed_url='https://example.com/feed.xml', title='Pod'
        )
        assert app_state.episode_exists(pod_id, 'https://example.com/nope.mp3') is False
