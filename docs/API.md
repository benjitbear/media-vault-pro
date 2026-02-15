# API Reference

Media Library exposes a REST API and WebSocket interface. All endpoints are served by the Flask web server (default port **8096**).

## Authentication

When `auth.enabled` is `true` in config.json (the default), all API requests require a valid `session_token` cookie. Unauthenticated API requests receive a **401** response:

```json
{ "error": "Unauthorized" }
```

Page routes (e.g., `/`) redirect to `/login` instead.

### Error Response Format

All errors follow this shape:

```json
{ "error": "Description of the problem" }
```

with an appropriate HTTP status code (400, 401, 403, 404, 409).

---

### `POST /login`

Authenticate and receive a session cookie.

**Form data:**

| Field | Type | Required |
|-------|------|----------|
| `username` | string | yes |
| `password` | string | yes |

**Response:** 302 redirect to `/` with `session_token` cookie set.

On first run (no users in database), this endpoint creates the admin account instead of authenticating.

### `GET /logout`

Invalidate the current session (server-side) and clear the cookie.

### `GET /api/me`

Returns the current authenticated user.

**Response 200:**

```json
{ "username": "admin", "role": "admin" }
```

When auth is disabled: `{ "username": null, "role": "anonymous" }`

---

## Media Item Object

All endpoints returning media items use this shape. Internal fields (`file_path`, `poster_path`) are stripped before sending to clients.

```json
{
  "id": "a1b2c3d4e5f6",
  "title": "Movie Title",
  "filename": "Movie Title (2024).mp4",
  "file_size": 1073741824,
  "size_formatted": "1.0 GB",
  "created_at": "2024-01-15T10:30:00",
  "modified_at": "2024-01-15T10:30:00",
  "year": "2024",
  "overview": "A description of the media.",
  "rating": 7.5,
  "genres": ["Drama", "Thriller"],
  "director": "Director Name",
  "cast": ["Actor 1", "Actor 2"],
  "has_poster": true,
  "has_metadata": true,
  "collection_name": "My Collection",
  "tmdb_id": 12345,
  "media_type": "video",
  "source_url": "https://example.com",
  "artist": "Artist Name",
  "duration_seconds": 7200.0,
  "added_at": "2024-01-15T10:30:00"
}
```

**Notes:**
- `id` is a 12-character hex string derived from the file path
- `genres` and `cast` are JSON arrays (stored as JSON strings in the DB)
- `has_poster` is derived from the presence of a poster file on disk
- `media_type` is one of: `video`, `audio`, `image`, `document`

---

## Library

### `GET /api/library`

List all media items in the library.

**Response 200:**

```json
{ "count": 42, "items": [ MediaItem, ... ] }
```

### `GET /api/media/<media_id>`

Get full metadata for a single media item.

**Response 200:** MediaItem object
**Response 404:** `{ "error": "Not found" }`

### `GET /api/search?q=<query>`

Search media by title, director, cast, or genres.

**Query parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `q` | string | no | Search query. Empty returns all items. |

**Response 200:**

```json
{ "query": "search term", "count": 5, "items": [ MediaItem, ... ] }
```

### `POST /api/scan`

Force a library re-scan. Emits `library_updated` via WebSocket.

**Response 200:**

```json
{ "status": "completed", "count": 42 }
```

### `GET /api/stats`

Library statistics.

**Response 200:**

```json
{
  "total_items": 42,
  "by_type": { "video": 20, "audio": 15, "document": 7 },
  "total_size": 123456789,
  "total_size_formatted": "117.7 MB",
  "podcasts": 3,
  "collections": 5
}
```

---

## Streaming & Download

### `GET /api/stream/<media_id>`

Stream media with HTTP range-request support (256 KB chunks). Returns 206 Partial Content for range requests, 200 for full file.

**Response headers:** `Content-Type`, `Content-Range`, `Accept-Ranges: bytes`
**Response 404:** `{ "error": "Not found" }`

### `GET /api/download/<media_id>`

Download a media file as an attachment (`Content-Disposition: attachment`).

**Response 404:** `{ "error": "Not found" }`

### `GET /api/poster/<media_id>`

Serve poster image (JPEG).

**Response 200:** Binary JPEG
**Response 404:** 404 (empty body)

---

## Metadata Editing

### `PUT /api/media/<media_id>/metadata`

Update metadata fields for a media item. Also updates the on-disk JSON sidecar.

**Request body (all fields optional):**

```json
{
  "title": "New Title",
  "year": "2024",
  "overview": "Description...",
  "director": "Name",
  "rating": 8.5,
  "genres": ["Action", "Sci-Fi"],
  "cast_members": ["Actor 1", "Actor 2"],
  "collection_name": "My Collection",
  "tmdb_id": 12345,
  "media_type": "video",
  "source_url": "https://example.com",
  "artist": "Artist Name",
  "duration_seconds": 3600.0
}
```

**Response 200:** `{ "status": "updated" }`
**Response 400:** `{ "error": "No data provided" }`
**Response 404:** `{ "error": "Media not found or no valid fields" }`

