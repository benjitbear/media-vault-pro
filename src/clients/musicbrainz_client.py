"""MusicBrainz, AcoustID, and CoverArtArchive client."""

import json
import subprocess
import time
from typing import Any, Dict, List, Optional

from ..constants import (
    APP_USER_AGENT,
    MB_DURATION_TOLERANCE_SECONDS,
    MB_RATE_LIMIT_SECONDS,
    MIN_ACOUSTID_SCORE,
)
from ..utils import setup_logger


class MusicBrainzClient:
    """Audio CD identification via AcoustID fingerprinting and MusicBrainz lookup."""

    def __init__(self, acoustid_api_key: Optional[str] = None) -> None:
        """Initialise the MusicBrainz client.

        Args:
            acoustid_api_key: AcoustID API key for audio fingerprinting.
                If ``None``, fingerprint lookups fall back to name-based
                MusicBrainz search.
        """
        self.acoustid_api_key = acoustid_api_key
        self.logger = setup_logger("musicbrainz_client", "metadata.log")
        self._last_mb_request = 0.0

    # ── Rate-limited request helper ──────────────────────────────

    def _mb_request(
        self, url: str, params: Optional[Dict[str, Any]] = None, retries: int = 3
    ) -> Optional[Any]:
        """
        Make a GET request to a MusicBrainz / CoverArtArchive endpoint
        with automatic rate-limit compliance (1 req/sec) and retry
        with exponential back-off on transient failures.

        Returns the ``requests.Response`` object, or None on total failure.
        """
        import requests

        headers = {"User-Agent": APP_USER_AGENT}

        for attempt in range(1, retries + 1):
            elapsed = time.time() - self._last_mb_request
            if elapsed < MB_RATE_LIMIT_SECONDS:
                time.sleep(MB_RATE_LIMIT_SECONDS - elapsed)

            try:
                self._last_mb_request = time.time()
                resp = requests.get(url, params=params, headers=headers, timeout=15)
                resp.raise_for_status()
                return resp
            except (requests.exceptions.ConnectionError, ConnectionResetError) as e:
                wait = 2**attempt
                self.logger.warning(
                    f"MB request {url} attempt {attempt}/{retries} "
                    f"failed ({e}), retrying in {wait}s"
                )
                time.sleep(wait)
            except requests.exceptions.HTTPError as e:
                if resp.status_code == 503:
                    wait = 2**attempt
                    self.logger.warning("MB 503 on %s, retrying in %ss", url, wait)
                    time.sleep(wait)
                else:
                    self.logger.error("MB HTTP error: %s", e)
                    return None
            except Exception as e:
                self.logger.error("MB request error: %s", e)
                return None

        self.logger.error("MB request failed after %s retries: %s", retries, url)
        return None

    # ── AcoustID / Chromaprint ───────────────────────────────────

    def fingerprint_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Generate an audio fingerprint using Chromaprint (fpcalc).

        Returns:
            Dict with 'duration' (int seconds) and 'fingerprint' (str),
            or None on failure.
        """
        self.logger.info("Generating audio fingerprint for: %s", file_path)

        try:
            import acoustid

            duration, fingerprint = acoustid.fingerprint_file(file_path)
            self.logger.info(
                f"Fingerprint generated (duration={duration}s, " f"fp length={len(fingerprint)})"
            )
            return {"duration": int(duration), "fingerprint": fingerprint}
        except ImportError:
            self.logger.debug("pyacoustid not installed, trying fpcalc CLI")
        except Exception as e:
            self.logger.warning("pyacoustid fingerprint failed: %s", e)

        try:
            result = subprocess.run(
                ["fpcalc", "-json", file_path],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)
            self.logger.info("Fingerprint via fpcalc (duration=%ss)", data.get("duration"))
            return {
                "duration": int(data["duration"]),
                "fingerprint": data["fingerprint"],
            }
        except FileNotFoundError:
            self.logger.warning(
                "fpcalc not found — install Chromaprint or pyacoustid " "for audio fingerprinting"
            )
        except Exception as e:
            self.logger.warning("fpcalc fingerprint failed: %s", e)

        return None

    def lookup_acoustid(
        self,
        file_path: str,
        disc_hints: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Identify an audio file via the AcoustID web service.

        Returns:
            Dict with keys: musicbrainz_recording_id, title, artist,
            musicbrainz_release_id, album — or None on failure.
        """
        if not self.acoustid_api_key:
            self.logger.warning("ACOUSTID_API_KEY not configured")
            return None

        fp_data = self.fingerprint_file(file_path)
        if not fp_data:
            return None

        return self.lookup_acoustid_from_fp(fp_data, disc_hints=disc_hints)

    def lookup_acoustid_from_fp(
        self,
        fp_data: Dict[str, Any],
        disc_hints: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Perform the AcoustID web lookup given pre-computed fingerprint data.

        Args:
            fp_data: Dict with 'duration' (int) and 'fingerprint' (str).
            disc_hints: Optional disc metadata for filtering.

        Returns:
            Dict with recording/release info or None.
        """
        self.logger.info("Looking up fingerprint on AcoustID…")

        try:
            import requests

            response = requests.post(
                "https://api.acoustid.org/v2/lookup",
                data={
                    "client": self.acoustid_api_key,
                    "duration": fp_data["duration"],
                    "fingerprint": fp_data["fingerprint"],
                    "meta": "recordings releasegroups",
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "ok":
                self.logger.warning("AcoustID error: %s", data)
                return None

            results = data.get("results", [])
            if not results:
                self.logger.info("No AcoustID matches")
                return None

            for result in sorted(results, key=lambda r: r.get("score", 0), reverse=True):
                score = result.get("score", 0)
                if score < MIN_ACOUSTID_SCORE:
                    self.logger.info(
                        f"Skipping AcoustID result with low score {score:.2f} "
                        f"(threshold {MIN_ACOUSTID_SCORE})"
                    )
                    continue

                for recording in result.get("recordings", []):
                    rec_id = recording.get("id")
                    rec_title = recording.get("title")
                    artists = recording.get("artists", [])
                    artist_name = artists[0].get("name") if artists else None

                    release_id = None
                    album_title = None
                    for rg in recording.get("releasegroups", []):
                        releases = rg.get("releases", [])
                        if releases:
                            release_id = releases[0].get("id")
                            album_title = rg.get("title")
                            break

                    if rec_id:
                        self.logger.info(
                            f"AcoustID match: '{rec_title}' by {artist_name} "
                            f"(score={score:.2f})"
                        )
                        return {
                            "musicbrainz_recording_id": rec_id,
                            "title": rec_title,
                            "artist": artist_name,
                            "musicbrainz_release_id": release_id,
                            "album": album_title,
                            "acoustid_score": score,
                        }

            self.logger.info("AcoustID results had no usable recordings")
            return None

        except Exception as e:
            self.logger.error("AcoustID lookup error: %s", e)
            return None

    # ── MusicBrainz release lookup ───────────────────────────────

    def lookup_musicbrainz_by_release_id(self, release_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch full album metadata + cover art from MusicBrainz using a
        known release MBID (typically obtained via AcoustID).

        Returns:
            Album metadata dict or None.
        """
        self.logger.info("Fetching MusicBrainz release: %s", release_id)
        try:
            detail_resp = self._mb_request(
                f"https://musicbrainz.org/ws/2/release/{release_id}",
                params={
                    "inc": "recordings+artist-credits+labels",
                    "fmt": "json",
                },
            )
            if not detail_resp:
                return None
            detail = detail_resp.json()

            artists = [
                a["artist"]["name"]
                for a in detail.get("artist-credit", [])
                if isinstance(a, dict) and "artist" in a
            ]

            tracks: List[Dict[str, Any]] = []
            for medium in detail.get("media", []):
                for t in medium.get("tracks", []):
                    tracks.append(
                        {
                            "number": t.get("number"),
                            "title": t.get("title"),
                            "duration_ms": t.get("length"),
                        }
                    )

            metadata: Dict[str, Any] = {
                "title": detail.get("title"),
                "artist": ", ".join(artists) if artists else None,
                "year": (detail.get("date") or "")[:4] or None,
                "label": None,
                "track_count": len(tracks),
                "tracks": tracks,
                "musicbrainz_id": release_id,
                "media_type": "audio",
                "identified_by": "acoustid_fingerprint",
            }

            label_info = detail.get("label-info", [])
            if label_info and isinstance(label_info[0], dict):
                lbl = label_info[0].get("label", {})
                metadata["label"] = lbl.get("name") if isinstance(lbl, dict) else None

            # Cover art
            try:
                cover_resp = self._mb_request(
                    f"https://coverartarchive.org/release/{release_id}",
                    retries=2,
                )
                if cover_resp and cover_resp.status_code == 200:
                    images = cover_resp.json().get("images", [])
                    if images:
                        metadata["cover_art_url"] = images[0].get("image")
                        for img in images:
                            if "Front" in img.get("types", []):
                                metadata["cover_art_url"] = img.get("image")
                                break
            except Exception as e:
                self.logger.debug("Cover art fetch failed for release: %s", e)

            self.logger.info("MusicBrainz release: %s by %s", metadata["title"], metadata["artist"])
            return metadata

        except Exception as e:
            self.logger.error("MusicBrainz release lookup error: %s", e)
            return None

    def validate_release_durations(
        self,
        mb_data: Optional[Dict[str, Any]],
        disc_hints: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Validate a MusicBrainz release against the disc's per-track
        durations.  Returns the release data unchanged if it passes, or
        None if the durations diverge too much (likely a wrong match).
        """
        if not mb_data:
            return None

        disc_hints = disc_hints or {}
        track_durations = disc_hints.get("track_durations", [])
        if not track_durations or not mb_data.get("tracks"):
            return mb_data

        mb_durations_ms = [
            t.get("duration_ms") for t in mb_data["tracks"] if t.get("duration_ms") is not None
        ]
        if not mb_durations_ms or len(mb_durations_ms) != len(track_durations):
            if mb_durations_ms and len(mb_durations_ms) != len(track_durations):
                self.logger.warning(
                    f"Track count mismatch: disc has {len(track_durations)} "
                    f"tracks, release '{mb_data.get('title')}' has "
                    f"{len(mb_durations_ms)} — rejecting"
                )
                return None
            return mb_data

        total_diff = sum(
            abs(disc_s * 1000 - mb_ms) for disc_s, mb_ms in zip(track_durations, mb_durations_ms)
        )
        avg_diff_s = (total_diff / len(mb_durations_ms)) / 1000
        self.logger.info(
            f"Release duration check: avg diff = {avg_diff_s:.1f}s/track "
            f"for '{mb_data.get('title')}'"
        )
        if avg_diff_s > MB_DURATION_TOLERANCE_SECONDS:
            self.logger.warning(
                f"Duration mismatch ({avg_diff_s:.1f}s avg) — rejecting "
                f"release '{mb_data.get('title')}'"
            )
            return None

        return mb_data

    def release_from_recording(
        self,
        recording_id: str,
        disc_hints: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Given a MusicBrainz recording ID (from AcoustID), find the best
        matching release (album) and return full album metadata.
        """
        disc_hints = disc_hints or {}
        target_tracks = disc_hints.get("track_count", 0)

        self.logger.info("Looking up releases for recording %s", recording_id)
        try:
            resp = self._mb_request(
                f"https://musicbrainz.org/ws/2/recording/{recording_id}",
                params={
                    "inc": "releases",
                    "fmt": "json",
                },
            )
            if not resp:
                return None
            releases = resp.json().get("releases", [])

            if not releases:
                self.logger.info("Recording has no linked releases")
                return None

            track_durations = disc_hints.get("track_durations", [])
            best = None
            best_score = -1

            for rel in releases:
                score = 0
                media_list = rel.get("media", [])
                if not media_list:
                    continue
                tc = media_list[0].get("track-count", 0)

                if target_tracks and tc == target_tracks:
                    score += 10
                elif target_tracks and tc != target_tracks:
                    score -= 20

                rg_type = rel.get("release-group", {}).get("primary-type", "").lower()
                if rg_type == "album":
                    score += 2
                elif rg_type in ("compilation", "single"):
                    score -= 5

                if score > best_score:
                    best_score = score
                    best = rel

            if best is None:
                best = releases[0]

            self.logger.info(
                f"Selected release '{best.get('title')}' " f"(id={best['id']}, score={best_score})"
            )

            mb_data = self.lookup_musicbrainz_by_release_id(best["id"])

            # Duration validation
            if mb_data and track_durations and mb_data.get("tracks"):
                mb_durations_ms = [
                    t.get("duration_ms")
                    for t in mb_data["tracks"]
                    if t.get("duration_ms") is not None
                ]
                if mb_durations_ms and len(mb_durations_ms) == len(track_durations):
                    total_diff = sum(
                        abs(disc_s * 1000 - mb_ms)
                        for disc_s, mb_ms in zip(track_durations, mb_durations_ms)
                    )
                    avg_diff_s = (total_diff / len(mb_durations_ms)) / 1000
                    self.logger.info(
                        f"Release duration check: avg diff = " f"{avg_diff_s:.1f}s/track"
                    )
                    if avg_diff_s > MB_DURATION_TOLERANCE_SECONDS:
                        self.logger.warning(
                            f"Duration mismatch ({avg_diff_s:.1f}s avg) — "
                            f"rejecting release '{mb_data.get('title')}'"
                        )
                        return None

            return mb_data

        except Exception as e:
            self.logger.error("Error looking up releases for recording %s: %s", recording_id, e)
            return None

    # ── MusicBrainz release search (name-based) ──────────────────

    def search_musicbrainz(
        self, album_name: str, disc_hints: Optional[Dict[str, Any]] = None, clean_title_fn=None
    ) -> Optional[Dict[str, Any]]:
        """
        Search MusicBrainz for album metadata (audio CDs).

        Args:
            album_name: Album title guess
            disc_hints: Audio CD info — track_count, total_duration_seconds,
                        track_durations (list of per-track seconds)
            clean_title_fn: Optional callable to clean title before search.
        """
        disc_hints = disc_hints or {}
        clean_name = clean_title_fn(album_name) if clean_title_fn else album_name
        self.logger.info("Searching MusicBrainz for: '%s'", clean_name)

        generic_titles = {
            "audio",
            "cd",
            "disc",
            "disk",
            "untitled",
            "unknown",
            "track",
            "album",
            "music",
            "my",
            "test",
            "new",
        }
        if clean_name.lower() in generic_titles or len(clean_name) <= 2:
            self.logger.warning(
                f"Title '{clean_name}' is too generic for reliable MusicBrainz "
                f"search — skipping name-based lookup (use AcoustID instead)"
            )
            return None

        try:
            params = {
                "query": f'release:"{clean_name}"',
                "fmt": "json",
                "limit": 25,
            }

            response = self._mb_request(
                "https://musicbrainz.org/ws/2/release",
                params=params,
            )
            if not response:
                return None
            releases = response.json().get("releases", [])

            if not releases:
                self.logger.info("No MusicBrainz results for: %s", clean_name)
                return None

            target_tracks = disc_hints.get("track_count", 0)
            track_durations = disc_hints.get("track_durations", [])

            best = None
            best_score = -1

            for rel in releases:
                score = 0
                media_list = rel.get("media", [])
                if not media_list:
                    continue
                mb_tracks = media_list[0].get("track-count", 0)

                if target_tracks and mb_tracks == target_tracks:
                    score += 1
                elif target_tracks and mb_tracks != target_tracks:
                    continue

                if rel.get("title", "").lower() == clean_name.lower():
                    score += 1

                if score > best_score:
                    best_score = score
                    best = rel

            if best is None:
                best = releases[0]

            release_id = best["id"]
            detail_resp = self._mb_request(
                f"https://musicbrainz.org/ws/2/release/{release_id}",
                params={"inc": "recordings+artist-credits+labels", "fmt": "json"},
            )
            if not detail_resp:
                return None
            detail = detail_resp.json()

            # Duration validation
            if track_durations and target_tracks:
                mb_durations_ms: List[int] = []
                for medium in detail.get("media", []):
                    for t in medium.get("tracks", []):
                        length = t.get("length")
                        if length is not None:
                            mb_durations_ms.append(length)
                if mb_durations_ms and len(mb_durations_ms) == len(track_durations):
                    total_diff = sum(
                        abs(disc_s * 1000 - mb_ms)
                        for disc_s, mb_ms in zip(track_durations, mb_durations_ms)
                    )
                    avg_diff_s = (total_diff / len(mb_durations_ms)) / 1000
                    self.logger.info(
                        f"MusicBrainz duration check: avg diff = {avg_diff_s:.1f}s/track"
                    )
                    if avg_diff_s > MB_DURATION_TOLERANCE_SECONDS:
                        self.logger.warning(
                            f"Duration mismatch too large ({avg_diff_s:.1f}s avg) "
                            f"— rejecting MusicBrainz match '{detail.get('title')}'"
                        )
                        return None

            # Build metadata
            artists = [
                a["artist"]["name"]
                for a in detail.get("artist-credit", [])
                if isinstance(a, dict) and "artist" in a
            ]

            tracks: List[Dict[str, Any]] = []
            for medium in detail.get("media", []):
                for t in medium.get("tracks", []):
                    tracks.append(
                        {
                            "number": t.get("number"),
                            "title": t.get("title"),
                            "duration_ms": t.get("length"),
                        }
                    )

            metadata: Dict[str, Any] = {
                "title": detail.get("title", best.get("title")),
                "artist": ", ".join(artists) if artists else None,
                "year": (detail.get("date") or "")[:4] or None,
                "label": None,
                "track_count": len(tracks),
                "tracks": tracks,
                "musicbrainz_id": release_id,
                "media_type": "audio",
            }

            label_info = detail.get("label-info", [])
            if label_info and isinstance(label_info[0], dict):
                lbl = label_info[0].get("label", {})
                metadata["label"] = lbl.get("name") if isinstance(lbl, dict) else None

            # Cover art
            try:
                cover_resp = self._mb_request(
                    f"https://coverartarchive.org/release/{release_id}",
                    retries=2,
                )
                if cover_resp and cover_resp.status_code == 200:
                    images = cover_resp.json().get("images", [])
                    if images:
                        metadata["cover_art_url"] = images[0].get("image")
                        for img in images:
                            if "Front" in img.get("types", []):
                                metadata["cover_art_url"] = img.get("image")
                                break
            except Exception as e:
                self.logger.debug("Cover art fetch failed for release: %s", e)

            self.logger.info("MusicBrainz match: %s by %s", metadata["title"], metadata["artist"])
            return metadata

        except Exception as e:
            self.logger.error("MusicBrainz search error: %s", e)
            return None

    # ── Cover art download ───────────────────────────────────────

    def download_cover_art(self, url: str, output_path: str) -> bool:
        """
        Download album cover art from a URL.

        Args:
            url: Cover art URL
            output_path: Local file path to save

        Returns:
            True if successful.
        """
        if not url:
            return False
        try:
            from io import BytesIO

            import requests
            from PIL import Image

            response = requests.get(url, timeout=15)
            response.raise_for_status()

            image = Image.open(BytesIO(response.content))
            image.save(output_path)
            self.logger.info("Downloaded cover art to: %s", output_path)
            return True
        except Exception as e:
            self.logger.error("Error downloading cover art: %s", e)
            return False
