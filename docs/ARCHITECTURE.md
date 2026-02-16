# Architecture

This document describes the internal design of Media Library.

## High-Level Overview

```
┌──────────────┐   HTTP/WS    ┌──────────────────┐
│   Browser    │◄────────────►│   web_server.py   │
└──────────────┘              └────────┬─────────┘
                                       │
          ┌────────────────────────────┼────────────────────────────┐
          │                            │                            │
 ┌────────▼─────────┐   ┌─────────────▼──────────┐   ┌────────────▼───────────┐
 │  disc_monitor.py  │   │  content_downloader.py  │   │     metadata.py        │
 │  (macOS native)   │   │  (yt-dlp / trafilatura) │   │ (TMDb/MBrainz/AcoustID)│
 └────────┬──────────┘   └─────────────┬──────────┘   └────────────────────────┘
          │                            │
          ▼                            ▼
 ┌──────────────────┐        ┌──────────────────┐
 │   ripper.py       │        │  Downloaded media  │
 │ (HandBrakeCLI)    │        │  in MEDIA_ROOT     │
 └────────┬──────────┘        └──────────────────┘
          │
          ▼
 ┌──────────────────────────────────────────────────┐
 │               app_state.py (AppState)             │
 │         SQLite WAL · Thread-safe singleton         │
 └──────────────────────────────────────────────────┘
```

## Key Components

### `main.py` — Entry Point & Orchestrator

Parses the `--mode` flag to determine which services to spawn:

| Mode | Services Started | Use Case |
|------|-----------------|----------|
| `full` | Web server + Disc monitor + Content worker | Bare-metal macOS |
| `server` | Web server + Content worker | Docker container |
| `monitor` | Disc monitor only | Native macOS alongside Docker |

Each service runs in its own daemon thread. A `_shutdown_event` coordinates graceful termination on `SIGINT`/`SIGTERM`.

### `app_state.py` — AppState Singleton

The single source of truth. Uses **SQLite WAL mode** for concurrent reads, with a thread-local connection pool to avoid cross-thread issues.

**Repository Mixin Pattern:** `AppState` inherits from 6 domain-specific mixins in `src/repositories/`:

| Mixin | File | Domain |
|-------|------|--------|
| `MediaRepositoryMixin` | `media_repo.py` | Media CRUD, library queries |
| `JobRepositoryMixin` | `job_repo.py` | Rip/encode job queue lifecycle |
| `CollectionRepositoryMixin` | `collection_repo.py` | Collections, playlist tracks |
| `AuthRepositoryMixin` | `auth_repo.py` | Users, sessions, password hashing |
| `PodcastRepositoryMixin` | `podcast_repo.py` | Podcast feeds, episodes |
| `PlaybackRepositoryMixin` | `playback_repo.py` | Per-user playback progress |

Each mixin expects the host class to provide `self._get_conn()`, `self.logger`, and `self.broadcast()`.

**Tables** (see [SCHEMA.md](SCHEMA.md) for full column reference):
- `media` — library items (title, path, type, metadata JSON)
- `jobs` — rip / encode job queue (status, progress, error)
- `content_jobs` — download / article / book ingestion queue
- `users` — pbkdf2-hashed credentials and roles
- `sessions` — server-side session tokens (enables invalidation)
- `collections` — named groups of media
- `collection_items` — ordered membership in collections
- `playlist_tracks` — imported Spotify/external playlist tracks
- `podcasts` / `podcast_episodes` — feed subscriptions
- `playback_progress` — per-user resume positions

**Key patterns:**
- All DB access goes through `AppState` public methods — no direct SQL outside repository mixins
- `_get_conn()` is private; consumers use methods like `get_next_queued_content_job()`
- Thread-local via `threading.local()` for connection-per-thread

### `constants.py` — Centralised Constants

All magic numbers, extension sets, thresholds, and default values live here. Modules import from `constants.py` instead of redefining values inline:

