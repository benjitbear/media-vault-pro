"""
Media identification service.

Identifies uploaded or unknown video files by:
1. Parsing the filename with ``guessit`` → title, year, type
2. Extracting technical metadata via MediaInfo → duration, codec, resolution
3. Searching TMDB with parsed title + year + duration hints
4. Downloading poster/backdrop artwork
5. Saving a metadata JSON sidecar file
6. Updating the database record via ``AppState``

This service bridges the gap between "file saved to disk" and
"fully enriched library item with poster and metadata."
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from ..constants import VIDEO_EXTENSIONS
from ..utils import (
    detect_media_type,
    format_size,
    generate_media_id,
    get_data_dir,
    sanitize_filename,
    setup_logger,
)


class MediaIdentifierService:
    """Identify and enrich media files with metadata from external sources.

    Composes a :class:`MetadataExtractor` (TMDB + MediaInfo) and ``guessit``
    to turn bare uploaded files into fully enriched library items.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        app_state: "AppState" = None,  # noqa: F821
        metadata_extractor: "MetadataExtractor" = None,  # noqa: F821
    ):
        """Initialise the identifier.

        Args:
            config: Application configuration dict.
            app_state: Shared database singleton.
            metadata_extractor: Pre-built MetadataExtractor. If ``None``,
                one will be created from *config*.
        """
        self.config = config
        self.logger = setup_logger("media_identifier", "media_identifier.log")

        # Lazy imports to avoid circular dependencies at module level
        if app_state is None:
            from ..app_state import AppState

            app_state = AppState()
        self.app_state = app_state

        if metadata_extractor is None:
            from ..metadata import MetadataExtractor

            metadata_extractor = MetadataExtractor(config=config)
        self.metadata_extractor = metadata_extractor

        data_dir = get_data_dir()
        self.metadata_dir = data_dir / "metadata"
        self.thumbnails_dir = data_dir / "thumbnails"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info("MediaIdentifierService initialized")

    # ── Public API ───────────────────────────────────────────────

    def identify_file(
        self,
        file_path: str,
        *,
        title_override: Optional[str] = None,
        year_override: Optional[int] = None,
        media_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Identify a media file and enrich its database record.

        Steps:
        1. Parse filename with guessit (unless *title_override* given)
        2. Extract MediaInfo (duration, codec, resolution)
        3. Search TMDB with title + year + runtime hints
        4. Download poster / backdrop
        5. Save metadata JSON sidecar
        6. Update the ``media`` table via ``AppState``

        Args:
            file_path: Absolute path to the media file.
            title_override: User-supplied title (skips filename parsing).
            year_override: User-supplied year (overrides guessit).
            media_id: Existing media ID. If ``None``, generated from *file_path*.

        Returns:
            Enriched media item dict as stored in the database.
        """
        fp = Path(file_path)
        if not fp.exists():
            self.logger.error("File not found: %s", file_path)
            return {}

        media_id = media_id or generate_media_id(file_path)
        self.logger.info(
            "Identifying file: %s (media_id=%s, override=%s)",
            fp.name,
            media_id,
            title_override,
        )

        # ── Step 1: Parse filename ────────────────────────────────
        guess = self._parse_filename(fp.name)
        title = title_override or guess.get("title") or fp.stem
        year = year_override or guess.get("year")

        self.logger.info("Parsed: title=%s, year=%s, type=%s", title, year, guess.get("type"))

        # ── Step 2: Extract MediaInfo ─────────────────────────────
        mediainfo = None
        duration_seconds = None
        if fp.suffix.lower() in VIDEO_EXTENSIONS and fp.is_file():
            mediainfo = self.metadata_extractor.extract_mediainfo(file_path)
            if mediainfo:
                duration_seconds = mediainfo.get("duration_seconds")

        # ── Step 3: Search TMDB with hints ────────────────────────
        tmdb_data = None
        if self.config.get("metadata", {}).get("fetch_online_metadata", True):
            disc_hints: Dict[str, Any] = {"disc_type": "dvd"}
            if duration_seconds:
                disc_hints["estimated_runtime_min"] = duration_seconds / 60.0

            tmdb_data = self.metadata_extractor.search_tmdb(
                title, year=year, disc_hints=disc_hints
            )
            if tmdb_data:
                self.logger.info(
                    "TMDB match: %s (%s)", tmdb_data.get("title"), tmdb_data.get("year")
                )

        # ── Step 4: Download artwork ──────────────────────────────
        poster_path = None
        backdrop_path = None
        if tmdb_data:
            safe_title = sanitize_filename(tmdb_data.get("title") or title)
            if tmdb_data.get("poster_path"):
                poster_out = self.thumbnails_dir / f"{safe_title}_poster.jpg"
                if self.metadata_extractor.download_poster(
                    tmdb_data["poster_path"], str(poster_out)
                ):
                    poster_path = str(poster_out)

            if tmdb_data.get("backdrop_path"):
                backdrop_out = self.thumbnails_dir / f"{safe_title}_backdrop.jpg"
                if self.metadata_extractor.download_backdrop(
                    tmdb_data["backdrop_path"], str(backdrop_out)
                ):
                    backdrop_path = str(backdrop_out)

        # ── Step 5: Save metadata JSON sidecar ────────────────────
        sidecar_data = self._build_sidecar(
            file_path, mediainfo, tmdb_data, guess, poster_path, backdrop_path
        )
        sidecar_stem = fp.stem
        if tmdb_data and tmdb_data.get("title"):
            sidecar_stem = sanitize_filename(tmdb_data["title"])
        self._save_sidecar(sidecar_data, sidecar_stem)

        # ── Step 6: Update database ───────────────────────────────
        item = self._build_media_item(
            file_path=file_path,
            media_id=media_id,
            tmdb_data=tmdb_data,
            guess=guess,
            title_override=title_override,
            year_override=year_override,
            duration_seconds=duration_seconds,
            poster_path=poster_path,
        )
        self.app_state.upsert_media(item)
        self.app_state.broadcast("library_updated", {})

        self.logger.info("Identification complete for %s → %s", fp.name, item.get("title"))
        return item

    def identify_by_media_id(
        self,
        media_id: str,
        *,
        title_override: Optional[str] = None,
        year_override: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Re-identify an existing media item by its database ID.

        Looks up the file path from the database, then delegates to
        :meth:`identify_file`.

        Args:
            media_id: Existing media ID in the database.
            title_override: User-supplied title for manual correction.
            year_override: User-supplied year.

        Returns:
            Enriched media item dict, or empty dict if not found.
        """
        existing = self.app_state.get_media(media_id)
        if not existing:
            self.logger.warning("Media ID not found: %s", media_id)
            return {}

        file_path = existing.get("file_path", "")
        if not file_path or not os.path.exists(file_path):
            self.logger.error("File missing for media_id=%s: %s", media_id, file_path)
            return {}

        return self.identify_file(
            file_path,
            title_override=title_override,
            year_override=year_override,
            media_id=media_id,
        )

    # ── Filename parsing ─────────────────────────────────────────

    @staticmethod
    def _parse_filename(filename: str) -> Dict[str, Any]:
        """Parse a media filename with ``guessit``.

        Returns a dict with normalised keys:
        ``title``, ``year``, ``type`` (``"movie"`` or ``"episode"``),
        ``screen_size``, ``source``, ``video_codec``, plus any extras
        guessit provides.

        Falls back gracefully if guessit is not installed.
        """
        try:
            from guessit import guessit  # type: ignore[import-untyped]

            result = guessit(filename)
            return {
                "title": str(result.get("title", "")) or None,
                "year": result.get("year"),
                "type": str(result.get("type", "movie")),
                "screen_size": result.get("screen_size"),
                "source": str(result.get("source", "")) or None,
                "video_codec": str(result.get("video_codec", "")) or None,
                "season": result.get("season"),
                "episode": result.get("episode"),
                "episode_title": str(result.get("episode_title", "")) or None,
                "_raw": dict(result),
            }
        except ImportError:
            # guessit not installed — fall back to basic splitting
            stem = Path(filename).stem
            # Try to extract year from common patterns like "Title (2024)" or "Title.2024"
            import re

            year_match = re.search(r"[.\s(](\d{4})[.\s)]", stem)
            year = int(year_match.group(1)) if year_match else None
            # Crude title extraction: take everything before the year
            if year_match:
                title = stem[: year_match.start()].replace(".", " ").replace("_", " ").strip()
            else:
                title = stem.replace(".", " ").replace("_", " ").strip()
            return {"title": title or None, "year": year, "type": "movie"}
        except Exception:
            return {"title": Path(filename).stem, "year": None, "type": "movie"}

    # ── Internal helpers ─────────────────────────────────────────

    def _build_sidecar(
        self,
        file_path: str,
        mediainfo: Optional[Dict[str, Any]],
        tmdb_data: Optional[Dict[str, Any]],
        guess: Dict[str, Any],
        poster_path: Optional[str],
        backdrop_path: Optional[str],
    ) -> Dict[str, Any]:
        """Build the metadata JSON sidecar dict."""
        data: Dict[str, Any] = {
            "extracted_at": datetime.now().isoformat(),
            "source_file": file_path,
            "identification": {
                "method": "guessit" if guess.get("title") else "filename",
                "parsed_title": guess.get("title"),
                "parsed_year": guess.get("year"),
                "parsed_type": guess.get("type"),
                "screen_size": guess.get("screen_size"),
                "source": guess.get("source"),
                "video_codec": guess.get("video_codec"),
            },
        }
        if mediainfo:
            data["file_info"] = mediainfo
        if tmdb_data:
            data["tmdb"] = tmdb_data
        if poster_path:
            data["poster_file"] = poster_path
        if backdrop_path:
            data["backdrop_file"] = backdrop_path
        return data

    def _save_sidecar(self, data: Dict[str, Any], stem: str) -> None:
        """Write the metadata sidecar JSON to disk."""
        import json

        if not self.config.get("metadata", {}).get("save_to_json", True):
            return

        filename = sanitize_filename(stem) + ".json"
        out = self.metadata_dir / filename
        try:
            with open(out, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.logger.info("Saved metadata sidecar: %s", out)
        except Exception as e:
            self.logger.error("Failed to write sidecar %s: %s", out, e)

    def _build_media_item(
        self,
        *,
        file_path: str,
        media_id: str,
        tmdb_data: Optional[Dict[str, Any]],
        guess: Dict[str, Any],
        title_override: Optional[str],
        year_override: Optional[int],
        duration_seconds: Optional[float],
        poster_path: Optional[str],
    ) -> Dict[str, Any]:
        """Build the media item dict for ``upsert_media``."""
        fp = Path(file_path)
        stat = fp.stat()

        # Prefer TMDB data → user override → guessit → filename stem
        if tmdb_data:
            title = tmdb_data.get("title") or title_override or guess.get("title") or fp.stem
            year = tmdb_data.get("year") or year_override or guess.get("year")
            overview = tmdb_data.get("overview")
            rating = tmdb_data.get("rating")
            genres = tmdb_data.get("genres", [])
            director = tmdb_data.get("director")
            cast = tmdb_data.get("cast", [])
            tmdb_id = tmdb_data.get("tmdb_id")
            collection_name = tmdb_data.get("collection_name")
        else:
            title = title_override or guess.get("title") or fp.stem
            year = year_override or guess.get("year")
            overview = None
            rating = None
            genres = []
            director = None
            cast = []
            tmdb_id = None
            collection_name = None

        return {
            "id": media_id,
            "title": title,
            "filename": fp.name,
            "file_path": file_path,
            "file_size": stat.st_size,
            "size_formatted": format_size(stat.st_size),
            "created_at": datetime.now().isoformat(),
            "modified_at": datetime.now().isoformat(),
            "media_type": detect_media_type(fp.name),
            "year": year,
            "overview": overview,
            "rating": rating,
            "genres": genres,
            "director": director,
            "cast": cast,
            "tmdb_id": tmdb_id,
            "collection_name": collection_name,
            "poster_path": poster_path,
            "has_metadata": bool(tmdb_data),
            "duration_seconds": duration_seconds,
        }
