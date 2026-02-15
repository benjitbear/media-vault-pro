# Configuration Reference

Complete reference for `config.json`. All string values support `${ENV_VAR:-default}` interpolation — environment variables are expanded at load time with optional fallback defaults.

## `output` — Encoding & File Output

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `base_directory` | string | `${MEDIA_ROOT:-~/Media}` | Root directory for all media. Ripped videos go to `<base>/movies/`, audio CDs to `<base>/music/`. |
| `format` | string | `"mp4"` | Output container format for video rips. |
| `video_encoder` | string | `"x264"` | Video codec passed to HandBrakeCLI. |
| `quality` | integer | `22` | Constant quality factor (CRF). Lower = better quality, larger files. 18–22 recommended. |
| `audio_encoder` | string | `"aac"` | Audio codec for video rips. |
| `audio_bitrate` | string | `"192"` | Audio bitrate in kbps for video rips. |

## `metadata` — Metadata Extraction

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `save_to_json` | boolean | `true` | Write metadata to a `.json` sidecar file alongside each media file. The library scanner reads these to populate the database. |
| `extract_chapters` | boolean | `true` | Extract chapter information from video files via MediaInfo. |
| `extract_subtitles` | boolean | `true` | Extract subtitle tracks during ripping. |
| `extract_audio_tracks` | boolean | `true` | Extract all audio tracks (multi-language) during ripping. |
| `fetch_online_metadata` | boolean | `true` | Fetch metadata from TMDB (video) or MusicBrainz (audio) after ripping. |
| `acoustid_fingerprint` | boolean | `true` | Use AcoustID/Chromaprint audio fingerprinting for CD identification. Requires `ACOUSTID_API_KEY` in `.env` and `fpcalc` on PATH. Falls back to name-based MusicBrainz search when disabled or unavailable. |

## `automation` — Disc Detection Behaviour

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `auto_detect_disc` | boolean | `true` | Automatically detect inserted discs and create rip jobs. |
| `auto_eject_after_rip` | boolean | `true` | Eject the disc after encoding completes. |
| `notification_enabled` | boolean | `false` | Send macOS notifications (via `osascript`) on rip start/complete. |

## `web_server` — Flask Server

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `true` | Start the web server. Set `false` for headless monitor-only mode. |
| `port` | integer | `8096` | HTTP listen port. |
| `host` | string | `"0.0.0.0"` | Bind address. Use `"127.0.0.1"` to restrict to localhost. |
| `library_name` | string | `"My Media Library"` | Display name shown in the web UI header. |

## `disc_detection` — Optical Drive Monitoring

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `check_interval_seconds` | integer | `5` | How often to poll `diskutil list` for new optical discs. |
| `mount_path` | string | `"/Volumes"` | macOS mount point to scan for disc volumes. |

## `handbrake` — HandBrakeCLI Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `preset` | string | `"Fast 1080p30"` | HandBrake encoding preset. Run `HandBrakeCLI --preset-list` to see available options. |
| `additional_options` | list | `[]` | Extra CLI flags passed to HandBrakeCLI (e.g., `["--encoder-tune", "film"]`). |

## `auth` — Authentication

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `true` | Enable session-based authentication. When `false`, all endpoints are public. |
| `session_hours` | integer | `24` | Session cookie lifetime in hours. After expiry, users must log in again. |

**First-run flow:** If auth is enabled and the database has no users, the login page becomes a "Create Admin Account" form. You can also bootstrap an admin account via `INIT_ADMIN_USER` / `INIT_ADMIN_PASS` environment variables (used once, on first start only).

**Roles:** `admin` can manage users (create, delete, change passwords). `user` has full library access but cannot manage other accounts.

## `library_cache` — Scan Caching

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `ttl_seconds` | integer | `300` | Cache lifetime for library scan results. The library is re-scanned from the filesystem when this TTL expires. Set lower for frequently changing libraries. |

