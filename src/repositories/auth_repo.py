"""Authentication, sessions, and user management repository mixin."""

import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from werkzeug.security import generate_password_hash, check_password_hash

from ..constants import PW_HASH_METHOD


class AuthRepositoryMixin:
    """Session and user management against ``sessions`` and ``users`` tables."""

    # ── Sessions ─────────────────────────────────────────────────

    def create_session(self, username: str = None, hours: int = 24) -> str:
        """Create a new auth session, returns token."""
        token = str(uuid.uuid4())
        expires = (datetime.now() + timedelta(hours=hours)).isoformat()
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO sessions (token, username, expires_at) VALUES (?, ?, ?)",
            (token, username, expires),
        )
        conn.commit()
        return token

    def validate_session(self, token: str) -> Optional[Dict[str, Any]]:
        """Check if a session token is valid and not expired.

        Returns dict with username and role, or None if invalid.
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT s.token, s.username, u.role FROM sessions s "
            "LEFT JOIN users u ON s.username = u.username "
            "WHERE s.token = ? AND s.expires_at > ?",
            (token, datetime.now().isoformat()),
        ).fetchone()
        if row is None:
            return None
        return {"token": row["token"], "username": row["username"], "role": row["role"] or "user"}

    def cleanup_sessions(self) -> None:
        """Remove expired sessions."""
        conn = self._get_conn()
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (datetime.now().isoformat(),))
        conn.commit()

    def invalidate_session(self, token: str) -> bool:
        """Invalidate (delete) a specific session token. Returns True if found."""
        conn = self._get_conn()
        result = conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        return result.rowcount > 0

    # ── Users ────────────────────────────────────────────────────

    def has_users(self) -> bool:
        """Check whether any user accounts exist."""
        conn = self._get_conn()
        row = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        return row is not None

    def create_user(self, username: str, password: str, role: str = "user") -> bool:
        """Create a new user with hashed password. Returns True if created."""
        conn = self._get_conn()
        pw_hash = generate_password_hash(password, method=PW_HASH_METHOD)
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, pw_hash, role),
            )
            conn.commit()
            self.logger.info("User created: %s (role=%s)", username, role)
            return True
        except sqlite3.IntegrityError:
            return False  # User already exists

    def verify_user(self, username: str, password: str) -> Optional[Dict[str, str]]:
        """Verify credentials. Returns user dict if valid, None otherwise."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT username, password_hash, role FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            return {"username": row["username"], "role": row["role"]}
        return None

    def get_user(self, username: str) -> Optional[Dict[str, str]]:
        """Get user info (without password hash)."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT username, role, created_at FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None

    def list_users(self) -> List[Dict[str, str]]:
        """List all users (without password hashes)."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT username, role, created_at FROM users ORDER BY username"
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_user(self, username: str) -> bool:
        """Delete a user."""
        conn = self._get_conn()
        result = conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
        return result.rowcount > 0

    def update_user_password(self, username: str, new_password: str) -> bool:
        """Update a user's password."""
        conn = self._get_conn()
        pw_hash = generate_password_hash(new_password, method=PW_HASH_METHOD)
        result = conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?", (pw_hash, username)
        )
        conn.commit()
        return result.rowcount > 0

    def seed_default_users(self, default_users: List[Dict[str, str]]) -> None:
        """Seed default user accounts from config (only if they don't exist)."""
        for user_def in default_users:
            username = user_def["username"]
            if not self.get_user(username):
                self.create_user(
                    username=username,
                    password=user_def["password"],
                    role=user_def.get("role", "user"),
                )
                self.logger.info("Seeded default user: %s", username)
