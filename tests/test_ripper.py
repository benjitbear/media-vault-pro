"""
Unit tests for the Ripper module
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestRipper:
    """Test suite for Ripper class"""

    @pytest.fixture
    def ripper(self, app_state, tmp_path):
        """Create a Ripper instance for testing"""
        from src.ripper import Ripper

        ripper = Ripper(config_path="config.json", app_state=app_state)
        ripper.output_dir = tmp_path / "output"
        ripper.output_dir.mkdir(parents=True, exist_ok=True)
        return ripper

    def test_ripper_initialization(self, ripper):
        """Test that ripper initializes correctly"""
        assert ripper is not None
        assert hasattr(ripper, "config")
        assert hasattr(ripper, "app_state")
        assert ripper.app_state is not None

    @pytest.mark.unit
    def test_handbrake_command_generation(self, ripper):
        """Test that HandBrake commands are generated correctly"""
        cmd = ripper.build_handbrake_command("/Volumes/DVD", "/tmp/output.mp4", title=1)
        assert any("HandBrakeCLI" in arg for arg in cmd)
        assert "--input" in cmd
        assert "/Volumes/DVD" in cmd
        assert "--output" in cmd
        assert "/tmp/output.mp4" in cmd
        assert "--title" in cmd

    @pytest.mark.unit
    def test_validate_source_path(self, ripper):
        """Test source path handling via detect_disc_info"""
        # HandBrake may still return scan output even for bad paths,
        # but should report no valid titles found
        result = ripper.detect_disc_info("/nonexistent/path")
        # HandBrake exits with returncode 0 but finds 0 titles
        if result is not None:
            assert "scan_output" in result

    @pytest.mark.unit
    @patch("subprocess.run")
    def test_handbrake_check(self, mock_run, ripper):
        """Test HandBrake installation check"""
        mock_run.return_value = MagicMock(returncode=0)
        assert ripper.check_handbrake_installed() is True

        mock_run.side_effect = FileNotFoundError
        assert ripper.check_handbrake_installed() is False

    @pytest.mark.unit
    def test_title_list(self, ripper):
        """Test get_title_list returns expected format"""
        # With non-existent source, should return empty
        result = ripper.get_title_list("/nonexistent")
        assert isinstance(result, list)

    @pytest.mark.unit
    def test_rip_audio_cd_no_tracks(self, ripper, tmp_path):
        """Test audio CD rip fails gracefully when no audio tracks found"""
        empty_dir = tmp_path / "EMPTY_CD"
        empty_dir.mkdir()
        result = ripper.rip_audio_cd(source_path=str(empty_dir), album_name="Test")
        assert result is None

    @pytest.mark.unit
    def test_rip_audio_cd_nonexistent_path(self, ripper):
        """Test audio CD rip handles missing path"""
        result = ripper.rip_audio_cd(source_path="/nonexistent", album_name="Test")
        assert result is None

    @pytest.mark.unit
    @patch("subprocess.run")
    def test_rip_audio_cd_with_tracks(self, mock_run, ripper, tmp_path):
        """Test audio CD rip processes .aiff files"""
        cd_dir = tmp_path / "MY_CD"
        cd_dir.mkdir()
        (cd_dir / "Track 01.aiff").write_bytes(b"\x00" * 100)
        (cd_dir / "Track 02.aiff").write_bytes(b"\x00" * 100)

        mock_run.return_value = MagicMock(returncode=0)
        result = ripper.rip_audio_cd(source_path=str(cd_dir), album_name="Test Album")
        assert result is not None
        result_path = Path(result)
        assert result_path.exists()
        # Audio CD output should be under music/ subdirectory
        assert "music" in result_path.parts