## `logging` — Log Verbosity

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `debug` | boolean | `false` | Enable DEBUG-level logging across all modules. |
| `progress_indicator` | boolean | `false` | Log encoding progress to stdout (useful for interactive terminals). |

## `jellyfin` — Jellyfin Integration

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `false` | Enable Jellyfin library refresh after new media is added. |
| `library_path` | string | `""` | Path to the Jellyfin media library (must match the path Jellyfin uses). |
| `api_url` | string | `""` | Jellyfin server URL (e.g., `"http://localhost:8096"`). |
| `api_key` | string | `""` | Jellyfin API key. Set via `JELLYFIN_API_KEY` env var instead of storing in config.json. |

## `uploads` — File Upload

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `true` | Allow file uploads via the web UI and API. |
| `max_upload_size_mb` | integer | `4096` | Maximum upload file size in megabytes. Flask enforces this via `MAX_CONTENT_LENGTH`. |
| `upload_directory` | string | `"${MEDIA_ROOT}/uploads"` | Directory where uploaded files are saved. |

## `podcasts` — Podcast Subscriptions

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `true` | Enable podcast features (feed checking, episode downloads). |
| `check_interval_hours` | integer | `6` | How often the background thread checks feeds for new episodes. |
| `auto_download` | boolean | `true` | Automatically download new episodes when discovered. |
| `download_directory` | string | `"${MEDIA_ROOT}/podcasts"` | Directory for downloaded podcast episodes. |
| `max_episodes_per_feed` | integer | `50` | Maximum number of episodes to track per feed (oldest are dropped). |

## `downloads` — Content Ingestion

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `true` | Enable video/article/book download features. |
| `download_directory` | string | `"${MEDIA_ROOT}/downloads"` | Directory for downloaded videos. |
| `ytdlp_format` | string | `"bestvideo[height<=1080]+bestaudio/best"` | yt-dlp format selection string. See [yt-dlp format docs](https://github.com/yt-dlp/yt-dlp#format-selection). |
| `articles_directory` | string | `"${MEDIA_ROOT}/articles"` | Directory for archived web articles (HTML). |
| `books_directory` | string | `"${MEDIA_ROOT}/books"` | Directory for catalogued books. |

## `file_naming` — Post-Rip File Renaming

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `video_template` | string | `"{title} ({year})"` | Filename template for ripped videos. |
| `audio_template` | string | `"{artist}/{album} ({year})/{track:02d} - {title}"` | Path template for ripped audio tracks. Creates subdirectories automatically. |
| `rename_after_rip` | boolean | `true` | Rename files after metadata is fetched. When `false`, files keep their raw rip names. |

### Template Variables

**Video templates:** `{title}`, `{year}`, `{director}`

**Audio templates:** `{title}`, `{artist}`, `{album}`, `{year}`, `{track}` (track number, use `{track:02d}` for zero-padded), `{disc}` (disc number)

## Environment Variables

In addition to config.json, these environment variables control behaviour. Set them in `.env` or export them before running.

| Variable | Description | Default |
|----------|-------------|---------|
| `MEDIA_ROOT` | Root directory for all media data | `~/Media` |
| `TMDB_API_KEY` | TMDB API key for movie/TV metadata | (required for metadata) |
| `ACOUSTID_API_KEY` | AcoustID API key for audio fingerprinting | (optional) |
| `JELLYFIN_API_KEY` | Jellyfin API key for library refresh | (optional) |
| `FLASK_SECRET_KEY` | Session cookie signing key | random per restart |
| `INIT_ADMIN_USER` | Bootstrap admin username (first run only) | — |
| `INIT_ADMIN_PASS` | Bootstrap admin password (first run only) | — |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allowed origins | `*` |
| `SECURE_COOKIES` | Set `true` behind HTTPS proxy | `false` |
| `LOG_LEVEL` | Override log level (`DEBUG`, `INFO`, `WARNING`) | `INFO` |
| `ALLOW_UNSAFE_WERKZEUG` | Allow Werkzeug dev server in SocketIO (set in Docker) | `false` |
