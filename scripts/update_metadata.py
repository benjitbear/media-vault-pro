#!/usr/bin/env python3
"""
Update metadata JSONs and poster files for all fixed albums.

- Updates source_file and poster_file paths in each track's metadata JSON.
- Copies album poster to per-track poster files if missing.
- Removes stale metadata files that don't match any current track.
"""
import json
import os
import shutil
import sys
from pathlib import Path

MEDIA_ROOT = Path("/Users/poppemacmini/Media")
MUSIC_DIR = MEDIA_ROOT / "music"
METADATA_DIR = MEDIA_ROOT / "data" / "metadata"
THUMBS_DIR = MEDIA_ROOT / "data" / "thumbnails"
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".aac", ".m4a", ".ogg", ".aiff"}


def update_album(artist_dir, album_dir):
    """Update metadata and posters for one album."""
    print(f"\n=== {artist_dir.name} / {album_dir.name} ===")

    tracks = sorted(
        [f for f in album_dir.iterdir() if f.suffix.lower() in AUDIO_EXTS],
        key=lambda p: p.name,
    )
    if not tracks:
        print("  No tracks found")
        return

    # Find existing album poster (check various naming patterns)
    album_poster = None
    for pattern in [
        THUMBS_DIR / f"{tracks[0].stem}_poster.jpg",
        THUMBS_DIR / f"Audio CD_poster.jpg",
        THUMBS_DIR / f"Test Album_poster.jpg",
    ]:
        if pattern.exists():
            album_poster = pattern
            break

    # Also check if any track already has a poster
    if not album_poster:
        for t in tracks:
            p = THUMBS_DIR / f"{t.stem}_poster.jpg"
            if p.exists():
                album_poster = p
                break

    if album_poster:
        print(f"  Album poster: {album_poster.name}")
    else:
        print("  No album poster found")

    for track_file in tracks:
        stem = track_file.stem
        meta_file = METADATA_DIR / f"{stem}.json"

        if meta_file.exists():
            with open(meta_file) as f:
                meta = json.load(f)

            # Update source_file to actual track path
            old_source = meta.get("source_file", "")
            meta["source_file"] = str(track_file)

            # Update poster_file
            poster_path = THUMBS_DIR / f"{stem}_poster.jpg"
            meta["poster_file"] = str(poster_path)

            # Write back
            with open(meta_file, "w") as f:
                json.dump(meta, f, indent=2)

            if old_source != str(track_file):
                print(f"  Updated: {stem}.json (source_file fixed)")
            else:
                print(f"  OK: {stem}.json")
        else:
            print(f"  MISSING: {stem}.json - not found")

        # Ensure per-track poster exists
        poster_path = THUMBS_DIR / f"{stem}_poster.jpg"
        if not poster_path.exists() and album_poster:
            shutil.copy2(str(album_poster), str(poster_path))
            print(f"    Copied poster -> {poster_path.name}")


def cleanup_stale_metadata():
    """Remove metadata files that don't match any current audio file."""
    print("\n=== Cleaning up stale metadata ===")
    # Build set of all current track stems
    current_stems = set()
    for artist in MUSIC_DIR.iterdir():
        if not artist.is_dir():
            continue
        for album in artist.iterdir():
            if not album.is_dir():
                continue
            for f in album.iterdir():
                if f.suffix.lower() in AUDIO_EXTS:
                    current_stems.add(f.stem)

    # Check metadata files
    stale = []
    for meta_file in METADATA_DIR.iterdir():
        if meta_file.suffix != ".json":
            continue
        stem = meta_file.stem
        if stem not in current_stems:
            # Keep if it's a general album metadata (has musicbrainz.tracks)
            try:
                with open(meta_file) as f:
                    data = json.load(f)
                # Stale general album files (Audio CD_xxx, Until_xxx)
                if stem.startswith("Audio CD") or stem.startswith("Until"):
                    stale.append(meta_file)
                    continue
            except Exception:
                pass

    for f in stale:
        print(f"  Removing stale: {f.name}")
        f.unlink()


def main():
    # Process all albums
    for artist_dir in sorted(MUSIC_DIR.iterdir()):
        if not artist_dir.is_dir():
            continue
        for album_dir in sorted(artist_dir.iterdir()):
            if not album_dir.is_dir():
                continue
            update_album(artist_dir, album_dir)

    cleanup_stale_metadata()

    # Summary
    print("\n=== Summary ===")
    meta_count = len(list(METADATA_DIR.glob("*.json")))
    poster_count = len(list(THUMBS_DIR.glob("*_poster.jpg")))
    track_count = 0
    for artist in MUSIC_DIR.iterdir():
        if not artist.is_dir():
            continue
        for album in artist.iterdir():
            if not album.is_dir():
                continue
            track_count += len([f for f in album.iterdir() if f.suffix.lower() in AUDIO_EXTS])
    print(f"  Tracks: {track_count}")
    print(f"  Metadata files: {meta_count}")
    print(f"  Poster files: {poster_count}")
    print("\nDone!")


if __name__ == "__main__":
    main()
