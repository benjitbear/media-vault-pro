# Data Directory

This directory stores metadata and media-related data files.

## Structure

- `metadata/` - JSON files containing metadata for each ripped media item
  - Format: `{title}_{year}.json`
  
- `thumbnails/` - Cover art and thumbnail images
  - Format: `{title}_{year}_cover.jpg`
  - Format: `{title}_{year}_thumb.jpg`

## Metadata Schema

Each JSON file contains:
```json
{
  "title": "Movie Title",
  "year": 2024,
  "director": "Director Name",
  "cast": ["Actor 1", "Actor 2"],
  "runtime_minutes": 120,
  "genres": ["Action", "Drama"],
  "synopsis": "Movie description...",
  "chapters": [
    {"number": 1, "title": "Opening", "time": "00:00:00"},
    ...
  ],
  "audio_tracks": [
    {"language": "English", "channels": 5.1, "codec": "AAC"}
  ],
  "subtitle_tracks": [
    {"language": "English", "format": "SRT"}
  ],
  "file_info": {
    "path": "/path/to/video.mp4",
    "size_bytes": 1234567890,
    "duration_seconds": 7200,
    "created": "2024-01-01T12:00:00"
  }
}
```
