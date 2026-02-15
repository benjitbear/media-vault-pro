# Database Schema Reference

MediaLibrary uses SQLite with WAL mode. The database file is `media_ripper.db` located in `MEDIA_ROOT/data/`. Schema is initialised in `AppState._init_db()` with automatic migrations for older databases in `_migrate()`.

## Tables

### `media`

Library items — movies, music tracks, documents, images.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | TEXT | PRIMARY KEY | 12-char hex string: `sha256(file_path)[:12]` |
| `title` | TEXT | NOT NULL | Display title |
| `filename` | TEXT | NOT NULL | Filename on disk |
| `file_path` | TEXT | NOT NULL | Absolute path to file |
| `file_size` | INTEGER | 0 | File size in bytes |
| `size_formatted` | TEXT | `''` | Human-readable size (e.g., "1.2 GB") |
| `created_at` | TEXT | | ISO 8601 timestamp of file creation |
| `modified_at` | TEXT | | ISO 8601 timestamp of last modification |
| `year` | TEXT | | Release year |
| `overview` | TEXT | | Synopsis / description |
| `rating` | REAL | | Numeric rating (e.g., TMDB score) |
| `genres` | TEXT | `'[]'` | JSON array of genre strings |
| `director` | TEXT | | Director name |
| `cast_members` | TEXT | `'[]'` | JSON array of actor names |
| `poster_path` | TEXT | | Absolute path to poster image |
| `has_metadata` | INTEGER | 0 | 1 if metadata has been fetched |
| `collection_name` | TEXT | | Name of owning collection (if any) |
| `tmdb_id` | INTEGER | | TMDB ID for movies/TV |
| `media_type` | TEXT | `'video'` | One of: `video`, `audio`, `image`, `document` |
| `source_url` | TEXT | | Original download URL (for yt-dlp content) |
| `artist` | TEXT | | Artist/author name (for audio/books) |
| `duration_seconds` | REAL | | Duration in seconds |
| `added_at` | TEXT | `CURRENT_TIMESTAMP` | When this record was created |

**API note:** `file_path` and `poster_path` are stripped before sending to API clients. `cast_members` is renamed to `cast` in API responses. `has_poster` (boolean) is derived from `poster_path` presence.

---

### `jobs`

Rip and encode job queue.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID |
| `title` | TEXT | NOT NULL | Display title |
| `source_path` | TEXT | NOT NULL | Path to disc volume or source |
| `title_number` | INTEGER | 1 | DVD/Blu-ray title number to rip |
| `disc_type` | TEXT | `'dvd'` | `dvd`, `bluray`, or `audiocd` |
| `disc_hints` | TEXT | `'{}'` | JSON dict with runtime, track count hints |
| `job_type` | TEXT | `'rip'` | `rip` (disc encode) |
| `status` | TEXT | `'queued'` | `queued`, `encoding`, `done`, `failed`, `cancelled` |
| `progress` | REAL | 0 | Encoding progress (0.0 – 100.0) |
| `eta` | TEXT | | Estimated time remaining |
| `fps` | REAL | | Current encoding FPS |
| `error_message` | TEXT | | Error details if `status = 'failed'` |
| `output_path` | TEXT | | Path to encoded output file |
| `started_at` | TEXT | | When encoding began |
| `completed_at` | TEXT | | When encoding finished |
| `created_at` | TEXT | `CURRENT_TIMESTAMP` | When the job was created |

---

### `content_jobs`

Download, article, and book ingestion queue. Managed by `ContentDownloader`.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID |
| `job_type` | TEXT | NOT NULL | `video`, `article`, `book`, `playlist` |
| `url` | TEXT | | Source URL |
| `title` | TEXT | | Display title |
| `status` | TEXT | `'queued'` | `queued`, `downloading`, `done`, `failed` |
| `error_message` | TEXT | | Error details if failed |
| `output_path` | TEXT | | Path to downloaded file |
| `extra_data` | TEXT | `'{}'` | JSON dict with job-type-specific metadata |
| `created_at` | TEXT | `CURRENT_TIMESTAMP` | When the job was created |

---

### `users`

Authentication accounts.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `username` | TEXT | PRIMARY KEY | Unique username |
| `password_hash` | TEXT | NOT NULL | pbkdf2:sha256 hash |
| `role` | TEXT | `'user'` | `admin` or `user` |
| `created_at` | TEXT | `CURRENT_TIMESTAMP` | Account creation time |

---

### `sessions`

