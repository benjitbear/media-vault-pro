# DVD/CD Media Ripping & Digital Library System

A comprehensive automated system for ripping physical media (DVDs, CDs) and creating a searchable digital library with web-based access.

## Features

- 🎬 **Automatic Disc Detection**: Automatically detects when a DVD/CD is inserted
- 📊 **Metadata Extraction**: Extracts title, year, director, cast, chapters, subtitles, and audio tracks
- 🎥 **Quality Encoding**: Converts to MP4 (H.264) format for maximum compatibility
- 🌐 **Web Interface**: Rich media library interface for browsing and streaming
- 📁 **Organized Storage**: Structured file organization with comprehensive metadata
- 🔍 **Online Lookup**: Fetches additional metadata from TMDB database

## Prerequisites

### System Requirements
- macOS (tested on macOS)
- DVD/CD drive
- Python 3.8+
- Sufficient storage space for media library

### Required Software
- [HandBrakeCLI](https://handbrake.fr/downloads.php) - For DVD ripping
- [MakeMKV](https://www.makemkv.com/) - For DVD decryption (optional but recommended)
- [MediaInfo](https://mediaarea.net/en/MediaInfo) - For metadata extraction

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Ripping
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install system dependencies** (using Homebrew)
   ```bash
   brew install handbrake
   brew install makemkv
   brew install mediainfo
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and add your TMDB API key
   ```

5. **Run setup script**
   ```bash
   python scripts/setup.py
   ```

## Configuration

Edit [config.json](config.json) to customize:
- Output directory and format
- Video/audio encoding settings
- Metadata preferences
- Web server settings
- Automation behavior

## Usage

### Automatic Mode (Recommended)
Start the disc detection daemon:
```bash
python src/disc_monitor.py
```

Insert a DVD/CD and the system will automatically:
1. Detect the disc
2. Extract metadata
3. Rip the content
4. Save organized files
5. Eject the disc

### Manual Mode
Rip a specific disc:
```bash
python src/ripper.py --source /Volumes/DVD_NAME
```

### Start Web Server
Access your library through the web interface:
```bash
python src/web_server.py
```

Then open http://localhost:8096 in your browser.

## Project Structure

```
Ripping/
├── src/                    # Source code
│   ├── __init__.py
│   ├── ripper.py          # Main ripping logic
│   ├── metadata.py        # Metadata extraction
│   ├── disc_monitor.py    # Automatic disc detection
│   └── web_server.py      # Web interface
├── tests/                  # Unit and integration tests
├── logs/                   # Application logs
├── docs/                   # Documentation
├── data/                   # Data storage
│   ├── metadata/          # JSON metadata files
│   └── thumbnails/        # Cover art and thumbnails
├── scripts/               # Utility scripts
├── config.json            # Configuration file
├── requirements.txt       # Python dependencies
└── README.md
```

## Testing

Run the test suite:
```bash
pytest tests/
```

Run with coverage:
```bash
pytest --cov=src tests/
```

## Logging

Logs are stored in the `logs/` directory:
- `ripper.log` - Ripping operations
- `metadata.log` - Metadata extraction
- `disc_monitor.log` - Disc detection events
- `web_server.log` - Web server activity

## Legal Notice

This software is intended for **personal use only** to create backup copies of media you legally own. Respecting copyright laws is your responsibility. Do not use this software to:
- Circumvent copy protection for unauthorized purposes
- Distribute copyrighted content
- Rip media you don't own

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

## Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md) for common issues and solutions.

## Support

For issues or questions, please open an issue on GitHub.
