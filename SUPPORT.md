# Support

## Getting Help

### 1. Check Existing Documentation

- [README.md](README.md) — Overview and quick start
- [docs/QUICKSTART.md](docs/QUICKSTART.md) — Detailed setup instructions
- [docs/troubleshooting.md](docs/troubleshooting.md) — Common issues and solutions
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) — Full config reference
- [docs/API.md](docs/API.md) — REST and WebSocket API reference
- [DEVELOPMENT.md](DEVELOPMENT.md) — Local development setup

### 2. Check the Logs

Log files are in the `logs/` directory. Run with verbose logging for more detail:

```bash
LOG_LEVEL=DEBUG python -m src.main --mode full
```

### 3. Search Existing Issues

Check [GitHub Issues](../../issues) to see if your problem has already been reported or resolved.

### 4. Open an Issue

If you can't find an answer, [open a new issue](../../issues/new/choose) with:

- **OS and Python version** (`python --version`)
- **Media Library version** (`python -c "import src; print(src.__version__)"`)
- **Steps to reproduce** the problem
- **Relevant log output** from `logs/`
- **Expected vs. actual behaviour**

### 5. Contributing a Fix

Found the problem yourself? Pull requests are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

## Useful Commands

```bash
# Check system dependencies
python scripts/setup.py

# Verify the installation
python -c "from src import AppState, Ripper, MetadataExtractor; print('OK')"

# Test database connectivity
python -c "from src.app_state import AppState; a = AppState('/tmp/test.db'); print('DB OK'); AppState.reset()"

# Check version
python -c "import src; print(src.__version__)"
```

## Reporting Security Issues

For security vulnerabilities, **do not open a public issue**. See [SECURITY.md](SECURITY.md) for responsible disclosure instructions.
