"""
Test fixtures and configuration for pytest
"""
import pytest
import os
import json
from pathlib import Path


@pytest.fixture(scope="session")
def test_config():
    """Provide test configuration"""
    return {
        "output": {
            "base_directory": "/tmp/test_media_library",
            "format": "mp4",
            "video_encoder": "x264",
            "quality": 22,
            "audio_encoder": "aac",
            "audio_bitrate": "192"
        },
        "metadata": {
            "save_to_json": True,
            "extract_chapters": True,
            "extract_subtitles": True,
            "extract_audio_tracks": True,
            "fetch_online_metadata": True
        },
        "automation": {
            "auto_detect_disc": False,
            "auto_eject_after_rip": False,
            "notification_enabled": False
        },
        "web_server": {
            "enabled": True,
            "port": 8097,
            "host": "127.0.0.1",
            "library_name": "Test Library"
        },
        "disc_detection": {
            "check_interval_seconds": 5,
            "mount_path": "/Volumes"
        },
        "handbrake": {
            "preset": "Fast 1080p30",
            "additional_options": []
        },
        "auth": {
            "enabled": False,
            "token": "test-token",
            "session_hours": 24
        },
        "library_cache": {
            "ttl_seconds": 300
        }
    }


@pytest.fixture(scope="session")
def test_output_dir(tmp_path_factory):
    """Create temporary output directory for tests"""
    output_dir = tmp_path_factory.mktemp("media_output")
    return output_dir


@pytest.fixture
def app_state(tmp_path):
    """Create an AppState with a temporary database"""
    from src.app_state import AppState
    AppState.reset()
    state = AppState(db_path=str(tmp_path / 'test.db'))
    yield state
    AppState.reset()


@pytest.fixture
def mock_dvd_structure(tmp_path):
    """Create a mock DVD directory structure"""
    dvd_path = tmp_path / "DVD_VOLUME"
    dvd_path.mkdir()
    
    # Create typical DVD structure
    video_ts = dvd_path / "VIDEO_TS"
    video_ts.mkdir()
    
    # Create dummy files
    (video_ts / "VIDEO_TS.IFO").touch()
    (video_ts / "VTS_01_1.VOB").touch()
    
    return dvd_path


@pytest.fixture
def sample_metadata():
    """Provide sample metadata for testing"""
    return {
        "title": "Test Movie",
        "year": 2024,
        "director": "Test Director",
        "cast": ["Actor 1", "Actor 2"],
        "runtime": 120,
        "chapters": 12
    }


@pytest.fixture(autouse=True)
def cleanup_test_files():
    """Cleanup test files after each test"""
    yield
    # Cleanup code here if needed