- File extension sets: `VIDEO_EXTENSIONS`, `AUDIO_EXTENSIONS`, `IMAGE_EXTENSIONS`, `DOCUMENT_EXTENSIONS`
- MIME type mapping: `MIME_TYPES`
- Streaming chunk size, log rotation limits
- Auth constants (`PW_HASH_METHOD`, `DEFAULT_SESSION_HOURS`)
- AcoustID/MusicBrainz thresholds
- macOS system volumes to ignore during disc detection

### `web_server.py` — Flask + Socket.IO

Serves the REST API (see [API.md](API.md)) and the SPA from `templates/`. Routes are organised into domain-specific Flask blueprints in `src/routes/` (media, jobs, collections, content, podcasts, playback, users).

**Security layers:**
- Session-based auth with bcrypt password hashing
- Server-side session invalidation on logout
- CSP, HSTS, XSS-Protection, Referrer-Policy, Permissions-Policy headers
- Configurable CORS via `CORS_ALLOWED_ORIGINS` env var
- Upload size enforcement (`MAX_CONTENT_LENGTH` + pre-check)
- First-run setup mode when database has no users

### `disc_monitor.py` — macOS Disc Detection

Polls `diskutil list` for optical drives every 5 seconds. When a disc is detected:

1. Reads the volume name from mount point
2. Strips trailing disc indicators (e.g., "Movie Disc 1" → "Movie")
3. Emits `disc_detected` via Socket.IO
4. Optionally auto-rips based on config

> **macOS only.** This component cannot run inside Docker.

### `ripper.py` — Encoding Pipeline

Wraps **HandBrakeCLI** for disc-to-file encoding:

1. Scans titles on the disc
2. Selects the main feature (or user-specified title)
3. Encodes with configured preset and quality
4. Reports progress via Socket.IO `rip_progress` events
5. Adds completed file to the library

### `content_downloader.py` — Content Ingestion

Handles multiple content types:

| Type | Tool | Output |
|------|------|--------|
| Video URL | yt-dlp | MP4 in MEDIA_ROOT |
| Article URL | trafilatura | HTML archive |
| Book | Manual entry | Metadata record |
| Playlist | yt-dlp + API | Collection of videos |

Runs as a worker thread polling `content_jobs` with 5-second intervals.

### `metadata.py` — External Metadata

Fetches enrichment data from:
- **TMDb** — movies and TV (poster, backdrop, overview, cast, rating)
- **MusicBrainz** — music (artist, album, track listing)
- **AcoustID / Chromaprint** — audio fingerprint identification; sends a fingerprint to AcoustID, receives MusicBrainz recording IDs, then fetches full album metadata + cover art. Falls back to name-based MusicBrainz search when fingerprinting is unavailable.

Images are cached locally in `MEDIA_ROOT/data/metadata/`.

### `utils.py` — Shared Utilities

- `load_config()` — loads `config.json` with `${ENV_VAR:-default}` interpolation
- `get_media_root()` / `get_data_dir()` — portable path resolution
- `setup_logger()` — per-module logger with file rotation
- `send_notification()` — macOS notifications (AppleScript, safely escaped)
- File helpers — `is_media_file()`, `get_file_type()`, `get_file_size()`

### `services/media_identifier.py` — Post-Upload Identification

Identifies uploaded or unknown video files through a three-layer pipeline:

1. **Filename parsing** — uses `guessit` to extract title, year, type (movie/episode),
   resolution, codec, and source from any common naming convention.
2. **MediaInfo extraction** — calls `MediaInfoClient` for duration, which serves as the
   strongest disambiguation signal when TMDB returns multiple results.
3. **TMDB search** — queries TMDB with the parsed title, year, and runtime hint via
   `TMDBClient.search_tmdb()`, then downloads poster and backdrop artwork.

The service saves a metadata JSON sidecar and updates the `media` table via `AppState`.

**Entry points:**
- Automatically via `identify` jobs queued by the upload endpoint
- Manually via `POST /api/media/<id>/identify`

## Data Flow: Disc Rip

