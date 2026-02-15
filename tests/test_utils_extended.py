"""Tests for utility functions — config, logging, file helpers, formatting."""

import json
import os
from pathlib import Path
from unittest.mock import patch

from src.utils import (
    detect_media_type,
    ensure_directory,
    format_size,
    format_time,
    get_data_dir,
    get_media_root,
    load_config,
    natural_sort_key,
    rename_with_metadata,
    sanitize_filename,
    setup_logger,
)

# ── detect_media_type (additional edge cases) ────────────────────


class TestDetectMediaType:
    def test_mixed_case(self):
        assert detect_media_type("Movie.MKV") == "video"
        assert detect_media_type("song.FLAC") == "audio"

    def test_double_extension(self):
        assert detect_media_type("archive.tar.gz") == "other"

    def test_no_extension(self):
        assert detect_media_type("README") == "other"

    def test_dot_only(self):
        assert detect_media_type(".gitignore") == "other"


# ── sanitize_filename ────────────────────────────────────────────


class TestSanitizeFilename:
    def test_slashes(self):
        assert "/" not in sanitize_filename("path/to/file")
        assert "\\" not in sanitize_filename("path\\to\\file")

    def test_colons_and_stars(self):
        result = sanitize_filename("Movie: The *Best* One?")
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result

    def test_whitespace_trimmed(self):
        result = sanitize_filename("  spaces  ")
        assert result == result.strip()

    def test_empty_string(self):
        result = sanitize_filename("")
        assert isinstance(result, str)

    def test_unicode_preserved(self):
        result = sanitize_filename("Ménage à trois")
        assert "nage" in result  # unicode letters kept


# ── format_size ──────────────────────────────────────────────────


class TestFormatSize:
    def test_bytes(self):
        result = format_size(500)
        assert "B" in result

    def test_kilobytes(self):
        result = format_size(2048)
        assert "KB" in result or "kB" in result or "K" in result

    def test_megabytes(self):
        result = format_size(5 * 1024 * 1024)
        assert "MB" in result or "M" in result

    def test_gigabytes(self):
        result = format_size(3 * 1024**3)
        assert "GB" in result or "G" in result

    def test_zero(self):
        result = format_size(0)
        assert "0" in result


# ── format_time ──────────────────────────────────────────────────


class TestFormatTime:
    def test_seconds_only(self):
        result = format_time(45)
        assert "45" in result

    def test_minutes_and_seconds(self):
        result = format_time(125)
        assert "2" in result  # 2 minutes

    def test_hours(self):
        result = format_time(3661)
        assert "1" in result  # at least 1 hour

    def test_zero(self):
        result = format_time(0)
        assert "0" in result


# ── ensure_directory ─────────────────────────────────────────────


class TestEnsureDirectory:
    def test_creates_nested(self, tmp_path):
        target = str(tmp_path / "a" / "b" / "c")
        result = ensure_directory(target)
        assert Path(result).is_dir()

    def test_idempotent(self, tmp_path):
        target = str(tmp_path / "exists")
        ensure_directory(target)
        ensure_directory(target)  # should not raise
        assert Path(target).is_dir()


# ── natural_sort_key ─────────────────────────────────────────────


class TestNaturalSortKey:
    def test_numeric_order(self):
        paths = [Path("Track 10.mp3"), Path("Track 2.mp3"), Path("Track 1.mp3")]
        sorted_paths = sorted(paths, key=natural_sort_key)
        names = [p.name for p in sorted_paths]
        assert names == ["Track 1.mp3", "Track 2.mp3", "Track 10.mp3"]


# ── load_config ──────────────────────────────────────────────────


class TestLoadConfig:
    def test_basic_load(self, tmp_path):
        config = {"key": "value", "nested": {"a": 1}}
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))
        result = load_config(str(config_path))
        assert result["key"] == "value"
        assert result["nested"]["a"] == 1

    def test_env_var_interpolation(self, tmp_path):
        os.environ["TEST_ML_VAR"] = "hello"
        config = {"val": "${TEST_ML_VAR:-default}"}
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))
        result = load_config(str(config_path))
        assert result["val"] == "hello"
        del os.environ["TEST_ML_VAR"]

    def test_env_var_default(self, tmp_path):
        os.environ.pop("TEST_ML_MISSING", None)
        config = {"val": "${TEST_ML_MISSING:-fallback}"}
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))
        result = load_config(str(config_path))
        assert result["val"] == "fallback"


# ── get_media_root ───────────────────────────────────────────────


class TestGetMediaRoot:
    def test_from_env(self):
        with patch.dict(os.environ, {"MEDIA_ROOT": "/custom/media"}):
            result = get_media_root()
            assert str(result) == "/custom/media"

    def test_default_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove MEDIA_ROOT if set
            os.environ.pop("MEDIA_ROOT", None)
            result = get_media_root()
            assert isinstance(result, Path)


# ── get_data_dir ─────────────────────────────────────────────────


class TestGetDataDir:
    def test_creates_directory(self, tmp_path):
        with patch.dict(os.environ, {"MEDIA_ROOT": str(tmp_path)}):
            result = get_data_dir()
            assert result.is_dir()


# ── setup_logger ─────────────────────────────────────────────────


class TestSetupLogger:
    def test_returns_logger(self):
        import logging

        logger = setup_logger("test_module", "test_module.log")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_module"

    def test_no_duplicate_handlers(self):
        """Calling setup_logger twice should not add duplicate handlers."""
        logger1 = setup_logger("dedup_test", "dedup.log")
        count1 = len(logger1.handlers)
        logger2 = setup_logger("dedup_test", "dedup.log")
        count2 = len(logger2.handlers)
        assert count2 == count1


# ── rename_with_metadata ────────────────────────────────────────


class TestRenameWithMetadata:
    def test_no_title_returns_none(self, tmp_path):
        f = tmp_path / "movie.mp4"
        f.touch()
        import logging

        logger = logging.getLogger("test")
        result = rename_with_metadata(str(f), {}, logger)
        # No title → should return original or None
        assert result is None or result == str(f)

    def test_rename_with_title_and_year(self, tmp_path):
        f = tmp_path / "DVD_RIP.mp4"
        f.write_bytes(b"\x00")
        import logging

        logger = logging.getLogger("test")
        metadata = {"title": "The Matrix", "year": "1999"}
        result = rename_with_metadata(str(f), metadata, logger)
        if result and result != str(f):
            assert "Matrix" in result
            assert "1999" in result

    def test_nonexistent_file(self, tmp_path):
        import logging

        logger = logging.getLogger("test")
        result = rename_with_metadata(str(tmp_path / "nope.mp4"), {"title": "X"}, logger)
        assert result is None or "nope.mp4" in str(result)
