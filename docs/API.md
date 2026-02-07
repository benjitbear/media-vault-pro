# API Documentation

## Core Modules

### Ripper

The main ripping engine that handles DVD/CD conversion.

```python
from src.ripper import Ripper

ripper = Ripper(config_path='config.json')
result = ripper.rip_disc(source_path='/Volumes/DVD_NAME')
```

### MetadataExtractor

Extracts and enriches metadata from media files.

```python
from src.metadata import MetadataExtractor

extractor = MetadataExtractor()
metadata = extractor.extract(file_path='/path/to/video.mp4')
```

### DiscMonitor

Monitors for disc insertion and triggers automatic ripping.

```python
from src.disc_monitor import DiscMonitor

monitor = DiscMonitor()
monitor.start()  # Runs in background
```

### MediaServer

Web server for browsing and streaming the media library.

```python
from src.web_server import MediaServer

server = MediaServer(port=8096)
server.run()
```

## Configuration API

All modules accept a configuration dictionary or path to config.json.

## REST API Endpoints (Web Server)

### GET /api/library
Returns list of all media in the library.

### GET /api/media/{id}
Returns detailed information about specific media item.

### GET /api/stream/{id}
Streams video file.

### GET /api/search?q={query}
Searches library by title, director, cast, etc.

### POST /api/scan
Triggers library rescan.

## Events

The disc monitor emits events that can be subscribed to:

- `disc_inserted` - When a new disc is detected
- `rip_started` - When ripping begins
- `rip_progress` - Progress updates
- `rip_completed` - When ripping finishes
- `rip_failed` - When an error occurs
