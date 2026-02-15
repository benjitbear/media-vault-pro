#!/usr/bin/env python3
"""Debug script: reproduce the wrong MusicBrainz match."""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

# The disc volume name was "Audio CD".
# _clean_search_title strips "CD" (matched by r'\bCD\s*\d*\b') -> leaves "Audio"
# So the MusicBrainz query was: release:"Audio"
print("=== Reproducing the MusicBrainz search ===")
print("Disc volume name: 'Audio CD'")
print("After _clean_search_title: 'Audio'  (CD stripped as noise pattern)")
print()

params = {"query": 'release:"Audio"', "fmt": "json", "limit": 10}
headers = {"User-Agent": "MediaLibrary/0.3.0"}
r = requests.get("https://musicbrainz.org/ws/2/release", params=params, headers=headers, timeout=10)
releases = r.json().get("releases", [])
print(f"MusicBrainz returned {len(releases)} releases for query 'Audio':")
for i, rel in enumerate(releases[:8]):
    media_list = rel.get("media", [])
    tc = media_list[0].get("track-count", "?") if media_list else "?"
    credits = [
        a["artist"]["name"]
        for a in rel.get("artist-credit", [])
        if isinstance(a, dict) and "artist" in a
    ]
    print(f"  {i+1}. \"{rel['title']}\" by {', '.join(credits)}  (tracks={tc})")

print()
print("The disc had 10 tracks.")
print("The matcher picks the FIRST release with track_count == 10:")
for rel in releases:
    media_list = rel.get("media", [])
    if media_list:
        tc = media_list[0].get("track-count", 0)
        if tc == 10:
            credits = [
                a["artist"]["name"]
                for a in rel.get("artist-credit", [])
                if isinstance(a, dict) and "artist" in a
            ]
            print(f"  -> Matched: \"{rel['title']}\" by {', '.join(credits)}")
            print(f"     MusicBrainz ID: {rel['id']}")
            break

print()
print("=== Root Cause ===")
print("1. macOS mounted the Casting Crowns CD with a generic volume name: 'Audio CD'")
print("2. _clean_search_title removed 'CD' as noise -> search query became just 'Audio'")
print("3. 'Audio' is also an album by Raindancer which happened to have 10 tracks")
print("4. Track-count matching picked it as the best match")
print()
print("=== Fix needed ===")
print("When the cleaned title is very generic (1 short word), the name-based")
print("search is unreliable. We should:")
print("  a) Use disc TOC / track durations for better disambiguation")
print("  b) Skip name-based search when the title is too generic")
print("  c) Prefer AcoustID fingerprinting (needs ACOUSTID_API_KEY)")
