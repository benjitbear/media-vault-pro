"""
Library scanner service.

Walks the media library directory, loads metadata JSONs, and syncs
the results to the SQLite database via AppState.

Extracted from ``web_server.py`` so that scanning logic is decoupled
from the HTTP layer.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..constants import ALL_MEDIA_EXTENSIONS, LIBRARY_SKIP_DIRS
from ..utils import detect_media_type, format_size, generate_media_id, setup_logger

if TYPE_CHECKING:
    from ..app_state import AppState


class LibraryScannerService:
    """Scans the media library directory and syncs findings to the DB."""

    def __init__(
        self,
        library_path: Path,
        metadata_path: Path,
        thumbnails_path: Path,
        app_state: "AppState",
    ):
        self.library_path = library_path
        self.metadata_path = metadata_path
        self.thumbnails_path = thumbnails_path
        self.app_state = app_state
        self.logger = setup_logger("library_scanner", "library_scanner.log")

    def scan(self) -> List[Dict[str, Any]]:
        """Perform a full library scan and sync results to SQLite.

        Returns:
            Sorted list of media item dicts.
        """
        media_items: List[Dict[str, Any]] = []

        if not self.library_path.exists():
            self.logger.warning("Library path does not exist: %s", self.library_path)
            return media_items

        scanned_ids: set = set()

        for file_path in self.library_path.rglob("*"):
            if not file_path.is_file():
                continue
            # Skip files inside data/thumbnails, data/metadata etc.
            rel_parts = file_path.relative_to(self.library_path).parts
            if rel_parts and rel_parts[0] in LIBRARY_SKIP_DIRS:
                continue
            if file_path.suffix.lower() not in ALL_MEDIA_EXTENSIONS:
                continue

            try:
                stat = file_path.stat()
            except OSError:
                continue

            media_id = generate_media_id(str(file_path))
            scanned_ids.add(media_id)

            media_type = detect_media_type(file_path.name)
            item: Dict[str, Any] = {
                "id": media_id,
                "title": file_path.stem,
                "filename": file_path.name,
                "file_path": str(file_path),
                "file_size": stat.st_size,
                "size_formatted": format_size(stat.st_size),
                "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "media_type": media_type,
            }

            # Load metadata JSON
            metadata = self._load_metadata(file_path, item)

            # Check for poster
            self._attach_poster(file_path, item, metadata)

            # Sync to SQLite
            self.app_state.upsert_media(item)
            media_items.append(item)

        # Remove stale entries (files deleted from disk)
        existing_ids = self.app_state.get_media_ids()
        for stale_id in existing_ids - scanned_ids:
            self.app_state.delete_media(stale_id)

        media_items.sort(key=lambda x: x.get("title", "").lower())
        self.logger.info("Scanned library: found %s items", len(media_items))
        return media_items

    # ── Private helpers ──────────────────────────────────────────

    def _load_metadata(self, file_path: Path, item: Dict[str, Any]) -> Optional[dict]:
        """Load the sidecar metadata JSON and enrich *item* in place."""
        metadata_file = self.metadata_path / f"{file_path.stem}.json"
        if not metadata_file.exists():
            return None

        try:
            with open(metadata_file, "r") as f:
                metadata = json.load(f)

            if "tmdb" in metadata:
                tmdb = metadata["tmdb"]
                item["title"] = tmdb.get("title", item["title"])
                item["year"] = tmdb.get("year")
                item["overview"] = tmdb.get("overview")
                item["rating"] = tmdb.get("rating")
                item["genres"] = tmdb.get("genres", [])
                item["director"] = tmdb.get("director")
                item["cast"] = tmdb.get("cast", [])
                item["tmdb_id"] = tmdb.get("tmdb_id")
                item["collection_name"] = tmdb.get("collection_name")

            if "musicbrainz" in metadata:
                mb = metadata["musicbrainz"]
                track_info = metadata.get("track_info", {})
                if track_info.get("title"):
                    item["title"] = track_info["title"]
                item["collection_name"] = mb.get("title")
                item["artist"] = mb.get("artist")
                item["year"] = mb.get("year")
                item["genres"] = mb.get("genres", [])
                item["media_type"] = "audio"

            item["has_metadata"] = True
            return metadata

        except Exception as e:
            self.logger.error("Error loading metadata for %s: %s", file_path, e)
            return None

    def _attach_poster(self, file_path: Path, item: Dict[str, Any], metadata: Optional[dict]) -> None:
        """Set ``poster_path`` on *item* if a poster image exists."""
        poster_file = self.thumbnails_path / f"{file_path.stem}_poster.jpg"
        if poster_file.exists():
            item["poster_path"] = str(poster_file)
        elif metadata and metadata.get("poster_file"):
            pf = metadata["poster_file"]
            if os.path.exists(pf):
                item["poster_path"] = pf
