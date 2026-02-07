"""
Metadata extraction and enrichment for media files
"""
import json
import os
import re
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
    
    def search_tmdb(self, title: str, year: Optional[int] = None,
                    disc_hints: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Search TMDB for movie metadata.
        Uses disc_hints (runtime, title count, disc label) to improve matching.
        
        Args:
            title: Movie title (often derived from disc volume name)
            year: Release year (optional)
            disc_hints: Extra info from disc scan — estimated_runtime_min,
                        title_count, disc_label, disc_type, etc.
            
        Returns:
            Movie metadata from TMDB or None
        """
        if not self.tmdb_api_key:
            self.logger.warning("TMDB API key not configured")
            return None
        
        disc_hints = disc_hints or {}
        
        # Clean up the title for better search results
        clean_title = self._clean_search_title(title)
        self.logger.info(f"Searching TMDB for: '{clean_title}' (raw: '{title}')")
        
        try:
            import requests
            
            # Search for movie
            search_url = "https://api.themoviedb.org/3/search/movie"
            params = {
                'api_key': self.tmdb_api_key,
                'query': clean_title
            }
            
            if year:
                params['year'] = year
            
            response = requests.get(search_url, params=params, timeout=10)
            response.raise_for_status()
            
            results = response.json().get('results', [])
            
            if not results:
                # Retry with even more aggressive title cleaning
                fallback_title = self._aggressive_clean_title(title)
                if fallback_title != clean_title:
                    self.logger.info(f"Retrying TMDB with fallback title: '{fallback_title}'")
                    params['query'] = fallback_title
                    response = requests.get(search_url, params=params, timeout=10)
                    response.raise_for_status()
                    results = response.json().get('results', [])

            if not results:
                self.logger.info(f"No TMDB results for: {title}")
                return None
            
            # Pick the best match using disc hints to disambiguate
            movie_id = self._pick_best_tmdb_match(results, disc_hints)
            
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

    def download_backdrop(self, backdrop_path: str, output_path: str) -> bool:
        """
        Download movie backdrop/fanart from TMDB
        
        Args:
            backdrop_path: TMDB backdrop path
            output_path: Local output path
            
        Returns:
            True if successful
        """
        if not backdrop_path:
            return False
        
        try:
            import requests
            from PIL import Image
            from io import BytesIO
            
            url = f"https://image.tmdb.org/t/p/w1280{backdrop_path}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            image = Image.open(BytesIO(response.content))
            image.save(output_path)
            
            self.logger.info(f"Downloaded backdrop to: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error downloading backdrop: {e}")
            return False

    # ── Title Cleaning ────────────────────────────────────────────

    def _clean_search_title(self, raw_title: str) -> str:
        """
        Clean a raw disc volume name into a reasonable search query.
        Handles common disc naming patterns like underscores, disc markers,
        trailing timestamps, region codes, etc.
        
        Args:
            raw_title: Raw title (usually from volume name)
            
        Returns:
            Cleaned title suitable for TMDB search
        """
        title = raw_title

        # Replace underscores with spaces
        title = title.replace('_', ' ')

        # Remove common disc markers (case-insensitive)
        noise_patterns = [
            r'\bDISC\s*\d*\b', r'\bDVD\b', r'\bBLU\s*RAY\b', r'\bBD\b',
            r'\bCD\s*\d*\b', r'\bVOL(UME)?\s*\d*\b',
            r'\bWIDESCREEN\b', r'\bFULLSCREEN\b', r'\bSPECIAL\s*EDITION\b',
            r'\bREGION\s*\d\b', r'\bNTSC\b', r'\bPAL\b',
            r'\bTHE\s*MOVIE\b',
        ]
        for pat in noise_patterns:
            title = re.sub(pat, '', title, flags=re.IGNORECASE)

        # Remove trailing timestamps like _20260207_160005
        # Match anywhere: 8-digit date + 6-digit time separated by underscore or space
        title = re.sub(r'\b\d{8}[\s_]\d{6}\b', '', title)

        # Remove trailing year-like numbers if they don't look like a year
        # (keep 1900-2099, remove others)
        match = re.search(r'\b(\d{4})\s*$', title)
        if match:
            num = int(match.group(1))
            if num < 1900 or num > 2099:
                title = title[:match.start()]

        # Collapse whitespace and strip
        title = re.sub(r'\s+', ' ', title).strip()

        return title if title else raw_title.replace('_', ' ').strip()

    def _aggressive_clean_title(self, raw_title: str) -> str:
        """
        More aggressive title cleaning as a fallback.
        Strips all non-alphabetic characters and short noise words.
        """
        title = raw_title.replace('_', ' ')
        # Keep only letters and spaces
        title = re.sub(r'[^a-zA-Z\s]', '', title)
        # Remove single-letter words (except 'I' and 'A')
        words = [w for w in title.split() if len(w) > 1 or w.upper() in ('I', 'A')]
        return ' '.join(words).strip() if words else raw_title

    def _pick_best_tmdb_match(self, results: list,
                               disc_hints: Dict[str, Any]) -> int:
        """
        Pick the best TMDB result using disc hints for disambiguation.
        
        Uses estimated runtime from disc scan to filter out wrong matches.
        Falls back to TMDB's default relevance ordering.
        
        Args:
            results: List of TMDB search results
            disc_hints: Disc scan hints (estimated_runtime_min, etc.)
            
        Returns:
            TMDB movie ID of the best match
        """
        estimated_runtime = disc_hints.get('estimated_runtime_min')
        
        if not estimated_runtime or len(results) <= 1:
            return results[0]['id']
        
        # Score each result by how close its runtime is to the disc's
        best_id = results[0]['id']
        best_diff = float('inf')
        
        for r in results[:5]:  # Only check top 5
            import requests
            try:
                detail = requests.get(
                    f"https://api.themoviedb.org/3/movie/{r['id']}",
                    params={'api_key': self.tmdb_api_key},
                    timeout=5
                ).json()
                tmdb_runtime = detail.get('runtime', 0)
                if tmdb_runtime:
                    diff = abs(tmdb_runtime - estimated_runtime)
                    self.logger.debug(
                        f"  TMDB match '{detail.get('title')}' runtime={tmdb_runtime}, "
                        f"disc≈{estimated_runtime}, diff={diff}"
                    )
                    if diff < best_diff:
                        best_diff = diff
                        best_id = r['id']
            except Exception:
                pass
        
        self.logger.info(f"Selected TMDB ID {best_id} (runtime diff: {best_diff} min)")
        return best_id

    # ── MusicBrainz (audio CDs) ──────────────────────────────────

    def search_musicbrainz(self, album_name: str,
                           disc_hints: Optional[Dict[str, Any]] = None
                           ) -> Optional[Dict[str, Any]]:
        """
        Search MusicBrainz for album metadata (audio CDs).
        Uses track count and total duration to improve matching.
        
        Args:
            album_name: Album title guess
            disc_hints: Audio CD info — track_count, total_duration_seconds
            
        Returns:
            Album metadata dict or None
        """
        disc_hints = disc_hints or {}
        clean_name = self._clean_search_title(album_name)
        self.logger.info(f"Searching MusicBrainz for: '{clean_name}'")
        
        try:
            import requests
            
            params = {
                'query': f'release:"{clean_name}"',
                'fmt': 'json',
                'limit': 10,
            }
            headers = {
                'User-Agent': 'MediaVaultPro/1.0 (media-vault-pro@github.com)'
            }
            
            response = requests.get(
                'https://musicbrainz.org/ws/2/release',
                params=params, headers=headers, timeout=10
            )
            response.raise_for_status()
            releases = response.json().get('releases', [])
            
            if not releases:
                self.logger.info(f"No MusicBrainz results for: {clean_name}")
                return None
            
            # Pick best match using track count if available
            target_tracks = disc_hints.get('track_count', 0)
            best = releases[0]
            if target_tracks:
                for rel in releases:
                    media_list = rel.get('media', [])
                    if media_list:
                        mb_tracks = media_list[0].get('track-count', 0)
                        if mb_tracks == target_tracks:
                            best = rel
                            break
            
            # Fetch detailed release info
            release_id = best['id']
            detail_resp = requests.get(
                f'https://musicbrainz.org/ws/2/release/{release_id}',
                params={'inc': 'recordings+artist-credits+labels', 'fmt': 'json'},
                headers=headers, timeout=10
            )
            detail_resp.raise_for_status()
            detail = detail_resp.json()
            
            # Build metadata
            artists = [a['artist']['name'] for a in detail.get('artist-credit', [])
                       if isinstance(a, dict) and 'artist' in a]
            
            tracks = []
            for medium in detail.get('media', []):
                for t in medium.get('tracks', []):
                    tracks.append({
                        'number': t.get('number'),
                        'title': t.get('title'),
                        'duration_ms': t.get('length'),
                    })
            
            metadata = {
                'title': detail.get('title', best.get('title')),
                'artist': ', '.join(artists) if artists else None,
                'year': (detail.get('date') or '')[:4] or None,
                'label': None,
                'track_count': len(tracks),
                'tracks': tracks,
                'musicbrainz_id': release_id,
                'media_type': 'audio',
            }

            # Label
            label_info = detail.get('label-info', [])
            if label_info and isinstance(label_info[0], dict):
                lbl = label_info[0].get('label', {})
                metadata['label'] = lbl.get('name') if isinstance(lbl, dict) else None

            # Try to get cover art
            try:
                cover_resp = requests.get(
                    f'https://coverartarchive.org/release/{release_id}',
                    headers=headers, timeout=10
                )
                if cover_resp.status_code == 200:
                    images = cover_resp.json().get('images', [])
                    if images:
                        metadata['cover_art_url'] = images[0].get('image')
                        # Find front cover specifically
                        for img in images:
                            if 'Front' in img.get('types', []):
                                metadata['cover_art_url'] = img.get('image')
                                break
            except Exception:
                pass
            
            self.logger.info(
                f"MusicBrainz match: {metadata['title']} by {metadata['artist']}"
            )
            return metadata
            
        except Exception as e:
            self.logger.error(f"MusicBrainz search error: {e}")
            return None

    def download_cover_art(self, url: str, output_path: str) -> bool:
        """
        Download album cover art from a URL.
        
        Args:
            url: Cover art URL
            output_path: Local file path to save
            
        Returns:
            True if successful
        """
        if not url:
            return False
        try:
            import requests
            from PIL import Image
            from io import BytesIO
            
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            
            image = Image.open(BytesIO(response.content))
            image.save(output_path)
            self.logger.info(f"Downloaded cover art to: {output_path}")
            return True
        except Exception as e:
            self.logger.error(f"Error downloading cover art: {e}")
            return False
    
    def extract_full_metadata(self, file_path: str, title_hint: Optional[str] = None,
                              disc_hints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Extract complete metadata from media file.
        Uses disc_hints for better online lookup matching.
        
        Args:
            file_path: Path to media file (or directory for audio CDs)
            title_hint: Optional title hint for online lookup
            disc_hints: Extra disc info (disc_type, estimated_runtime_min,
                        track_count, etc.)
            
        Returns:
            Complete metadata dictionary
        """
        self.logger.info(f"Extracting full metadata for: {file_path}")

        disc_hints = disc_hints or {}
        disc_type = disc_hints.get('disc_type', 'dvd')
        
        metadata = {
            'extracted_at': datetime.now().isoformat(),
            'source_file': file_path,
            'disc_type': disc_type,
        }

        # ── Audio CD path ─────────────────────────────────────────
        if disc_type == 'audio_cd':
            # Search MusicBrainz for album metadata
            if self.config['metadata'].get('fetch_online_metadata', True) and title_hint:
                mb_data = self.search_musicbrainz(title_hint, disc_hints)
                if mb_data:
                    metadata['musicbrainz'] = mb_data

                    # Download cover art
                    if mb_data.get('cover_art_url'):
                        cover_filename = f"{sanitize_filename(title_hint)}_poster.jpg"
                        cover_path = self.metadata_dir.parent / 'thumbnails' / cover_filename
                        cover_path.parent.mkdir(parents=True, exist_ok=True)
                        if self.download_cover_art(mb_data['cover_art_url'], str(cover_path)):
                            metadata['poster_file'] = str(cover_path)

            return metadata

        # ── Video path (DVD / Blu-ray) ────────────────────────────
        # Extract technical metadata
        if os.path.isfile(file_path):
            mediainfo = self.extract_mediainfo(file_path)
            if mediainfo:
                metadata['file_info'] = mediainfo
        
        # Extract chapters if enabled
        if self.config['metadata']['extract_chapters'] and os.path.isfile(file_path):
            chapters = self.extract_chapters(file_path)
            if chapters:
                metadata['chapters'] = chapters
        
        # Search TMDB if enabled and title hint provided
        if self.config['metadata'].get('fetch_online_metadata', True) and title_hint:
            tmdb_data = self.search_tmdb(title_hint, disc_hints=disc_hints)
            if tmdb_data:
                metadata['tmdb'] = tmdb_data
                
                safe_title = sanitize_filename(title_hint)
                thumbnails_dir = self.metadata_dir.parent / 'thumbnails'
                thumbnails_dir.mkdir(parents=True, exist_ok=True)

                # Download poster if available
                if tmdb_data.get('poster_path'):
                    poster_filename = f"{safe_title}_poster.jpg"
                    poster_out = thumbnails_dir / poster_filename
                    
                    if self.download_poster(tmdb_data['poster_path'], str(poster_out)):
                        metadata['poster_file'] = str(poster_out)

                # Download backdrop if available
                if tmdb_data.get('backdrop_path'):
                    backdrop_filename = f"{safe_title}_backdrop.jpg"
                    backdrop_out = thumbnails_dir / backdrop_filename

                    if self.download_backdrop(tmdb_data['backdrop_path'], str(backdrop_out)):
                        metadata['backdrop_file'] = str(backdrop_out)
        
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
