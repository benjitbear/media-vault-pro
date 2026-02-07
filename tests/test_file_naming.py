"""
Tests for file renaming and media type detection utilities.
"""
import os
import json
import pytest
from pathlib import Path

from src.utils import (
    rename_with_metadata,
    reorganize_audio_album,
    detect_media_type,
    sanitize_filename,
)


class TestDetectMediaType:
    """Tests for detect_media_type()"""

    def test_video_extensions(self):
        assert detect_media_type('movie.mp4') == 'video'
        assert detect_media_type('movie.mkv') == 'video'
        assert detect_media_type('clip.avi') == 'video'
        assert detect_media_type('film.m4v') == 'video'
        assert detect_media_type('video.mov') == 'video'
        assert detect_media_type('video.webm') == 'video'

    def test_audio_extensions(self):
        assert detect_media_type('song.mp3') == 'audio'
        assert detect_media_type('track.flac') == 'audio'
        assert detect_media_type('music.aac') == 'audio'
        assert detect_media_type('audio.m4a') == 'audio'
        assert detect_media_type('sound.ogg') == 'audio'
        assert detect_media_type('sound.wav') == 'audio'

    def test_image_extensions(self):
        assert detect_media_type('photo.jpg') == 'image'
        assert detect_media_type('pic.png') == 'image'
        assert detect_media_type('art.gif') == 'image'
        assert detect_media_type('banner.webp') == 'image'

    def test_document_extensions(self):
        assert detect_media_type('book.pdf') == 'document'
        assert detect_media_type('novel.epub') == 'document'
        assert detect_media_type('page.html') == 'document'

    def test_other_extensions(self):
        assert detect_media_type('archive.zip') == 'other'
        assert detect_media_type('data.bin') == 'other'
        assert detect_media_type('noext') == 'other'

    def test_case_insensitive(self):
        assert detect_media_type('Movie.MP4') == 'video'
        assert detect_media_type('Song.FLAC') == 'audio'
        assert detect_media_type('Photo.JPG') == 'image'


class TestRenameWithMetadata:
    """Tests for rename_with_metadata()"""

    def test_rename_video_with_title_and_year(self, tmp_path):
        # Create a dummy file
        src = tmp_path / "SOME_DVD_RIP.mp4"
        src.write_text("fake video data")

        metadata = {
            'tmdb': {
                'title': 'The Matrix',
                'year': '1999',
            }
        }

        result = rename_with_metadata(str(src), metadata)
        assert result is not None
        assert Path(result).name == "The Matrix (1999).mp4"
        assert Path(result).exists()
        assert not src.exists()

    def test_rename_no_year(self, tmp_path):
        src = tmp_path / "raw_file.mp4"
        src.write_text("data")

        metadata = {'tmdb': {'title': 'Inception'}}
        result = rename_with_metadata(str(src), metadata)
        assert Path(result).name == "Inception.mp4"

    def test_rename_no_tmdb_key(self, tmp_path):
        src = tmp_path / "untitled.mp4"
        src.write_text("data")

        metadata = {'title': 'Fallback Title'}
        result = rename_with_metadata(str(src), metadata)
        # Should not rename if no tmdb data
        assert result is None or Path(result).name == "untitled.mp4"

    def test_rename_handles_collision(self, tmp_path):
        # Create existing file with target name
        existing = tmp_path / "The Matrix (1999).mp4"
        existing.write_text("first")

        src = tmp_path / "duplicate_rip.mp4"
        src.write_text("second")

        metadata = {'tmdb': {'title': 'The Matrix', 'year': '1999'}}
        result = rename_with_metadata(str(src), metadata)
        assert result is not None
        assert "The Matrix (1999) (2).mp4" in Path(result).name

    def test_rename_sanitizes_title(self, tmp_path):
        src = tmp_path / "raw.mp4"
        src.write_text("data")

        metadata = {'tmdb': {'title': 'Movie: The Sequel / Part 2', 'year': '2020'}}
        result = rename_with_metadata(str(src), metadata)
        assert result is not None
        name = Path(result).name
        assert '/' not in name
        assert ':' not in name

    def test_rename_nonexistent_file(self):
        """When file doesn't exist, returns the original path"""
        result = rename_with_metadata("/nonexistent/file.mp4", {'tmdb': {'title': 'X'}})
        assert result == "/nonexistent/file.mp4"


class TestReorganizeAudioAlbum:
    """Tests for reorganize_audio_album()"""

    def test_reorganize_creates_structure(self, tmp_path):
        # Create source album directory with tracks
        album_dir = tmp_path / "raw_album"
        album_dir.mkdir()
        for i in range(3):
            (album_dir / f"track{i+1}.mp3").write_text(f"audio {i}")

        base_output = tmp_path / "output"
        base_output.mkdir()

        metadata = {
            'musicbrainz': {
                'artist': 'Pink Floyd',
                'title': 'The Dark Side of the Moon',
                'year': '1973',
                'tracks': [
                    {'title': 'Speak to Me', 'position': 1, 'filename': 'track1.mp3'},
                    {'title': 'Breathe', 'position': 2, 'filename': 'track2.mp3'},
                    {'title': 'On the Run', 'position': 3, 'filename': 'track3.mp3'},
                ]
            }
        }

        result = reorganize_audio_album(str(album_dir), metadata, str(base_output))
        assert result is not None
        result_path = Path(result)
        assert result_path.exists()
        # Check artist/album directory structure
        assert 'Pink Floyd' in str(result_path)

    def test_reorganize_no_musicbrainz(self, tmp_path):
        album_dir = tmp_path / "raw_album"
        album_dir.mkdir()
        (album_dir / "track.mp3").write_text("audio")

        metadata = {'tmdb': {'title': 'Not Music'}}
        result = reorganize_audio_album(str(album_dir), metadata, str(tmp_path / "out"))
        # Returns original directory path when no musicbrainz data
        assert result == str(album_dir)


class TestSanitizeFilename:
    """Tests for the sanitize_filename utility"""

    def test_removes_slashes(self):
        assert '/' not in sanitize_filename("path/name")

    def test_removes_special_chars(self):
        result = sanitize_filename("file:name*test?.mp4")
        assert ':' not in result
        assert '*' not in result
        assert '?' not in result

    def test_strips_whitespace(self):
        result = sanitize_filename("  hello  world  ")
        assert not result.startswith(' ')
        assert not result.endswith(' ')

    def test_empty_string(self):
        result = sanitize_filename("")
        assert result == "" or result == "untitled"  # Implementation may vary
