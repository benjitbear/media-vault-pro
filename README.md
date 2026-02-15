# Media Library

Automated digital media library system: rip physical discs, download online content, subscribe to podcasts, and stream everything from a web UI your whole family can use.

## Features

- **Physical Media Ripping** — DVD, Blu-ray (HandBrakeCLI) and Audio CD (ffmpeg) with automatic disc detection
- **Content Downloads** — YouTube / video URLs (yt-dlp), web article archiving (trafilatura), podcast feeds (feedparser), playlist imports
- **Web Interface** — Single-page app with dark mode, search, collections, drag-and-drop upload, and queue playback
- **Media Streaming** — Chunked range-request streaming for video and audio with playback progress tracking per user
- **Metadata Enrichment** — TMDB for movies, MusicBrainz for music, automatic poster/backdrop/cover art downloads
- **Job Queue** — Asynchronous processing of rips and downloads with real-time WebSocket progress updates
- **Authentication** — Session-based login with admin/user roles, first-run setup flow
- **Podcasts** — Subscribe, auto-check feeds, download episodes
- **Collections** — Create playlists, reorder with drag-and-drop, shuffle playback
- **Docker Ready** — Containerised deployment with `docker-compose`; host behind Cloudflare Tunnel for family access

## Prerequisites

### System
- macOS (disc ripping features are macOS-specific; web server works anywhere)
- Python 3.10+
- DVD/Blu-ray drive (for physical media features)

### Required Software
```bash
brew install handbrake mediainfo ffmpeg
```

