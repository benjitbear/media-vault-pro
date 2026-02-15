# Utility Scripts

Maintenance and debugging scripts in `scripts/`. Run from the project root with the virtual environment activated:

```bash
source .venv/bin/activate
python scripts/<script_name>.py
```

## Setup & Diagnostics

| Script | Description |
|--------|-------------|
| `setup.py` | **First-time setup checks.** Verifies that required system dependencies (HandBrakeCLI, mediainfo, ffmpeg, ffprobe) are installed and on PATH. Run this after cloning the repository. |

## Metadata Repair

| Script | Description |
|--------|-------------|
| `rescan_metadata.py` | Re-scan existing media and generate per-track metadata JSON sidecar files so the library scanner can pick up MusicBrainz / TMDB data. Propagates album-level metadata to individual tracks. |
| `rerun_audio_metadata.py` | Re-run AcoustID fingerprint identification for a single album directory that was initially identified as generic "Audio CD". |
| `rescan_failed_cds.py` | Scan all artist/album directories for albums missing per-track metadata JSON and re-run metadata extraction on them. Useful after bulk rips where some CDs failed identification. |
| `update_metadata.py` | Synchronise metadata JSON paths and poster files across all albums. Updates `source_file` and `poster_file` paths, copies album posters to per-track poster files, and removes stale metadata entries. |

## Cover Art

| Script | Description |
|--------|-------------|
| `fix_cover_art.py` | Download correct album-specific cover art from the Cover Art Archive for all albums in the music library, then assign poster images to each track. |
| `download_missing_covers.py` | Download cover art for specific hardcoded albums (Casting Crowns and Sons of Korah) from the Cover Art Archive. |

## Track Ordering

| Script | Description |
|--------|-------------|
| `fix_track_ordering.py` | Fix audio track ordering for albums ripped with the lexicographic sort bug (Track 10 sorted between Track 1 and Track 2). Matches file durations to MusicBrainz metadata, renames files, rewrites ID3 tags, and optionally reorganises into Artist/Album directories. |
| `fix_until_album.py` | Restore correct track ordering for the specific album "Until The Whole World Hears" by parsing embedded CD track numbers from filenames. No API calls needed. |

## Debugging

| Script | Description |
|--------|-------------|
| `debug_acoustid.py` | Run an AcoustID fingerprint lookup on a sample track and print the matched MusicBrainz release metadata. Useful for verifying your `ACOUSTID_API_KEY` works correctly. |
| `debug_metadata.py` | Reproduce and diagnose a faulty MusicBrainz search caused by generic disc volume names like "Audio CD" being cleaned to the query "Audio". |
