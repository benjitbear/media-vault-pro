# Quick Start Guide

Get Media Library running in under 10 minutes.

## Prerequisites

| Tool | Required For | Install |
|------|-------------|---------|
| Python 3.10+ | Everything | `brew install python@3.12` |
| HandBrakeCLI | Disc ripping | `brew install --cask handbrake` |
| ffmpeg | Media processing | `brew install ffmpeg` |
| mediainfo | File inspection | `brew install mediainfo` |
| chromaprint | Audio fingerprinting | `brew install chromaprint` |
| Docker | Containerized web server | [Docker Desktop](https://docker.com) |

## Option A: Bare Metal (macOS)

### 1. Clone & install

```bash
git clone https://github.com/your-org/MediaLibrary.git
cd MediaLibrary
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[content,dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```bash
MEDIA_ROOT=/Users/you/Media          # Where your media lives
TMDB_API_KEY=your_tmdb_key           # From themoviedb.org
ACOUSTID_API_KEY=your_acoustid_key   # From acoustid.org (free, for audio CD identification)
FLASK_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### 3. Run

```bash
# All services (web + disc monitor + content worker)
make run-full

# Or directly:
python -m src.main --mode full
```

### 4. Open the web UI

Visit **http://localhost:8096**. On first launch you'll be prompted to create an admin account.

---

## Option B: Docker (Web Server) + Native (Disc Monitor)

This is the recommended setup for the Mac Mini. Docker runs the web server and content downloader, while disc monitoring runs natively to access the optical drive.

### 1. Start the web server container

```bash
cp .env.example .env
# Uncomment and edit the values you need (API keys, paths, etc.)

docker compose up -d
```

The container runs in `--mode server` (web + content downloads only).

### 2. Start the native disc monitor

```bash
source .venv/bin/activate
python -m src.main --mode monitor
```

Both processes share the same `MEDIA_ROOT` volume and SQLite database.

### 3. (Optional) Auto-start on boot

**Docker container:** Restart policy is set to `unless-stopped` in `docker-compose.yml`.

**Disc monitor:** Create a macOS Launch Agent:

```bash
cat > ~/Library/LaunchAgents/com.medialibrary.monitor.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.medialibrary.monitor</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/you/MediaLibrary/.venv/bin/python</string>
        <string>-m</string>
        <string>src.main</string>
        <string>--mode</string>
        <string>monitor</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/you/MediaLibrary</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/you/MediaLibrary/logs/monitor.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/you/MediaLibrary/logs/monitor-error.log</string>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.medialibrary.monitor.plist
```

---

## Option C: Expose to the Internet (Cloudflare Tunnel)

Let family members access your library from anywhere without opening firewall ports.

### 1. Install cloudflared

```bash
brew install cloudflare/cloudflare/cloudflared
```

### 2. Authenticate

```bash
cloudflared tunnel login
```

This opens a browser to authorize your Cloudflare account.

### 3. Create a tunnel

```bash
cloudflared tunnel create media-library
```

Note the tunnel UUID printed.

### 4. Configure DNS

```bash
cloudflared tunnel route dns media-library media.yourdomain.com
```

### 5. Create tunnel config

```bash
cat > ~/.cloudflared/config.yml << EOF
tunnel: <TUNNEL_UUID>
credentials-file: /Users/you/.cloudflared/<TUNNEL_UUID>.json

ingress:
  - hostname: media.yourdomain.com
    service: http://localhost:8096
  - service: http_status:404
EOF
```

### 6. Run the tunnel

```bash
# Foreground:
cloudflared tunnel run media-library

# Or install as a service:
sudo cloudflared service install
```

### 7. Enable HTTPS cookies

In `.env`:
```bash
SECURE_COOKIES=true
CORS_ALLOWED_ORIGINS=https://media.yourdomain.com
```

Family can now visit **https://media.yourdomain.com** and log in with their accounts.

---

## Creating User Accounts

After the admin account is set up:

1. Log in as admin
2. Go to Settings → User Management
3. Click "Add User" and set username / password / role

Roles:
- **admin** — full access including user management and settings
- **user** — browse, stream, download, manage own profile

---

## Directory Structure

After setup, your media root will look like:

```
$MEDIA_ROOT/
├── movies/            # Ripped DVDs / Blu-rays (auto-renamed)
├── music/             # Ripped audio CDs (Artist/Album/tracks)
├── articles/
├── books/
├── podcasts/
├── downloads/
├── uploads/
└── data/
    ├── media_ripper.db
    ├── metadata/      # JSON metadata files
    └── thumbnails/    # Posters and backdrops
```

---

## Next Steps

- Read the [API Reference](API.md) for integration details
- See [Architecture](ARCHITECTURE.md) for how the system works internally
- Check [Troubleshooting](troubleshooting.md) if you hit issues
