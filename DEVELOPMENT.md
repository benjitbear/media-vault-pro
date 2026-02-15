# Development Guide

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.10+ | `brew install python@3.12` |
| HandBrakeCLI | Latest | `brew install --cask handbrake` |
| ffmpeg | Latest | `brew install ffmpeg` |
| mediainfo | Latest | `brew install mediainfo` |
| chromaprint | Latest | `brew install chromaprint` |

Optional:
- [MakeMKV](https://www.makemkv.com/) — Blu-ray decryption
- Docker — for containerised testing

## Initial Setup

```bash
# Clone the repository
git clone <repository-url>
cd MediaLibrary

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install all dependencies (production + content features + dev tools)
pip install -e ".[content,dev]"

# Copy environment config
cp .env.example .env
# Edit .env — set TMDB_API_KEY and FLASK_SECRET_KEY at minimum

# Verify system dependencies
python scripts/setup.py
```

## Running the Application

```bash
# Full mode (all services)
make run-full

# Or directly:
python -m src.main --mode full

# Server only (no disc monitoring)
make run-server

# Disc monitor only
make run-monitor
```

The web UI is available at **http://localhost:8096**.

### CLI Flags

| Flag | Description |
|------|-------------|
| `--config PATH` | Path to config file (default: `config.json`) |
| `--mode full\|server\|monitor` | Run mode |
| `--host HOST` | Override bind address |
| `--port PORT` | Override port |
| `--no-monitor` | Deprecated; use `--mode server` |
| `--no-worker` | Disable job worker (no automatic ripping) |
| `--background` | Suppress console output |

### Console Entry Points

Defined in `pyproject.toml`:

| Command | Module | Description |
|---------|--------|-------------|
| `media-server-full` | `src.main:main` | All services |
| `media-server` | `src.web_server:main` | Web server only |
| `media-ripper` | `src.ripper:main` | Ripper CLI |
| `disc-monitor` | `src.disc_monitor:main` | Disc monitor CLI |

## Project Structure

```
src/
├── __init__.py              # Package metadata & exports
├── app_state.py             # SQLite singleton (inherits 6 repo mixins)
├── constants.py             # All constants, extension sets, thresholds
├── content_downloader.py    # yt-dlp, trafilatura, feedparser, playlists
├── disc_monitor.py          # macOS disc detection daemon
├── main.py                  # Entry point, thread orchestration
├── metadata.py              # Metadata extraction facade
├── ripper.py                # HandBrakeCLI (video) & ffmpeg (audio CD)
├── utils.py                 # Config, logging, file helpers
├── web_server.py            # Flask + Socket.IO server setup
├── clients/                 # External API clients
│   ├── tmdb_client.py       # TMDB API
│   ├── musicbrainz_client.py # MusicBrainz + AcoustID
│   └── mediainfo_client.py  # MediaInfo wrapper
├── repositories/            # DB mixin classes for AppState
│   ├── auth_repo.py         # Users & sessions
│   ├── collection_repo.py   # Collections & playlists
│   ├── job_repo.py          # Job queue
│   ├── media_repo.py        # Media CRUD
│   ├── playback_repo.py     # Playback progress
│   └── podcast_repo.py      # Podcasts & episodes
├── routes/                  # Flask blueprint route handlers
│   ├── media_bp.py          # Library, streaming, metadata
│   ├── jobs_bp.py           # Job queue
│   ├── collections_bp.py    # Collections
│   ├── content_bp.py        # Downloads, articles, uploads
│   ├── podcasts_bp.py       # Podcasts
│   ├── playback_bp.py       # Playback progress
│   └── users_bp.py          # Auth & user management
├── static/                  # CSS, JS, images
└── templates/               # Jinja2 templates
    ├── index.html           # SPA main interface
    └── login.html           # Login / first-run setup
```

## Key Architecture Patterns

### Repository Mixin Pattern
`AppState` inherits from 6 repository mixins. Each mixin expects `self._get_conn()`, `self.logger`, and `self.broadcast()` from the host class. All database access goes through `AppState` public methods — never write raw SQL outside a mixin.

### Thread Model
`main.py` spawns daemon threads based on `--mode`. Threads share state via the `AppState` singleton. Each thread gets its own SQLite connection via `threading.local()`.

### Configuration
- `.env` → environment variables (loaded by `python-dotenv`)
- `config.json` → application settings (supports `${ENV_VAR:-default}` interpolation)
- `MEDIA_ROOT` env var → drives all path resolution

## Code Style

### Formatting

```bash
make format    # black + isort
make lint      # flake8 + mypy
```

### Conventions

- **Imports:** Always import constants from `src/constants.py`
- **Logging:** Use lazy formatting (`%s`), not f-strings, in log calls
- **Type hints:** All public methods need parameter and return annotations
- **Docstrings:** Google-style with `Args:` and `Returns:` sections
- **Error handling:** Catch specific exceptions before `Exception`

See [CONTRIBUTING.md](CONTRIBUTING.md) for full coding standards.

## Debugging

### Log Files

Logs are in the `logs/` directory with 10 MB rotation (5 backups):

| File | Content |
|------|---------|
| `main.log` | Entry point, worker threads |
| `web_server.log` | HTTP requests, API calls |
| `disc_monitor.log` | Disc detection events |
| `ripper.log` | Encoding progress |
| `metadata.log` | TMDB/MusicBrainz lookups |
| `content_downloader.log` | Downloads, articles, podcasts |
| `app_state.log` | Database operations |

### Verbose Logging

```bash
LOG_LEVEL=DEBUG python -m src.main --mode full
```

Or set in `config.json`:
```json
"logging": { "debug": true }
```

### Debugging Scripts

See [scripts/README.md](scripts/README.md) for utility scripts:

| Script | Purpose |
|--------|---------|
| `debug_acoustid.py` | Test AcoustID fingerprint lookup |
| `debug_metadata.py` | Diagnose MusicBrainz search issues |
| `setup.py` | Verify system dependencies |

### Common Issues

See [docs/troubleshooting.md](docs/troubleshooting.md) for solutions to frequent problems.

## Database

SQLite in WAL mode at `MEDIA_ROOT/data/media_ripper.db`. Schema is in [docs/SCHEMA.md](docs/SCHEMA.md).

```bash
# Inspect the database
sqlite3 "$MEDIA_ROOT/data/media_ripper.db"

# Check WAL mode
sqlite3 "$MEDIA_ROOT/data/media_ripper.db" "PRAGMA journal_mode;"
```

## Making Changes

1. Create a feature branch from `main`
2. Write tests for your changes
3. Run `make lint && make test`
4. Submit a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow.
