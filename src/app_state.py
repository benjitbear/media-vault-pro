"""
Application state management using SQLite.
Thread-safe singleton for shared state between web server, disc monitor, and job worker.
"""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from werkzeug.security import generate_password_hash, check_password_hash

from .utils import setup_logger

# Use pbkdf2 instead of scrypt — Python 3.9 + LibreSSL lacks hashlib.scrypt
_PW_METHOD = 'pbkdf2:sha256'


class AppState:
    """Thread-safe application state backed by SQLite"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path: str = None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, db_path: str = None):
        if self._initialized:
            return
        self._initialized = True

        if db_path is None:
            db_path = '/Users/poppemacmini/Media/data/media_ripper.db'

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.logger = setup_logger('app_state', 'app_state.log')
        self._local = threading.local()
        self._socketio = None
        self._init_db()
        self.logger.info(f"AppState initialized with database: {db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local database connection"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_db(self):
        """Initialize database schema"""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS media (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                size_formatted TEXT DEFAULT '',
                created_at TEXT,
                modified_at TEXT,
                year TEXT,
                overview TEXT,
                rating REAL,
                genres TEXT DEFAULT '[]',
                director TEXT,
                cast_members TEXT DEFAULT '[]',
                poster_path TEXT,
                has_metadata INTEGER DEFAULT 0,
                collection_name TEXT,
                tmdb_id INTEGER,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source_path TEXT NOT NULL,
                title_number INTEGER DEFAULT 1,
                disc_type TEXT DEFAULT 'dvd',
                disc_hints TEXT DEFAULT '{}',
                status TEXT DEFAULT 'queued',
                progress REAL DEFAULT 0,
                eta TEXT,
                fps REAL,
                error_message TEXT,
                output_path TEXT,
                started_at TEXT,
                completed_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS collection_items (
                collection_id INTEGER,
                media_id TEXT,
                sort_order INTEGER DEFAULT 0,
                PRIMARY KEY (collection_id, media_id),
                FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
                FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                username TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT
            );

            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

        # Migrate: add username column to sessions if missing (existing DBs)
        try:
            conn.execute("SELECT username FROM sessions LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE sessions ADD COLUMN username TEXT")
            conn.commit()

        # Migrate: add disc_type and disc_hints columns to jobs if missing
        for col, default in [('disc_type', "'dvd'"), ('disc_hints', "'{}'")]:
            try:
                conn.execute(f"SELECT {col} FROM jobs LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT DEFAULT {default}")
                conn.commit()

    def set_socketio(self, socketio):
        """Set the SocketIO instance for broadcasting events"""
        self._socketio = socketio

    def broadcast(self, event: str, data: dict):
        """Broadcast event to all connected WebSocket clients"""
        if self._socketio:
            try:
                self._socketio.emit(event, data)
            except Exception:
                pass

    # ── Media / Library ──────────────────────────────────────────────

    def upsert_media(self, item: Dict[str, Any]):
        """Insert or update a media item"""
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO media (id, title, filename, file_path, file_size, size_formatted,
                             created_at, modified_at, year, overview, rating, genres,
                             director, cast_members, poster_path, has_metadata,
                             collection_name, tmdb_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, filename=excluded.filename,
                file_path=excluded.file_path, file_size=excluded.file_size,
                size_formatted=excluded.size_formatted,
                created_at=excluded.created_at, modified_at=excluded.modified_at,
                year=excluded.year, overview=excluded.overview, rating=excluded.rating,
                genres=excluded.genres, director=excluded.director,
                cast_members=excluded.cast_members, poster_path=excluded.poster_path,
                has_metadata=excluded.has_metadata,
                collection_name=excluded.collection_name, tmdb_id=excluded.tmdb_id
        """, (
            item['id'], item['title'], item['filename'], item['file_path'],
            item.get('file_size', 0), item.get('size_formatted', ''),
            item.get('created_at', ''), item.get('modified_at', ''),
            item.get('year'), item.get('overview'), item.get('rating'),
            json.dumps(item.get('genres', [])), item.get('director'),
            json.dumps(item.get('cast', [])), item.get('poster_path'),
            1 if item.get('has_metadata') else 0,
            item.get('collection_name'), item.get('tmdb_id')
        ))
        conn.commit()

    def get_all_media(self) -> List[Dict[str, Any]]:
        """Get all media items sorted by title"""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM media ORDER BY title COLLATE NOCASE").fetchall()
        return [self._media_row_to_dict(row) for row in rows]

    def get_media(self, media_id: str) -> Optional[Dict[str, Any]]:
        """Get a single media item by ID"""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
        return self._media_row_to_dict(row) if row else None

    def search_media(self, query: str) -> List[Dict[str, Any]]:
        """Search media by title, director, cast, genres"""
        conn = self._get_conn()
        like = f"%{query}%"
        rows = conn.execute("""
            SELECT * FROM media
            WHERE title LIKE ? OR director LIKE ? OR cast_members LIKE ? OR genres LIKE ?
            ORDER BY title COLLATE NOCASE
        """, (like, like, like, like)).fetchall()
        return [self._media_row_to_dict(row) for row in rows]

    def update_media_metadata(self, media_id: str, updates: Dict[str, Any]) -> bool:
        """Update metadata fields for a media item"""
        conn = self._get_conn()
        allowed = {
            'title', 'year', 'overview', 'director', 'rating',
            'genres', 'cast_members', 'collection_name', 'tmdb_id'
        }
        set_clauses = []
        values = []
        for key, value in updates.items():
            if key in allowed:
                if key in ('genres', 'cast_members') and isinstance(value, list):
                    value = json.dumps(value)
                set_clauses.append(f"{key} = ?")
                values.append(value)

        if not set_clauses:
            return False

        values.append(media_id)
        result = conn.execute(
            f"UPDATE media SET {', '.join(set_clauses)} WHERE id = ?", values
        )
        conn.commit()
        return result.rowcount > 0

    def delete_media(self, media_id: str):
        """Delete a media item from the database"""
        conn = self._get_conn()
        conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
        conn.commit()

    def clear_media(self):
        """Clear all media items"""
        conn = self._get_conn()
        conn.execute("DELETE FROM media")
        conn.commit()

    def get_media_ids(self) -> set:
        """Get set of all current media IDs"""
        conn = self._get_conn()
        rows = conn.execute("SELECT id FROM media").fetchall()
        return {row['id'] for row in rows}

    def _media_row_to_dict(self, row) -> Dict[str, Any]:
        """Convert a database row to a media dict"""
        d = dict(row)
        d['genres'] = json.loads(d.get('genres') or '[]')
        d['cast'] = json.loads(d.get('cast_members') or '[]')
        d.pop('cast_members', None)
        d['has_metadata'] = bool(d.get('has_metadata'))
        d['has_poster'] = bool(d.get('poster_path'))
        return d

    # ── Jobs ─────────────────────────────────────────────────────────

    def create_job(self, title: str, source_path: str, title_number: int = 1,
                    disc_type: str = 'dvd',
                    disc_hints: Optional[Dict[str, Any]] = None) -> str:
        """Create a new rip job, returns job ID"""
        job_id = str(uuid.uuid4())[:8]
        hints_json = json.dumps(disc_hints or {})
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO jobs (id, title, source_path, title_number,
                             disc_type, disc_hints, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'queued', ?)
        """, (job_id, title, source_path, title_number,
              disc_type, hints_json, datetime.now().isoformat()))
        conn.commit()
        self.broadcast('job_created', {'id': job_id, 'title': title,
                                       'status': 'queued', 'disc_type': disc_type})
        self.logger.info(f"Job created: {job_id} - {title} ({disc_type})")
        return job_id

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """Get all jobs ordered by creation time (newest first)"""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a single job"""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def get_next_queued_job(self) -> Optional[Dict[str, Any]]:
        """Get the next job in the queue"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def update_job_status(self, job_id: str, status: str, **kwargs):
        """Update job status and optional fields"""
        conn = self._get_conn()
        sets = ["status = ?"]
        vals = [status]

        for key in ('progress', 'eta', 'fps', 'error_message', 'output_path',
                     'started_at', 'completed_at'):
            if key in kwargs:
                sets.append(f"{key} = ?")
                vals.append(kwargs[key])

        vals.append(job_id)
        conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()

        job = self.get_job(job_id)
        if job:
            self.broadcast('job_update', job)

    def update_job_progress(self, job_id: str, progress: float,
                            eta: str = None, fps: float = None, title: str = None):
        """Update job progress (called frequently during encoding)"""
        conn = self._get_conn()
        conn.execute(
            "UPDATE jobs SET progress = ?, eta = ?, fps = ? WHERE id = ?",
            (progress, eta, fps, job_id)
        )
        conn.commit()
        self.broadcast('rip_progress', {
            'id': job_id, 'progress': progress,
            'eta': eta, 'fps': fps, 'title': title or ''
        })

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job (only if queued or encoding)"""
        conn = self._get_conn()
        result = conn.execute(
            "UPDATE jobs SET status = 'cancelled', completed_at = ? "
            "WHERE id = ? AND status IN ('queued', 'encoding')",
            (datetime.now().isoformat(), job_id)
        )
        conn.commit()
        if result.rowcount > 0:
            job = self.get_job(job_id)
            if job:
                self.broadcast('job_update', job)
            return True
        return False

    def retry_job(self, job_id: str) -> Optional[str]:
        """Retry a failed/cancelled job by creating a new one"""
        job = self.get_job(job_id)
        if job and job['status'] in ('failed', 'cancelled'):
            return self.create_job(job['title'], job['source_path'], job['title_number'])
        return None

    def get_active_job(self) -> Optional[Dict[str, Any]]:
        """Get currently encoding job"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM jobs WHERE status = 'encoding' LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    # ── Collections ──────────────────────────────────────────────────

    def get_all_collections(self) -> List[Dict[str, Any]]:
        """Get all collections with their media items"""
        conn = self._get_conn()
        collections = []
        for row in conn.execute("SELECT * FROM collections ORDER BY name").fetchall():
            col = dict(row)
            items = conn.execute("""
                SELECT m.* FROM media m
                JOIN collection_items ci ON m.id = ci.media_id
                WHERE ci.collection_id = ?
                ORDER BY ci.sort_order
            """, (col['id'],)).fetchall()
            col['items'] = [self._media_row_to_dict(item) for item in items]
            collections.append(col)
        return collections

    def create_collection(self, name: str) -> int:
        """Create a collection, returns ID"""
        conn = self._get_conn()
        cursor = conn.execute("INSERT INTO collections (name) VALUES (?)", (name,))
        conn.commit()
        return cursor.lastrowid

    def update_collection(self, name: str, media_ids: List[str]):
        """Set collection items (replaces existing)"""
        conn = self._get_conn()
        row = conn.execute("SELECT id FROM collections WHERE name = ?", (name,)).fetchone()
        if row:
            col_id = row['id']
        else:
            col_id = self.create_collection(name)

        conn.execute("DELETE FROM collection_items WHERE collection_id = ?", (col_id,))
        for i, media_id in enumerate(media_ids):
            conn.execute(
                "INSERT OR IGNORE INTO collection_items (collection_id, media_id, sort_order) "
                "VALUES (?, ?, ?)",
                (col_id, media_id, i)
            )
        conn.commit()

    def delete_collection(self, name: str) -> bool:
        """Delete a collection by name"""
        conn = self._get_conn()
        result = conn.execute("DELETE FROM collections WHERE name = ?", (name,))
        conn.commit()
        return result.rowcount > 0

    # ── Auth ─────────────────────────────────────────────────────────

    def create_session(self, username: str = None, hours: int = 24) -> str:
        """Create a new auth session, returns token"""
        token = str(uuid.uuid4())
        expires = (datetime.now() + timedelta(hours=hours)).isoformat()
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO sessions (token, username, expires_at) VALUES (?, ?, ?)",
            (token, username, expires)
        )
        conn.commit()
        return token

    def validate_session(self, token: str) -> Optional[Dict[str, Any]]:
        """Check if a session token is valid and not expired.
        Returns dict with username and role, or None if invalid."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT s.token, s.username, u.role FROM sessions s "
            "LEFT JOIN users u ON s.username = u.username "
            "WHERE s.token = ? AND s.expires_at > ?",
            (token, datetime.now().isoformat())
        ).fetchone()
        if row is None:
            return None
        return {
            'token': row['token'],
            'username': row['username'],
            'role': row['role'] or 'user'
        }

    def cleanup_sessions(self):
        """Remove expired sessions"""
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM sessions WHERE expires_at < ?",
            (datetime.now().isoformat(),)
        )
        conn.commit()

    # ── Users ────────────────────────────────────────────────────────

    def create_user(self, username: str, password: str, role: str = 'user') -> bool:
        """Create a new user with hashed password. Returns True if created."""
        conn = self._get_conn()
        pw_hash = generate_password_hash(password, method=_PW_METHOD)
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, pw_hash, role)
            )
            conn.commit()
            self.logger.info(f"User created: {username} (role={role})")
            return True
        except sqlite3.IntegrityError:
            return False  # User already exists

    def verify_user(self, username: str, password: str) -> Optional[Dict[str, str]]:
        """Verify credentials. Returns user dict if valid, None otherwise."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT username, password_hash, role FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        if row and check_password_hash(row['password_hash'], password):
            return {'username': row['username'], 'role': row['role']}
        return None

    def get_user(self, username: str) -> Optional[Dict[str, str]]:
        """Get user info (without password hash)"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT username, role, created_at FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        return dict(row) if row else None

    def list_users(self) -> List[Dict[str, str]]:
        """List all users (without password hashes)"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT username, role, created_at FROM users ORDER BY username"
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_user(self, username: str) -> bool:
        """Delete a user"""
        conn = self._get_conn()
        result = conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
        return result.rowcount > 0

    def update_user_password(self, username: str, new_password: str) -> bool:
        """Update a user's password"""
        conn = self._get_conn()
        pw_hash = generate_password_hash(new_password, method=_PW_METHOD)
        result = conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (pw_hash, username)
        )
        conn.commit()
        return result.rowcount > 0

    def seed_default_users(self, default_users: List[Dict[str, str]]):
        """Seed default user accounts from config (only if they don't already exist)"""
        for user_def in default_users:
            username = user_def['username']
            if not self.get_user(username):
                self.create_user(
                    username=username,
                    password=user_def['password'],
                    role=user_def.get('role', 'user')
                )
                self.logger.info(f"Seeded default user: {username}")

    def close(self):
        """Close database connection for current thread"""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    @classmethod
    def reset(cls):
        """Reset singleton (for testing)"""
        with cls._lock:
            if cls._instance and hasattr(cls._instance, '_local'):
                cls._instance.close()
            cls._instance = None
