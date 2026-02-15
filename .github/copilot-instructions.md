# Copilot Instructions — MediaLibrary

## Project Overview

Automated digital media library: rip physical discs (DVD/Blu-ray/Audio CD), download online content (YouTube, articles, podcasts), and stream everything via a Flask web UI. Targets a Mac Mini running macOS with an optical drive.

- **Language:** Python 3.10+
- **Framework:** Flask + Flask-SocketIO
- **Database:** SQLite (WAL mode, thread-local connections)
- **Frontend:** Single-page app in `src/templates/index.html` (Jinja2 + Tailwind CSS + vanilla JS)
- **Entry point:** `python -m src.main --mode full|server|monitor`

## Key Architecture Patterns

### Repository Mixin Pattern
`AppState` (in `src/app_state.py`) is a **thread-safe singleton** that inherits from 6 repository mixins defined in `src/repositories/`:

| Mixin | File | Domain |
|-------|------|--------|
| `MediaRepositoryMixin` | `media_repo.py` | Media CRUD, library queries |
| `JobRepositoryMixin` | `job_repo.py` | Rip/encode job queue lifecycle |
| `CollectionRepositoryMixin` | `collection_repo.py` | Collections, playlist tracks |
| `AuthRepositoryMixin` | `auth_repo.py` | Users, sessions, password hashing |
| `PodcastRepositoryMixin` | `podcast_repo.py` | Podcast feeds, episodes |
| `PlaybackRepositoryMixin` | `playback_repo.py` | Per-user playback progress |

**Contract:** Each mixin expects the host class to provide `self._get_conn()`, `self.logger`, and `self.broadcast()`.

**Rule:** All database access goes through `AppState` public methods. Never write raw SQL outside a repository mixin.

### Thread Model
`main.py` spawns daemon threads based on `--mode`:
- `full` = web server + disc monitor + job worker + content worker + podcast checker
- `server` = web server + content worker + podcast checker (Docker)
- `monitor` = disc monitor + job worker (native macOS)

Threads share state via `AppState` singleton. Each thread gets its own SQLite connection via `threading.local()`.

### Configuration
- `.env` loaded by `python-dotenv` → environment variables
- `config.json` parsed by `utils.load_config()` with `${ENV_VAR:-default}` interpolation
- `MEDIA_ROOT` env var drives all path resolution
- See `docs/CONFIGURATION.md` for every config key

### Constants
All magic numbers, extension sets, thresholds, and defaults live in `src/constants.py`. Always import from there — never redefine extension sets or MIME maps inline.

## Code Conventions

### Imports
```python
from src.constants import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, MIME_TYPES
from src.utils import setup_logger, load_config, get_media_root
from src.app_state import AppState
```

### Logging
Use lazy formatting (not f-strings) in log calls:
```python
# Good
self.logger.info("Job created: %s", job_id)
# Bad — evaluates string even when log level is above INFO
self.logger.info(f"Job created: {job_id}")
```

Each module gets its own logger and log file:
```python
self.logger = setup_logger('module_name', 'module_name.log')
```

### Error Handling
Catch specific exceptions before falling back to `Exception`:
```python
try:
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
except requests.Timeout:
    self.logger.warning("Request timed out: %s", url)
except requests.HTTPError as e:
    self.logger.error("HTTP error: %s", e)
except Exception as e:
    self.logger.error("Unexpected error: %s", e)
```

### Type Hints
All public methods should have parameter and return type annotations. Use Google-style docstrings with `Args:` and `Returns:` sections.

### Web Routes
Routes are defined in `web_server.py` inside `_setup_routes()` as nested closures. When adding routes, follow the existing pattern and group by domain.

### Frontend
The SPA lives in `src/templates/index.html`. Key conventions:
- Use `escHtml()` for HTML content, `escAttr()` for attribute values
- WebSocket events go through the global `socket` object (Socket.IO)
- Dark mode state persisted in `localStorage`

## Testing

### Running Tests
```bash
make test              # Full suite with coverage
make test-verbose      # Verbose output
pytest tests/test_app_state.py -v  # Single file
```

### Test Conventions
- Fixtures are in `tests/conftest.py`
- `app_state` fixture: creates `AppState` with temp DB, yields, then calls `AppState.reset()`
- `test_config` fixture: returns a full config dict (session-scoped)
- Always call `AppState.reset()` in teardown to clear the singleton
- Mock external services (TMDB, MusicBrainz, yt-dlp) — never make real API calls
- Use `tmp_path` for any file I/O in tests
- Config fixtures are created per-test-file; consider using the shared `test_config` from conftest

### Test File Naming
```
tests/test_<module_name>.py  →  tests one src/<module_name>.py
```

## File Structure

```
src/
├── __init__.py              # Package exports
├── app_state.py             # SQLite singleton (inherits repo mixins)
├── constants.py             # All constants, extension sets, thresholds
├── content_downloader.py    # yt-dlp, trafilatura, feedparser, playlists
├── disc_monitor.py          # macOS disc detection (polls diskutil)
├── main.py                  # Entry point, thread orchestration
├── metadata.py              # TMDB, MusicBrainz, AcoustID, MediaInfo
├── ripper.py                # HandBrakeCLI (video) + ffmpeg (audio CD)
├── utils.py                 # Config, logging, file helpers
├── web_server.py            # Flask + Socket.IO (REST API + SPA)
├── repositories/            # Domain-specific DB mixins for AppState
│   ├── __init__.py
│   ├── auth_repo.py
│   ├── collection_repo.py
│   ├── job_repo.py
│   ├── media_repo.py
│   ├── playback_repo.py
│   └── podcast_repo.py
└── templates/
    ├── index.html           # SPA frontend
    └── login.html           # Login / first-run setup
```

## Gotchas

1. **Singleton reset in tests:** Always call `AppState.reset()` before and after creating a test instance, or use the `app_state` fixture which handles this.
2. **Thread-local connections:** `AppState._get_conn()` returns a connection bound to the current thread. Never pass connections between threads.
3. **WAL mode:** SQLite WAL allows concurrent reads but only one writer. Long-running writes can block other writers.
4. **macOS-only features:** `disc_monitor.py` and `ripper.py` depend on macOS APIs (`diskutil`, optical drive access). They cannot run in Docker.
5. **Console entry points:** `pyproject.toml` defines 4 CLI commands: `media-ripper`, `disc-monitor`, `media-server`, `media-server-full`.

## Key Documentation

- `docs/API.md` — REST/WebSocket API reference
- `docs/ARCHITECTURE.md` — System design and data flows
- `docs/CONFIGURATION.md` — Full config.json reference
- `docs/SCHEMA.md` — Database schema reference
- `docs/QUICKSTART.md` — Deployment guides
- `docs/troubleshooting.md` — Common issues and fixes
- `CHANGELOG.md` — Version history
- `scripts/README.md` — Utility script reference
