# Roadmap

Planned features and milestones for Media Library. Items are roughly ordered by priority within each milestone.

## v0.4.0 — Polish & Reliability

- [ ] Gunicorn / production WSGI server support
- [ ] Automatic database backups (configurable schedule)
- [ ] Retry logic with exponential backoff for TMDB/MusicBrainz API failures
- [ ] Batch metadata refresh from the web UI
- [ ] Improved error messages in the web UI (toast notifications for failures)
- [ ] WebSocket reconnection handling in the frontend
- [ ] Rate limiting on login attempts
- [ ] Per-user library filtering and access control

## v0.5.0 — Enhanced Media Management

- [ ] TV show / series support with season/episode organisation
- [ ] Multi-disc set handling (automatic grouping of related discs)
- [ ] Subtitle download integration (OpenSubtitles)
- [ ] Transcode profiles (4K → 1080p, HEVC options)
- [ ] Bulk edit metadata for multiple items
- [ ] Smart collections (auto-populated by genre, year, rating)
- [ ] Watch history and recommendations

## v0.6.0 — Multi-User & Sharing

- [ ] User profiles with avatar and preferences
- [ ] Per-user watch lists and favourites
- [ ] Parental controls / content ratings
- [ ] Shared watch party (synchronised playback)
- [ ] Mobile-friendly responsive UI improvements
- [ ] PWA support (installable web app)

## Future / Backlog

- [ ] DLNA / UPnP server for local network streaming
- [ ] Chromecast integration
- [ ] Plugin system for custom metadata providers
- [ ] Import from existing Plex/Jellyfin libraries
- [ ] Audiobook support with chapter navigation
- [ ] Music player with queue, shuffle, and repeat
- [ ] Full-text search across article archives
- [ ] Webhook notifications (Discord, Slack, Pushover)
- [ ] REST API versioning (v1/v2)
- [ ] OpenAPI / Swagger spec generation

## Completed

### v0.3.0 (2026-02-07)
- Docker support
- Run modes (`full`, `server`, `monitor`)
- First-run admin setup
- Security headers and session management
- Configurable CORS and secure cookies

### v0.2.0 (2025-12-01)
- Web interface (Flask + Socket.IO SPA)
- Authentication system
- Content downloader (yt-dlp, trafilatura, feedparser)
- Collections, podcasts, playback progress

### v0.1.0 (2025-09-01)
- Initial release: disc ripping, metadata, notifications

---

> This roadmap is aspirational and subject to change. Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
