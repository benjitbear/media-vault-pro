# Architecture Overview

This document describes the architecture and design of the Media Ripper system.

## System Components

### 1. Core Modules

#### Ripper (`src/ripper.py`)
- Handles DVD/CD ripping using HandBrakeCLI
- Configurable encoding settings
- Progress monitoring and logging
- Automatic disc ejection

**Key Methods:**
- `rip_disc()` - Main ripping function
- `detect_disc_info()` - Scan disc for content
- `build_handbrake_command()` - Generate HandBrake CLI command

#### MetadataExtractor (`src/metadata.py`)
- Extracts technical metadata using MediaInfo
- Fetches movie information from TMDB
- Downloads cover art and posters
- Saves metadata to structured JSON files

**Key Methods:**
- `extract_full_metadata()` - Complete metadata extraction
- `search_tmdb()` - Look up movie information
- `extract_chapters()` - Extract chapter information

#### DiscMonitor (`src/disc_monitor.py`)
- Monitors `/Volumes` for new disc insertion
- Automatically triggers ripping workflow
- macOS notification integration
- Configurable polling interval

**Key Methods:**
- `start()` - Begin monitoring loop
- `check_for_new_discs()` - Detect volume changes
- `process_disc()` - Handle new disc insertion

#### MediaServer (`src/web_server.py`)
- Flask-based web interface
- Library browsing and searching
- Video streaming capabilities
- RESTful API endpoints

**Key Endpoints:**
- `GET /api/library` - List all media
- `GET /api/search?q=<query>` - Search library
- `GET /api/stream/<id>` - Stream video
- `GET /api/poster/<id>` - Get cover art

### 2. Utilities (`src/utils.py`)

Common functions used across modules:
- Configuration loading
- Logging setup with rotation
- Filename sanitization
- Size/time formatting
- macOS notifications

## Data Flow

```
1. Disc Insertion
   ↓
2. DiscMonitor detects new volume
   ↓
3. Ripper initiated with disc path
   ↓
4. HandBrakeCLI converts to MP4
   ↓
5. MetadataExtractor processes file
   ↓
6. TMDB lookup for movie info
   ↓
7. Metadata saved to JSON
   ↓
8. Poster downloaded to thumbnails/
   ↓
9. Disc ejected (if configured)
   ↓
10. Available in MediaServer
```

## Directory Structure

```
/
├── src/                        # Application code
│   ├── ripper.py              # DVD ripping logic
│   ├── metadata.py            # Metadata extraction
│   ├── disc_monitor.py        # Auto-detection daemon
│   ├── web_server.py          # Web interface
│   └── utils.py               # Common utilities
├── tests/                      # Test suite
├── logs/                       # Application logs
├── data/
│   ├── metadata/              # JSON metadata files
│   └── thumbnails/            # Cover art images
└── /Users/.../MediaLibrary/   # Actual video files
```

## Configuration

All components read from `config.json`:

- **output**: Video encoding settings
- **metadata**: What to extract and save
- **automation**: Auto-detection behavior
- **web_server**: Server configuration
- **disc_detection**: Monitoring settings
- **handbrake**: HandBrake-specific options

Environment variables (`.env`):
- `TMDB_API_KEY`: Required for metadata lookup

## Logging

Each module has its own logger:
- `logs/ripper.log` - Ripping operations
- `logs/metadata.log` - Metadata extraction
- `logs/disc_monitor.log` - Disc detection events
- `logs/web_server.log` - Web requests

All logs use rotating file handlers (10MB max, 5 backups).

## Error Handling

- All modules catch exceptions and log errors
- Failed rips don't crash the monitor
- Missing dependencies are detected early
- User notifications for critical events

## Performance Considerations

- Disc monitoring uses configurable polling (default: 5s)
- Metadata fetching is asynchronous from ripping
- Web server scans library on-demand
- Video streaming uses Flask's send_file (efficient)

## Security Considerations

- Web server binds to configurable host (default: 0.0.0.0)
- No authentication (intended for local network)
- File paths are validated
- API key stored in .env (not committed)

## Extensibility

The modular design allows for:
- Custom ripping presets
- Additional metadata sources
- Alternative web frameworks
- Plugin architecture (future)

## Testing Strategy

- Unit tests for individual functions
- Integration tests for workflows
- Mock external dependencies (HandBrake, TMDB)
- Fixtures for disc structures
