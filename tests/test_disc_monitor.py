"""
Unit tests for the DiscMonitor module
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import time


class TestDiscMonitor:
    """Test suite for DiscMonitor class"""

    @pytest.fixture
    def monitor(self, app_state):
        """Create a DiscMonitor instance for testing"""
        from src.disc_monitor import DiscMonitor
        return DiscMonitor(app_state=app_state)

    @pytest.mark.unit
    def test_monitor_initialization(self, monitor):
        """Test that monitor initializes correctly"""
        assert monitor is not None
        assert monitor.app_state is not None
        assert hasattr(monitor, 'known_volumes')

    @pytest.mark.unit
    def test_disc_detection_dvd(self, monitor, mock_dvd_structure):
        """Test DVD disc detection via VIDEO_TS"""
        assert monitor.is_disc_volume(mock_dvd_structure) is True

    @pytest.mark.unit
    def test_disc_detection_non_disc(self, monitor, tmp_path):
        """Test that regular directories are not detected as discs"""
        regular_dir = tmp_path / "regular_dir"
        regular_dir.mkdir()
        assert monitor.is_disc_volume(regular_dir) is False

    @pytest.mark.unit
    def test_title_extraction(self, monitor):
        """Test title extraction from volume names"""
        assert monitor.extract_title_from_volume('THE_MATRIX') == 'THE MATRIX'
        assert monitor.extract_title_from_volume('MY_DVD_DISC') == 'MY'

    @pytest.mark.unit
    def test_process_disc_enqueues_job(self, monitor, app_state, mock_dvd_structure):
        """Test that process_disc creates a job in app_state"""
        volume_name = mock_dvd_structure.name
        monitor.mount_path = mock_dvd_structure.parent
        monitor.process_disc(volume_name)
        
        jobs = app_state.get_all_jobs()
        assert len(jobs) == 1
        assert jobs[0]['status'] == 'queued'

    @pytest.mark.unit
    def test_audio_cd_detection(self, monitor, tmp_path):
        """Test that audio CDs are detected by .aiff files"""
        cd_dir = tmp_path / "AUDIO_CD"
        cd_dir.mkdir()
        (cd_dir / "Track 01.aiff").write_bytes(b'\x00' * 100)
        (cd_dir / "Track 02.aiff").write_bytes(b'\x00' * 100)
        assert monitor.is_audio_cd(cd_dir) is True
        assert monitor.is_disc_volume(cd_dir) is True

    @pytest.mark.unit
    def test_audio_cd_detection_negative(self, monitor, tmp_path):
        """Test that dirs with no audio files are not audio CDs"""
        regular_dir = tmp_path / "REGULAR"
        regular_dir.mkdir()
        (regular_dir / "readme.txt").write_text("hello")
        assert monitor.is_audio_cd(regular_dir) is False

    @pytest.mark.unit
    def test_get_disc_type(self, monitor, tmp_path, mock_dvd_structure):
        """Test disc type detection"""
        assert monitor.get_disc_type(mock_dvd_structure) == 'dvd'

        bluray_dir = tmp_path / "BLURAY_DISC"
        bluray_dir.mkdir()
        (bluray_dir / "BDMV").mkdir()
        assert monitor.get_disc_type(bluray_dir) == 'bluray'

        cd_dir = tmp_path / "MUSIC_CD"
        cd_dir.mkdir()
        (cd_dir / "Track 01.aiff").write_bytes(b'\x00' * 100)
        assert monitor.get_disc_type(cd_dir) == 'audio_cd'

        empty_dir = tmp_path / "EMPTY"
        empty_dir.mkdir()
        assert monitor.get_disc_type(empty_dir) == 'unknown'

    @pytest.mark.unit
    def test_process_disc_audio_cd(self, monitor, app_state, tmp_path):
        """Test that audio CD processing creates a job with disc_type=audio_cd"""
        cd_dir = tmp_path / "MY_ALBUM"
        cd_dir.mkdir()
        (cd_dir / "Track 01.aiff").write_bytes(b'\x00' * 100)

        monitor.mount_path = tmp_path
        monitor.process_disc("MY_ALBUM")

        jobs = app_state.get_all_jobs()
        assert len(jobs) == 1
        assert jobs[0]['disc_type'] == 'audio_cd'