### Optional
- [MakeMKV](https://www.makemkv.com/) — for Blu-ray decryption

## Quick Start

```bash
# Clone & enter
git clone <repository-url>
cd MediaLibrary

# Create virtual environment
python -m venv .venv && source .venv/bin/activate

# Install (with all optional content features)
pip install -e ".[content]"

# Configure
cp .env.example .env
# Edit .env — at minimum set TMDB_API_KEY and FLASK_SECRET_KEY

# Run setup checks
python scripts/setup.py

# Start everything
python -m src.main --config config.json
```

Open **http://localhost:8096**. On first launch with auth enabled, you'll be prompted to create an admin account.

### Run Modes

```bash
# Full: web server + disc monitor + all workers (default)
python -m src.main --mode full

# Server only: web server + downloads + podcasts (for Docker)
python -m src.main --mode server

# Monitor only: disc detection + ripping (native macOS)
python -m src.main --mode monitor
```

### Docker

```bash
docker-compose up -d
```

See [Docker & Hosting](#docker--hosting) below for details.

## Configuration

### Environment Variables (`.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `MEDIA_ROOT` | Root directory for all media data | `~/Media` |
| `TMDB_API_KEY` | TMDB API key for metadata lookup | (required) |
| `FLASK_SECRET_KEY` | Session signing key (generate with `python -c "import os; print(os.urandom(32).hex())"`) | random per restart |
| `INIT_ADMIN_USER` | Initial admin username (first run only) | — |
| `INIT_ADMIN_PASS` | Initial admin password (first run only) | — |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allowed origins | `*` (dev) |
| `SECURE_COOKIES` | Set to `true` behind HTTPS reverse proxy | `false` |

### Config File (`config.json`)

Controls encoding settings, automation behaviour, web server port, library cache TTL, podcast intervals, upload limits, and more. Path values support `${MEDIA_ROOT:-default}` interpolation. See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for every key.

## Project Structure

```
MediaLibrary/
├── src/                         # Application source
│   ├── __init__.py              # Package metadata & exports
│   ├── app_state.py             # SQLite-backed singleton state (inherits repo mixins)
│   ├── constants.py             # All constants, extension sets, thresholds, MIME maps
│   ├── content_downloader.py    # yt-dlp, trafilatura, feedparser, playlist imports
│   ├── disc_monitor.py          # Automatic disc detection daemon
│   ├── main.py                  # Unified entry point (threads + web server)
│   ├── metadata.py              # MediaInfo, TMDB, MusicBrainz, AcoustID
│   ├── ripper.py                # HandBrakeCLI (video) & ffmpeg (audio CD)
│   ├── utils.py                 # Config loading, logging, helpers
│   ├── web_server.py            # Flask + Socket.IO web server (30+ API endpoints)
│   ├── clients/                 # External API client modules
│   │   ├── tmdb_client.py       # TMDB API client
│   │   ├── musicbrainz_client.py # MusicBrainz / AcoustID client
│   │   └── mediainfo_client.py  # MediaInfo wrapper
│   ├── repositories/            # Domain-specific DB mixins for AppState
│   │   ├── auth_repo.py         # Users, sessions, password hashing
│   │   ├── collection_repo.py   # Collections, playlist tracks
│   │   ├── job_repo.py          # Rip/encode job queue lifecycle
│   │   ├── media_repo.py        # Media CRUD, library queries
│   │   ├── playback_repo.py     # Per-user playback progress
│   │   └── podcast_repo.py      # Podcast feeds, episodes
│   ├── routes/                  # Flask blueprint route handlers
│   │   ├── media_bp.py          # Library, streaming, metadata routes
│   │   ├── jobs_bp.py           # Job queue routes
│   │   ├── collections_bp.py    # Collection routes
│   │   ├── content_bp.py        # Download, article, upload routes
│   │   ├── podcasts_bp.py       # Podcast routes
│   │   ├── playback_bp.py       # Playback progress routes
│   │   └── users_bp.py          # Auth and user management routes
│   ├── static/                  # Static assets (CSS, JS, images)
│   └── templates/               # Jinja2 HTML templates
│       ├── index.html           # SPA main interface
│       └── login.html           # Login / first-run setup
├── tests/                       # pytest test suite
├── docs/                        # Extended documentation
│   ├── API.md                   # Full API reference with response schemas
│   ├── ARCHITECTURE.md          # System design & data flows
│   ├── CONFIGURATION.md         # Full config.json reference
│   ├── SCHEMA.md                # Database schema reference
│   ├── QUICKSTART.md            # Getting started guide
│   └── troubleshooting.md       # Common issues
├── scripts/                     # Utility & maintenance scripts (see scripts/README.md)
├── config.json                  # Application configuration (see docs/CONFIGURATION.md)
├── requirements.txt             # Python dependencies
├── pyproject.toml               # Build & tool configuration
├── Dockerfile                   # Container image
├── docker-compose.yml           # Container orchestration
├── CHANGELOG.md                 # Version history
├── CONTRIBUTING.md              # Contribution & coding guidelines
├── Makefile                     # Developer shortcuts
└── LICENSE                      # MIT
```

## Testing

```bash
# Run full suite with coverage
make test

# Verbose with stdout
make test-verbose

# Individual test files
pytest tests/test_app_state.py -v
```

## Logging

Log files in `logs/` with 10 MB rotation (5 backups):

| File | Content |
|------|---------|
| `main.log` | Entry point, worker threads |
| `web_server.log` | HTTP requests, API calls |
| `disc_monitor.log` | Disc detection events |
| `ripper.log` | Encoding progress |
| `metadata.log` | TMDB/MusicBrainz lookups |
| `content_downloader.log` | Downloads, articles, podcasts |
| `app_state.log` | Database operations |

## Docker & Hosting

### Docker Compose

The Docker container runs the web server, content downloads, and podcast checker. Disc ripping stays native on macOS (optical drive access).

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f web

# Rebuild after code changes
docker-compose up -d --build
```

### Family Access via Cloudflare Tunnel

To expose your library to family members over the internet:

1. Register a domain and add it to Cloudflare
2. Install `cloudflared` on the Mac Mini: `brew install cloudflared`
3. Authenticate: `cloudflared tunnel login`
4. Create a tunnel: `cloudflared tunnel create media-library`
5. Configure: point `media.yourdomain.com` → `http://localhost:8096`
6. Set `CORS_ALLOWED_ORIGINS=https://media.yourdomain.com` and `SECURE_COOKIES=true` in `.env`

See [docs/QUICKSTART.md](docs/QUICKSTART.md) for detailed hosting instructions.

## Legal Notice

This software is intended for **personal use only** to create backup copies of media you legally own. Respecting copyright laws is your responsibility. Do not use this software to circumvent copy protection for unauthorised purposes, distribute copyrighted content, or rip media you don't own.

## License

MIT License — see [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for coding conventions, testing guidelines, and development workflow.

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Run `make lint && make test`
5. Submit a pull request
