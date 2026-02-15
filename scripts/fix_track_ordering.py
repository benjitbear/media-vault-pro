#!/usr/bin/env python3
"""
Fix audio track ordering for albums that were ripped with the
lexicographic sort bug (Track 10 sorted between Track 1 and Track 2).

For each album:
 1. Loads MusicBrainz metadata (from existing JSON or re-fetches via AcoustID)
 2. Matches each file's actual duration to the correct MB track
 3. Renames files to the correct track number + title
 4. Rewrites ID3 tags
 5. Saves per-track metadata JSONs
 6. Syncs poster files

For unreorganised albums (timestamped dirs), also reorganises into
Artist/Album (Year)/ structure.
"""
import json
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

from src.metadata import MetadataExtractor
from src.utils import (
    sanitize_filename,
    reorganize_audio_album,
    natural_sort_key,
    get_data_dir,
)

MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/Users/poppemacmini/Media"))
MUSIC_DIR = MEDIA_ROOT / "music"
METADATA_DIR = MEDIA_ROOT / "data" / "metadata"
THUMBNAILS_DIR = MEDIA_ROOT / "data" / "thumbnails"
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".aac", ".m4a", ".ogg", ".aiff"}

ext = MetadataExtractor()


# ── Helpers ──────────────────────────────────────────────────────


def get_duration(path: Path) -> float:
    """Return duration in seconds via ffprobe."""
    try:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def update_mp3_tags(
    file_path: Path,
    artist: str,
    album: str,
    title: str,
    track_num: int,
    total: int,
    year: str = None,
):
    """Rewrite ID3 tags with ffmpeg (copy codec)."""
    fd, tmp = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(file_path),
            "-codec",
            "copy",
            "-id3v2_version",
            "3",
            "-metadata",
            f"artist={artist}",
            "-metadata",
            f"album={album}",
            "-metadata",
            f"title={title}",
            "-metadata",
            f"track={track_num}/{total}",
        ]
        if year:
            cmd.extend(["-metadata", f"date={year}"])
        cmd.append(tmp)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            shutil.move(tmp, str(file_path))
        else:
            os.unlink(tmp)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def match_files_to_tracks(files: list, tracks: list) -> dict:
    """
    Match actual audio files to MusicBrainz tracks by duration.

    Returns dict mapping file_index -> track_index.
    """
    file_durations = [(i, get_duration(f)) for i, f in enumerate(files)]
    track_durations = [(i, t.get("duration_ms", 0) / 1000.0) for i, t in enumerate(tracks)]

    # Greedy closest-duration matching
    used_tracks = set()
    mapping = {}

    for fi, fdur in file_durations:
        best_ti = None
        best_diff = float("inf")
        for ti, tdur in track_durations:
            if ti in used_tracks:
                continue
            diff = abs(fdur - tdur)
            if diff < best_diff:
                best_diff = diff
                best_ti = ti
        if best_ti is not None and best_diff < 10.0:  # 10s tolerance
            mapping[fi] = best_ti
            used_tracks.add(best_ti)
        else:
            print(
                f"    WARNING: No duration match for file {files[fi].name} "
                f"(dur={fdur:.1f}s, best_diff={best_diff:.1f}s)"
            )

    return mapping


def find_metadata_for_album(album_dir: Path, track_count: int):
    """
    Try to find existing MusicBrainz metadata for this album
    from the metadata directory.
    """
    # Check existing JSONs for one that matches the track count
    for jf in sorted(METADATA_DIR.glob("*.json")):
        try:
            with open(jf) as f:
                data = json.load(f)
            mb = data.get("musicbrainz", {})
            if mb.get("track_count") == track_count and mb.get("tracks"):
                # Verify this is likely the right album by checking
                # if the album dir name is related
                album_name = mb.get("title", "").lower()
                dir_name = album_dir.name.lower()
                # Accept if album title appears in dir name, or vice versa
                if (
                    album_name in dir_name
                    or dir_name.split("(")[0].strip().replace("_", " ") in album_name
                    or any(w in dir_name for w in album_name.split() if len(w) > 3)
                ):
                    return data
        except Exception:
            continue
    return None