Server-side session store. Enables session invalidation on logout.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `token` | TEXT | PRIMARY KEY | Session token (hex string) |
| `username` | TEXT | | Associated username |
| `created_at` | TEXT | `CURRENT_TIMESTAMP` | Session creation time |
| `expires_at` | TEXT | | Expiry timestamp (config: `auth.session_hours`) |

---

### `collections`

Named groups of media items for playlists and organisation.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Collection ID |
| `name` | TEXT | UNIQUE NOT NULL | Display name (used in API paths) |
| `description` | TEXT | `''` | Optional description |
| `collection_type` | TEXT | `'collection'` | `collection` or `playlist` |
| `created_at` | TEXT | `CURRENT_TIMESTAMP` | Creation time |

---

### `collection_items`

Ordered membership of media items in collections.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `collection_id` | INTEGER | | FK → `collections.id` (CASCADE) |
| `media_id` | TEXT | | FK → `media.id` (CASCADE) |
| `sort_order` | INTEGER | 0 | Display/playback order |

**Primary key:** (`collection_id`, `media_id`)

---

### `playlist_tracks`

Tracks imported from Spotify/external playlists. These track external metadata and can optionally link to local media.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Track ID |
| `collection_id` | INTEGER | NOT NULL | FK → `collections.id` (CASCADE) |
| `sort_order` | INTEGER | 0 | Track order in playlist |
| `title` | TEXT | NOT NULL | Track title |
| `artist` | TEXT | `''` | Artist name |
| `album` | TEXT | `''` | Album name |
| `duration_ms` | INTEGER | 0 | Duration in milliseconds |
| `artwork_url` | TEXT | `''` | External artwork URL |
| `spotify_uri` | TEXT | `''` | Spotify URI (e.g., `spotify:track:...`) |
| `isrc` | TEXT | `''` | ISRC code for matching |
| `matched_media_id` | TEXT | | FK → `media.id` (SET NULL) — local match |

---

### `podcasts`

Podcast feed subscriptions.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID |
| `feed_url` | TEXT | UNIQUE NOT NULL | RSS/Atom feed URL |
| `title` | TEXT | `''` | Podcast title |
| `author` | TEXT | `''` | Podcast author/host |
| `description` | TEXT | `''` | Podcast description |
| `artwork_url` | TEXT | | Remote artwork URL |
| `artwork_path` | TEXT | | Local cached artwork path |
| `last_checked` | TEXT | | When the feed was last polled |
| `check_interval_hours` | INTEGER | 6 | Per-feed check interval override |
| `is_active` | INTEGER | 1 | 0 = paused, 1 = active |
| `created_at` | TEXT | `CURRENT_TIMESTAMP` | Subscription time |

---

### `podcast_episodes`

Individual podcast episodes.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | TEXT | PRIMARY KEY | UUID |
| `podcast_id` | TEXT | NOT NULL | FK → `podcasts.id` (CASCADE) |
| `title` | TEXT | NOT NULL | Episode title |
| `audio_url` | TEXT | | Remote audio URL |
| `file_path` | TEXT | | Local file path (if downloaded) |
| `duration_seconds` | REAL | | Episode duration |
| `published_at` | TEXT | | Publication date |
| `description` | TEXT | `''` | Episode notes/description |
| `is_downloaded` | INTEGER | 0 | 1 if locally downloaded |
| `created_at` | TEXT | `CURRENT_TIMESTAMP` | Record creation time |

---

### `playback_progress`

Per-user playback position tracking.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Row ID |
| `media_id` | TEXT | NOT NULL | FK → `media.id` (CASCADE) |
| `username` | TEXT | `'anonymous'` | Username (from session) |
| `position_seconds` | REAL | 0 | Saved playback position |
| `duration_seconds` | REAL | 0 | Total media duration |
| `finished` | INTEGER | 0 | 1 if user finished watching (≥95% progress) |
| `updated_at` | TEXT | `CURRENT_TIMESTAMP` | Last update time |

**Unique constraint:** (`media_id`, `username`) — one progress record per user per media item.

---

## Foreign Keys

All foreign keys use `ON DELETE CASCADE` (deleting a parent removes children) except:
- `playlist_tracks.matched_media_id` → `media.id` uses `ON DELETE SET NULL` (deleting media unlinks the match but keeps the playlist track)

## Indexes

SQLite automatically creates indexes for PRIMARY KEY and UNIQUE columns. No additional indexes are explicitly created.

## Migrations

`AppState._migrate()` handles schema upgrades for existing databases by adding missing columns. This runs on every startup and is idempotent. New columns added via migration get default values matching the schema above.
