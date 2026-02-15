#!/usr/bin/env python3
"""Download cover art for Casting Crowns and Sons of Korah."""
import shutil
import time
import urllib.request
from pathlib import Path

THUMBS = Path("/Users/poppemacmini/Media/data/thumbnails")

albums = [
    {
        "name": "Casting Crowns",
        "url": "https://coverartarchive.org/release/5fa87c4d-8e2c-4a00-89ab-1ae980031264/front",
        "dest": THUMBS / "Casting Crowns_poster.jpg",
        "track_prefix": [
            "01 - What If His People Prayed",
            "02 - If We Are the Body",
            "03 - Voice of Truth",
            "04 - Who Am I",
            "05 - American Dream",
            "06 - Here I Go Again",
            "07 - Praise You With the Dance",
            "08 - Glory",
            "09 - Life of Praise",
            "10 - Your Love Is Extravagant",
        ],
    },
    {
        "name": "Shelter (Sons of Korah)",
        "url": "https://coverartarchive.org/release/1f20a51f-ab50-4504-b1e7-2fe83813e164/front",
        "dest": THUMBS / "Shelter_poster.jpg",
        "track_prefix": [
            "01 - Psalm 35 (Contend)",
            "02 - Psalm 1 (Blessed is the Man)",
            "03 - Psalm 37a (Shine Like the Dawn)",
            "04 - Psalm 127 (Unless the Lord Builds the House)",
            "05 - Psalm 30 (Garments of Joy)",
            "06 - Psalm 73 (Whom Have I in Heaven but You)",
            "07 - Psalm 123 (I Lift Up My Eyes)",
            "08 - Psalm 128 (Olive Plants)",
            "09 - Psalm 37b (Be Still Before the Lord)",
            "10 - Psalm 51 (A Broken Spirit and a Contrite Heart)",
        ],
    },
]

for album in albums:
    print(f"\n{album['name']}:")
    try:
        req = urllib.request.Request(
            album["url"], headers={"User-Agent": "MediaLibrary/1.0 (contact@example.com)"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        with open(album["dest"], "wb") as f:
            f.write(data)
        print(f"  Downloaded: {album['dest'].name} ({len(data)} bytes)")

        # Copy to per-track posters
        for stem in album["track_prefix"]:
            dest = THUMBS / f"{stem}_poster.jpg"
            shutil.copy2(str(album["dest"]), str(dest))
        print(f"  Copied to {len(album['track_prefix'])} track posters")

    except Exception as e:
        print(f"  FAILED: {e}")

    time.sleep(2)

print("\nDone!")