def fix_album(album_dir: Path, meta: dict):
    """Fix track ordering for a single album using duration matching."""
    mb = meta.get("musicbrainz", {})
    tracks = mb.get("tracks", [])
    artist = mb.get("artist", "Unknown Artist")
    album_title = mb.get("title", album_dir.name)
    year = mb.get("year")

    audio_files = sorted(
        [f for f in album_dir.iterdir() if f.suffix.lower() in AUDIO_EXTS],
        key=natural_sort_key,
    )

    if not audio_files:
        print(f"  No audio files found in {album_dir}")
        return

    print(f"  Album: {album_title} by {artist} ({year})")
    print(f"  Tracks: {len(audio_files)} files, {len(tracks)} in MusicBrainz")

    if len(audio_files) != len(tracks):
        print(f"  WARNING: Track count mismatch! Skipping.")
        return

    # Match files to tracks by duration
    mapping = match_files_to_tracks(audio_files, tracks)

    if len(mapping) != len(audio_files):
        print(
            f"  WARNING: Could only match {len(mapping)}/{len(audio_files)} " f"tracks. Skipping."
        )
        return

    # Check if any files are mismatched
    mismatched = []
    for fi, ti in mapping.items():
        expected_title = tracks[ti]["title"]
        actual_stem = audio_files[fi].stem
        # Strip leading "## - " from filename to get current title
        current_title = re.sub(r"^\d+\s*-\s*", "", actual_stem)
        if current_title != sanitize_filename(expected_title):
            mismatched.append((fi, ti))

    if not mismatched:
        print(f"  All tracks correctly named. No changes needed.")
        return

    print(f"  {len(mismatched)} tracks need fixing:")
    for fi, ti in mismatched:
        t = tracks[ti]
        print(f"    File: {audio_files[fi].name}")
        print(f"      -> Should be: {int(t['number']):02d} - {t['title']}")

    # Rename via temp names to avoid collisions
    temp_names = {}
    total = len(audio_files)

    # Phase 1: move all to temp names
    for fi, ti in mapping.items():
        src = audio_files[fi]
        tmp = src.parent / f"__temp_fix_{fi}_{src.suffix}"
        shutil.move(str(src), str(tmp))
        temp_names[fi] = tmp

    # Phase 2: move to correct names and update tags
    for fi, ti in mapping.items():
        t = tracks[ti]
        track_num = int(t["number"])
        track_title = sanitize_filename(t["title"])
        raw_title = t["title"]
        suffix = temp_names[fi].suffix
        new_name = f"{track_num:02d} - {track_title}{suffix}"
        dest = album_dir / new_name
        shutil.move(str(temp_names[fi]), str(dest))

        # Update ID3 tags
        if suffix.lower() == ".mp3":
            update_mp3_tags(dest, artist, album_title, raw_title, track_num, total, year)

        # Save per-track metadata JSON
        per_track = dict(meta)
        per_track["track_info"] = t
        json_path = METADATA_DIR / f"{dest.stem}.json"
        with open(json_path, "w") as f:
            json.dump(per_track, f, indent=2, ensure_ascii=False)

        # Sync poster
        poster_src = meta.get("poster_file", "")
        if poster_src and os.path.exists(poster_src):
            poster_dest = THUMBNAILS_DIR / f"{dest.stem}_poster.jpg"
            if not poster_dest.exists():
                try:
                    shutil.copy2(poster_src, str(poster_dest))
                except Exception:
                    pass

    print(f"  FIXED: All {total} tracks renamed and tagged correctly.")


def fix_unreorganized_album(album_dir: Path):
    """
    Handle an album that was never reorganized (still in timestamped dir).
    Run metadata extraction, then reorganize.
    """
    audio_files = sorted(
        [f for f in album_dir.iterdir() if f.suffix.lower() in AUDIO_EXTS],
        key=natural_sort_key,
    )
    if not audio_files:
        print(f"  No audio files in {album_dir.name}, skipping.")
        return

    print(f"  Found {len(audio_files)} tracks (unreorganized)")

    # Try AcoustID on the first track
    sample = str(audio_files[0])
    print(f"  Fingerprinting: {audio_files[0].name}")

    meta = ext.extract_full_metadata(
        str(album_dir),
        title_hint=album_dir.name,
        disc_hints={
            "disc_type": "audio_cd",
            "sample_track_path": sample,
            "track_count": len(audio_files),
        },
    )

    mb = meta.get("musicbrainz")
    if not mb:
        print(f"  No MusicBrainz match found. Cannot fix automatically.")
        return

    print(f"  Identified: {mb.get('title')} by {mb.get('artist')} ({mb.get('year')})")

    # Save album-level metadata
    ext.save_metadata(meta, album_dir.name)

    # Reorganize using the fixed natural_sort_key
    new_dir = reorganize_audio_album(str(album_dir), meta, str(MEDIA_ROOT))
    if new_dir and new_dir != str(album_dir):
        print(f"  Reorganized to: {new_dir}")

        # Now verify the reorganized album is correct via duration matching
        new_path = Path(new_dir)
        new_files = sorted(
            [f for f in new_path.iterdir() if f.suffix.lower() in AUDIO_EXTS],
            key=natural_sort_key,
        )

        # Save per-track metadata JSONs & sync poster
        tracks = mb.get("tracks", [])
        for i, tf in enumerate(new_files):
            per_track = dict(meta)
            if i < len(tracks):
                per_track["track_info"] = tracks[i]
            json_path = METADATA_DIR / f"{tf.stem}.json"
            with open(json_path, "w") as f:
                json.dump(per_track, f, indent=2, ensure_ascii=False)

            poster_src = meta.get("poster_file", "")
            if poster_src and os.path.exists(poster_src):
                poster_dest = THUMBNAILS_DIR / f"{tf.stem}_poster.jpg"
                if not poster_dest.exists():
                    try:
                        shutil.copy2(poster_src, str(poster_dest))
                    except Exception:
                        pass

        print(f"  Saved {len(new_files)} track metadata files + posters")
    else:
        print(f"  Reorganization returned same dir or failed.")


