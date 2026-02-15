"""Podcast and episode repository mixin."""

import sqlite3
import uuid
from typing import Any, Dict, List, Optional


class PodcastRepositoryMixin:
    """CRUD for ``podcasts`` and ``podcast_episodes`` tables."""

    # ── Podcasts ─────────────────────────────────────────────────

    def add_podcast(
        self,
        feed_url: str,
        title: str = "",
        author: str = "",
        description: str = "",
        artwork_url: str = None,
    ) -> Optional[str]:
        """Add a podcast subscription, returns podcast ID."""
        pod_id = str(uuid.uuid4())[:8]
        conn = self._get_conn()
        try:
            conn.execute(
                """

                INSERT INTO podcasts (id, feed_url, title, author, description, artwork_url)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (pod_id, feed_url, title, author, description, artwork_url),
            )
            conn.commit()
            return pod_id
        except sqlite3.IntegrityError:
            return None  # feed_url already exists

    def get_all_podcasts(self) -> List[Dict[str, Any]]:
        """Get all podcast subscriptions."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM podcasts ORDER BY title").fetchall()
        return [dict(r) for r in rows]

    def get_podcast(self, pod_id: str) -> Optional[Dict[str, Any]]:
        """Get a single podcast by ID."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM podcasts WHERE id = ?", (pod_id,)).fetchone()
        return dict(row) if row else None

    def update_podcast(self, pod_id: str, **kwargs: Any) -> None:
        """Update allowed fields on a podcast."""
        conn = self._get_conn()
        allowed = {
            "title",
            "author",
            "description",
            "artwork_url",
            "artwork_path",
            "last_checked",
            "check_interval_hours",
            "is_active",
        }
        sets: list[str] = []
        vals: list[Any] = []
        for k, v in kwargs.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                vals.append(v)
        if sets:
            vals.append(pod_id)
            conn.execute(f"UPDATE podcasts SET {', '.join(sets)} WHERE id = ?", vals)
            conn.commit()

    def delete_podcast(self, pod_id: str) -> bool:
        """Delete a podcast subscription."""
        conn = self._get_conn()
        result = conn.execute("DELETE FROM podcasts WHERE id = ?", (pod_id,))
        conn.commit()
        return result.rowcount > 0

    def get_due_podcasts(self) -> List[Dict[str, Any]]:
        """Get podcasts that are due for a feed check."""
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT * FROM podcasts
            WHERE is_active = 1
              AND (last_checked IS NULL
                   OR datetime(last_checked, '+' || check_interval_hours || ' hours')
                      <= datetime('now'))
        """
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Podcast Episodes ─────────────────────────────────────────

    def add_episode(
        self,
        podcast_id: str,
        title: str,
        audio_url: str = None,
        duration_seconds: float = None,
        published_at: str = None,
        description: str = "",
    ) -> Optional[str]:
        """Add a podcast episode, returns episode ID."""
        ep_id = str(uuid.uuid4())[:8]
        conn = self._get_conn()
        try:
            conn.execute(
                """

                INSERT INTO podcast_episodes
                    (id, podcast_id, title, audio_url, duration_seconds,
                     published_at, description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (ep_id, podcast_id, title, audio_url, duration_seconds, published_at, description),
            )
            conn.commit()
            return ep_id
        except sqlite3.IntegrityError:
            return None

    def get_episodes(self, podcast_id: str) -> List[Dict[str, Any]]:
        """Get episodes for a podcast, newest first."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM podcast_episodes WHERE podcast_id = ? ORDER BY published_at DESC",
            (podcast_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_episode(self, ep_id: str, **kwargs: Any) -> None:
        """Update allowed fields on a podcast episode."""
        conn = self._get_conn()
        allowed = {"file_path", "is_downloaded", "duration_seconds"}
        sets: list[str] = []
        vals: list[Any] = []
        for k, v in kwargs.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                vals.append(v)
        if sets:
            vals.append(ep_id)
            conn.execute(f"UPDATE podcast_episodes SET {', '.join(sets)} WHERE id = ?", vals)
            conn.commit()

    def episode_exists(self, podcast_id: str, audio_url: str) -> bool:
        """Check if an episode already exists (by audio URL)."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM podcast_episodes WHERE podcast_id = ? AND audio_url = ?",
            (podcast_id, audio_url),
        ).fetchone()
        return row is not None
