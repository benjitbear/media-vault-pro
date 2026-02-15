# Glossary

Project-specific terminology used throughout Media Library documentation and code.

## A

**AcoustID**
: A free audio fingerprint service. Given a Chromaprint fingerprint, it returns MusicBrainz recording IDs for music identification. Requires `ACOUSTID_API_KEY`.

**AppState**
: The central singleton class in `src/app_state.py` that wraps the SQLite database. Inherits from 6 repository mixins. All database access goes through AppState public methods.

**Audio CD**
: A physical compact disc containing uncompressed audio tracks. Ripped via ffmpeg (not HandBrakeCLI). Identified by checking if the disc volume contains `.aiff` files.

## B

**Backdrop**
: A wide landscape image associated with a movie or TV show, fetched from TMDB. Stored in `MEDIA_ROOT/data/thumbnails/`.

**Blueprint**
: A Flask blueprint — a modular group of related routes. Route blueprints are in `src/routes/` (e.g., `media_bp`, `jobs_bp`).

## C

**Chromaprint**
: An audio fingerprinting library. The `fpcalc` command-line tool generates fingerprints that are submitted to AcoustID for identification. Install via `brew install chromaprint`.

**Collection**
: A user-created group of media items. Can be either a `collection` (general grouping) or a `playlist` (ordered for sequential playback).

**Content Job**
: A queued task for downloading or archiving content (video, article, book, playlist). Stored in the `content_jobs` database table and processed by the content worker thread.

## D

**Disc Hints**
: Metadata collected from a physical disc before ripping — runtime, track count, disc type. Used to disambiguate TMDB/MusicBrainz search results. Stored as JSON in the `jobs.disc_hints` column.

**Disc Monitor**
: The `DiscMonitor` class in `src/disc_monitor.py`. Polls `diskutil list` for optical drives every 5 seconds. macOS-only.

## F

**feedparser**
: Python library used to parse RSS/Atom podcast feeds.

**First-Run Setup**
: When auth is enabled and no users exist in the database, the login page becomes a "Create Admin Account" form. Alternatively, set `INIT_ADMIN_USER` and `INIT_ADMIN_PASS` environment variables.

## H

**HandBrakeCLI**
: Command-line video encoder used for DVD and Blu-ray ripping. Configured via `config.json` → `handbrake` section.

## J

**Job**
: A rip/encode task in the `jobs` table. Statuses: `queued` → `encoding` → `done` (or `failed` / `cancelled`).

**Job Worker**
: A background thread in `main.py` that picks up queued jobs and runs the ripper.

## M

**Media ID**
: A 12-character hex string derived from `sha256(file_path)[:12]`. Deterministic and collision-resistant. Used as the primary key in the `media` table.

**MEDIA_ROOT**
: The root directory for all media data — movies, music, downloads, uploads, podcasts, database, and metadata cache. Set via the `MEDIA_ROOT` environment variable.

**MediaInfo**
: A tool for extracting technical metadata from media files (codec, resolution, duration, bitrate). Wrapped by `src/clients/mediainfo_client.py`.

**Metadata Sidecar**
: A `.json` file stored alongside each media file containing TMDB/MusicBrainz metadata. Written by `MetadataExtractor.save_metadata()` and read during library scans.

**MusicBrainz**
: An open music encyclopedia and database. Used for identifying audio CDs by name or AcoustID fingerprint. Returns artist, album, track listing, and links to cover art.

## P

**Playback Progress**
: Per-user saved position in a media item. Stored in the `playback_progress` table. A media item is considered "finished" at ≥95% progress.

**Podcast**
: An RSS/Atom feed subscription. The podcast checker thread polls feeds at configurable intervals and optionally auto-downloads new episodes.

**Poster**
: A portrait image associated with a media item — movie poster (from TMDB) or album cover art (from MusicBrainz / Cover Art Archive). Stored in `MEDIA_ROOT/data/thumbnails/`.

## R

**Repository Mixin**
: A class in `src/repositories/` that provides domain-specific database methods. AppState inherits from all 6 mixins, which each expect `self._get_conn()`, `self.logger`, and `self.broadcast()`.

## S

**Session Token**
: A hex string stored in the `sessions` table and set as a `session_token` cookie. Validated on each request when auth is enabled. Server-side invalidation on logout.

**Sidecar File**
: See **Metadata Sidecar**.

**Socket.IO**
: A WebSocket library used for real-time communication between the Flask server and the browser. Events include `job_update`, `rip_progress`, `library_updated`, `disc_detected`.

## T

**TMDB (The Movie Database)**
: External API for movie and TV show metadata, posters, and backdrops. Requires `TMDB_API_KEY`. Client is in `src/clients/tmdb_client.py`.

**trafilatura**
: Python library for extracting content from web pages. Used by the article archiving feature.

## W

**WAL (Write-Ahead Logging)**
: A SQLite journal mode that allows concurrent reads with a single writer. Enabled by default in AppState for better performance with multiple threads.

## Y

**yt-dlp**
: A command-line tool for downloading videos from YouTube and other sites. Used by `ContentDownloader` for video and playlist downloads.
