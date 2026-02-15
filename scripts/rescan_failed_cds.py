#!/usr/bin/env python3
"""Re-run metadata extraction for audio CDs that failed on first attempt."""
import json
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from src.metadata import MetadataExtractor
from src.utils import natural_sort_key, reorganize_audio_album

ext = MetadataExtractor()
media_root = Path("/Users/poppemacmini/Media")
metadata_dir = media_root / "data" / "metadata"
metadata_dir.mkdir(parents=True, exist_ok=True)

audio_exts = {".mp3", ".flac", ".wav", ".aac", ".m4a", ".ogg", ".aiff"}

# Scan all music artist/album dirs for missing per-track metadata
music_dir = media_root / "music"
for artist_dir in sorted(music_dir.iterdir()):
    if not artist_dir.is_dir():
        continue
    for album_dir in sorted(artist_dir.iterdir()):
        if not album_dir.is_dir():
            continue
        track_files = sorted(
            [f for f in album_dir.iterdir() if f.suffix.lower() in audio_exts], key=natural_sort_key
        )
        if not track_files:
            continue
        # Check if first track has metadata
        first = track_files[0]
        meta_file = metadata_dir / f"{first.stem}.json"
        if meta_file.exists():
            print(f"[skip] {artist_dir.name}/{album_dir.name} — already has per-track metadata")
            continue

        print(f"\n[scan] {artist_dir.name}/{album_dir.name} ({len(track_files)} tracks)")
        sample = str(track_files[0])

        meta = ext.extract_full_metadata(
            str(album_dir),
            title_hint=f"{artist_dir.name} {album_dir.name}",
            disc_hints={
                "disc_type": "audio_cd",
                "sample_track_path": sample,
                "track_count": len(track_files),
            },
        )
        mb = meta.get("musicbrainz")
        if mb:
            print(f"  Found: {mb.get('artist')} - {mb.get('title')} ({mb.get('year')})")
            ext.save_metadata(meta, album_dir.stem)
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
            print("  No metadata found")

# Also scan unrenamed "Audio CD" / "Test Album" directories
for cd_dir in sorted(music_dir.iterdir()):
    if not cd_dir.is_dir():
        continue
    if not (cd_dir.name.startswith("Audio CD_") or cd_dir.name.startswith("Test Album_")):
        continue
    track_files = sorted(
        [f for f in cd_dir.iterdir() if f.suffix.lower() in audio_exts], key=natural_sort_key
    )
    if not track_files:
        continue

    print(f"\n[scan-unidentified] {cd_dir.name} ({len(track_files)} tracks)")
    sample = str(track_files[0])
    meta = ext.extract_full_metadata(
        str(cd_dir),
        title_hint=cd_dir.name,
        disc_hints={
            "disc_type": "audio_cd",
            "sample_track_path": sample,
            "track_count": len(track_files),
        },
    )
    mb = meta.get("musicbrainz")
    if mb:
        print(f"  Found: {mb.get('artist')} - {mb.get('title')} ({mb.get('year')})")
        ext.save_metadata(meta, cd_dir.stem)
        tracks_meta = mb.get("tracks", [])
        for i, tf in enumerate(track_files):
            per_track = dict(meta)
            if i < len(tracks_meta):
                per_track["track_info"] = tracks_meta[i]
            out = metadata_dir / f"{tf.stem}.json"
            with open(out, "w") as f:
                json.dump(per_track, f, indent=2, ensure_ascii=False)
            print(f"    -> {out.name}")
        new_dir = reorganize_audio_album(str(cd_dir), meta, str(media_root), None)
        if new_dir and new_dir != str(cd_dir):
            print(f"  Reorganized to: {new_dir}")
    else:
        print("  No metadata found")

print("\nDone!")
