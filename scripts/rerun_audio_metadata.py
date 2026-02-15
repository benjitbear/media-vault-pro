#!/usr/bin/env python3
"""
Re-run metadata extraction for the Audio CD album using AcoustID.
"""
import sys, os, json
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from src.metadata import MetadataExtractor
from src.utils import sanitize_filename, reorganize_audio_album

ext = MetadataExtractor()
media_root = Path(os.environ.get("MEDIA_ROOT", "/Users/poppemacmini/Media"))
metadata_dir = media_root / "data" / "metadata"
album_dir = media_root / "music" / "Audio CD"

if not album_dir.exists():
    print(f"Album directory not found: {album_dir}")
    sys.exit(1)

audio_files = sorted(f for f in album_dir.iterdir() if f.suffix.lower() == ".mp3")
print(f"Found {len(audio_files)} tracks in {album_dir}")

sample = str(audio_files[0])
print(f"Using sample track for AcoustID: {audio_files[0].name}")
print()

# Run full metadata extraction with AcoustID
meta = ext.extract_full_metadata(
    str(album_dir),
    title_hint="Audio CD",
    disc_hints={
        "disc_type": "audio_cd",
        "sample_track_path": sample,
        "track_count": len(audio_files),
    },
)

mb = meta.get("musicbrainz")
if mb:
    print(f"\n=== Match Found ===")
    print(f"  Artist:  {mb.get('artist')}")
    print(f"  Album:   {mb.get('title')}")
    print(f"  Year:    {mb.get('year')}")
    print(f"  Label:   {mb.get('label')}")
    print(f"  Tracks:  {mb.get('track_count')}")
    if mb.get("tracks"):
        for t in mb["tracks"]:
            print(f"    {t['number']:>2}. {t['title']}")
    print()

    # Save album-level metadata
    ext.save_metadata(meta, album_dir.name)

    # Save per-track metadata
    tracks = mb.get("tracks", [])
    for i, tf in enumerate(audio_files):
        per_track = dict(meta)
        if i < len(tracks):
            per_track["track_info"] = tracks[i]
        out = metadata_dir / f"{tf.stem}.json"
        with open(out, "w") as f:
            json.dump(per_track, f, indent=2, ensure_ascii=False)
        print(f"  Saved: {out.name}")

    # Reorganize: rename files and directory with correct metadata
    print()
    base_output = str(media_root)
    new_dir = reorganize_audio_album(str(album_dir), meta, base_output)
    if new_dir and new_dir != str(album_dir):
        print(f"\n  Reorganized to: {new_dir}")

        # Re-save per-track JSONs with new filenames
        new_path = Path(new_dir)
        new_tracks = sorted(f for f in new_path.iterdir() if f.suffix.lower() == ".mp3")
        for i, tf in enumerate(new_tracks):
            per_track = dict(meta)
            if i < len(tracks):
                per_track["track_info"] = tracks[i]
            out = metadata_dir / f"{tf.stem}.json"
            with open(out, "w") as f:
                json.dump(per_track, f, indent=2, ensure_ascii=False)
            print(f"  Saved: {out.name}")
    else:
        print("  (no reorganization needed)")
else:
    print("\n=== No match found ===")
    print("Check that ACOUSTID_API_KEY is set in .env and fpcalc/chromaprint is installed.")

print("\nDone!")
