"""
Content downloader for various media sources.
Handles: YouTube/video URLs (yt-dlp), web articles (trafilatura),
         podcast feed parsing (feedparser), and Spotify/playlist import.
"""

import html as _html_mod
import json
import re
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen

from .app_state import AppState
from .config import load_config
from .utils import format_size, sanitize_filename, setup_logger


def _escape_html(text: str) -> str:
    """HTML-escape text to prevent XSS in archived articles."""
    return _html_mod.escape(text, quote=True)


class ContentDownloader:
    """Unified content downloader for all external media types."""

    def __init__(
        self,
        config: Dict[str, Any] = None,
        *,
        config_path: str = None,
        app_state: AppState = None,
    ):
        """Initialise the content downloader.

        Args:
            config: Pre-loaded configuration dict (preferred).
            config_path: Path to the JSON config file (backward compat).
            app_state: Optional pre-existing AppState instance.
                Created automatically if not provided.
        """
        self.config = config if config is not None else load_config(config_path or "config.json")
        self.logger = setup_logger("content_downloader", "content_downloader.log")
        self.app_state = app_state or AppState()

        dl_cfg = self.config.get("downloads", {})
        self.download_dir = Path(
            dl_cfg.get(
                "download_directory",
                str(Path(self.config["output"]["base_directory"]) / "downloads"),
            )
        )
        self.articles_dir = Path(
            dl_cfg.get(
                "articles_directory",
                str(Path(self.config["output"]["base_directory"]) / "articles"),
            )
        )
        self.books_dir = Path(
            dl_cfg.get(
                "books_directory", str(Path(self.config["output"]["base_directory"]) / "books")
            )
        )
        self.ytdlp_format = dl_cfg.get("ytdlp_format", "bestvideo[height<=1080]+bestaudio/best")

        pod_cfg = self.config.get("podcasts", {})
        self.podcast_dir = Path(
            pod_cfg.get(
                "download_directory",
                str(Path(self.config["output"]["base_directory"]) / "podcasts"),
            )
        )

        # Ensure directories exist
        for d in (self.download_dir, self.articles_dir, self.books_dir, self.podcast_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ── Video Downloads (yt-dlp) ─────────────────────────────────

    def download_video(self, url: str, job_id: str = None) -> Optional[str]:
        """Download a video via yt-dlp. Returns output file path or None."""
        self.logger.info("Downloading video: %s", url)

        # Use yt-dlp to extract info first for naming
        try:
            info_cmd = ["yt-dlp", "--no-download", "--print-json", "--no-warnings", url]
            result = subprocess.run(info_cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                info = json.loads(result.stdout.strip().split("\n")[0])
                title = sanitize_filename(info.get("title", "download"))
                uploader = info.get("uploader", "Unknown")
            else:
                title = f"download_{uuid.uuid4().hex[:8]}"
                uploader = "Unknown"
        except Exception as e:
            self.logger.warning("Could not extract video info: %s", e)
            title = f"download_{uuid.uuid4().hex[:8]}"
            uploader = "Unknown"

        output_template = str(self.download_dir / f"{title}.%(ext)s")

        cmd = [
            "yt-dlp",
            "-f",
            self.ytdlp_format,
            "--merge-output-format",
            "mp4",
            "-o",
            output_template,
            "--no-warnings",
            "--progress",
            url,
        ]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if proc.returncode == 0:
                # Find the output file
                for f in self.download_dir.iterdir():
                    if f.stem == title and f.suffix in (".mp4", ".mkv", ".webm"):
                        output_path = str(f)
                        self.logger.info("Video downloaded: %s", output_path)

                        # Register in library
                        media_id = uuid.uuid4().hex
                        stat = f.stat()
                        item = {
                            "id": media_id,
                            "title": title,
                            "filename": f.name,
                            "file_path": output_path,
                            "file_size": stat.st_size,
                            "size_formatted": format_size(stat.st_size),
                            "created_at": datetime.now().isoformat(),
                            "modified_at": datetime.now().isoformat(),
                            "media_type": "video",
                            "source_url": url,
                            "artist": uploader,
                        }
                        self.app_state.upsert_media(item)
                        return output_path

                self.logger.error("yt-dlp succeeded but output file not found")
                return None
            else:
                self.logger.error("yt-dlp failed: %s", proc.stderr)
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
        self.logger.info("Archiving article: %s", url)

        try:
            import trafilatura
        except ImportError:
            self.logger.error("trafilatura not installed. Install with: pip install trafilatura")
            return None

        try:
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                self.logger.error("Could not fetch article: %s", url)
                return None

            result = trafilatura.extract(
                downloaded, include_comments=False, include_tables=True, output_format="json"
            )
            if not result:
                self.logger.error("Could not extract article content: %s", url)
                return None

            article_data = json.loads(result)
            title = sanitize_filename(article_data.get("title", "article"))
            author = article_data.get("author", "Unknown")
            date_str = article_data.get("date", datetime.now().strftime("%Y-%m-%d"))
            text = article_data.get("text", "")

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
    <article>{_escape_html(text).replace(chr(10), '<br>')}</article>
</body>
</html>"""

            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            self.logger.info("Article archived: %s", html_path)

            # Save metadata JSON
            meta_path = self.articles_dir / f"{safe_title}.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "source_url": url,
                        "title": article_data.get("title"),
                        "author": author,
                        "date": date_str,
                        "hostname": article_data.get("hostname"),
                        "archived_at": datetime.now().isoformat(),
                    },
                    f,
                    indent=2,
                )

            # Register in library
            media_id = uuid.uuid4().hex
            stat = html_path.stat()
            item = {
                "id": media_id,
                "title": article_data.get("title", title),
                "filename": html_path.name,
                "file_path": str(html_path),
                "file_size": stat.st_size,
                "size_formatted": format_size(stat.st_size),
                "created_at": datetime.now().isoformat(),
                "modified_at": datetime.now().isoformat(),
                "media_type": "document",
                "source_url": url,
                "artist": author,
            }
            self.app_state.upsert_media(item)
            return str(html_path)

        except Exception as e:
            self.logger.error("Article archiving failed: %s", e)
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
                self.logger.error("Invalid feed: %s", feed_url)
                return None

            info = {
                "title": feed.feed.get("title", ""),
                "author": feed.feed.get("author", feed.feed.get("itunes_author", "")),
                "description": feed.feed.get("summary", feed.feed.get("subtitle", "")),
                "artwork_url": None,
                "episodes": [],
            }

            # Get artwork
            if hasattr(feed.feed, "image") and feed.feed.image:
                info["artwork_url"] = feed.feed.image.get("href")
            elif hasattr(feed.feed, "itunes_image"):
                info["artwork_url"] = feed.feed.get("itunes_image", {}).get("href")

            # Parse episodes
            max_eps = self.config.get("podcasts", {}).get("max_episodes_per_feed", 50)
            for entry in feed.entries[:max_eps]:
                ep = {
                    "title": entry.get("title", "Untitled"),
                    "audio_url": None,
                    "duration_seconds": None,
                    "published_at": None,
                    "description": entry.get("summary", ""),
                }

                # Find audio enclosure
                for link in entry.get("enclosures", []):
                    if "audio" in link.get("type", ""):
                        ep["audio_url"] = link.get("href")
                        break
                # Fallback: check links
                if not ep["audio_url"]:
                    for link in entry.get("links", []):
                        if "audio" in link.get("type", ""):
                            ep["audio_url"] = link.get("href")
                            break

                # Duration
                duration_str = entry.get("itunes_duration", "")
                if duration_str:
                    ep["duration_seconds"] = self._parse_duration(duration_str)

                # Published date
                if entry.get("published_parsed"):
                    try:
                        from time import mktime

                        ep["published_at"] = datetime.fromtimestamp(
                            mktime(entry.published_parsed)
                        ).isoformat()
                    except Exception:
                        pass

                if ep["audio_url"]:
                    info["episodes"].append(ep)

            return info

        except Exception as e:
            self.logger.error("Feed parsing failed: %s", e)
            return None

    def subscribe_podcast(self, feed_url: str) -> Optional[str]:
        """Subscribe to a podcast — parse feed, store in DB, download artwork."""
        feed_info = self.parse_podcast_feed(feed_url)
        if not feed_info:
            return None

        pod_id = self.app_state.add_podcast(
            feed_url=feed_url,
            title=feed_info["title"],
            author=feed_info["author"],
            description=feed_info["description"],
            artwork_url=feed_info.get("artwork_url"),
        )
        if not pod_id:
            self.logger.warning("Podcast already subscribed: %s", feed_url)
            return None

        # Download artwork
        if feed_info.get("artwork_url"):
            try:
                import requests

                resp = requests.get(feed_info["artwork_url"], timeout=15)
                if resp.status_code == 200:
                    art_path = self.podcast_dir / f"{pod_id}_artwork.jpg"
                    with open(art_path, "wb") as f:
                        f.write(resp.content)
                    self.app_state.update_podcast(pod_id, artwork_path=str(art_path))
            except Exception as e:
                self.logger.warning("Could not download podcast artwork: %s", e)

        # Store episodes
        for ep in feed_info.get("episodes", []):
            self.app_state.add_episode(
                podcast_id=pod_id,
                title=ep["title"],
                audio_url=ep["audio_url"],
                duration_seconds=ep.get("duration_seconds"),
                published_at=ep.get("published_at"),
                description=ep.get("description", ""),
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

        self.logger.info("Checking %s podcast feeds", len(due))

        for pod in due:
            try:
                feed_info = self.parse_podcast_feed(pod["feed_url"])
                if not feed_info:
                    continue

                new_count = 0
                for ep in feed_info.get("episodes", []):
                    if not self.app_state.episode_exists(pod["id"], ep["audio_url"]):
                        self.app_state.add_episode(
                            podcast_id=pod["id"],
                            title=ep["title"],
                            audio_url=ep["audio_url"],
                            duration_seconds=ep.get("duration_seconds"),
                            published_at=ep.get("published_at"),
                            description=ep.get("description", ""),
                        )
                        new_count += 1

                self.app_state.update_podcast(
                    pod["id"],
                    last_checked=datetime.now().isoformat(),
                    title=feed_info.get("title") or pod["title"],
                )

                if new_count:
                    self.logger.info("Podcast '%s': %s new episodes", pod["title"], new_count)

                    # Auto-download if enabled
                    if self.config.get("podcasts", {}).get("auto_download", True):
                        episodes = self.app_state.get_episodes(pod["id"])
                        for ep in episodes:
                            if not ep.get("is_downloaded") and ep.get("audio_url"):
                                self.download_podcast_episode(pod["id"], ep["id"])
                                break  # Download one at a time

            except Exception as e:
                self.logger.error("Error checking feed %s: %s", pod["feed_url"], e)

    def download_podcast_episode(self, podcast_id: str, episode_id: str) -> Optional[str]:
        """Download a single podcast episode."""
        pod = self.app_state.get_podcast(podcast_id)
        episodes = self.app_state.get_episodes(podcast_id)
        episode = next((e for e in episodes if e["id"] == episode_id), None)

        if not pod or not episode or not episode.get("audio_url"):
            return None

        pod_title = sanitize_filename(pod.get("title", "podcast"))
        ep_title = sanitize_filename(episode["title"])
        pod_dir = self.podcast_dir / pod_title
        pod_dir.mkdir(parents=True, exist_ok=True)

        ext = ".mp3"
        audio_url = episode["audio_url"]
        if ".m4a" in audio_url:
            ext = ".m4a"
        elif ".ogg" in audio_url:
            ext = ".ogg"

        out_path = pod_dir / f"{ep_title}{ext}"

        try:
            import requests

            resp = requests.get(audio_url, stream=True, timeout=300)
            resp.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            self.app_state.update_episode(episode_id, file_path=str(out_path), is_downloaded=1)

            # Also add to main library
            stat = out_path.stat()
            media_id = uuid.uuid4().hex
            item = {
                "id": media_id,
                "title": episode["title"],
                "filename": out_path.name,
                "file_path": str(out_path),
                "file_size": stat.st_size,
                "size_formatted": format_size(stat.st_size),
                "created_at": datetime.now().isoformat(),
                "modified_at": datetime.now().isoformat(),
                "media_type": "audio",
                "source_url": audio_url,
                "artist": pod.get("author", ""),
                "duration_seconds": episode.get("duration_seconds"),
            }
            self.app_state.upsert_media(item)

            self.logger.info("Episode downloaded: %s", out_path)
            return str(out_path)

        except Exception as e:
            self.logger.error("Episode download failed: %s", e)
            return None

    # ── Playlist Import ──────────────────────────────────────────

    def import_spotify_playlist(self, url: str, collection_name: str = None) -> Optional[int]:
        """Import a Spotify playlist by scraping the public embed page.
        Stores track metadata in playlist_tracks; no audio downloaded.
        Matches tracks against local library for available playback.
        """
        self.logger.info("Importing Spotify playlist: %s", url)

        # Extract playlist ID from various Spotify URL formats
        match = re.search(r"playlist[/:]([A-Za-z0-9]+)", url)
        if not match:
            self.logger.error("Could not extract playlist ID from URL: %s", url)
            return None
        playlist_id = match.group(1)

        try:
            tracks, playlist_title = self._fetch_spotify_embed(playlist_id)
        except Exception as e:
            self.logger.error("Failed to fetch Spotify playlist: %s", e)
            return None

        if not tracks:
            self.logger.warning("Playlist is empty or could not be parsed")
            return None

        name = collection_name or playlist_title or "Imported Playlist"
        col_id = self.app_state.create_collection(
            name=name, description=f"Imported from Spotify: {url}", collection_type="playlist"
        )

        self.app_state.add_playlist_tracks(col_id, tracks)
        self.app_state.match_playlist_tracks(col_id)

        self.logger.info("Spotify playlist imported: %s (%s tracks)", name, len(tracks))
        return col_id

    def _fetch_spotify_embed(self, playlist_id: str):
        """Fetch playlist tracks from Spotify's public embed page.
        Returns (tracks_list, playlist_title).
        """
        # Try the Spotify embed endpoint which returns JSON data
        embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36",
        }
        req = Request(embed_url, headers=headers)
        response = urlopen(req, timeout=30)
        html = response.read().decode("utf-8", errors="replace")

        tracks = []
        playlist_title = None

        # Extract the __NEXT_DATA__ or resource JSON embedded in the page
        # Spotify embed pages include a <script id="__NEXT_DATA__"> tag
        next_data_match = re.search(
            r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
        )
        if next_data_match:
            try:
                data = json.loads(next_data_match.group(1))
                # Navigate the JSON structure for track data
                tracks, playlist_title = self._parse_next_data(data)
                if tracks:
                    return tracks, playlist_title
            except (json.JSONDecodeError, KeyError) as e:
                self.logger.debug("__NEXT_DATA__ parse failed: %s", e)

        # Fallback: try to find any JSON with track info
        json_blocks = re.findall(
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', html, re.DOTALL
        )
        for block in json_blocks:
            try:
                data = json.loads(block)
                tracks, playlist_title = self._parse_next_data(data)
                if tracks:
                    return tracks, playlist_title
            except (json.JSONDecodeError, KeyError):
                continue

        # Last fallback: try the oEmbed API for at least the title
        try:
            oembed_url = (
                f"https://open.spotify.com/oembed?url="
                f"https://open.spotify.com/playlist/{playlist_id}"
            )
            req2 = Request(oembed_url, headers=headers)
            resp2 = urlopen(req2, timeout=15)
            oembed = json.loads(resp2.read().decode("utf-8"))
            playlist_title = oembed.get("title", playlist_title)
        except Exception:
            pass

        # Try scraping the regular playlist page for meta tags
        if not tracks:
            tracks, playlist_title = self._scrape_spotify_page(playlist_id, headers)

        return tracks, playlist_title

    def _parse_next_data(self, data):
        """Parse Spotify __NEXT_DATA__ JSON for track listings."""
        tracks = []
        title = None

        # Try the known embed structure first:
        # props.pageProps.state.data.entity.trackList[]
        try:
            entity = data["props"]["pageProps"]["state"]["data"]["entity"]
            title = entity.get("name") or entity.get("title")
            # Get cover art for playlist-level artwork
            playlist_art = ""
            cover = entity.get("coverArt", {})
            if isinstance(cover, dict):
                sources = cover.get("sources", [])
                if sources and isinstance(sources[0], dict):
                    playlist_art = sources[0].get("url", "")

            for t in entity.get("trackList", []):
                track_info = self._extract_track_info(t, playlist_art)
                if track_info:
                    tracks.append(track_info)
            if tracks:
                return tracks, title
        except (KeyError, TypeError):
            pass

        # Fallback: walk the JSON tree looking for track-like objects
        def walk(obj, depth=0):
            nonlocal title
            if depth > 15:
                return
            if isinstance(obj, dict):
                if "track" in obj and isinstance(obj["track"], dict):
                    t = obj["track"]
                    track_info = self._extract_track_info(t)
                    if track_info:
                        tracks.append(track_info)
                elif obj.get("type") == "track" and (obj.get("name") or obj.get("title")):
                    track_info = self._extract_track_info(obj)
                    if track_info:
                        tracks.append(track_info)
                elif obj.get("entityType") == "track" and obj.get("title"):
                    track_info = self._extract_track_info(obj)
                    if track_info:
                        tracks.append(track_info)
                if obj.get("type") == "playlist" or obj.get("__typename") == "Playlist":
                    title = title or obj.get("name")
                if "name" in obj and "trackList" in obj:
                    title = title or obj.get("name")
                for v in obj.values():
                    walk(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item, depth + 1)

        walk(data)
        return tracks, title

    def _extract_track_info(self, t, fallback_artwork=""):
        """Extract track info dict from a Spotify track JSON object."""
        name = t.get("name") or t.get("title")
        if not name:
            return None

        # Artist: could be in 'artists' list or 'subtitle' (embed format)
        artists = t.get("artists", [])
        if isinstance(artists, list) and artists:
            artist_names = [a.get("name", "") for a in artists if isinstance(a, dict)]
            artist = ", ".join(filter(None, artist_names))
        else:
            artist = t.get("subtitle", "") or str(artists) if artists else ""

        album_obj = t.get("album", {})
        album = album_obj.get("name", "") if isinstance(album_obj, dict) else ""

        # Duration: 'duration_ms' or 'duration' (embed uses plain ms int)
        duration = t.get("duration_ms") or t.get("duration", 0)
        if isinstance(duration, dict):
            duration = duration.get("totalMilliseconds", 0)
        # Extract artwork URL from album images
        artwork_url = ""
        if isinstance(album_obj, dict):
            images = album_obj.get("images", album_obj.get("coverArt", {}).get("sources", []))
            if isinstance(images, list) and images:
                img = images[0]
                artwork_url = img.get("url", "") if isinstance(img, dict) else ""
        # Cover art from coverArt directly on track
        if not artwork_url:
            cover = t.get("coverArt", {})
            if isinstance(cover, dict):
                sources = cover.get("sources", [])
                if sources and isinstance(sources[0], dict):
                    artwork_url = sources[0].get("url", "")
        # Use playlist-level artwork as fallback
        if not artwork_url and fallback_artwork:
            artwork_url = fallback_artwork
        return {
            "title": name,
            "artist": artist,
            "album": album,
            "duration_ms": int(duration) if duration else 0,
            "artwork_url": artwork_url,
            "spotify_uri": t.get("uri", ""),
            "isrc": (t.get("externalIds", {}) or {}).get("isrc", ""),
        }

    def _scrape_spotify_page(self, playlist_id, headers):
        """Fallback: scrape the regular Spotify playlist page for metadata."""
        tracks = []
        title = None
        try:
            page_url = f"https://open.spotify.com/playlist/{playlist_id}"
            req = Request(page_url, headers=headers)
            resp = urlopen(req, timeout=30)
            html = resp.read().decode("utf-8", errors="replace")

            # Extract title from <title> or og:title
            title_match = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
            if title_match:
                title = title_match.group(1)

            # Try to parse Spotify's structured data
            ld_matches = re.findall(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL
            )
            for ld in ld_matches:
                try:
                    data = json.loads(ld)
                    if isinstance(data, dict) and "track" in data:
                        for t in data["track"]:
                            if isinstance(t, dict):
                                tracks.append(
                                    {
                                        "title": t.get("name", "Unknown"),
                                        "artist": (t.get("byArtist", {}) or {}).get("name", ""),
                                        "album": (t.get("inAlbum", {}) or {}).get("name", ""),
                                        "duration_ms": 0,
                                        "artwork_url": "",
                                        "spotify_uri": "",
                                        "isrc": "",
                                    }
                                )
                except json.JSONDecodeError:
                    continue

            # If still no tracks, try a simpler regex scrape of meta tags
            if not tracks:
                # Spotify pages include music:song tags
                song_titles = re.findall(
                    r'<meta\s+name="music:song"\s+content="[^"]*?/track/[^"]*"' r"[^>]*/?>", html
                )
                if song_titles:
                    self.logger.info(
                        f"Found {len(song_titles)} song references via meta tags"
                        " but cannot get full details without API access"
                    )
        except Exception as e:
            self.logger.debug("Scrape fallback failed: %s", e)

        return tracks, title

    # ── Content Job Worker ───────────────────────────────────────

    def process_content_job(self, job: Dict[str, Any]) -> Optional[str]:
        """Process a content download/archive job. Returns output path or None."""
        job_type = job.get("job_type", "download")
        url = job.get("source_path", "")
        job_id = job.get("id", "")

        if job_type == "download":
            return self.download_video(url, job_id=job_id)
        elif job_type == "article":
            return self.archive_article(url, job_id=job_id)
        elif job_type == "playlist_import":
            col_name = job.get("title", None)
            result = self.import_spotify_playlist(url, collection_name=col_name)
            return str(result) if result else None
        elif job_type == "podcast":
            result = self.subscribe_podcast(url)
            return result
        elif job_type == "identify":
            # Handled by content_worker directly — not by ContentDownloader
            self.logger.debug("Identify job %s delegated to content_worker", job_id)
            return None
        else:
            self.logger.warning("Unknown job type: %s", job_type)
            return None

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _parse_duration(duration_str: str) -> Optional[float]:
        """Parse iTunes duration string (HH:MM:SS or seconds) to float."""
        try:
            if ":" in duration_str:
                parts = duration_str.split(":")
                if len(parts) == 3:
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                elif len(parts) == 2:
                    return int(parts[0]) * 60 + float(parts[1])
            return float(duration_str)
        except (ValueError, TypeError):
            return None
