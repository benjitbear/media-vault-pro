"""Playback progress repository mixin."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..constants import PLAYBACK_FINISH_THRESHOLD


class PlaybackRepositoryMixin:
    """Track and resume playback progress via ``playback_progress`` table."""

    def save_playback_progress(
        self,
        media_id: str,
        position_seconds: float,
        duration_seconds: float = 0,
        username: str = "anonymous",
    ) -> None:
        """Save or update the playback position for a user / media item.

        Automatically marks as finished when past the threshold.
        """
        finished = 0
        if (
            duration_seconds > 0
            and position_seconds >= duration_seconds * PLAYBACK_FINISH_THRESHOLD
        ):
            finished = 1
        conn = self._get_conn()
        conn.execute(
            """

            INSERT INTO playback_progress
                (media_id, username, position_seconds, duration_seconds, finished, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(media_id, username) DO UPDATE SET
                position_seconds = excluded.position_seconds,
                duration_seconds = excluded.duration_seconds,
                finished = excluded.finished,
                updated_at = excluded.updated_at
        """,
            (
                media_id,
                username,
                position_seconds,
                duration_seconds,
                finished,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()

    def get_playback_progress(
        self, media_id: str, username: str = "anonymous"
    ) -> Optional[Dict[str, Any]]:
        """Get stored playback position for a media item + user."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM playback_progress WHERE media_id = ? AND username = ?",
            (media_id, username),
        ).fetchone()
        return dict(row) if row else None

    def get_in_progress_media(self, username: str = "anonymous") -> List[Dict[str, Any]]:
        """Get all media items that the user has started but not finished,
        sorted by most recently watched."""
        conn = self._get_conn()
        rows = conn.execute(
            """

            SELECT m.*, pp.position_seconds AS progress_position,
                   pp.duration_seconds AS progress_duration,
                   pp.updated_at AS progress_updated_at
            FROM playback_progress pp
            JOIN media m ON m.id = pp.media_id
            WHERE pp.username = ? AND pp.finished = 0 AND pp.position_seconds > 5
            ORDER BY pp.updated_at DESC
        """,
            (username,),
        ).fetchall()
        results: list[Dict[str, Any]] = []
        for row in rows:
            d = self._media_row_to_dict(row)
            d["progress_position"] = row["progress_position"]
            d["progress_duration"] = row["progress_duration"]
            d["progress_updated_at"] = row["progress_updated_at"]
            results.append(d)
        return results

    def clear_playback_progress(self, media_id: str, username: str = "anonymous") -> bool:
        """Clear playback progress for a media item."""
        conn = self._get_conn()
        result = conn.execute(
            "DELETE FROM playback_progress WHERE media_id = ? AND username = ?",
            (media_id, username),
        )
        conn.commit()
        return result.rowcount > 0