```
disc_monitor detects disc
       │
       ▼
AppState.add_job(status="queued")
       │
       ▼
ripper.py picks up job → status="encoding"
       │  ├─ Video (DVD/Blu-ray) → output to movies/
       │  └─ Audio CD            → output to music/
       │
       ├─► Socket.IO: rip_progress (every ~2s)
       │
       ▼
Encoding complete → status="done"
       │
       ├─► metadata.py fetches TMDb / MusicBrainz / AcoustID data
       ├─► Rename: movies/Title (Year).mp4
       │       or: music/Artist/Album (Year)/## - Track.mp3
       ├─► AppState.add_media(...)
       └─► Socket.IO: library_updated
```

## Data Flow: Content Download

```
POST /api/downloads { url }
       │
       ▼
AppState.add_content_job(status="queued")
       │
       ▼
content_worker thread polls → picks up job → status="downloading"
       │
       ▼
yt-dlp / trafilatura processes URL
       │
       ▼
status="done" → AppState.add_media(...)
```

## Data Flow: Upload

```
POST /api/upload (multipart form data)
       │
       ├─► Size check (Content-Length vs max_upload_size_mb)
       │
       ▼
Save to uploads/ directory
       │
       ├─► generate_media_id(file_path)
       ├─► AppState.upsert_media(...)  (initial record, title = filename)
       ├─► return { uploaded: [...] }
       │
       └─► (video files only) Queue "identify" job
                    │
                    ▼
           content_worker picks up identify job
                    │
                    ├─► guessit parses filename → title, year
                    ├─► MediaInfo extracts duration, codec
                    ├─► TMDB search (title + year + runtime hint)
                    ├─► Download poster / backdrop
                    ├─► Save metadata JSON sidecar
                    ├─► AppState.upsert_media(...)  (enriched record)
                    └─► broadcast("library_updated")
```

## Data Flow: Podcast Episode

```
podcast_checker thread (runs every check_interval_hours)
       │
       ▼
feedparser fetches RSS feed
       │
       ▼
New episodes? → AppState.add_podcast_episode(...)
       │
       ├─ auto_download=true → content_worker downloads audio
       │                        → save to podcasts/{podcast_title}/
       │                        → AppState.update_episode(is_downloaded=1)
       │
       └─ auto_download=false → episode tracked but not downloaded
```

## Deployment Architecture

```
┌─────────────────────────────────────────────┐
│              Mac Mini (host)                 │
│                                              │
│  ┌───────────────────┐  ┌────────────────┐  │
│  │  Docker Container  │  │  Native macOS   │  │
│  │  --mode server     │  │  --mode monitor │  │
│  │                    │  │                  │  │
│  │  Flask web server  │  │  disc_monitor    │  │
│  │  Content worker    │  │  ripper          │  │
│  └────────┬───────────┘  └────────┬────────┘  │
│           │                       │            │
│           └───────┬───────────────┘            │
│                   │                            │
│           ┌───────▼───────┐                    │
│           │  Shared volume │                    │
│           │  MEDIA_ROOT    │                    │
│           │  SQLite DB     │                    │
│           └───────────────┘                    │
│                   │                            │
│           ┌───────▼───────┐                    │
│           │ cloudflared    │                    │
│           │ tunnel         │                    │
│           └───────┬───────┘                    │
└───────────────────┼────────────────────────────┘
                    │
            ┌───────▼───────┐
            │  Cloudflare    │
            │  media.domain  │
            └───────────────┘
```

## Configuration Resolution

1. `.env` file loaded by `python-dotenv`
2. `config.json` parsed with `${ENV_VAR:-default}` interpolation
3. Environment variables override defaults
4. `MEDIA_ROOT` drives all path resolution

## Thread Safety

- `AppState` uses **one SQLite connection per thread** via `threading.local()`
- WAL mode allows concurrent readers with a single writer
- The shutdown event (`threading.Event`) coordinates clean exit
- Flask-SocketIO handles its own thread pool for WebSocket connections
