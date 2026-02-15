#!/usr/bin/env python3
"""
Download correct album-specific cover art for all albums and update
per-track poster files.
"""
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

MEDIA_ROOT = Path("/Users/poppemacmini/Media")
MUSIC_DIR = MEDIA_ROOT / "music"
METADATA_DIR = MEDIA_ROOT / "data" / "metadata"
THUMBS_DIR = MEDIA_ROOT / "data" / "thumbnails"
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".aac", ".m4a", ".ogg", ".aiff"}


def download_image(url: str, dest: str) -> bool:
    """Download an image from a URL."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "MediaLibrary/1.0 (contact@example.com)"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        with open(dest, "wb") as f:
            f.write(data)
        print(f"  Downloaded: {os.path.basename(dest)} ({len(data)} bytes)")
        return True
    except Exception as e:
        print(f"  FAILED to download {url}: {e}")
        return False


def process_album(album_dir: Path) -> None:
    """Download album poster and copy to all tracks."""
    tracks = sorted(
        [f for f in album_dir.iterdir() if f.suffix.lower() in AUDIO_EXTS],
        key=lambda p: p.name,
    )
    if not tracks:
        return

    # Load metadata from first track to get cover_art_url
    first_track = tracks[0]
    meta_file = METADATA_DIR / f"{first_track.stem}.json"
    if not meta_file.exists():
        print(f"  No metadata for {first_track.stem}")
        return

    with open(meta_file) as f:
        meta = json.load(f)

    mb = meta.get("musicbrainz", {})
    album_title = mb.get("title", album_dir.name)
    cover_url = mb.get("cover_art_url")

    if not cover_url:
        # Try Cover Art Archive directly using release_id
        release_id = mb.get("release_id")
        if release_id:
            try_url = f"https://coverartarchive.org/release/{release_id}/front"
            print(f"  Trying CAA front image for release {release_id}...")
            album_poster = THUMBS_DIR / f"{album_title}_poster.jpg"
            if download_image(try_url, str(album_poster)):
                cover_url = try_url
                # Update metadata with the URL
                mb["cover_art_url"] = try_url
            else:
                print(f"  No cover art available for: {album_title}")
        else:
            print(f"  No cover art URL and no release_id for: {album_title}")

    if cover_url:
        # Download album-level poster
        from src.utils import sanitize_filename

        safe_name = sanitize_filename(album_title)
        album_poster = THUMBS_DIR / f"{safe_name}_poster.jpg"

        # Always re-download to ensure we have the right image
        if download_image(cover_url, str(album_poster)):
            # Copy to all per-track posters
            for track in tracks:
                dest = THUMBS_DIR / f"{track.stem}_poster.jpg"
                shutil.copy2(str(album_poster), str(dest))

            # Update all track metadata JSONs
            for track in tracks:
                tmf = METADATA_DIR / f"{track.stem}.json"
                if tmf.exists():
                    with open(tmf) as f:
                        td = json.load(f)
                    dest = THUMBS_DIR / f"{track.stem}_poster.jpg"
                    td["poster_file"] = str(dest)
                    if "musicbrainz" in td and cover_url:
                        td["musicbrainz"]["cover_art_url"] = cover_url
                    with open(tmf, "w") as f:
                        json.dump(td, f, indent=2)

            print(f"  Updated {len(tracks)} track posters")
        else:
            print(f"  Could not download poster for: {album_title}")
    else:
        print(f"  Skipping (no cover art): {album_title}")


def main():
    for artist_dir in sorted(MUSIC_DIR.iterdir()):
        if not artist_dir.is_dir():
            continue
        for album_dir in sorted(artist_dir.iterdir()):
            if not album_dir.is_dir():
                continue
            print(f"\n{artist_dir.name} / {album_dir.name}")
            process_album(album_dir)

    # Clean up stale generic posters
    for stale in ["Audio CD_poster.jpg", "Test Album_poster.jpg"]:
        p = THUMBS_DIR / stale
        if p.exists():
            p.unlink()
            print(f"\nRemoved stale: {stale}")

    print("\nDone!")


if __name__ == "__main__":
    main()
