# Testing Guide

## Quick Start

```bash
# Activate virtual environment
source .venv/bin/activate

# Install dev dependencies (if not already)
pip install -e ".[dev]"

# Run full test suite with coverage
make test

# Verbose output
make test-verbose

# Coverage report (HTML)
make test-coverage
# Open htmlcov/index.html in a browser
```

## Running Tests

### Full Suite

```bash
pytest
```

The default configuration in `pyproject.toml` runs with coverage enabled:

```ini
addopts = "-v --cov=src --cov-report=html --cov-report=term-missing"
```

### Individual Files

```bash
pytest tests/test_app_state.py -v
pytest tests/test_web_server.py -v
pytest tests/test_ripper.py -v
```

### Individual Tests

```bash
pytest -k "test_add_media" -v
pytest tests/test_app_state.py::TestAppState::test_add_media -v
```

### By Marker

```bash
pytest -m unit -v
```

## Test Structure

```
tests/
├── conftest.py                     # Shared fixtures
├── test_app_state.py               # AppState singleton & DB operations
├── test_collections.py             # Collection repository
├── test_content_downloader.py      # Content downloader core
├── test_content_downloader_extended.py  # Extended downloader tests
├── test_disc_monitor.py            # Disc detection
├── test_file_naming.py             # File naming templates
├── test_jobs_routes.py             # Job queue routes
├── test_main.py                    # Entry point / thread orchestration
├── test_media_routes.py            # Media API routes
├── test_mediainfo_client.py        # MediaInfo client
├── test_metadata.py                # Metadata extraction
├── test_musicbrainz_client.py      # MusicBrainz client
├── test_playback.py                # Playback progress
├── test_podcast_repo.py            # Podcast repository
├── test_ripper.py                  # Ripper / encoding
├── test_runtime_validation.py      # Runtime checks
├── test_tmdb_client.py             # TMDB client
├── test_upload.py                  # File upload
├── test_users.py                   # User management & auth
├── test_utils_extended.py          # Utility functions
└── test_web_server.py              # Web server setup & routes
```

### Naming Convention

Test files follow `tests/test_<module_name>.py` → tests `src/<module_name>.py`.

## Key Fixtures

Defined in `tests/conftest.py`:

| Fixture | Scope | Description |
|---------|-------|-------------|
| `app_state` | function | Creates `AppState` with a temp DB, yields it, calls `AppState.reset()` on teardown |
| `test_config` | session | Returns a full config dict matching `config.json` structure |
| `mock_dvd_structure` | function | Creates a fake DVD directory tree in `tmp_path` |
| `sample_metadata` | function | Returns a sample metadata dict for testing |

### Singleton Reset

The `AppState` singleton persists across tests unless explicitly reset. Always use the `app_state` fixture or manually call `AppState.reset()`:

```python
def test_something(app_state):
    # app_state is already initialised with a temp DB
    app_state.upsert_media({...})
    # fixture handles reset in teardown
```

## Writing Tests

### Conventions

1. **Use fixtures** — prefer the shared fixtures in `conftest.py`
2. **Mock external services** — never make real API calls (TMDB, MusicBrainz, yt-dlp)
3. **Use `tmp_path`** — for any file I/O in tests
4. **Reset singletons** — always call `AppState.reset()` in teardown
5. **Test one thing** — each test function should verify a single behaviour

### Example

```python
def test_add_and_retrieve_media(app_state):
    """Test adding a media item and retrieving it."""
    media_id = app_state.upsert_media({
        'id': 'abc123def456',
        'title': 'Test Movie',
        'filename': 'test.mp4',
        'file_path': '/tmp/test.mp4',
        'media_type': 'video',
    })

    item = app_state.get_media('abc123def456')
    assert item is not None
    assert item['title'] == 'Test Movie'
```

### Mocking External Services

```python
from unittest.mock import patch, MagicMock

def test_tmdb_search(app_state):
    with patch('src.clients.tmdb_client.requests.get') as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {'results': [{'id': 550, 'title': 'Fight Club'}]}
        )
        # ... test code
```

## Coverage

### Viewing Coverage

After running `make test` or `make test-coverage`:

- **Terminal:** Coverage summary is printed to stdout
- **HTML report:** Open `htmlcov/index.html` in a browser

### Coverage Expectations

- **Target:** 80%+ line coverage across `src/`
- **Critical paths:** Authentication, database operations, and API routes should have higher coverage
- **Exclusions:** macOS-specific code (`disc_monitor.py`, parts of `ripper.py`) may have lower coverage in CI environments

## Linting

```bash
make lint      # flake8 + mypy
make format    # black + isort (auto-fix)
```

### Tools

| Tool | Purpose | Config |
|------|---------|--------|
| `flake8` | Style checking | default settings |
| `mypy` | Type checking | `pyproject.toml` `[tool.mypy]` |
| `black` | Code formatting | `pyproject.toml` `[tool.black]` |
| `isort` | Import sorting | `pyproject.toml` `[tool.isort]` |
| `bandit` | Security linting | dev dependency |

## CI/CD

Tests run automatically on push and pull requests via GitHub Actions. See `.github/workflows/tests.yml`.
