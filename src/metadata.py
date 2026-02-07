"""
Metadata extraction and enrichment for media files
"""
import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from dotenv import load_dotenv

from .utils import load_config, setup_logger, sanitize_filename

# Load environment variables
load_dotenv()


class MetadataExtractor:
    """Extracts and enriches metadata from media files"""
    
    def __init__(self, config_path: str = "config.json"):
        """
        Initialize the MetadataExtractor
        
        Args:
            config_path: Path to configuration file
        """
        self.config = load_config(config_path)
        self.logger = setup_logger('metadata', 'metadata.log')
        self.metadata_dir = Path('/Users/poppemacmini/Media/data/metadata')
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.tmdb_api_key = os.getenv('TMDB_API_KEY')
        self.logger.info("MetadataExtractor initialized")
    
    def extract_mediainfo(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Extract technical metadata using MediaInfo
        
        Args:
            file_path: Path to media file
            
        Returns:
            Dictionary with media information
        """
        self.logger.info(f"Extracting mediainfo from: {file_path}")
        
        try:
            result = subprocess.run(
                ['mediainfo', '--Output=JSON', file_path],
                capture_output=True,
                text=True,
                check=True
            )
            
            data = json.loads(result.stdout)
            
            # Parse relevant information
            metadata = {
                'file_path': file_path,
                'file_size_bytes': os.path.getsize(file_path),
                'tracks': []
            }
            
            if 'media' in data and 'track' in data['media']:
                for track in data['media']['track']:
                    track_type = track.get('@type', '').lower()
                    
                    if track_type == 'general':
                        metadata['duration_seconds'] = float(track.get('Duration', 0))
                        metadata['format'] = track.get('Format', '')
                        metadata['file_size'] = track.get('FileSize', '')
                    
                    elif track_type == 'video':
                        metadata['video'] = {
                            'codec': track.get('Format', ''),
                            'width': track.get('Width', ''),
                            'height': track.get('Height', ''),
                            'frame_rate': track.get('FrameRate', ''),
                            'bit_depth': track.get('BitDepth', '')
                        }
                    
                    elif track_type == 'audio':
                        metadata['tracks'].append({
                            'type': 'audio',
                            'language': track.get('Language', 'Unknown'),
                            'codec': track.get('Format', ''),
                            'channels': track.get('Channels', ''),
                            'sampling_rate': track.get('SamplingRate', '')
                        })
                    
                    elif track_type == 'text':
                        metadata['tracks'].append({
                            'type': 'subtitle',
                            'language': track.get('Language', 'Unknown'),
                            'format': track.get('Format', '')
                        })
            
            self.logger.info(f"Successfully extracted mediainfo")
            return metadata
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"MediaInfo error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error extracting mediainfo: {e}")
            return None
    
    def extract_chapters(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Extract chapter information using FFprobe
        
        Args:
            file_path: Path to media file
            
        Returns:
            List of chapter dictionaries
        """
        self.logger.info(f"Extracting chapters from: {file_path}")
        
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-print_format', 'json',
                 '-show_chapters', file_path],
                capture_output=True,
                text=True,
                check=True
            )
            
            data = json.loads(result.stdout)
            chapters = []
            
            if 'chapters' in data:
                for idx, chapter in enumerate(data['chapters'], 1):
                    chapters.append({
                        'number': idx,
                        'start_time': float(chapter.get('start_time', 0)),
                        'end_time': float(chapter.get('end_time', 0)),
                        'title': chapter.get('tags', {}).get('title', f'Chapter {idx}')
                    })
            
            self.logger.info(f"Extracted {len(chapters)} chapters")
            return chapters
            
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.logger.warning("Could not extract chapters (ffprobe not available)")
            return []
        except Exception as e:
            self.logger.error(f"Error extracting chapters: {e}")
            return []
    
    def search_tmdb(self, title: str, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Search TMDB for movie metadata
        
        Args:
            title: Movie title
            year: Release year (optional)
            
        Returns:
            Movie metadata from TMDB or None
        """
        if not self.tmdb_api_key:
            self.logger.warning("TMDB API key not configured")
            return None
        
        self.logger.info(f"Searching TMDB for: {title}")
        
        try:
            import requests
            
            # Search for movie
            search_url = "https://api.themoviedb.org/3/search/movie"
            params = {
                'api_key': self.tmdb_api_key,
                'query': title
            }
            
            if year:
                params['year'] = year
            
            response = requests.get(search_url, params=params, timeout=10)
            response.raise_for_status()
            
            results = response.json().get('results', [])
            
            if not results:
                self.logger.info(f"No TMDB results for: {title}")
                return None
            
            # Get first result (best match)
            movie_id = results[0]['id']
            
            # Fetch detailed information
            detail_url = f"https://api.themoviedb.org/3/movie/{movie_id}"
            credits_url = f"https://api.themoviedb.org/3/movie/{movie_id}/credits"
            
            movie_response = requests.get(
                detail_url,
                params={'api_key': self.tmdb_api_key},
                timeout=10
            )
            credits_response = requests.get(
                credits_url,
                params={'api_key': self.tmdb_api_key},
                timeout=10
            )
            
            movie_data = movie_response.json()
            credits_data = credits_response.json()
            
            # Extract relevant information
            metadata = {
                'title': movie_data.get('title'),
                'original_title': movie_data.get('original_title'),
                'year': movie_data.get('release_date', '')[:4] if movie_data.get('release_date') else None,
                'overview': movie_data.get('overview'),
                'runtime_minutes': movie_data.get('runtime'),
                'genres': [g['name'] for g in movie_data.get('genres', [])],
                'rating': movie_data.get('vote_average'),
                'tmdb_id': movie_id,
                'poster_path': movie_data.get('poster_path'),
                'backdrop_path': movie_data.get('backdrop_path'),
                'collection_name': None
            }
            
            # Extract collection info (e.g., "The Dark Knight Collection")
            if movie_data.get('belongs_to_collection'):
                metadata['collection_name'] = movie_data['belongs_to_collection'].get('name')
            
            # Add director and cast
            if 'crew' in credits_data:
                directors = [c['name'] for c in credits_data['crew'] if c['job'] == 'Director']
                metadata['director'] = directors[0] if directors else None
            
            if 'cast' in credits_data:
                metadata['cast'] = [c['name'] for c in credits_data['cast'][:10]]
            
            self.logger.info(f"Found TMDB match: {metadata['title']} ({metadata['year']})")
            return metadata
            
        except Exception as e:
            self.logger.error(f"Error searching TMDB: {e}")
            return None
    
    def download_poster(self, poster_path: str, output_path: str) -> bool:
        """
        Download movie poster from TMDB
        
        Args:
            poster_path: TMDB poster path
            output_path: Local output path
            
        Returns:
            True if successful
        """
        if not poster_path:
            return False
        
        try:
            import requests
            from PIL import Image
            from io import BytesIO
            
            url = f"https://image.tmdb.org/t/p/w500{poster_path}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            image = Image.open(BytesIO(response.content))
            image.save(output_path)
            
            self.logger.info(f"Downloaded poster to: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error downloading poster: {e}")
            return False
    
    def extract_full_metadata(self, file_path: str, title_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract complete metadata from media file
        
        Args:
            file_path: Path to media file
            title_hint: Optional title hint for TMDB lookup
            
        Returns:
            Complete metadata dictionary
        """
        self.logger.info(f"Extracting full metadata for: {file_path}")
        
        metadata = {
            'extracted_at': datetime.now().isoformat(),
            'source_file': file_path
        }
        
        # Extract technical metadata
        mediainfo = self.extract_mediainfo(file_path)
        if mediainfo:
            metadata['file_info'] = mediainfo
        
        # Extract chapters if enabled
        if self.config['metadata']['extract_chapters']:
            chapters = self.extract_chapters(file_path)
            if chapters:
                metadata['chapters'] = chapters
        
        # Search TMDB if enabled and title hint provided
        if self.config['metadata'].get('fetch_online_metadata', True) and title_hint:
            tmdb_data = self.search_tmdb(title_hint)
            if tmdb_data:
                metadata['tmdb'] = tmdb_data
                
                # Download poster if available
                if tmdb_data.get('poster_path'):
                    poster_filename = f"{sanitize_filename(title_hint)}_poster.jpg"
                    poster_path = self.metadata_dir.parent / 'thumbnails' / poster_filename
                    poster_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    if self.download_poster(tmdb_data['poster_path'], str(poster_path)):
                        metadata['poster_file'] = str(poster_path)
        
        return metadata
    
    def save_metadata(self, metadata: Dict[str, Any], title: str):
        """
        Save metadata to JSON file
        
        Args:
            metadata: Metadata dictionary
            title: Title for filename
        """
        if not self.config['metadata']['save_to_json']:
            return
        
        filename = f"{sanitize_filename(title)}.json"
        output_path = self.metadata_dir / filename
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Saved metadata to: {output_path}")
            
        except Exception as e:
            self.logger.error(f"Error saving metadata: {e}")


def main():
    """Main entry point for command-line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract media metadata')
    parser.add_argument('file', help='Path to media file')
    parser.add_argument('--title', help='Title hint for TMDB lookup')
    parser.add_argument('--save', action='store_true', help='Save metadata to JSON')
    
    args = parser.parse_args()
    
    extractor = MetadataExtractor()
    metadata = extractor.extract_full_metadata(args.file, args.title)
    
    # Print metadata
    print(json.dumps(metadata, indent=2))
    
    # Save if requested
    if args.save and args.title:
        extractor.save_metadata(metadata, args.title)


if __name__ == '__main__':
    main()
