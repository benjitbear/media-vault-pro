# Deployment Guide

## Deployment Architectures

### Single Machine (Bare Metal macOS)

Run all services on one Mac Mini. Best for simple setups.

```bash
python -m src.main --mode full
```

Services started: web server, disc monitor, job worker, content worker, podcast checker.

### Split: Docker (Web) + Native (Disc Monitor)

**Recommended for the Mac Mini.** Docker handles the web server and content downloads, while disc monitoring runs natively for optical drive access.

```
┌─────────────────────────────────────────────┐
│              Mac Mini (host)                 │
│                                              │
│  ┌───────────────────┐  ┌────────────────┐  │
│  │  Docker Container  │  │  Native macOS   │  │
│  │  --mode server     │  │  --mode monitor │  │
│  │  Flask + downloads │  │  disc_monitor   │  │
│  └────────┬───────────┘  └────────┬────────┘  │
│           └───────┬───────────────┘            │
│           ┌───────▼───────┐                    │
│           │  Shared volume │                    │
│           │  MEDIA_ROOT    │                    │
│           └───────────────┘                    │
└────────────────────────────────────────────────┘
```

**Start the Docker container:**

```bash
docker compose up -d
```

**Start the native disc monitor:**

```bash
source .venv/bin/activate
python -m src.main --mode monitor
```

Both processes share the same `MEDIA_ROOT` volume and SQLite database.

---

## Step-by-Step: Docker Deployment

### 1. Prerequisites

- Docker and Docker Compose installed
- `.env` file configured (copy from `.env.example`)

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` — at minimum set:
```bash
MEDIA_ROOT=/path/to/your/media
TMDB_API_KEY=your_key_here
FLASK_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### 3. Build and Start

```bash
docker compose up -d --build
```

### 4. Verify

```bash
# Check container status
docker compose ps

# View logs
docker compose logs -f medialibrary

# Health check
curl http://localhost:8096/
```

### 5. Update

```bash
git pull
docker compose up -d --build
```

---

## Step-by-Step: Bare Metal Deployment

### 1. System Dependencies

```bash
brew install python@3.12 handbrake ffmpeg mediainfo chromaprint
```

### 2. Application Setup

```bash
git clone <repository-url>
cd MediaLibrary
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[content]"
cp .env.example .env
# Edit .env with your settings
```

### 3. Verify Setup

```bash
python scripts/setup.py
```

### 4. Start

```bash
python -m src.main --mode full
```

### 5. Auto-Start on Boot (macOS Launch Agent)

Create `~/Library/LaunchAgents/com.medialibrary.full.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.medialibrary.full</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/MediaLibrary/.venv/bin/python</string>
        <string>-m</string>
        <string>src.main</string>
        <string>--mode</string>
        <string>full</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/MediaLibrary</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/path/to/MediaLibrary/logs/main-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/MediaLibrary/logs/main-stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.medialibrary.full.plist
```

---

## Exposing to the Internet (Cloudflare Tunnel)

See [docs/QUICKSTART.md](docs/QUICKSTART.md#option-c-expose-to-the-internet-cloudflare-tunnel) for full Cloudflare Tunnel setup instructions.

Key settings for production:

```bash
# .env
SECURE_COOKIES=true
CORS_ALLOWED_ORIGINS=https://media.yourdomain.com
FLASK_SECRET_KEY=<long-random-hex>
```

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `MEDIA_ROOT` | Yes | Root directory for all media data |
| `TMDB_API_KEY` | Yes | TMDB API key for metadata |
| `FLASK_SECRET_KEY` | Recommended | Session signing key |
| `ACOUSTID_API_KEY` | No | AcoustID key for audio fingerprinting |
| `JELLYFIN_API_KEY` | No | Jellyfin integration key |
| `INIT_ADMIN_USER` | No | Bootstrap admin username (first run) |
| `INIT_ADMIN_PASS` | No | Bootstrap admin password (first run) |
| `CORS_ALLOWED_ORIGINS` | No | Comma-separated allowed origins |
| `SECURE_COOKIES` | No | `true` for HTTPS deployments |
| `LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `ALLOW_UNSAFE_WERKZEUG` | No | Set in Docker for SocketIO |

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for config.json reference.

---

## Rollback

### Docker

```bash
# Stop current version
docker compose down

# Check out previous version
git checkout v0.2.0

# Rebuild and start
docker compose up -d --build
```

### Bare Metal

```bash
# Stop the running process (Ctrl+C or launchctl unload)
git checkout v0.2.0
pip install -e ".[content]"
python -m src.main --mode full
```

### Database

The SQLite database uses forward-only migrations. To roll back to a previous schema:

```bash
# Back up current database
cp "$MEDIA_ROOT/data/media_ripper.db" "$MEDIA_ROOT/data/media_ripper.db.backup"

# Restore from a previous backup
cp "$MEDIA_ROOT/data/media_ripper.db.pre-upgrade" "$MEDIA_ROOT/data/media_ripper.db"
```

> **Tip:** Always back up the database before upgrading: `cp data/media_ripper.db data/media_ripper.db.$(date +%Y%m%d)`

---

## Health Checks

The Docker container includes a built-in health check:

```bash
curl -f http://localhost:8096/
```

For monitoring, check:
- HTTP response on port 8096
- Log files in `logs/` for errors
- Database file exists and is not locked: `sqlite3 data/media_ripper.db "SELECT count(*) FROM media;"`

---

## Ports

| Port | Service | Configurable |
|------|---------|-------------|
| 8096 | Flask web server | `config.json` → `web_server.port` |
