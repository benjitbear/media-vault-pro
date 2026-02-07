# Quick Start Guide

Get up and running with the Media Ripper in minutes!

## Installation

### 1. Install System Dependencies

```bash
# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install required tools
brew install handbrake
brew install mediainfo
brew install ffmpeg  # Optional, for chapter extraction
```

### 2. Setup Python Environment

```bash
# Navigate to project directory
cd /Users/poppemacmini/Documents/Scripting/Ripping

# Install Python dependencies
pip install -r requirements.txt

# Or use make
make dev-install
```

### 3. Configure Application

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your TMDB API key
# Get free API key from: https://www.themoviedb.org/settings/api
nano .env
```

### 4. Run Setup Script

```bash
python scripts/setup.py
```

## Basic Usage

### Option 1: Automatic Mode (Recommended)

Start the disc monitor to automatically rip discs when inserted:

```bash
# Using Python
python src/disc_monitor.py

# Or using make
make run-monitor
```

Now just insert a disc and it will automatically:
1. Detect the disc
2. Rip the content
3. Extract metadata from TMDB
4. Eject the disc when done
5. Notify you of completion

### Option 2: Manual Mode

Rip a specific disc manually:

```bash
# Find your disc mount point
ls /Volumes/

# Rip the disc
python src/ripper.py --source /Volumes/YOUR_DVD_NAME --title "Movie Title"
```

### Option 3: Web Interface

Browse and stream your library:

```bash
# Start the web server
python src/web_server.py

# Or using make
make run-server
```

Then open http://localhost:8096 in your browser.

## Quick Configuration

Edit `config.json` to customize:

```json
{
  "output": {
    "base_directory": "/Users/poppemacmini/Documents/MediaLibrary",
    "quality": 22  // Lower = better quality (18-28 range)
  },
  "automation": {
    "auto_detect_disc": true,
    "auto_eject_after_rip": true
  }
}
```

## Common Tasks

### Change Output Directory
```bash
# Edit config.json
nano config.json
# Change "base_directory" to your preferred location
```

### Change Video Quality
```bash
# Edit config.json
# Lower quality number = better quality, larger file
# 18 = very high quality, 22 = good balance, 28 = smaller files
"quality": 22
```

### Disable Automatic Ripping
```bash
# Start monitor in notification-only mode
python src/disc_monitor.py --no-auto-rip
```

### Extract Just Metadata
```bash
python src/metadata.py /path/to/video.mp4 --title "Movie Name" --save
```

## Troubleshooting

### "HandBrakeCLI not found"
```bash
brew install handbrake
which HandBrakeCLI  # Verify installation
```

### "No TMDB results found"
- Check your API key in `.env`
- Try a more specific title
- Ensure internet connection

### Disc not detected
- Check `/Volumes/` to see if disc is mounted
- Try ejecting and reinserting
- Check `logs/disc_monitor.log`

### Port already in use
```bash
# Change port in config.json
"web_server": {
  "port": 8097  // Change to different port
}
```

## Next Steps

- Read the full [README](../README.md)
- Check [API Documentation](API.md)
- Review [Architecture](ARCHITECTURE.md)
- See [Troubleshooting Guide](troubleshooting.md)

## Tips

1. **Quality Settings**: Start with quality 22, adjust based on results
2. **Naming**: Use descriptive disc volume names for better auto-titling
3. **Monitoring**: Keep an eye on disk space - DVDs can be 4-8GB each
4. **Backup**: Consider backing up your metadata JSON files
5. **Testing**: Test with a non-critical disc first

Enjoy your digital library! 🎬
