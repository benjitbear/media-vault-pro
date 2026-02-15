"""
Poster-sync helpers used after rip jobs complete.
"""

import json
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from ..constants import AUDIO_EXTENSIONS
from ..utils import get_data_dir, natural_sort_key

if TYPE_CHECKING:
    import logging

    from ..metadata import MetadataExtractor


def sync_video_poster(
    new_path: str, metadata: dict, metadata_extractor: "MetadataExtractor", logger: "logging.Logger"
) -> None:
    """Ensure a poster exists that matches the renamed video file stem.

    The web server looks for ``{stem}_poster.jpg`` in the thumbnails dir.
    """
    poster_src = metadata.get("poster_file", "")
    if not poster_src or not os.path.exists(poster_src):
        return

    thumbnails_dir = get_data_dir() / "thumbnails"
    new_stem = Path(new_path).stem
    dest = thumbnails_dir / f"{new_stem}_poster.jpg"

    if dest.exists() or dest == Path(poster_src):
        return

    try:
        shutil.copy2(poster_src, str(dest))
        metadata["poster_file"] = str(dest)
        logger.info("Poster synced: %s", dest.name)
    except Exception as e:
        logger.error("Failed to sync poster: %s", e)


def sync_album_poster(
    album_dir: str,
    metadata: dict,
    metadata_extractor: "MetadataExtractor",
    logger: "logging.Logger",
) -> None:
    """Copy album cover art so each track has a matching poster.

    Also re-saves per-track metadata JSONs with the correct ``poster_file``.
    """
    poster_src = metadata.get("poster_file", "")
    if not poster_src or not os.path.exists(poster_src):
        return

    thumbnails_dir = get_data_dir() / "thumbnails"
    for track_file in sorted(Path(album_dir).iterdir(), key=natural_sort_key):
        if track_file.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        dest = thumbnails_dir / f"{track_file.stem}_poster.jpg"
        try:
            shutil.copy2(poster_src, str(dest))
        except Exception as e:
            logger.error("Failed to copy poster for %s: %s", track_file.name, e)

        # Update per-track metadata JSON with poster path
        track_meta_file = get_data_dir() / "metadata" / f"{track_file.stem}.json"
        if track_meta_file.exists():
            try:
                with open(track_meta_file, "r") as f:
                    track_meta = json.load(f)
                track_meta["poster_file"] = str(dest)
                with open(track_meta_file, "w") as f:
                    json.dump(track_meta, f, indent=2)
            except Exception as e:
                logger.debug("Failed to update track metadata JSON %s: %s", track_meta_file, e)
