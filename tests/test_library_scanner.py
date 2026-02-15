"""Tests for the LibraryScannerService."""

import json

import pytest

from src.app_state import AppState
from src.services.library_scanner import LibraryScannerService


@pytest.fixture
def app_state(tmp_path):
    AppState.reset()
    state = AppState(db_path=str(tmp_path / "test.db"))
    yield state
    AppState.reset()


@pytest.fixture
def library_dirs(tmp_path):
    """Create library, metadata, and thumbnails directories."""
    lib = tmp_path / "library"
    meta = tmp_path / "metadata"
    thumb = tmp_path / "thumbnails"
    lib.mkdir()
    meta.mkdir()
    thumb.mkdir()
    return lib, meta, thumb


@pytest.fixture
def scanner(library_dirs, app_state):
    lib, meta, thumb = library_dirs
    return LibraryScannerService(
        library_path=lib,
        metadata_path=meta,
        thumbnails_path=thumb,
        app_state=app_state,
    )


class TestLibraryScanner:
    def test_empty_library_returns_empty(self, scanner):
        """Scanning an empty directory should return no items."""
        result = scanner.scan()
        assert result == []

    def test_finds_video_file(self, scanner, library_dirs):
        """A .mp4 file should be discovered and returned."""
        lib, _, _ = library_dirs
        (lib / "movie.mp4").write_bytes(b"\x00" * 100)

        result = scanner.scan()
        assert len(result) == 1
        assert result[0]["filename"] == "movie.mp4"
        assert result[0]["media_type"] == "video"

    def test_finds_audio_file(self, scanner, library_dirs):
        """A .mp3 file should be discovered."""
        lib, _, _ = library_dirs
        (lib / "song.mp3").write_bytes(b"\x00" * 50)

        result = scanner.scan()
        assert len(result) == 1
        assert result[0]["media_type"] == "audio"

    def test_skips_non_media_files(self, scanner, library_dirs):
        """Files with unsupported extensions should be excluded."""
        lib, _, _ = library_dirs
        (lib / "notes.log").write_text("hello")
        (lib / "data.csv").write_text("a,b,c")
        (lib / "build.py").write_text("print('hi')")

        result = scanner.scan()
        assert result == []

    def test_skips_data_subdirectories(self, scanner, library_dirs):
        """Files in data/ and thumbnails/ should be skipped."""
        lib, _, _ = library_dirs
        data_dir = lib / "data" / "metadata"
        data_dir.mkdir(parents=True)
        (data_dir / "something.mp4").write_bytes(b"\x00" * 100)

        result = scanner.scan()
        assert result == []

    def test_enriches_with_tmdb_metadata(self, scanner, library_dirs):
        """Items should be enriched from sidecar JSON with TMDB data."""
        lib, meta, _ = library_dirs
        (lib / "movie.mp4").write_bytes(b"\x00" * 100)
        meta_json = {
            "tmdb": {
                "title": "The Matrix",
                "year": 1999,
                "overview": "A hacker discovers reality is simulated.",
                "rating": 8.7,
                "genres": ["Action", "Sci-Fi"],
                "director": "Wachowskis",
                "cast": ["Keanu Reeves"],
                "tmdb_id": 603,
            }
        }
        (meta / "movie.json").write_text(json.dumps(meta_json))

        result = scanner.scan()
        assert len(result) == 1
        assert result[0]["title"] == "The Matrix"
        assert result[0]["year"] == 1999
        assert result[0]["has_metadata"] is True

    def test_enriches_with_musicbrainz_metadata(self, scanner, library_dirs):
        """Audio items should pick up MusicBrainz metadata."""
        lib, meta, _ = library_dirs
        (lib / "track.flac").write_bytes(b"\x00" * 50)
        meta_json = {
            "musicbrainz": {
                "title": "Album Name",
                "artist": "Band",
                "year": 2020,
                "genres": ["Rock"],
            },
            "track_info": {"title": "Song Title"},
        }
        (meta / "track.json").write_text(json.dumps(meta_json))

        result = scanner.scan()
        assert len(result) == 1
        assert result[0]["title"] == "Song Title"
        assert result[0]["artist"] == "Band"
        assert result[0]["media_type"] == "audio"

    def test_attaches_poster_path(self, scanner, library_dirs):
        """Items with matching poster files should have poster_path set."""
        lib, _, thumb = library_dirs
        (lib / "movie.mp4").write_bytes(b"\x00" * 100)
        (thumb / "movie_poster.jpg").write_bytes(b"\xff\xd8")

        result = scanner.scan()
        assert result[0].get("poster_path") is not None

    def test_removes_stale_entries(self, scanner, library_dirs, app_state):
        """Files deleted from disk should be removed from the DB."""
        lib, _, _ = library_dirs
        video = lib / "movie.mp4"
        video.write_bytes(b"\x00" * 100)

        # First scan — adds the file
        scanner.scan()
        assert len(app_state.get_media_ids()) == 1

        # Remove the file, scan again
        video.unlink()
        scanner.scan()
        assert len(app_state.get_media_ids()) == 0

    def test_nonexistent_library_returns_empty(self, app_state, tmp_path):
        """Scanning a nonexistent path should return an empty list."""
        s = LibraryScannerService(
            library_path=tmp_path / "nonexistent",
            metadata_path=tmp_path / "meta",
            thumbnails_path=tmp_path / "thumb",
            app_state=app_state,
        )
        result = s.scan()
        assert result == []

    def test_results_sorted_by_title(self, scanner, library_dirs):
        """Results should be sorted alphabetically by title."""
        lib, _, _ = library_dirs
        (lib / "zebra.mp4").write_bytes(b"\x00" * 50)
        (lib / "apple.mp4").write_bytes(b"\x00" * 50)
        (lib / "mango.mp4").write_bytes(b"\x00" * 50)

        result = scanner.scan()
        titles = [r["title"] for r in result]
        assert titles == ["apple", "mango", "zebra"]
