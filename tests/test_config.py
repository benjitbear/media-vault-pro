"""Tests for the config module — loading, placeholder resolution, validation."""

import json

import pytest

from src.config import ConfigError, load_config, validate_config


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """Create a temporary project-root-like directory for config loading."""
    # config.py resolves relative to its own parent's parent (project root).
    # We monkeypatch Path(__file__) indirectly by writing a real config file
    # and passing the full path logic.
    return tmp_path


@pytest.fixture
def write_config(config_dir):
    """Helper that writes a config dict to config_dir/config.json."""

    def _write(cfg: dict, name: str = "config.json"):
        path = config_dir / name
        path.write_text(json.dumps(cfg))
        return str(path)

    return _write


# ── load_config ──────────────────────────────────────────────────


class TestLoadConfig:
    def test_loads_valid_json(self, tmp_path):
        """load_config should parse JSON and return a dict."""
        cfg = {"output": {"base_directory": "/tmp/media"}}
        path = tmp_path / "cfg.json"
        path.write_text(json.dumps(cfg))
        # load_config resolves relative to project root, so use the real config
        result = load_config()
        assert isinstance(result, dict)
        assert "output" in result

    def test_resolves_env_placeholders(self, monkeypatch):
        """${ENV_VAR:-default} placeholders should be resolved."""
        monkeypatch.setenv("TEST_MEDIA_ROOT", "/custom/path")
        result = load_config()
        # The real config.json uses ${MEDIA_ROOT:-...} — verify resolution works
        base_dir = result.get("output", {}).get("base_directory", "")
        assert "${" not in base_dir  # Should be resolved, not a raw placeholder

    def test_missing_file_raises_config_error(self):
        """load_config should raise ConfigError for missing files."""
        with pytest.raises(ConfigError, match="not found"):
            load_config("nonexistent_file_that_does_not_exist.json")


# ── validate_config ──────────────────────────────────────────────


class TestValidateConfig:
    def test_valid_config_returns_no_errors(self):
        """A complete config should validate without errors."""
        config = {
            "output": {
                "base_directory": "/tmp/media",
                "format": "mp4",
                "video_encoder": "x264",
                "quality": "20",
                "audio_encoder": "aac",
                "audio_bitrate": "160",
            },
            "metadata": {"save_to_json": True},
            "automation": {"auto_detect_disc": True},
            "web_server": {"port": 5000, "host": "0.0.0.0", "library_name": "My Library"},
            "disc_detection": {"check_interval_seconds": 5, "mount_path": "/Volumes"},
            "auth": {"enabled": True},
        }
        errors = validate_config(config)
        assert errors == []

    def test_missing_top_level_section(self):
        """Missing required sections should be reported."""
        config = {"output": {"base_directory": "/tmp"}}
        errors = validate_config(config)
        assert any("metadata" in e for e in errors)
        assert any("auth" in e for e in errors)

    def test_missing_sub_key(self):
        """Missing required sub-keys should be reported."""
        config = {
            "output": {"base_directory": "/tmp"},  # missing format, video_encoder, etc.
            "metadata": {"save_to_json": True},
            "automation": {"auto_detect_disc": True},
            "web_server": {"port": 5000, "host": "0.0.0.0", "library_name": "Test"},
            "disc_detection": {"check_interval_seconds": 5, "mount_path": "/Volumes"},
            "auth": {"enabled": True},
        }
        errors = validate_config(config)
        assert any("format" in e for e in errors)
        assert any("video_encoder" in e for e in errors)

    def test_unresolved_placeholder_detected(self):
        """An unresolved ${...} in base_directory should be flagged."""
        config = {
            "output": {
                "base_directory": "${UNSET_VAR}",
                "format": "mp4",
                "video_encoder": "x264",
                "quality": "20",
                "audio_encoder": "aac",
                "audio_bitrate": "160",
            },
            "metadata": {"save_to_json": True},
            "automation": {"auto_detect_disc": True},
            "web_server": {"port": 5000, "host": "0.0.0.0", "library_name": "Test"},
            "disc_detection": {"check_interval_seconds": 5, "mount_path": "/Volumes"},
            "auth": {"enabled": True},
        }
        errors = validate_config(config)
        assert any("unresolved" in e.lower() for e in errors)
