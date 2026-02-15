#!/usr/bin/env python3
"""Debug: check what AcoustID returns for the first track."""
import sys, os, json
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from src.metadata import MetadataExtractor

ext = MetadataExtractor()
sample = "/Users/poppemacmini/Media/music/Audio CD/01 - Regret.mp3"

print("=== AcoustID lookup ===")
result = ext.lookup_acoustid(sample)
print(f"Result: {json.dumps(result, indent=2)}")

if result and result.get("musicbrainz_release_id"):
    print(f"\n=== MusicBrainz release lookup ===")
    mb = ext.lookup_musicbrainz_by_release_id(result["musicbrainz_release_id"])
    if mb:
        print(f"Artist: {mb.get('artist')}")
        print(f"Album: {mb.get('title')}")
        print(f"Year: {mb.get('year')}")
        print(f"Tracks: {mb.get('track_count')}")
    else:
        print("No MusicBrainz release data found")
elif result:
    print(f"\nAcoustID found a recording but no release_id.")
    print(f"Recording: {result.get('title')} by {result.get('artist')}")
    print(f"Recording MBID: {result.get('musicbrainz_recording_id')}")
    print("\nNeed to look up release via the recording ID instead.")
else:
    print("No AcoustID match at all.")
