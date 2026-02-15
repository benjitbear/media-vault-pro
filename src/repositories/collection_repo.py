"""Collections and playlist tracks repository mixin."""

from typing import Any, Dict, List, Optional


class CollectionRepositoryMixin:
    """CRUD for ``collections``, ``collection_items``, and ``playlist_tracks``."""

    def get_all_collections(self) -> List[Dict[str, Any]]:
        """Get all collections with their media items and playlist tracks."""
        conn = self._get_conn()
        collections: list[Dict[str, Any]] = []
        for row in conn.execute("SELECT * FROM collections ORDER BY name").fetchall():
            col = dict(row)
            items = conn.execute(
                """
                SELECT m.* FROM media m
                JOIN collection_items ci ON m.id = ci.media_id
                WHERE ci.collection_id = ?
                ORDER BY ci.sort_order
            """,
                (col["id"],),
            ).fetchall()
            col["items"] = [self._media_row_to_dict(item) for item in items]
            pt_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM playlist_tracks WHERE collection_id = ?", (col["id"],)
            ).fetchone()
            col["has_playlist_tracks"] = (pt_count["cnt"] or 0) > 0
            col["playlist_track_count"] = pt_count["cnt"] or 0
            collections.append(col)
        return collections

    def create_collection(
        self, name: str, description: str = "", collection_type: str = "collection"
    ) -> int:
        """Create a collection, returns ID."""
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO collections (name, description, collection_type) VALUES (?, ?, ?)",
            (name, description, collection_type),
        )
        conn.commit()
        return cursor.lastrowid

    def get_collection_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a collection by name, returns dict or None."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM collections WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

    def update_collection_metadata(
        self, col_id: int, description: str = None, collection_type: str = None
    ) -> None:
        """Update description and/or type on an existing collection."""
        conn = self._get_conn()
        updates: list[str] = []
        vals: list[Any] = []
        if description is not None:
            updates.append("description = ?")
            vals.append(description)
        if collection_type is not None:
            updates.append("collection_type = ?")
            vals.append(collection_type)
        if updates:
            vals.append(col_id)
            conn.execute(f"UPDATE collections SET {', '.join(updates)} WHERE id = ?", vals)
            conn.commit()

    def get_collection_items(self, col_id: int) -> List[Dict[str, Any]]:
        """Get ordered media items for a collection."""
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT m.* FROM media m
            JOIN collection_items ci ON m.id = ci.media_id
            WHERE ci.collection_id = ?
            ORDER BY ci.sort_order
        """,
            (col_id,),
        ).fetchall()
        return [self._media_row_to_dict(r) for r in rows]

    def update_collection(self, name: str, media_ids: List[str]) -> None:
        """Set collection items (replaces existing)."""
        conn = self._get_conn()
        row = conn.execute("SELECT id FROM collections WHERE name = ?", (name,)).fetchone()
        if row:
            col_id = row["id"]
        else:
            col_id = self.create_collection(name)

        conn.execute("DELETE FROM collection_items WHERE collection_id = ?", (col_id,))
        for i, media_id in enumerate(media_ids):
            conn.execute(
                "INSERT OR IGNORE INTO collection_items (collection_id, media_id, sort_order) "
                "VALUES (?, ?, ?)",
                (col_id, media_id, i),
            )
        conn.commit()

    def delete_collection(self, name: str) -> bool:
        """Delete a collection by name."""
        conn = self._get_conn()
        result = conn.execute("DELETE FROM collections WHERE name = ?", (name,))
        conn.commit()
        return result.rowcount > 0

    # ── Playlist Tracks ──────────────────────────────────────────

    def add_playlist_tracks(self, collection_id: int, tracks: List[Dict[str, Any]]) -> None:
        """Add playlist tracks (from Spotify import) to a collection."""
        conn = self._get_conn()
        conn.execute("DELETE FROM playlist_tracks WHERE collection_id = ?", (collection_id,))
        for i, t in enumerate(tracks):
            conn.execute(
                """
                INSERT INTO playlist_tracks
                    (collection_id, sort_order, title, artist, album,
                     duration_ms, artwork_url, spotify_uri, isrc,
                     matched_media_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    collection_id,
                    i,
                    t.get("title", "Unknown"),
                    t.get("artist", ""),
                    t.get("album", ""),
                    t.get("duration_ms", 0),
                    t.get("artwork_url", ""),
                    t.get("spotify_uri", ""),
                    t.get("isrc", ""),
                    t.get("matched_media_id"),
                ),
            )
        conn.commit()

    def get_playlist_tracks(self, collection_id: int) -> List[Dict[str, Any]]:
        """Retrieve playlist tracks for a collection."""
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT pt.*, m.id AS local_id, m.file_path, m.poster_path,
                   m.duration_seconds AS local_dur
            FROM playlist_tracks pt
            LEFT JOIN media m ON pt.matched_media_id = m.id
            WHERE pt.collection_id = ?
            ORDER BY pt.sort_order
        """,
            (collection_id,),
        ).fetchall()
        result: list[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["available"] = bool(d.get("file_path") and d["file_path"])
            d["has_poster"] = bool(d.get("poster_path"))
            result.append(d)
        return result

    def match_playlist_tracks(self, collection_id: int) -> None:
        """Try to match playlist tracks to local library items.

        Matches on title + artist (case-insensitive, fuzzy).
        """
        conn = self._get_conn()
        tracks = conn.execute(
            "SELECT id, title, artist FROM playlist_tracks WHERE collection_id = ?",
            (collection_id,),
        ).fetchall()
        media = conn.execute("SELECT id, title, artist, collection_name FROM media").fetchall()
        for track in tracks:
            t_title = (track["title"] or "").lower().strip()
            t_artist = (track["artist"] or "").lower().strip()
            best = None
            for m in media:
                m_title = (m["title"] or "").lower().strip()
                m_artist = (m["artist"] or "").lower().strip()
                if t_title and m_title and t_title in m_title or m_title in t_title:
                    if t_artist and m_artist and (t_artist in m_artist or m_artist in t_artist):
                        best = m["id"]
                        break
                    elif not t_artist or not m_artist:
                        best = m["id"]
            if best:
                conn.execute(
                    "UPDATE playlist_tracks SET matched_media_id = ? WHERE id = ?",
                    (best, track["id"]),
                )
        conn.commit()
