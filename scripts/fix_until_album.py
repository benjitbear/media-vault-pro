#!/usr/bin/env python3
"""
Fix 'Until The Whole World Hears' album.

The files are named like:
  01 - 1 Until The Whole World Hears.mp3   (file pos 1, CD track 1)
  02 - 10 Jesus, Hold Me Now.mp3           (file pos 2, CD track 10)
  ...

The embedded number after "## - " is the ORIGINAL CD track number.
We use that to restore correct ordering and clean up the names.
No MusicBrainz API calls needed.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from src.utils import sanitize_filename, natural_sort_key

MEDIA_ROOT = Path("/Users/poppemacmini/Media")
MUSIC_DIR = MEDIA_ROOT / "music"
METADATA_DIR = MEDIA_ROOT / "data" / "metadata"
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".aac", ".m4a", ".ogg", ".aiff"}

album_dir = MUSIC_DIR / "Until The Whole World Hears_20250209_212343"
if not album_dir.exists():
    # Try alternate timestamp
    candidates = [
        d
        for d in MUSIC_DIR.iterdir()
        if d.is_dir() and "Until" in d.name and "Whole World" in d.name
    ]
    if candidates:
        album_dir = candidates[0]
    else:
        print(f"Album dir not found. Available dirs in {MUSIC_DIR}:")
        for d in sorted(MUSIC_DIR.iterdir()):
            if d.is_dir():
                print(f"  {d.name}")
        sys.exit(1)

print(f"Album dir: {album_dir.name}")

audio_files = sorted(
    [f for f in album_dir.iterdir() if f.suffix.lower() in AUDIO_EXTS],
    key=natural_sort_key,
)
print(f"Found {len(audio_files)} tracks\n")

# Parse: "01 - 1 Until The Whole World Hears.mp3"
#   -> file_pos=01, original_track_num=1, title="Until The Whole World Hears"
parsed = []
for f in audio_files:
    m = re.match(r"^(\d+)\s*-\s*(\d+)\s+(.+)$", f.stem)
    if m:
        file_pos = int(m.group(1))
        orig_track = int(m.group(2))
        title = m.group(3).strip()
        parsed.append((f, file_pos, orig_track, title))
        print(f"  File pos {file_pos:2d} -> CD track {orig_track:2d}: {title}")
    else:
        print(f"  WARNING: cannot parse: {f.name}")

if len(parsed) != len(audio_files):
    print("\nNot all files could be parsed. Aborting.")
    sys.exit(1)

# Sort by original track number to get correct order
parsed.sort(key=lambda x: x[2])

# Create destination directory
artist = "Casting Crowns"
album_title = "Until the Whole World Hears"
year = "2009"
safe_artist = sanitize_filename(artist)
safe_album = f"{sanitize_filename(album_title)} ({year})"
new_dir = MUSIC_DIR / safe_artist / safe_album
new_dir.mkdir(parents=True, exist_ok=True)

total = len(parsed)

print(f"\nReorganizing to: {new_dir}")
print(f"Artist: {artist}, Album: {album_title}, Year: {year}\n")

for f, file_pos, orig_track, title in parsed:
    safe_title = sanitize_filename(title)
    new_name = f"{orig_track:02d} - {safe_title}{f.suffix}"
    dest = new_dir / new_name

    print(f"  {f.name}  ->  {new_name}")
    shutil.move(str(f), str(dest))

    # Update ID3 tags
    if dest.suffix.lower() == ".mp3":
        fd, tmp = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(dest),
                "-codec",
                "copy",
                "-id3v2_version",
                "3",
                "-metadata",
                f"artist={artist}",
                "-metadata",
                f"album={album_title}",
                "-metadata",
                f"title={title}",
                "-metadata",
                f"track={orig_track}/{total}",
                "-metadata",
                f"date={year}",
                tmp,
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                shutil.move(tmp, str(dest))
            else:
                os.unlink(tmp)
                print(f"    WARNING: ffmpeg tag update failed")
        except Exception as e:
            print(f"    WARNING: tag update error: {e}")
            try:
                os.unlink(tmp)
            except OSError:
                pass

# Remove old empty directory
try:
    remaining = list(album_dir.iterdir())
    if not remaining:
        album_dir.rmdir()
        print(f"\nRemoved empty dir: {album_dir.name}")
    else:
        print(f"\nOld dir still has files: {[f.name for f in remaining]}")
except Exception as e:
    print(f"\nCould not remove old dir: {e}")

# Verify result
result_files = sorted(
    [f for f in new_dir.iterdir() if f.suffix.lower() in AUDIO_EXTS],
    key=natural_sort_key,
)
print(f"\nFinal result ({len(result_files)} tracks in {new_dir}):")
for f in result_files:
    print(f"  {f.name}")

print("\nDone!")
