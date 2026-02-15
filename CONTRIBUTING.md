# Contributing to MediaLibrary

## Getting Started

```bash
git clone <repository-url>
cd MediaLibrary
python -m venv .venv && source .venv/bin/activate
pip install -e ".[content,dev]"
cp .env.example .env
# Edit .env — set TMDB_API_KEY and FLASK_SECRET_KEY at minimum
python scripts/setup.py
```

## Development Workflow

1. Create a feature branch from `main`
2. Make your changes with tests
3. Run checks: `make lint && make test`
4. Submit a pull request

## Code Conventions

### Imports

Always import constants from `src/constants.py` — never redefine extension sets, MIME maps, or thresholds inline:

```python
from src.constants import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, MIME_TYPES
from src.utils import setup_logger, load_config
from src.app_state import AppState
```

### Logging

Use lazy formatting (not f-strings) in log calls:

```python
# Good — string formatting only happens if the message is logged
self.logger.info("Processing job: %s", job_id)

# Bad — f-string is always evaluated regardless of log level
self.logger.info(f"Processing job: {job_id}")
```

Each module gets its own logger and log file:

```python
self.logger = setup_logger('module_name', 'module_name.log')
```

### Type Hints & Docstrings

All public methods should have parameter and return type annotations. Use Google-style docstrings:

```python
def add_media(self, title: str, file_path: str, media_type: str = "video") -> str:
    """Add a media item to the library.

    Args:
        title: Display title for the media item.
        file_path: Absolute path to the file on disk.
        media_type: One of 'video', 'audio', 'image', 'document'.

    Returns:
        The generated media ID (12-char hex string).
    """
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

### Database Access

All database access goes through `AppState` public methods. Never write raw SQL outside a repository mixin in `src/repositories/`. To add a new data operation:

1. Add the method to the appropriate mixin in `src/repositories/`
2. The mixin can use `self._get_conn()`, `self.logger`, and `self.broadcast()`
3. The method becomes available on `AppState` automatically

### Web Routes

Routes are defined as Flask blueprints in `src/routes/`. Each blueprint handles a specific domain (media, jobs, collections, content, podcasts, playback, users). When adding a new route, add it to the appropriate blueprint file.

### Configuration

When adding a new config key:

1. Add it to `config.json` with a sensible default
2. Document it in `docs/CONFIGURATION.md`
3. Use `${ENV_VAR:-default}` syntax for paths that should be configurable via environment

## Testing

### Running Tests

```bash
make test              # Full suite with coverage report
make test-verbose      # Verbose output
pytest tests/test_app_state.py -v  # Single file
pytest -k "test_name"  # Single test by name
```

### Writing Tests

- **Fixtures** are in `tests/conftest.py`:
  - `app_state` — creates `AppState` with a temp DB, yields it, then calls `AppState.reset()`. Use for any test that touches the database.
  - `test_config` — returns a full config dict (session-scoped). Use for tests that need configuration.
  - `mock_dvd_structure` — creates a fake DVD directory tree in `tmp_path`.
  - `sample_metadata` — returns a sample metadata dict.

- **Singleton reset:** Always use the `app_state` fixture or manually call `AppState.reset()` before/after creating test instances. The singleton persists across tests otherwise.

- **Mock external services:** Never make real API calls in tests. Mock TMDB, MusicBrainz, yt-dlp, and other external services.

- **File I/O:** Use `tmp_path` (pytest built-in) for any file operations in tests.

- **Naming:** `tests/test_<module_name>.py` tests `src/<module_name>.py`.

### Linting & Formatting

```bash
make lint              # flake8 + mypy
make format            # black + isort
```

## Project Structure

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system design and [docs/SCHEMA.md](docs/SCHEMA.md) for the database schema.

## Documentation

When making changes, update the relevant docs:

| Change | Update |
|--------|--------|
| New API endpoint | `docs/API.md` |
| New config key | `docs/CONFIGURATION.md` and `config.json` |
| New DB table/column | `docs/SCHEMA.md` and `AppState._init_db()` / `_migrate()` |
| New env variable | `.env.example` and `docs/CONFIGURATION.md` |
| Architecture change | `docs/ARCHITECTURE.md` |
| New utility script | `scripts/README.md` |