---

## Jobs

### `GET /api/jobs`

List all jobs (newest first).

**Response 200:**

```json
{
  "jobs": [
    {
      "id": "job-uuid",
      "title": "Movie Title",
      "source_path": "/Volumes/DVD",
      "disc_type": "dvd",
      "job_type": "rip",
      "status": "queued",
      "progress": 0,
      "eta": null,
      "error_message": null,
      "created_at": "2024-01-15T10:30:00"
    }
  ]
}
```

**Job statuses:** `queued`, `encoding`, `done`, `failed`, `cancelled`

### `POST /api/jobs`

Create a rip job.

**Request body:**

```json
{
  "source_path": "/Volumes/MY_DVD",
  "title": "Movie Title",
  "title_number": 1
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source_path` | string | yes | Path to the disc volume |
| `title` | string | no | Display title (defaults to volume name) |
| `title_number` | integer | no | DVD/BD title number to rip (default: 1) |

**Response 201:** `{ "id": "job_id", "status": "queued" }`
**Response 400:** `{ "error": "source_path required" }`

### `DELETE /api/jobs/<job_id>`

Cancel a queued or encoding job.

**Response 200:** `{ "status": "cancelled" }`
**Response 400:** `{ "error": "Cannot cancel this job" }`

### `POST /api/jobs/<job_id>/retry`

Retry a failed or cancelled job.

**Response 201:** `{ "id": "new_job_id", "status": "queued" }`
**Response 400:** `{ "error": "Cannot retry this job" }`

---

## Content Ingestion

### `POST /api/downloads`

Queue a URL for video download (yt-dlp).

**Request body:**

