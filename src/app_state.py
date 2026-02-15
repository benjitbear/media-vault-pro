"""
Application state management using SQLite.
Thread-safe singleton for shared state between web server, disc monitor, and job worker.

Domain logic is split into repository mixins under ``src/repositories/``.
AppState inherits from all of them so existing ``app_state.method()`` calls
keep working unchanged.
"""

import sqlite3
import threading
from pathlib import Path
from .repositories import (
    AuthRepositoryMixin,
    CollectionRepositoryMixin,
    JobRepositoryMixin,
    MediaRepositoryMixin,
    PlaybackRepositoryMixin,
    PodcastRepositoryMixin,
)
from .utils import setup_logger


class AppState(
    MediaRepositoryMixin,
    JobRepositoryMixin,
    CollectionRepositoryMixin,
    AuthRepositoryMixin,
    PodcastRepositoryMixin,
    PlaybackRepositoryMixin,
):
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
        """Initialise the AppState singleton.

        Args:
            db_path: Path to the SQLite database file. Defaults to
                ``MEDIA_ROOT/data/media_ripper.db``.
        """
        if self._initialized:
            return
        self._initialized = True

        if db_path is None:
            from .utils import get_data_dir

            db_path = str(get_data_dir() / "media_ripper.db")

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.logger = setup_logger("app_state", "app_state.log")
        self._local = threading.local()
        self._socketio = None
        self._init_db()
        self.logger.info("AppState initialized with database: %s", db_path)

    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local database connection"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_db(self):
        """Initialize database schema"""
        conn = self._get_conn()
        conn.executescript(
            """
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
                media_type TEXT DEFAULT 'video',
                source_url TEXT,
                artist TEXT,
                duration_seconds REAL,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source_path TEXT NOT NULL,
                title_number INTEGER DEFAULT 1,
                disc_type TEXT DEFAULT 'dvd',
                disc_hints TEXT DEFAULT '{}',
                job_type TEXT DEFAULT 'rip',
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
                description TEXT DEFAULT '',
                collection_type TEXT DEFAULT 'collection',
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

            CREATE TABLE IF NOT EXISTS podcasts (
                id TEXT PRIMARY KEY,
                feed_url TEXT UNIQUE NOT NULL,
                title TEXT DEFAULT '',
                author TEXT DEFAULT '',
                description TEXT DEFAULT '',
                artwork_url TEXT,
                artwork_path TEXT,
                last_checked TEXT,
                check_interval_hours INTEGER DEFAULT 6,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS podcast_episodes (
                id TEXT PRIMARY KEY,
                podcast_id TEXT NOT NULL,
                title TEXT NOT NULL,
                audio_url TEXT,
                file_path TEXT,
                duration_seconds REAL,
                published_at TEXT,
                description TEXT DEFAULT '',
                is_downloaded INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (podcast_id) REFERENCES podcasts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS playlist_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_id INTEGER NOT NULL,
                sort_order INTEGER DEFAULT 0,
                title TEXT NOT NULL,
                artist TEXT DEFAULT '',
                album TEXT DEFAULT '',
                duration_ms INTEGER DEFAULT 0,
                artwork_url TEXT DEFAULT '',
                spotify_uri TEXT DEFAULT '',
                isrc TEXT DEFAULT '',
                matched_media_id TEXT,
                FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
                FOREIGN KEY (matched_media_id) REFERENCES media(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS playback_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                media_id TEXT NOT NULL,
                username TEXT DEFAULT 'anonymous',
                position_seconds REAL DEFAULT 0,
                duration_seconds REAL DEFAULT 0,
                finished INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(media_id, username),
                FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
            );
        """
        )
        conn.commit()

        # ── Migrations for existing DBs ──
        self._migrate(conn)

    def _migrate(self, conn):
        """Add columns/tables that may be missing in older databases."""
        # ── media table ──
        for col, default in [
            ("media_type", "'video'"),
            ("source_url", "NULL"),
            ("artist", "NULL"),
            ("duration_seconds", "NULL"),
        ]:
            try:
                conn.execute(f"SELECT {col} FROM media LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(f"ALTER TABLE media ADD COLUMN {col} TEXT DEFAULT {default}")
                conn.commit()

        # ── jobs table ──
        for col, default in [
            ("disc_type", "'dvd'"),
            ("disc_hints", "'{}'"),
            ("job_type", "'rip'"),
        ]:
            try:
                conn.execute(f"SELECT {col} FROM jobs LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT DEFAULT {default}")
                conn.commit()

        # ── collections table ──
        for col, default in [
            ("description", "''"),
            ("collection_type", "'collection'"),
        ]:
            try:
                conn.execute(f"SELECT {col} FROM collections LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(f"ALTER TABLE collections ADD COLUMN {col} TEXT DEFAULT {default}")
                conn.commit()

        # ── sessions table ──
        try:
            conn.execute("SELECT username FROM sessions LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE sessions ADD COLUMN username TEXT")
            conn.commit()

        # ── playlist_tracks table (may not exist in older DBs) ──
        try:
            conn.execute("SELECT id FROM playlist_tracks LIMIT 1")
        except sqlite3.OperationalError:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS playlist_tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection_id INTEGER NOT NULL,
                    sort_order INTEGER DEFAULT 0,
                    title TEXT NOT NULL,
                    artist TEXT DEFAULT '',
                    album TEXT DEFAULT '',
                    duration_ms INTEGER DEFAULT 0,
                    artwork_url TEXT DEFAULT '',
                    spotify_uri TEXT DEFAULT '',
                    isrc TEXT DEFAULT '',
                    matched_media_id TEXT,
                    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
                    FOREIGN KEY (matched_media_id) REFERENCES media(id) ON DELETE SET NULL
                );
            """
            )
            conn.commit()

    def set_socketio(self, socketio):
        """Set the SocketIO instance for broadcasting events"""
        self._socketio = socketio

    def broadcast(self, event: str, data: dict):
        """Broadcast event to all connected WebSocket clients"""
        if self._socketio:
            try:
                self._socketio.emit(event, data)
            except Exception as e:
                self.logger.debug("WebSocket broadcast of '%s' failed: %s", event, e)

    # -- Domain methods provided by repository mixins ----------------
    # MediaRepositoryMixin      -> media CRUD
    # JobRepositoryMixin        -> job queue lifecycle
    # CollectionRepositoryMixin -> collections + playlist tracks
    # AuthRepositoryMixin       -> sessions + users
    # PodcastRepositoryMixin    -> podcasts + episodes
    # PlaybackRepositoryMixin   -> playback progress

    def close(self):
        """Close database connection for current thread"""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    @classmethod
    def reset(cls):
        """Reset singleton (for testing)"""
        with cls._lock:
            if cls._instance and hasattr(cls._instance, "_local"):
                cls._instance.close()
            cls._instance = None
