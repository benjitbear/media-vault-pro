"""Tests for collection repository mixin (advanced operations)."""

import pytest

from src.app_state import AppState


@pytest.fixture
def app_state(tmp_path):
    AppState.reset()
    state = AppState(db_path=str(tmp_path / "test.db"))
    yield state
    AppState.reset()


def _add_media(state, media_id, title="Test", artist="", **kw):
    item = {
        "id": media_id,
        "title": title,
        "filename": f"{title}.mp4",
        "file_path": f"/tmp/{title}.mp4",
        "file_size": 1024,
        "size_formatted": "1 KB",
        "created_at": "2024-01-01",
        "modified_at": "2024-01-01",
        "media_type": "video",
        "artist": artist,
    }
    item.update(kw)
    state.upsert_media(item)
    return item


class TestGetAllCollections:
    def test_empty(self, app_state):
        assert app_state.get_all_collections() == []

    def test_with_items(self, app_state):
        _add_media(app_state, "m1", "Movie A")
        _add_media(app_state, "m2", "Movie B")
        app_state.update_collection("Favourites", ["m1", "m2"])
        cols = app_state.get_all_collections()
        assert len(cols) == 1
        assert cols[0]["name"] == "Favourites"
        assert len(cols[0]["items"]) == 2
        assert cols[0]["items"][0]["id"] == "m1"

    def test_playlist_track_count(self, app_state):
        col_id = app_state.create_collection("Mix", collection_type="playlist")
        app_state.add_playlist_tracks(
            col_id,
            [
                {"title": "Song A", "artist": "Band"},
                {"title": "Song B", "artist": "Band"},
            ],
        )
        cols = app_state.get_all_collections()
        assert cols[0]["has_playlist_tracks"] is True
        assert cols[0]["playlist_track_count"] == 2


class TestGetCollectionByName:
    def test_found(self, app_state):
        app_state.create_collection("Action")
        col = app_state.get_collection_by_name("Action")
        assert col is not None
        assert col["name"] == "Action"

    def test_not_found(self, app_state):
        assert app_state.get_collection_by_name("Nope") is None


class TestUpdateCollectionMetadata:
    def test_update_description(self, app_state):
        col_id = app_state.create_collection("A")
        app_state.update_collection_metadata(col_id, description="New desc")
        col = app_state.get_collection_by_name("A")
        assert col["description"] == "New desc"

    def test_update_type(self, app_state):
        col_id = app_state.create_collection("B")
        app_state.update_collection_metadata(col_id, collection_type="playlist")
        col = app_state.get_collection_by_name("B")
        assert col["collection_type"] == "playlist"

    def test_no_updates(self, app_state):
        col_id = app_state.create_collection("C", description="orig")
        app_state.update_collection_metadata(col_id)  # no-op
        col = app_state.get_collection_by_name("C")
        assert col["description"] == "orig"


class TestGetCollectionItems:
    def test_ordered(self, app_state):
        _add_media(app_state, "x1", "First")
        _add_media(app_state, "x2", "Second")
        col_id = app_state.create_collection("Queue")
        app_state.update_collection("Queue", ["x2", "x1"])
        items = app_state.get_collection_items(col_id)
        assert [i["id"] for i in items] == ["x2", "x1"]

    def test_empty_collection(self, app_state):
        col_id = app_state.create_collection("Empty")
        assert app_state.get_collection_items(col_id) == []


class TestPlaylistTracks:
    def test_add_and_get(self, app_state):
        col_id = app_state.create_collection("Import")
        tracks = [
            {
                "title": "Track 1",
                "artist": "Artist A",
                "album": "Album",
                "duration_ms": 210000,
                "spotify_uri": "spotify:track:abc",
            },
            {"title": "Track 2", "artist": "Artist B"},
        ]
        app_state.add_playlist_tracks(col_id, tracks)
        result = app_state.get_playlist_tracks(col_id)
        assert len(result) == 2
        assert result[0]["title"] == "Track 1"
        assert result[0]["artist"] == "Artist A"
        assert result[0]["available"] is False  # no matched media
        assert result[1]["sort_order"] == 1

    def test_add_replaces_existing(self, app_state):
        col_id = app_state.create_collection("Re")
        app_state.add_playlist_tracks(col_id, [{"title": "Old"}])
        app_state.add_playlist_tracks(col_id, [{"title": "New"}])
        result = app_state.get_playlist_tracks(col_id)
        assert len(result) == 1
        assert result[0]["title"] == "New"


class TestMatchPlaylistTracks:
    def test_match_by_title_and_artist(self, app_state):
        _add_media(app_state, "local1", "Amazing Grace", artist="Chris Tomlin")
        col_id = app_state.create_collection("Match")
        app_state.add_playlist_tracks(
            col_id,
            [
                {"title": "Amazing Grace", "artist": "Chris Tomlin"},
            ],
        )
        app_state.match_playlist_tracks(col_id)
        tracks = app_state.get_playlist_tracks(col_id)
        assert tracks[0]["matched_media_id"] == "local1"
        assert tracks[0]["available"] is True  # file_path is non-empty

    def test_no_match(self, app_state):
        col_id = app_state.create_collection("NoMatch")
        app_state.add_playlist_tracks(
            col_id,
            [
                {"title": "Nonexistent Song", "artist": "Nobody"},
            ],
        )
        app_state.match_playlist_tracks(col_id)
        tracks = app_state.get_playlist_tracks(col_id)
        assert tracks[0]["matched_media_id"] is None

    def test_match_partial_title(self, app_state):
        _add_media(app_state, "loc2", "How Great Is Our God", artist="Chris Tomlin")
        col_id = app_state.create_collection("Partial")
        app_state.add_playlist_tracks(
            col_id,
            [
                {"title": "How Great Is Our God", "artist": "Chris Tomlin"},
            ],
        )
        app_state.match_playlist_tracks(col_id)
        tracks = app_state.get_playlist_tracks(col_id)
        assert tracks[0]["matched_media_id"] == "loc2"
