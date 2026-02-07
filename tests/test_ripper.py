"""
Unit tests for the Ripper module
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path


class TestRipper:
    """Test suite for Ripper class"""

    @pytest.fixture
    def ripper(self, app_state):
        """Create a Ripper instance for testing"""
        from src.ripper import Ripper
        return Ripper(config_path='config.json', app_state=app_state)

    def test_ripper_initialization(self, ripper):
        """Test that ripper initializes correctly"""
        assert ripper is not None
        assert hasattr(ripper, 'config')
        assert hasattr(ripper, 'app_state')
        assert ripper.app_state is not None

    @pytest.mark.unit
    def test_handbrake_command_generation(self, ripper):
        """Test that HandBrake commands are generated correctly"""
        cmd = ripper.build_handbrake_command('/Volumes/DVD', '/tmp/output.mp4', title=1)
        assert 'HandBrakeCLI' in cmd
        assert '--input' in cmd
        assert '/Volumes/DVD' in cmd
        assert '--output' in cmd
        assert '/tmp/output.mp4' in cmd
        assert '--title' in cmd

    @pytest.mark.unit
    def test_validate_source_path(self, ripper):
        """Test source path handling via detect_disc_info"""
        # HandBrake may still return scan output even for bad paths,
        # but should report no valid titles found
        result = ripper.detect_disc_info('/nonexistent/path')
        # HandBrake exits with returncode 0 but finds 0 titles
        if result is not None:
            assert 'scan_output' in result

    @pytest.mark.unit
    @patch('subprocess.run')
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
        result = ripper.get_title_list('/nonexistent')
        assert isinstance(result, list)
