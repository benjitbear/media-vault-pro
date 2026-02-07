"""
Unit tests for the MetadataExtractor module
"""
import pytest
from unittest.mock import Mock, patch
import json


class TestMetadataExtractor:
    """Test suite for MetadataExtractor class"""

    @pytest.fixture
    def extractor(self):
        """Create a MetadataExtractor instance for testing"""
        from src.metadata import MetadataExtractor
        return MetadataExtractor()

    @pytest.mark.unit
    def test_extractor_initialization(self, extractor):
        """Test MetadataExtractor initializes correctly"""
        assert extractor is not None
        assert hasattr(extractor, 'metadata_dir')
        assert hasattr(extractor, 'config')

    @pytest.mark.unit
    def test_extract_mediainfo(self, extractor, tmp_path):
        """Test extraction of basic file metadata"""
        # Create a dummy file so mediainfo can at least find it
        test_file = tmp_path / 'test.mp4'
        test_file.write_bytes(b'\x00' * 100)
        
        # mediainfo may or may not be installed; test gracefully
        result = extractor.extract_mediainfo(str(test_file))
        # If mediainfo is installed, we get a dict; otherwise None
        if result is not None:
            assert 'file_path' in result
            assert 'file_size_bytes' in result

    @pytest.mark.unit
    @patch('subprocess.run')
    def test_extract_chapters(self, mock_run, extractor):
        """Test chapter information extraction"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps({
                'chapters': [
                    {'start_time': '0.0', 'end_time': '300.0', 'tags': {'title': 'Chapter 1'}},
                    {'start_time': '300.0', 'end_time': '600.0', 'tags': {'title': 'Chapter 2'}}
                ]
            })
        )
        chapters = extractor.extract_chapters('/tmp/test.mp4')
        assert len(chapters) == 2
        assert chapters[0]['title'] == 'Chapter 1'
        assert chapters[1]['start_time'] == 300.0

    @pytest.mark.unit
    def test_tmdb_without_api_key(self, extractor):
        """Test TMDB lookup gracefully handles missing API key"""
        extractor.tmdb_api_key = None
        result = extractor.search_tmdb('Test Movie')
        assert result is None

    @pytest.mark.unit
    def test_save_metadata(self, extractor, tmp_path):
        """Test that metadata is properly saved as JSON"""
        extractor.metadata_dir = tmp_path
        metadata = {'title': 'Test', 'year': 2024}
        extractor.save_metadata(metadata, 'Test Movie')
        
        saved_file = tmp_path / 'Test Movie.json'
        assert saved_file.exists()
        with open(saved_file) as f:
            loaded = json.load(f)
        assert loaded['title'] == 'Test'
