# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Post-upload media identification pipeline**: Uploaded video files are now automatically
  identified via `guessit` filename parsing + TMDB metadata lookup. Posters, cast, genres,
  year, rating, and overview are enriched automatically in the background.
- `MediaIdentifierService` in `src/services/media_identifier.py` — orchestrates filename
  parsing → MediaInfo extraction → TMDB search → poster download → DB update.
- `POST /api/media/<media_id>/identify` endpoint for manual (re-)identification of any
  media item. Accepts optional `title` and `year` overrides in the JSON body.
- `identify` job type: upload endpoint queues an identify job for each video file, processed
  by the content worker thread in the background.
- `guessit` added as a core dependency for structured filename parsing (title, year,
  season/episode, codec, resolution, source).
- Tests: `tests/test_media_identifier.py` — 27 tests covering filename parsing, identify flow,
  upload integration, and the manual identify API endpoint.

## [0.3.0] - 2026-02-07

### Added
- Docker support with `Dockerfile` and `docker-compose.yml` for containerised deployment.
- `--mode` flag on `main.py`: `full`, `server`, `monitor` to separate web from disc ripping.
- `MEDIA_ROOT` environment variable for portable path configuration.
- First-run admin setup flow when no users exist in the database.
- `FLASK_SECRET_KEY` env var for persistent session signing across restarts.
- `CORS_ALLOWED_ORIGINS` env var for restricting WebSocket origins.
- `SECURE_COOKIES` env var for HTTPS deployments.
- `Content-Security-Policy`, `Strict-Transport-Security`, `X-XSS-Protection`, `Referrer-Policy`,
  and `Permissions-Policy` security headers on all responses.
- Server-side session invalidation on logout.
- Upload size enforcement via Flask `MAX_CONTENT_LENGTH` (checks before saving to disk).
- Public API methods on `AppState`: `get_next_queued_content_job()`, `get_collection_by_name()`,
  `update_collection_metadata()`, `get_collection_items()`, `has_users()`, `invalidate_session()`.
- `ContentDownloader` exported from `src/__init__.py`.
- `CHANGELOG.md` (this file).
- `.dockerignore`.
- `bandit` added to dev dependencies for security linting.
- `ffmpeg` / `ffprobe` checks added to `scripts/setup.py`.

### Changed
- **BREAKING**: Plaintext default passwords removed from `config.json`. Users must create accounts
  via first-run setup or `INIT_ADMIN_USER` / `INIT_ADMIN_PASS` env vars.
- All hardcoded `/Users/poppemacmini/Media/...` paths now resolve via `MEDIA_ROOT` env var
  or `${MEDIA_ROOT:-default}` placeholders in `config.json`.
- Config loader now resolves `${ENV_VAR:-default}` patterns in all string values.
- `send_notification()` uses `subprocess.run()` instead of `os.system()` (fixes command injection).
- Article archiving HTML-escapes content (fixes XSS).
- Media IDs now use SHA-256-based hex (12 chars) derived from the file path for deterministic, collision-resistant identification.
- `download_poster()` / `download_backdrop()` consolidated into shared `_download_tmdb_image()`.
- MusicBrainz User-Agent updated to match project name.
- `extract_title_from_volume()` fixed: now correctly strips trailing disc numbers.
- `content_worker` uses `AppState.get_next_queued_content_job()` instead of private `_get_conn()`.
- Collections API uses public `AppState` methods instead of direct DB access.
- `pyproject.toml` updated: version 0.3.0, Python ≥ 3.10, `werkzeug` as explicit dependency,
  optional `[content]` dependency group for `yt-dlp`, `trafilatura`, `feedparser`.
- `requirements.txt` now includes `werkzeug>=3.0.0`.
- `Makefile` targets `run-monitor`, `run-server` now use `python -m src.main` with `--mode`.
- `login.html` supports first-run setup mode.

### Removed
- `default_users` block from `config.json` (security: plaintext passwords).
- `seed_default_users()` usage from `MediaServer` (replaced by env-var-based seeding).
- Stale `src/media_ripper.egg-info/` directory.
- Duplicate `pytest.ini` (consolidated into `pyproject.toml`).

### Fixed
- OS command injection vulnerability in `send_notification()` via unsanitised title/message.
- XSS vulnerability in archived article HTML via unescaped article content.
- Upload endpoint wrote files to disk before checking size limits.
- Logout did not invalidate server-side session (token remained valid until expiry).
- Flask secret key regenerated on every restart (sessions lost). Now configurable via env.
- CORS wide-open (`*`) for WebSocket connections. Now configurable.
- `escAttr()` in `index.html` only escaped quotes, not `<`, `>`, `&`.
- `extract_title_from_volume()` had a no-op `pass` instead of actually stripping disc numbers.

### Security
- Removed plaintext credentials from version-controlled config file.
- Added CSP, HSTS, XSS-Protection, Referrer-Policy, Permissions-Policy headers.
- Cookie `secure` flag configurable for HTTPS deployments.
- Upload size pre-check via `Content-Length` header + Flask `MAX_CONTENT_LENGTH`.

## [0.2.0] - 2025-12-01

### Added
- Web interface with Flask + Socket.IO (single-page application).
- Authentication system with session-based login, user management, roles (admin/user).
- SQLite-backed `AppState` singleton for shared state across threads.
- Content downloader: YouTube/video via yt-dlp, web articles via trafilatura,
  podcast feeds via feedparser, playlist imports.
- Job queue system for asynchronous rip and download processing.
- Collections with drag-and-drop ordering and queue playback.
- Podcast subscriptions with automatic feed checking and episode downloads.
- Playback progress tracking per user with "continue watching" feature.
- File upload with drag-and-drop support.
- Library search across title, director, cast, and genres.
- Dark mode with localStorage persistence.
- Range-request media streaming with chunked responses.
- Metadata editing via web UI.
- Library statistics API.

### Changed
- Entry point unified to `src/main.py` with background threads for all services.
- Ripper now supports audio CDs via ffmpeg (in addition to DVD/Blu-ray via HandBrake).
- Disc monitor collects disc hints (runtime, track count) for better metadata matching.
- Metadata extractor uses disc hints for TMDB/MusicBrainz disambiguation.

## [0.1.0] - 2025-09-01

### Added
- Initial release: DVD/Blu-ray ripping via HandBrakeCLI.
- Automatic disc detection and monitoring.
- TMDB metadata lookup and poster downloading.
- MusicBrainz metadata for audio CDs.
- macOS notifications via osascript.
- JSON configuration file.
- Basic logging with rotation.
