"""
Metadata extraction and enrichment for media files.

This module is a thin orchestrator that delegates to specialised client
modules under ``src/clients/``:

- :class:`~src.clients.mediainfo_client.MediaInfoClient`
- :class:`~src.clients.tmdb_client.TMDBClient`
- :class:`~src.clients.musicbrainz_client.MusicBrainzClient`

Existing callers that import ``MetadataExtractor`` keep working unchanged.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from dotenv import load_dotenv

from .clients import MediaInfoClient, TMDBClient, MusicBrainzClient
from .constants import AUDIO_EXTENSIONS
from .config import load_config
from .utils import setup_logger, sanitize_filename, natural_sort_key

# Load environment variables
load_dotenv()


class MetadataExtractor:
    """Extracts and enriches metadata from media files.

    Composes specialised clients for TMDB, MusicBrainz, and MediaInfo,
    exposing every public method from the old monolithic class so that
    existing callers continue to work unchanged.
    """

    def __init__(self, config: Dict[str, Any] = None, *, config_path: str = None):
        """
        Initialize the MetadataExtractor.

        Args:
            config: Pre-loaded configuration dict (preferred).
            config_path: Path to configuration file (backward compat).
        """
        self.config = config if config is not None else load_config(config_path or "config.json")
        self.logger = setup_logger("metadata", "metadata.log")

        from .utils import get_data_dir

        self.metadata_dir = get_data_dir() / "metadata"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        self.tmdb_api_key = os.getenv("TMDB_API_KEY")
        self.acoustid_api_key = os.getenv("ACOUSTID_API_KEY")

        # Compose specialised clients
        self._mediainfo = MediaInfoClient()
        self._tmdb = TMDBClient(api_key=self.tmdb_api_key)
        self._mb = MusicBrainzClient(acoustid_api_key=self.acoustid_api_key)

        self.logger.info("MetadataExtractor initialized")

    # ── MediaInfo delegates ──────────────────────────────────────

    def extract_mediainfo(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Extract technical metadata using MediaInfo."""
        return self._mediainfo.extract_mediainfo(file_path)

    def extract_chapters(self, file_path: str):
        """Extract chapter information from a media file using ffprobe."""
        return self._mediainfo.extract_chapters(file_path)

    # ── TMDB delegates ───────────────────────────────────────────

    def search_tmdb(
        self, title: str, year: Optional[int] = None, disc_hints: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Search TMDB for movie metadata."""
        self._tmdb.api_key = self.tmdb_api_key  # sync in case tests mutated it
        return self._tmdb.search_tmdb(title, year=year, disc_hints=disc_hints)

    def download_poster(self, poster_path: str, output_path: str) -> bool:
        """Download movie poster from TMDB."""
        return self._tmdb.download_poster(poster_path, output_path)

    def download_backdrop(self, backdrop_path: str, output_path: str) -> bool:
        """Download movie backdrop/fanart from TMDB."""
        return self._tmdb.download_backdrop(backdrop_path, output_path)

    def _pick_best_tmdb_match(self, results: list, disc_hints: Dict[str, Any]) -> int:
        """Pick the best TMDB match from search results."""
        return self._tmdb._pick_best_tmdb_match(results, disc_hints)

    # ── MusicBrainz / AcoustID delegates ─────────────────────────

    def fingerprint_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Generate an audio fingerprint using Chromaprint."""
        return self._mb.fingerprint_file(file_path)

    def lookup_acoustid(
        self, file_path: str, disc_hints: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Identify an audio file via the AcoustID web service.

        Calls ``self.fingerprint_file()`` (patchable at the extractor level)
        then delegates the API lookup to the MusicBrainz client.
        """
        self._mb.acoustid_api_key = self.acoustid_api_key  # sync
        if not self.acoustid_api_key:
            self._mb.logger.warning("ACOUSTID_API_KEY not configured")
            return None

        fp_data = self.fingerprint_file(file_path)
        if not fp_data:
            return None

        return self._mb.lookup_acoustid_from_fp(fp_data, disc_hints=disc_hints)

    def lookup_musicbrainz_by_release_id(self, release_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full album metadata from MusicBrainz by release MBID."""
        return self._mb.lookup_musicbrainz_by_release_id(release_id)

    def search_musicbrainz(
        self, album_name: str, disc_hints: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Search MusicBrainz for album metadata (audio CDs)."""
        return self._mb.search_musicbrainz(
            album_name,
            disc_hints=disc_hints,
            clean_title_fn=self._tmdb._clean_search_title,
        )

    def download_cover_art(self, url: str, output_path: str) -> bool:
        """Download album cover art from a URL."""
        return self._mb.download_cover_art(url, output_path)

    # ── Private helpers (delegated) ──────────────────────────────

    def _validate_release_durations(
        self, mb_data: Optional[Dict[str, Any]], disc_hints: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Validate a MusicBrainz release against disc track durations."""
        return self._mb.validate_release_durations(mb_data, disc_hints)

    def _release_from_recording(
        self, recording_id: str, disc_hints: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Find the best matching release for a MusicBrainz recording."""
        return self._mb.release_from_recording(recording_id, disc_hints)

    def _clean_search_title(self, raw_title: str) -> str:
        """Clean a raw disc volume name into a search query."""
        return self._tmdb._clean_search_title(raw_title)

    def _aggressive_clean_title(self, raw_title: str) -> str:
        """More aggressive title cleaning as a fallback."""
        return self._tmdb._aggressive_clean_title(raw_title)

    # ── Orchestration ────────────────────────────────────────────

    def extract_full_metadata(
        self,
        file_path: str,
        title_hint: Optional[str] = None,
        disc_hints: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
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
        self.logger.info("Extracting full metadata for: %s", file_path)

        disc_hints = disc_hints or {}
        disc_type = disc_hints.get("disc_type", "dvd")

        metadata: Dict[str, Any] = {
            "extracted_at": datetime.now().isoformat(),
            "source_file": file_path,
            "disc_type": disc_type,
        }

        # ── Audio CD path ─────────────────────────────────────────
        if disc_type == "audio_cd":
            mb_data = None

            # 1) Try fingerprint-based identification first
            if self.config["metadata"].get("acoustid_fingerprint", True) and self.acoustid_api_key:
                audio_file = disc_hints.get("sample_track_path")
                if not audio_file and os.path.isfile(file_path):
                    audio_file = file_path
                if not audio_file and os.path.isdir(file_path):
                    for f in sorted(Path(file_path).iterdir(), key=natural_sort_key):
                        if f.suffix.lower() in AUDIO_EXTENSIONS:
                            audio_file = str(f)
                            break
                if audio_file:
                    aid_result = self.lookup_acoustid(audio_file, disc_hints=disc_hints)
                    if aid_result:
                        release_id = aid_result.get("musicbrainz_release_id")
                        if release_id:
                            mb_data = self.lookup_musicbrainz_by_release_id(release_id)
                            mb_data = self._validate_release_durations(mb_data, disc_hints)
                        if not mb_data and aid_result.get("musicbrainz_recording_id"):
                            mb_data = self._release_from_recording(
                                aid_result["musicbrainz_recording_id"],
                                disc_hints,
                            )
                        if mb_data:
                            self.logger.info("Identified audio CD via AcoustID fingerprint")

            # 2) Fall back to name-based MusicBrainz search
            if (
                not mb_data
                and self.config["metadata"].get("fetch_online_metadata", True)
                and title_hint
            ):
                mb_data = self.search_musicbrainz(title_hint, disc_hints)

            if mb_data:
                metadata["musicbrainz"] = mb_data

                if mb_data.get("cover_art_url"):
                    album_name = mb_data.get("title") or title_hint or "unknown"
                    cover_filename = sanitize_filename(album_name) + "_poster.jpg"
                    cover_path = self.metadata_dir.parent / "thumbnails" / cover_filename
                    cover_path.parent.mkdir(parents=True, exist_ok=True)
                    if self.download_cover_art(mb_data["cover_art_url"], str(cover_path)):
                        metadata["poster_file"] = str(cover_path)

            return metadata

        # ── Video path (DVD / Blu-ray) ────────────────────────────
        if os.path.isfile(file_path):
            mediainfo = self.extract_mediainfo(file_path)
            if mediainfo:
                metadata["file_info"] = mediainfo

        if self.config["metadata"]["extract_chapters"] and os.path.isfile(file_path):
            chapters = self.extract_chapters(file_path)
            if chapters:
                metadata["chapters"] = chapters

        if self.config["metadata"].get("fetch_online_metadata", True) and title_hint:
            tmdb_data = self.search_tmdb(title_hint, disc_hints=disc_hints)
            if tmdb_data:
                metadata["tmdb"] = tmdb_data

                safe_title = sanitize_filename(title_hint)
                thumbnails_dir = self.metadata_dir.parent / "thumbnails"
                thumbnails_dir.mkdir(parents=True, exist_ok=True)

                if tmdb_data.get("poster_path"):
                    poster_filename = safe_title + "_poster.jpg"
                    poster_out = thumbnails_dir / poster_filename
                    if self.download_poster(tmdb_data["poster_path"], str(poster_out)):
                        metadata["poster_file"] = str(poster_out)

                if tmdb_data.get("backdrop_path"):
                    backdrop_filename = safe_title + "_backdrop.jpg"
                    backdrop_out = thumbnails_dir / backdrop_filename
                    if self.download_backdrop(tmdb_data["backdrop_path"], str(backdrop_out)):
                        metadata["backdrop_file"] = str(backdrop_out)

        return metadata

    def save_metadata(self, metadata: Dict[str, Any], title: str) -> None:
        """
        Save metadata to JSON file.

        Args:
            metadata: Metadata dictionary
            title: Title for filename
        """
        if not self.config["metadata"]["save_to_json"]:
            return

        filename = sanitize_filename(title) + ".json"
        output_path = self.metadata_dir / filename

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            self.logger.info("Saved metadata to: %s", output_path)
        except Exception as e:
            self.logger.error("Error saving metadata: %s", e)


def main():
    """Main entry point for command-line usage."""
    import argparse

    parser = argparse.ArgumentParser(description="Extract media metadata")
    parser.add_argument("file", help="Path to media file")
    parser.add_argument("--title", help="Title hint for TMDB lookup")
    parser.add_argument("--save", action="store_true", help="Save metadata to JSON")

    args = parser.parse_args()

    extractor = MetadataExtractor()
    metadata = extractor.extract_full_metadata(args.file, args.title)

    print(json.dumps(metadata, indent=2))

    if args.save and args.title:
        extractor.save_metadata(metadata, args.title)


if __name__ == "__main__":
    main()
