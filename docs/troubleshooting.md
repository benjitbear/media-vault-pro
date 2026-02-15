# Troubleshooting

## Common Issues

### App won't start

**Symptom:** `ModuleNotFoundError` on import.

```
ModuleNotFoundError: No module named 'flask'
```

**Fix:** Activate the virtual environment and install dependencies:
```bash
source .venv/bin/activate
pip install -e ".[content]"
```

---

**Symptom:** `FLASK_SECRET_KEY` warning or crash.

**Fix:** Generate a secret key and add it to `.env`:
```bash
echo "FLASK_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> .env
```

---

### Port 8096 already in use

**Symptom:** `OSError: [Errno 48] Address already in use`

**Fix:** Find and kill the existing process:
```bash
lsof -ti :8096 | xargs kill -9
```

Or change the port in `config.json`:
```json
"web_server": { "port": 9090 }
```

---

### SQLite database locked

**Symptom:** `sqlite3.OperationalError: database is locked`

This can happen when both Docker and native processes access the DB simultaneously under heavy load.

**Fixes:**
1. Ensure WAL mode is active (it should be by default):
   ```bash
   sqlite3 data/media_ripper.db "PRAGMA journal_mode;"
   # Should print: wal
   ```
2. If the DB is corrupted, recover:
   ```bash
   sqlite3 data/media_ripper.db ".recover" | sqlite3 data/media_ripper_recovered.db
   mv data/media_ripper_recovered.db data/media_ripper.db
   ```

---

### HandBrakeCLI not found

**Symptom:** Rip jobs fail immediately with "HandBrakeCLI not found."

**Fix:**
```bash
brew install --cask handbrake
# Verify:
which HandBrakeCLI
```

If installed but not on PATH, set the full path in `config.json`:
```json
"handbrake": { "cli_path": "/usr/local/bin/HandBrakeCLI" }
```

---

### Disc not detected

**Symptom:** Inserting a disc does not trigger a rip or `disc_detected` event.

**Checklist:**
1. Are you running in `full` or `monitor` mode? (`--mode server` does **not** include disc monitoring)
2. Does `diskutil list` show the disc?
3. Check logs: `tail -f logs/disc_monitor.log`
4. The monitor polls every 5 seconds — wait at least 10 seconds

---

### yt-dlp download fails

**Symptom:** Content job stuck at "downloading" or error "yt-dlp not found."

**Fix:**
```bash
pip install -U yt-dlp
```

If a specific site isn't working, update yt-dlp — sites break frequently:
```bash
pip install -U yt-dlp
# Check version:
yt-dlp --version
```

For age-restricted or geo-blocked content, configure cookies:
```bash
yt-dlp --cookies-from-browser chrome "URL"
```

---

### Metadata not fetching (TMDb)

**Symptom:** Posters/backdrops missing, metadata empty.

**Checklist:**
1. Is `TMDB_API_KEY` set in `.env`?
2. Test the key:
   ```bash
   curl "https://api.themoviedb.org/3/movie/550?api_key=$TMDB_API_KEY"
   ```
3. Check for rate limiting (40 requests per 10 seconds for TMDb)

---

### Audio CD not identified (AcoustID / Chromaprint)

**Symptom:** Audio CDs rip successfully but metadata (title, artist, cover art) is missing.

**Checklist:**
1. Is `ACOUSTID_API_KEY` set in `.env`? Get a free key at [acoustid.org](https://acoustid.org/new-application)
2. Is Chromaprint installed?
   ```bash
   brew install chromaprint
   which fpcalc
   ```
   Or install the Python binding: `pip install pyacoustid`
3. The system falls back to name-based MusicBrainz search if fingerprinting fails — check the disc label is reasonable
4. Check logs: `grep -i acoustid logs/metadata.log`

---

### Files in wrong directory

**Symptom:** Ripped files appear in the media root instead of `movies/` or `music/`.

**Fix:** This was fixed in a recent update. Ensure you're running the latest code. Video rips go to `$MEDIA_ROOT/movies/` and audio CD rips go to `$MEDIA_ROOT/music/`.

---

### Podcast feed errors

**Symptom:** "Failed to fetch feed" or "Invalid feed" error.

**Checklist:**
1. Test the feed URL directly:
   ```bash
   curl -sL "FEED_URL" | head -20
   ```
2. Some feeds require a User-Agent header — the app sets one automatically
3. Check if `feedparser` is installed:
   ```bash
   pip install feedparser
   ```

---

### Upload fails

**Symptom:** "File too large" or upload silently fails.

**Fix:** Increase the upload limit in `config.json`:
```json
"uploads": { "max_upload_size_mb": 2048 }
```

Or via environment: ensure the upload limit matches your needs. The default is 4096 MB.

---

### Docker container won't start

**Symptom:** Container exits immediately.

**Debug:**
```bash
docker compose logs medialibrary
```

Common causes:
1. Missing `.env` file — copy from `.env.example` and uncomment the values you need
2. `MEDIA_ROOT` directory doesn't exist on the host
3. Port conflict — change the port mapping in `docker-compose.yml`

---

### Cloudflare Tunnel not connecting

**Symptom:** Domain shows "502 Bad Gateway" or "Connection refused."

**Checklist:**
1. Is the tunnel running? `cloudflared tunnel list`
2. Is the web server running on port 8096? `curl http://localhost:8096`
3. Check tunnel logs: `cloudflared tunnel run media-library --loglevel debug`
4. Verify DNS: `dig media.yourdomain.com`

---

## Getting Help

1. Check the logs in the `logs/` directory
2. Run with verbose logging:
   ```bash
   LOG_LEVEL=DEBUG python -m src.main --mode full
   ```
3. Open an issue on GitHub with:
   - OS and Python version
   - Relevant log output
   - Steps to reproduce