```json
{
  "url": "https://youtube.com/watch?v=...",
  "title": "Optional title"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | yes | URL to download |
| `title` | string | no | Display title (defaults to URL) |

**Response 201:** `{ "id": "job_id", "status": "queued" }`
**Response 400:** `{ "error": "url required" }`

### `POST /api/articles`

Archive a web article (trafilatura).

**Request body:**

```json
{
  "url": "https://example.com/article",
  "title": "Optional title"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | yes | Article URL to archive |
| `title` | string | no | Display title (defaults to URL) |

**Response 201:** `{ "id": "job_id", "status": "queued" }`
**Response 400:** `{ "error": "url required" }`

### `POST /api/books`

Catalogue a book.

**Request body:**

```json
{
  "title": "Book Title",
  "url": "https://example.com/book",
  "author": "Author Name",
  "year": "2024",
  "description": "Book description"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | yes | Book title |
| `url` | string | no | Source URL |
| `author` | string | no | Author name |
| `year` | string | no | Publication year |
| `description` | string | no | Description / overview |

**Response 201:** `{ "id": "book_id", "status": "added" }`
**Response 400:** `{ "error": "title required" }`

### `POST /api/import/playlist`

Import a YouTube or Spotify playlist as a collection.

**Request body:**

```json
{
  "url": "https://open.spotify.com/playlist/...",
  "name": "My Playlist"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | yes | Playlist URL (Spotify or YouTube) |
| `name` | string | no | Collection name (defaults to "Imported Playlist") |

**Response 201:** `{ "collection_id": 1, "job_id": "job_id", "status": "queued" }`
**Response 400:** `{ "error": "url required" }`

---

## Upload

### `POST /api/upload`

Upload files to the library. Multipart form data with field name `files`. Enforced size limit via `uploads.max_upload_size_mb`.

**Request:** `Content-Type: multipart/form-data`, field name `files` (supports multiple files).

**Response 201:**

```json
{
  "uploaded": [
    { "file": "video.mp4", "id": "abc123def456", "media_type": "video" }
  ]
}
```

Per-file errors are included inline: `{ "file": "big.mp4", "error": "File too large" }`

**Response 400:** `{ "error": "No files provided" }`
**Response 403:** `{ "error": "Uploads disabled" }`

---

## Collections

### `GET /api/collections`

List all collections with their media items.

**Response 200:**

```json
{
  "collections": [
    {
      "id": 1,
      "name": "Favourites",
      "description": "",
      "collection_type": "collection",
      "created_at": "2024-01-15T10:30:00",
      "items": [ MediaItem, ... ]
    }
  ]
}
```

### `PUT /api/collections/<name>`

Create or update a collection.

**Request body:**

```json
{
  "media_ids": ["id1", "id2", "id3"],
  "description": "Optional description",
  "collection_type": "collection"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `media_ids` | string[] | no | Ordered list of media item IDs |
| `description` | string | no | Collection description |
| `collection_type` | string | no | `"collection"` or `"playlist"` |

**Response 200:** `{ "status": "updated" }`
**Response 400:** `{ "error": "Request body required" }`

### `DELETE /api/collections/<name>`

Delete a collection.

**Response 200:** `{ "status": "deleted" }`
**Response 404:** `{ "error": "Collection not found" }`

### `GET /api/collections/<col_id>/items`

Get ordered media items for queue playback (`col_id` is an integer).

**Response 200:**

```json
{ "items": [ MediaItem, ... ] }
```

---

## Podcasts

### `GET /api/podcasts`

List all podcast subscriptions.

**Response 200:**

```json
{
  "podcasts": [
    {
      "id": "pod-uuid",
      "feed_url": "https://example.com/feed.xml",
      "title": "Podcast Name",
      "author": "Host Name",
      "description": "About the podcast",
      "artwork_url": "https://...",
      "is_active": 1,
      "last_checked": "2024-01-15T10:30:00",
      "created_at": "2024-01-01T00:00:00"
    }
  ]
}
```

### `POST /api/podcasts`

Subscribe to a podcast feed.

**Request body:**

```json
{
  "feed_url": "https://example.com/feed.xml",
  "title": "Optional title",
  "author": "Optional author"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `feed_url` | string | yes | RSS/Atom feed URL |
| `title` | string | no | Podcast title (auto-fetched from feed if omitted) |

**Response 201:** `{ "id": "pod_id", "status": "subscribed" }`
**Response 409:** `{ "error": "Podcast already subscribed" }`

### `DELETE /api/podcasts/<pod_id>`

Unsubscribe.

**Response 200:** `{ "status": "deleted" }`
**Response 404:** `{ "error": "Not found" }`

### `GET /api/podcasts/<pod_id>/episodes`

List episodes for a podcast.

**Response 200:**

```json
{
  "episodes": [
    {
      "id": "episode-uuid",
      "podcast_id": "pod-uuid",
      "title": "Episode 42",
      "audio_url": "https://...",
      "duration_seconds": 3600,
      "published_at": "2024-01-15",
      "description": "Episode notes...",
      "is_downloaded": 1,
      "created_at": "2024-01-15T10:30:00"
    }
  ]
}
```

---

## Playback Progress

### `GET /api/media/<media_id>/progress`

Get saved playback position for current user.

**Response 200:**

```json
{ "position_seconds": 1234.5, "duration_seconds": 7200.0, "finished": 0 }
```

### `PUT /api/media/<media_id>/progress`

Save position.

**Request body:**

```json
{ "position": 1234.5, "duration": 7200.0 }
```

**Response 200:** `{ "status": "saved" }`
**Response 400:** `{ "error": "No data" }`

### `DELETE /api/media/<media_id>/progress`

Clear progress (mark unwatched).

**Response 200:** `{ "status": "cleared" }`

### `GET /api/continue-watching`

Get in-progress media for current user (items with saved progress that aren't finished).

**Response 200:**

```json
{
  "items": [
    {
      "...all MediaItem fields...",
      "progress_position": 1234.5,
      "progress_duration": 7200.0
    }
  ]
}
```

---

## User Management (Admin Only)

These endpoints require the `admin` role. Non-admin users receive **403** `{ "error": "Admin access required" }`.

### `GET /api/users`

List all users.

**Response 200:**

```json
{ "users": [{ "username": "admin", "role": "admin", "created_at": "..." }] }
```

### `POST /api/users`

Create user.

**Request body:**

```json
{ "username": "newuser", "password": "secure123", "role": "user" }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | yes | Unique username |
| `password` | string | yes | Password (hashed server-side with pbkdf2:sha256) |
| `role` | string | no | `"admin"` or `"user"` (default: `"user"`) |

**Response 201:** `{ "status": "created", "username": "newuser" }`
**Response 400:** `{ "error": "username and password required" }`
**Response 409:** `{ "error": "User already exists" }`

### `DELETE /api/users/<username>`

Delete a user. Cannot delete yourself.

**Response 200:** `{ "status": "deleted" }`
**Response 400:** `{ "error": "Cannot delete your own account" }`
**Response 404:** `{ "error": "User not found" }`

### `PUT /api/users/<username>/password`

Change password. Admin can change anyone's password; regular users can change their own only.

**Request body:** `{ "password": "newpassword" }`

**Response 200:** `{ "status": "updated" }`
**Response 400:** `{ "error": "password required" }`
**Response 403:** `{ "error": "Forbidden" }`
**Response 404:** `{ "error": "User not found" }`

---

## WebSocket Events

Connect via Socket.IO (path: `/socket.io`). When auth is enabled, the connection is validated against the `session_token` cookie.

### Server → Client

| Event | Payload | Description |
|-------|---------|-------------|
| `job_created` | Job object | New job queued |
| `job_update` | Job object | Job status/progress changed |
| `rip_progress` | `{ "id", "progress", "eta", "fps" }` | Encoding progress (every ~2s) |
| `library_updated` | `{ "count": N }` | Library changed, refresh recommended |
| `disc_detected` | `{ "volume", "path" }` | Physical disc detected |
| `library_data` | `{ "count", "items": [...] }` | Response to `request_library` |

### Client → Server

| Event | Payload | Description |
|-------|---------|-------------|
| `request_library` | (none) | Request full library data via WebSocket |