def cleanup_empty_dirs():
    """Remove empty timestamp-named album directories."""
    removed = 0
    for d in sorted(MUSIC_DIR.iterdir()):
        if not d.is_dir():
            continue
        # Match timestamped dirs like "Test Album_20260209_182300"
        if re.search(r"_\d{8}_\d{6}$", d.name):
            contents = list(d.iterdir())
            if not contents:
                d.rmdir()
                print(f"  Removed empty dir: {d.name}")
                removed += 1
    return removed


def cleanup_stale_metadata():
    """Remove metadata JSONs whose source files no longer exist."""
    removed = 0
    for jf in sorted(METADATA_DIR.glob("*.json")):
        # Skip album-level metadata (Audio CD*.json etc.)
        stem = jf.stem
        # Check if any audio file with this stem exists
        found = False
        for ext_s in AUDIO_EXTS:
            matches = list(MUSIC_DIR.rglob(f"{stem}{ext_s}"))
            if matches:
                found = True
                break
        if not found:
            # Check if it's an album-level JSON (disc_type: audio_cd)
            try:
                with open(jf) as f:
                    data = json.load(f)
                if data.get("disc_type") == "audio_cd" and data.get("musicbrainz"):
                    continue  # Keep album-level metadata
            except Exception:
                pass
            jf.unlink()
            print(f"  Removed stale: {jf.name}")
            removed += 1
    return removed


# ── Main ─────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("Track Ordering Fix Script")
    print("=" * 60)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

    # Collect all albums to process
    organized_albums = []  # Artist/Album dirs
    unorganized_albums = []  # Timestamped dirs

    for entry in sorted(MUSIC_DIR.iterdir()):
        if not entry.is_dir():
            continue
        # Timestamped dir = unreorganized
        if re.search(r"_\d{8}_\d{6}$", entry.name):
            files = [f for f in entry.iterdir() if f.suffix.lower() in AUDIO_EXTS]
            if files:
                unorganized_albums.append(entry)
            continue
        # Artist dir with album subdirs
        for album_dir in sorted(entry.iterdir()):
            if album_dir.is_dir():
                files = [f for f in album_dir.iterdir() if f.suffix.lower() in AUDIO_EXTS]
                if files:
                    organized_albums.append(album_dir)

    # 1) Fix organized albums (wrong track assignment)
    if organized_albums:
        print(f"\n--- Fixing {len(organized_albums)} organized album(s) ---")
        for album_dir in organized_albums:
            print(f"\n[{album_dir.parent.name}/{album_dir.name}]")
            audio_files = [f for f in album_dir.iterdir() if f.suffix.lower() in AUDIO_EXTS]
            meta = find_metadata_for_album(album_dir, len(audio_files))
            if not meta or not meta.get("musicbrainz", {}).get("tracks"):
                print(f"  No matching metadata found. Attempting AcoustID...")
                sample = sorted(
                    [f for f in album_dir.iterdir() if f.suffix.lower() in AUDIO_EXTS],
                    key=natural_sort_key,
                )[0]
                meta = ext.extract_full_metadata(
                    str(album_dir),
                    title_hint=album_dir.name,
                    disc_hints={
                        "disc_type": "audio_cd",
                        "sample_track_path": str(sample),
                        "track_count": len(audio_files),
                    },
                )
            if meta and meta.get("musicbrainz", {}).get("tracks"):
                fix_album(album_dir, meta)
            else:
                print(f"  Could not obtain metadata. Skipping.")

    # 2) Fix unreorganized albums
    if unorganized_albums:
        print(f"\n--- Processing {len(unorganized_albums)} unreorganized album(s) ---")
        for album_dir in unorganized_albums:
            print(f"\n[{album_dir.name}]")
            fix_unreorganized_album(album_dir)

    # 3) Cleanup
    print(f"\n--- Cleanup ---")
    n = cleanup_empty_dirs()
    print(f"  {n} empty directories removed")
    n = cleanup_stale_metadata()
    print(f"  {n} stale metadata files removed")

    print(f"\n{'=' * 60}")
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
