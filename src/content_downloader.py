"""
Content downloader for various media sources.
Handles: YouTube/video URLs (yt-dlp), web articles (trafilatura),
         podcast feed parsing (feedparser), and Spotify/playlist import.
"""
import json
import os
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .app_state import AppState
from .utils import load_config, setup_logger, sanitize_filename, \
    format_size, detect_media_type


class ContentDownloader:
    """Unified content downloader for all external media types."""

    def __init__(self, config_path: str = 'config.json', app_state: AppState = None):
        self.config = load_config(config_path)
        self.logger = setup_logger('content_downloader', 'content_downloader.log')
        self.app_state = app_state or AppState()

        dl_cfg = self.config.get('downloads', {})
        self.download_dir = Path(dl_cfg.get(
            'download_directory',
            str(Path(self.config['output']['base_directory']) / 'downloads')
        ))
        self.articles_dir = Path(dl_cfg.get(
            'articles_directory',
            str(Path(self.config['output']['base_directory']) / 'articles')
        ))
        self.books_dir = Path(dl_cfg.get(
            'books_directory',
            str(Path(self.config['output']['base_directory']) / 'books')
        ))
        self.ytdlp_format = dl_cfg.get(
            'ytdlp_format', 'bestvideo[height<=1080]+bestaudio/best')

        pod_cfg = self.config.get('podcasts', {})
        self.podcast_dir = Path(pod_cfg.get(
            'download_directory',
            str(Path(self.config['output']['base_directory']) / 'podcasts')
        ))

        # Ensure directories exist
        for d in (self.download_dir, self.articles_dir,
                  self.books_dir, self.podcast_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ── Video Downloads (yt-dlp) ─────────────────────────────────

    def download_video(self, url: str, job_id: str = None) -> Optional[str]:
        """Download a video via yt-dlp. Returns output file path or None."""
        self.logger.info(f"Downloading video: {url}")

        # Use yt-dlp to extract info first for naming
        try:
            info_cmd = [
                'yt-dlp', '--no-download', '--print-json',
                '--no-warnings', url
            ]
            result = subprocess.run(info_cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                info = json.loads(result.stdout.strip().split('\n')[0])
                title = sanitize_filename(info.get('title', 'download'))
                uploader = info.get('uploader', 'Unknown')
            else:
                title = f"download_{uuid.uuid4().hex[:8]}"
                uploader = 'Unknown'
        except Exception as e:
            self.logger.warning(f"Could not extract video info: {e}")
            title = f"download_{uuid.uuid4().hex[:8]}"
            uploader = 'Unknown'

        output_template = str(self.download_dir / f"{title}.%(ext)s")

        cmd = [
            'yt-dlp',
            '-f', self.ytdlp_format,
            '--merge-output-format', 'mp4',
            '-o', output_template,
            '--no-warnings',
            '--progress',
            url
        ]

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=3600)
            if proc.returncode == 0:
                # Find the output file
                for f in self.download_dir.iterdir():
                    if f.stem == title and f.suffix in ('.mp4', '.mkv', '.webm'):
                        output_path = str(f)
                        self.logger.info(f"Video downloaded: {output_path}")

                        # Register in library
                        media_id = str(uuid.uuid4())[:12]
                        stat = f.stat()
                        item = {
                            'id': media_id,
                            'title': title,
                            'filename': f.name,
                            'file_path': output_path,
                            'file_size': stat.st_size,
                            'size_formatted': format_size(stat.st_size),
                            'created_at': datetime.now().isoformat(),
                            'modified_at': datetime.now().isoformat(),
                            'media_type': 'video',
                            'source_url': url,
                            'artist': uploader,
                        }
                        self.app_state.upsert_media(item)
                        return output_path

                self.logger.error("yt-dlp succeeded but output file not found")
                return None
            else:
                self.logger.error(f"yt-dlp failed: {proc.stderr}")
                return None
        except subprocess.TimeoutExpired:
            self.logger.error("yt-dlp timed out after 1 hour")
            return None
        except FileNotFoundError:
            self.logger.error("yt-dlp not installed. Install with: pip install yt-dlp")
            return None

    # ── Article Archiving ────────────────────────────────────────

    def archive_article(self, url: str, job_id: str = None) -> Optional[str]:
        """Download and archive a web article as HTML + optional PDF."""
        self.logger.info(f"Archiving article: {url}")

        try:
            import trafilatura
        except ImportError:
            self.logger.error("trafilatura not installed. Install with: pip install trafilatura")
            return None

        try:
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                self.logger.error(f"Could not fetch article: {url}")
                return None

            result = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=True,
                output_format='json'
            )
            if not result:
                self.logger.error(f"Could not extract article content: {url}")
                return None

            article_data = json.loads(result)
            title = sanitize_filename(article_data.get('title', 'article'))
            author = article_data.get('author', 'Unknown')
            date_str = article_data.get('date', datetime.now().strftime('%Y-%m-%d'))
            text = article_data.get('text', '')

            # Save as HTML
            safe_title = f"{date_str}_{title}"[:120]
            html_path = self.articles_dir / f"{safe_title}.html"

            html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{article_data.get('title', 'Article')}</title>
    <style>
        body {{ font-family: Georgia, serif; max-width: 720px; margin: 2rem auto;
               padding: 0 1rem; line-height: 1.7; color: #1a1a1a; }}
        h1 {{ font-size: 1.8rem; margin-bottom: 0.2rem; }}
        .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 2rem; }}
        a {{ color: #1a6fbf; }}
    </style>
</head>
<body>
    <h1>{article_data.get('title', 'Article')}</h1>
    <div class="meta">
        <span>By {author}</span> &middot; <span>{date_str}</span>
        &middot; <a href="{url}">Original</a>
    </div>
    <article>{text.replace(chr(10), '<br>')}</article>
</body>
</html>"""

            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            self.logger.info(f"Article archived: {html_path}")

            # Save metadata JSON
            meta_path = self.articles_dir / f"{safe_title}.json"
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'source_url': url,
                    'title': article_data.get('title'),
                    'author': author,
                    'date': date_str,
                    'hostname': article_data.get('hostname'),
                    'archived_at': datetime.now().isoformat(),
                }, f, indent=2)

            # Register in library
            media_id = str(uuid.uuid4())[:12]
            stat = html_path.stat()
            item = {
                'id': media_id,
                'title': article_data.get('title', title),
                'filename': html_path.name,
                'file_path': str(html_path),
                'file_size': stat.st_size,
                'size_formatted': format_size(stat.st_size),
                'created_at': datetime.now().isoformat(),
                'modified_at': datetime.now().isoformat(),
                'media_type': 'document',
                'source_url': url,
                'artist': author,
            }
            self.app_state.upsert_media(item)
            return str(html_path)

        except Exception as e:
            self.logger.error(f"Article archiving failed: {e}")
            return None

    # ── Podcast Feed Parsing & Download ──────────────────────────

    def parse_podcast_feed(self, feed_url: str) -> Optional[Dict[str, Any]]:
        """Parse a podcast RSS feed. Returns feed info dict."""
        try:
            import feedparser
        except ImportError:
            self.logger.error("feedparser not installed. Install with: pip install feedparser")
            return None

        try:
            feed = feedparser.parse(feed_url)
            if feed.bozo and not feed.entries:
                self.logger.error(f"Invalid feed: {feed_url}")
                return None

            info = {
                'title': feed.feed.get('title', ''),
                'author': feed.feed.get('author', feed.feed.get('itunes_author', '')),
                'description': feed.feed.get('summary', feed.feed.get('subtitle', '')),
                'artwork_url': None,
                'episodes': [],
            }

            # Get artwork
            if hasattr(feed.feed, 'image') and feed.feed.image:
                info['artwork_url'] = feed.feed.image.get('href')
            elif hasattr(feed.feed, 'itunes_image'):
                info['artwork_url'] = feed.feed.get('itunes_image', {}).get('href')

            # Parse episodes
            max_eps = self.config.get('podcasts', {}).get('max_episodes_per_feed', 50)
            for entry in feed.entries[:max_eps]:
                ep = {
                    'title': entry.get('title', 'Untitled'),
                    'audio_url': None,
                    'duration_seconds': None,
                    'published_at': None,
                    'description': entry.get('summary', ''),
                }

                # Find audio enclosure
                for link in entry.get('enclosures', []):
                    if 'audio' in link.get('type', ''):
                        ep['audio_url'] = link.get('href')
                        break
                # Fallback: check links
                if not ep['audio_url']:
                    for link in entry.get('links', []):
                        if 'audio' in link.get('type', ''):
                            ep['audio_url'] = link.get('href')
                            break

                # Duration
                duration_str = entry.get('itunes_duration', '')
                if duration_str:
                    ep['duration_seconds'] = self._parse_duration(duration_str)

                # Published date
                if entry.get('published_parsed'):
                    try:
                        from time import mktime
                        ep['published_at'] = datetime.fromtimestamp(
                            mktime(entry.published_parsed)).isoformat()
                    except Exception:
                        pass

                if ep['audio_url']:
                    info['episodes'].append(ep)

            return info

        except Exception as e:
            self.logger.error(f"Feed parsing failed: {e}")
            return None

    def subscribe_podcast(self, feed_url: str) -> Optional[str]:
        """Subscribe to a podcast — parse feed, store in DB, download artwork."""
        feed_info = self.parse_podcast_feed(feed_url)
        if not feed_info:
            return None

        pod_id = self.app_state.add_podcast(
            feed_url=feed_url,
            title=feed_info['title'],
            author=feed_info['author'],
            description=feed_info['description'],
            artwork_url=feed_info.get('artwork_url'),
        )
        if not pod_id:
            self.logger.warning(f"Podcast already subscribed: {feed_url}")
            return None

        # Download artwork
        if feed_info.get('artwork_url'):
            try:
                import requests
                resp = requests.get(feed_info['artwork_url'], timeout=15)
                if resp.status_code == 200:
                    art_path = self.podcast_dir / f"{pod_id}_artwork.jpg"
                    with open(art_path, 'wb') as f:
                        f.write(resp.content)
                    self.app_state.update_podcast(
                        pod_id, artwork_path=str(art_path))
            except Exception as e:
                self.logger.warning(f"Could not download podcast artwork: {e}")

        # Store episodes
        for ep in feed_info.get('episodes', []):
            self.app_state.add_episode(
                podcast_id=pod_id,
                title=ep['title'],
                audio_url=ep['audio_url'],
                duration_seconds=ep.get('duration_seconds'),
                published_at=ep.get('published_at'),
                description=ep.get('description', ''),
            )

        self.logger.info(
            f"Subscribed to podcast: {feed_info['title']} "
            f"({len(feed_info.get('episodes', []))} episodes)"
        )
        return pod_id

    def check_podcast_feeds(self):
        """Check all due podcast feeds for new episodes."""
        due = self.app_state.get_due_podcasts()
        if not due:
            return

        self.logger.info(f"Checking {len(due)} podcast feeds")

        for pod in due:
            try:
                feed_info = self.parse_podcast_feed(pod['feed_url'])
                if not feed_info:
                    continue

                new_count = 0
                for ep in feed_info.get('episodes', []):
                    if not self.app_state.episode_exists(
                            pod['id'], ep['audio_url']):
                        self.app_state.add_episode(
                            podcast_id=pod['id'],
                            title=ep['title'],
                            audio_url=ep['audio_url'],
                            duration_seconds=ep.get('duration_seconds'),
                            published_at=ep.get('published_at'),
                            description=ep.get('description', ''),
                        )
                        new_count += 1

                self.app_state.update_podcast(
                    pod['id'],
                    last_checked=datetime.now().isoformat(),
                    title=feed_info.get('title') or pod['title'],
                )

                if new_count:
                    self.logger.info(
                        f"Podcast '{pod['title']}': {new_count} new episodes")

                    # Auto-download if enabled
                    if self.config.get('podcasts', {}).get('auto_download', True):
                        episodes = self.app_state.get_episodes(pod['id'])
                        for ep in episodes:
                            if not ep.get('is_downloaded') and ep.get('audio_url'):
                                self.download_podcast_episode(
                                    pod['id'], ep['id'])
                                break  # Download one at a time

            except Exception as e:
                self.logger.error(f"Error checking feed {pod['feed_url']}: {e}")

    def download_podcast_episode(self, podcast_id: str,
                                  episode_id: str) -> Optional[str]:
        """Download a single podcast episode."""
        pod = self.app_state.get_podcast(podcast_id)
        episodes = self.app_state.get_episodes(podcast_id)
        episode = next((e for e in episodes if e['id'] == episode_id), None)

        if not pod or not episode or not episode.get('audio_url'):
            return None

        pod_title = sanitize_filename(pod.get('title', 'podcast'))
        ep_title = sanitize_filename(episode['title'])
        pod_dir = self.podcast_dir / pod_title
        pod_dir.mkdir(parents=True, exist_ok=True)

        ext = '.mp3'
        audio_url = episode['audio_url']
        if '.m4a' in audio_url:
            ext = '.m4a'
        elif '.ogg' in audio_url:
            ext = '.ogg'

        out_path = pod_dir / f"{ep_title}{ext}"

        try:
            import requests
            resp = requests.get(audio_url, stream=True, timeout=300)
            resp.raise_for_status()
            with open(out_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            self.app_state.update_episode(
                episode_id,
                file_path=str(out_path),
                is_downloaded=1
            )

            # Also add to main library
            stat = out_path.stat()
            media_id = str(uuid.uuid4())[:12]
            item = {
                'id': media_id,
                'title': episode['title'],
                'filename': out_path.name,
                'file_path': str(out_path),
                'file_size': stat.st_size,
                'size_formatted': format_size(stat.st_size),
                'created_at': datetime.now().isoformat(),
                'modified_at': datetime.now().isoformat(),
                'media_type': 'audio',
                'source_url': audio_url,
                'artist': pod.get('author', ''),
                'duration_seconds': episode.get('duration_seconds'),
            }
            self.app_state.upsert_media(item)

            self.logger.info(f"Episode downloaded: {out_path}")
            return str(out_path)

        except Exception as e:
            self.logger.error(f"Episode download failed: {e}")
            return None

    # ── Playlist Import ──────────────────────────────────────────

    def import_spotify_playlist(self, url: str,
                                 collection_name: str = None) -> Optional[int]:
        """Import a Spotify playlist as a collection (track listing only).
        Actual audio would require Spotify API + premium, so we just catalogue
        the track names/artists for manual matching or yt-dlp download.
        """
        self.logger.info(f"Importing playlist: {url}")

        # Use yt-dlp to get playlist info (works for YouTube playlists)
        try:
            cmd = [
                'yt-dlp', '--flat-playlist', '--print-json',
                '--no-warnings', url
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                self.logger.error(f"Cannot parse playlist: {result.stderr}")
                return None

            entries = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

            if not entries:
                self.logger.warning("Playlist is empty or could not be parsed")
                return None

            name = collection_name or entries[0].get('playlist_title', 'Imported Playlist')
            col_id = self.app_state.create_collection(
                name=name,
                description=f'Imported from {url}',
                collection_type='playlist'
            )

            media_ids = []
            for entry in entries:
                media_id = str(uuid.uuid4())[:12]
                item = {
                    'id': media_id,
                    'title': entry.get('title', 'Unknown'),
                    'filename': '',
                    'file_path': '',
                    'media_type': 'audio',
                    'source_url': entry.get('url', entry.get('webpage_url', '')),
                    'artist': entry.get('uploader', entry.get('channel', '')),
                    'duration_seconds': entry.get('duration'),
                }
                self.app_state.upsert_media(item)
                media_ids.append(media_id)

            self.app_state.update_collection(name, media_ids)
            self.logger.info(
                f"Playlist imported: {name} ({len(media_ids)} tracks)")
            return col_id

        except FileNotFoundError:
            self.logger.error("yt-dlp not installed")
            return None
        except Exception as e:
            self.logger.error(f"Playlist import failed: {e}")
            return None

    # ── Content Job Worker ───────────────────────────────────────

    def process_content_job(self, job: Dict[str, Any]) -> Optional[str]:
        """Process a content download/archive job. Returns output path or None."""
        job_type = job.get('job_type', 'download')
        url = job.get('source_path', '')
        job_id = job.get('id', '')

        if job_type == 'download':
            return self.download_video(url, job_id=job_id)
        elif job_type == 'article':
            return self.archive_article(url, job_id=job_id)
        elif job_type == 'playlist_import':
            result = self.import_spotify_playlist(url)
            return str(result) if result else None
        elif job_type == 'podcast':
            result = self.subscribe_podcast(url)
            return result
        else:
            self.logger.warning(f"Unknown job type: {job_type}")
            return None

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _parse_duration(duration_str: str) -> Optional[float]:
        """Parse iTunes duration string (HH:MM:SS or seconds) to float."""
        try:
            if ':' in duration_str:
                parts = duration_str.split(':')
                if len(parts) == 3:
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                elif len(parts) == 2:
                    return int(parts[0]) * 60 + float(parts[1])
            return float(duration_str)
        except (ValueError, TypeError):
            return None
