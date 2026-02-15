"""Media / Library repository mixin."""

import json
from typing import Any, Dict, List, Optional


class MediaRepositoryMixin:
    """CRUD operations for the ``media`` table."""

    def upsert_media(self, item: Dict[str, Any]) -> None:
        """Insert or update a media item."""
        conn = self._get_conn()
        conn.execute(
            """

            INSERT INTO media (id, title, filename, file_path, file_size, size_formatted,
                             created_at, modified_at, year, overview, rating, genres,
                             director, cast_members, poster_path, has_metadata,
                             collection_name, tmdb_id,
                             media_type, source_url, artist, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, filename=excluded.filename,
                file_path=excluded.file_path, file_size=excluded.file_size,
                size_formatted=excluded.size_formatted,
                created_at=excluded.created_at, modified_at=excluded.modified_at,
                year=excluded.year, overview=excluded.overview, rating=excluded.rating,
                genres=excluded.genres, director=excluded.director,
                cast_members=excluded.cast_members, poster_path=excluded.poster_path,
                has_metadata=excluded.has_metadata,
                collection_name=excluded.collection_name, tmdb_id=excluded.tmdb_id,
                media_type=excluded.media_type, source_url=excluded.source_url,
                artist=excluded.artist, duration_seconds=excluded.duration_seconds
        """,
            (
                item["id"],
                item["title"],
                item["filename"],
                item["file_path"],
                item.get("file_size", 0),
                item.get("size_formatted", ""),
                item.get("created_at", ""),
                item.get("modified_at", ""),
                item.get("year"),
                item.get("overview"),
                item.get("rating"),
                json.dumps(item.get("genres", [])),
                item.get("director"),
                json.dumps(item.get("cast", [])),
                item.get("poster_path"),
                1 if item.get("has_metadata") else 0,
                item.get("collection_name"),
                item.get("tmdb_id"),
                item.get("media_type", "video"),
                item.get("source_url"),
                item.get("artist"),
                item.get("duration_seconds"),
            ),
        )
        conn.commit()

    def get_all_media(self) -> List[Dict[str, Any]]:
        """Get all media items sorted by title."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM media ORDER BY title COLLATE NOCASE").fetchall()
        return [self._media_row_to_dict(row) for row in rows]

    def get_media(self, media_id: str) -> Optional[Dict[str, Any]]:
        """Get a single media item by ID."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
        return self._media_row_to_dict(row) if row else None

    def search_media(self, query: str) -> List[Dict[str, Any]]:
        """Search media by title, director, cast, genres."""
        conn = self._get_conn()
        like = f"%{query}%"
        rows = conn.execute(
            """

            SELECT * FROM media
            WHERE title LIKE ? OR director LIKE ? OR cast_members LIKE ? OR genres LIKE ?
            ORDER BY title COLLATE NOCASE
        """,
            (like, like, like, like),
        ).fetchall()
        return [self._media_row_to_dict(row) for row in rows]

    def update_media_metadata(self, media_id: str, updates: Dict[str, Any]) -> bool:
        """Update metadata fields for a media item."""
        conn = self._get_conn()
        allowed = {
            "title",
            "year",
            "overview",
            "director",
            "rating",
            "genres",
            "cast_members",
            "collection_name",
            "tmdb_id",
            "media_type",
            "source_url",
            "artist",
            "duration_seconds",
            "filename",
            "file_path",
        }
        set_clauses: list[str] = []
        values: list[Any] = []
        for key, value in updates.items():
            if key in allowed:
                if key in ("genres", "cast_members") and isinstance(value, list):
                    value = json.dumps(value)
                set_clauses.append(f"{key} = ?")
                values.append(value)

        if not set_clauses:
            return False

        values.append(media_id)
        result = conn.execute(f"UPDATE media SET {', '.join(set_clauses)} WHERE id = ?", values)
        conn.commit()
        return result.rowcount > 0

    def delete_media(self, media_id: str) -> None:
        """Delete a media item from the database."""
        conn = self._get_conn()
        conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
        conn.commit()

    def clear_media(self) -> None:
        """Clear all media items."""
        conn = self._get_conn()
        conn.execute("DELETE FROM media")
        conn.commit()

    def get_media_ids(self) -> set:
        """Get set of all current media IDs."""
        conn = self._get_conn()
        rows = conn.execute("SELECT id FROM media").fetchall()
        return {row["id"] for row in rows}

    def _media_row_to_dict(self, row) -> Dict[str, Any]:
        """Convert a database row to a media dict."""
        d = dict(row)
        d["genres"] = json.loads(d.get("genres") or "[]")
        d["cast"] = json.loads(d.get("cast_members") or "[]")
        d.pop("cast_members", None)
        d["has_metadata"] = bool(d.get("has_metadata"))
        d["has_poster"] = bool(d.get("poster_path"))
        d.setdefault("media_type", "video")
        d.setdefault("source_url", None)
        d.setdefault("artist", None)
        d.setdefault("duration_seconds", None)
        return d
