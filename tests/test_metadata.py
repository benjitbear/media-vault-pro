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

    @pytest.mark.unit
    def test_clean_search_title(self, extractor):
        """Test title cleaning strips disc noise from volume names"""
        assert extractor._clean_search_title('THE_MATRIX') == 'THE MATRIX'
        assert 'DVD' not in extractor._clean_search_title('MOVIE_DVD')
        assert 'DISC' not in extractor._clean_search_title('MOVIE_DISC_1')
        assert 'WIDESCREEN' not in extractor._clean_search_title('MOVIE_WIDESCREEN')
        # Timestamps should be stripped
        cleaned = extractor._clean_search_title('PRELUDE_20260207_160005')
        assert '20260207' not in cleaned

    @pytest.mark.unit
    def test_aggressive_clean_title(self, extractor):
        """Test aggressive title cleaning removes non-alpha chars"""
        result = extractor._aggressive_clean_title('M0V13_2024!!!')
        assert result.isalpha() or ' ' in result

    @pytest.mark.unit
    def test_pick_best_tmdb_match_no_hints(self, extractor):
        """Test best match picker falls back to first result without hints"""
        results = [{'id': 100}, {'id': 200}]
        assert extractor._pick_best_tmdb_match(results, {}) == 100

    @pytest.mark.unit
    def test_search_musicbrainz_no_results(self, extractor):
        """Test MusicBrainz search handles no results gracefully"""
        with patch('requests.get') as mock_get:
            mock_get.return_value = Mock(
                status_code=200,
                json=lambda: {'releases': []}
            )
            mock_get.return_value.raise_for_status = lambda: None
            result = extractor.search_musicbrainz('Nonexistent Album XYZ123')
            assert result is None

    @pytest.mark.unit
    def test_extract_full_metadata_audio_cd(self, extractor, tmp_path):
        """Test full metadata extraction for audio CD type"""
        extractor.tmdb_api_key = None  # No API key
        metadata = extractor.extract_full_metadata(
            str(tmp_path),
            title_hint='Test Album',
            disc_hints={'disc_type': 'audio_cd', 'track_count': 10}
        )
        assert metadata['disc_type'] == 'audio_cd'

    @pytest.mark.unit
    def test_download_backdrop_no_path(self, extractor):
        """Test backdrop download returns False for None path"""
        assert extractor.download_backdrop(None, '/tmp/test.jpg') is False

    @pytest.mark.unit
    def test_download_cover_art_no_url(self, extractor):
        """Test cover art download returns False for None URL"""
        assert extractor.download_cover_art(None, '/tmp/test.jpg') is False
