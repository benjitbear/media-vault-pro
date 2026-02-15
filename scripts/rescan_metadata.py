#!/usr/bin/env python3
"""
Re-scan existing media and generate per-track metadata JSON files
so the library scanner can pick up MusicBrainz / TMDB data.
"""
import json
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from src.metadata import MetadataExtractor
from src.utils import sanitize_filename

ext = MetadataExtractor()
media_root = Path(os.environ.get("MEDIA_ROOT", "/Users/poppemacmini/Media"))
metadata_dir = media_root / "data" / "metadata"
metadata_dir.mkdir(parents=True, exist_ok=True)

audio_exts = {".mp3", ".flac", ".wav", ".aac", ".m4a", ".ogg", ".aiff"}
video_exts = {".mp4", ".mkv", ".avi", ".m4v", ".mov"}

# ── 1. Propagate existing album-level metadata to per-track JSONs ──
print("=== Phase 1: Propagate album metadata to per-track JSONs ===")
for meta_file in sorted(metadata_dir.glob("*.json")):
    with open(meta_file) as f:
        meta = json.load(f)
    mb = meta.get("musicbrainz")
    if not mb:
        continue
    source = meta.get("source_file", "")
    if not source or not Path(source).is_dir():
        continue
    # This is album-level metadata — find the actual tracks
    album_dir = Path(source)
    if not album_dir.exists():
        # Album may have been reorganized
        continue
    tracks_meta = mb.get("tracks", [])
    track_files = sorted(f for f in album_dir.iterdir() if f.suffix.lower() in audio_exts)
    print(f"  Album: {mb.get('artist', '?')} - {mb.get('title', '?')} ({len(track_files)} files)")
    for i, tf in enumerate(track_files):
        per_track = dict(meta)
        if i < len(tracks_meta):
            per_track["track_info"] = tracks_meta[i]
        out = metadata_dir / f"{tf.stem}.json"
        with open(out, "w") as f:
            json.dump(per_track, f, indent=2, ensure_ascii=False)
        print(f"    -> {out.name}")

# ── 2. Find reorganized albums and create per-track JSONs ──
print("\n=== Phase 2: Scan reorganized music directories ===")
music_dir = media_root / "music"
if music_dir.exists():
    for artist_dir in sorted(music_dir.iterdir()):
        if not artist_dir.is_dir():
            continue
        for album_dir in sorted(artist_dir.iterdir()):
            if not album_dir.is_dir():
                continue
            track_files = sorted(f for f in album_dir.iterdir() if f.suffix.lower() in audio_exts)
            if not track_files:
                continue
            # Check if any track already has metadata
            first_track = track_files[0]
            existing_meta = metadata_dir / f"{first_track.stem}.json"
            if existing_meta.exists():
                print(f"  [skip] {artist_dir.name}/{album_dir.name} — already has metadata")
                continue
            # Look for an album-level JSON that matches
            # Try to find by searching all JSONs for source_file matching
            found = False
            for meta_file in metadata_dir.glob("*.json"):
                with open(meta_file) as f:
                    m = json.load(f)
                mb = m.get("musicbrainz")
                if not mb:
                    continue
                # Match by artist + album title
                if mb.get("artist", "").lower() == artist_dir.name.lower():
                    print(f"  [match] {artist_dir.name}/{album_dir.name} from {meta_file.name}")
                    tracks_meta = mb.get("tracks", [])
                    for i, tf in enumerate(track_files):
                        per_track = dict(m)
                        if i < len(tracks_meta):
                            per_track["track_info"] = tracks_meta[i]
                        out = metadata_dir / f"{tf.stem}.json"
                        with open(out, "w") as f:
                            json.dump(per_track, f, indent=2, ensure_ascii=False)
                        print(f"    -> {out.name}")
                    found = True
                    break

            if not found:
                # Try fresh MusicBrainz lookup using directory names
                album_name = album_dir.name
                # Strip trailing (Year) for search
                import re

                clean = re.sub(r"\s*\(\d{4}\)\s*$", "", album_name)
                search_query = f"{artist_dir.name} {clean}".strip()
                print(
                    f"  [lookup] {artist_dir.name}/{album_dir.name} -> searching '{search_query}'"
                )
                sample = str(track_files[0])
                meta = ext.extract_full_metadata(
                    str(album_dir),
                    title_hint=search_query,
                    disc_hints={
                        "disc_type": "audio_cd",
                        "sample_track_path": sample,
                    },
                )
                mb = meta.get("musicbrainz")
                if mb:
                    print(f"    Found: {mb.get('artist')} - {mb.get('title')} ({mb.get('year')})")
                    tracks_meta = mb.get("tracks", [])
                    for i, tf in enumerate(track_files):
                        per_track = dict(meta)
                        if i < len(tracks_meta):
                            per_track["track_info"] = tracks_meta[i]
                        out = metadata_dir / f"{tf.stem}.json"
                        with open(out, "w") as f:
                            json.dump(per_track, f, indent=2, ensure_ascii=False)
                        print(f"    -> {out.name}")
                else:
                    print(f"    No match found")

# ── 3. Scan video files without metadata ──
print("\n=== Phase 3: Scan video files ===")
movies_dir = media_root / "movies"
if movies_dir.exists():
    for vf in sorted(movies_dir.rglob("*")):
        if not vf.is_file() or vf.suffix.lower() not in video_exts:
            continue
        meta_file = metadata_dir / f"{vf.stem}.json"
        if meta_file.exists():
            print(f"  [skip] {vf.name} — already has metadata")
            continue
        print(f"  [lookup] {vf.name} -> TMDB search")
        meta = ext.extract_full_metadata(
            str(vf), title_hint=vf.stem, disc_hints={"disc_type": "dvd"}
        )
        tmdb = meta.get("tmdb")
        if tmdb:
            print(f"    Found: {tmdb.get('title')} ({tmdb.get('year')})")
        else:
            print(f"    No TMDB match")
        ext.save_metadata(meta, vf.stem)

print("\n=== Done! Restart the web server to see updated metadata. ===")
