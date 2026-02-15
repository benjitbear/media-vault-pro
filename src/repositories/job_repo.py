"""Job queue repository mixin."""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


class JobRepositoryMixin:
    """CRUD and lifecycle operations for the ``jobs`` table."""

    def create_job(
        self,
        title: str,
        source_path: str,
        title_number: int = 1,
        disc_type: str = "dvd",
        disc_hints: Optional[Dict[str, Any]] = None,
        job_type: str = "rip",
    ) -> str:
        """Create a new job, returns job ID.

        job_type: 'rip' | 'download' | 'upload' | 'podcast'
        """
        job_id = str(uuid.uuid4())[:8]
        hints_json = json.dumps(disc_hints or {})
        conn = self._get_conn()
        conn.execute(
            """

            INSERT INTO jobs (id, title, source_path, title_number,
                             disc_type, disc_hints, job_type, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?)
        """,
            (
                job_id,
                title,
                source_path,
                title_number,
                disc_type,
                hints_json,
                job_type,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        self.broadcast(
            "job_created",
            {
                "id": job_id,
                "title": title,
                "status": "queued",
                "disc_type": disc_type,
                "job_type": job_type,
            },
        )
        self.logger.info("Job created: %s - %s (%s/%s)", job_id, title, disc_type, job_type)
        return job_id

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """Get all jobs ordered by creation time (newest first)."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a single job."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def get_next_queued_job(self) -> Optional[Dict[str, Any]]:
        """Get the next job in the queue."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def get_next_queued_content_job(self) -> Optional[Dict[str, Any]]:
        """Get the next queued non-rip job (download, article, podcast, etc.)."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM jobs WHERE status = 'queued' "
            "AND job_type != 'rip' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def update_job_status(self, job_id: str, status: str, **kwargs: Any) -> None:
        """Update job status and optional fields."""
        conn = self._get_conn()
        sets = ["status = ?"]
        vals: list[Any] = [status]

        for key in (
            "progress",
            "eta",
            "fps",
            "error_message",
            "output_path",
            "started_at",
            "completed_at",
        ):
            if key in kwargs:
                sets.append(f"{key} = ?")
                vals.append(kwargs[key])

        vals.append(job_id)
        conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()

        job = self.get_job(job_id)
        if job:
            self.broadcast("job_update", job)

    def update_job_progress(
        self, job_id: str, progress: float, eta: str = None, fps: float = None, title: str = None
    ) -> None:
        """Update job progress (called frequently during encoding)."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE jobs SET progress = ?, eta = ?, fps = ? WHERE id = ?",
            (progress, eta, fps, job_id),
        )
        conn.commit()
        self.broadcast(
            "rip_progress",
            {"id": job_id, "progress": progress, "eta": eta, "fps": fps, "title": title or ""},
        )

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job (only if queued or encoding)."""
        conn = self._get_conn()
        result = conn.execute(
            "UPDATE jobs SET status = 'cancelled', completed_at = ? "
            "WHERE id = ? AND status IN ('queued', 'encoding')",
            (datetime.now().isoformat(), job_id),
        )
        conn.commit()
        if result.rowcount > 0:
            job = self.get_job(job_id)
            if job:
                self.broadcast("job_update", job)
            return True
        return False

    def retry_job(self, job_id: str) -> Optional[str]:
        """Retry a failed/cancelled job by creating a new one."""
        job = self.get_job(job_id)
        if job and job["status"] in ("failed", "cancelled"):
            return self.create_job(job["title"], job["source_path"], job["title_number"])
        return None

    def get_active_job(self) -> Optional[Dict[str, Any]]:
        """Get currently encoding job."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM jobs WHERE status = 'encoding' LIMIT 1").fetchone()
        return dict(row) if row else None
