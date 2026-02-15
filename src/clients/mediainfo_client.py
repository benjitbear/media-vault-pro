"""MediaInfo / ffprobe CLI wrappers."""

import json
import os
import subprocess
from typing import Any, Dict, List, Optional

from ..utils import setup_logger


class MediaInfoClient:
    """Extract technical metadata from media files via local CLI tools."""

    def __init__(self) -> None:
        """Initialise the MediaInfo client."""
        self.logger = setup_logger("mediainfo_client", "metadata.log")

    def extract_mediainfo(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Extract technical metadata using MediaInfo.

        Args:
            file_path: Path to media file

        Returns:
            Dictionary with media information, or None on failure.
        """
        self.logger.info("Extracting mediainfo from: %s", file_path)

        try:
            result = subprocess.run(
                ["mediainfo", "--Output=JSON", file_path],
                capture_output=True,
                text=True,
                check=True,
            )

            data = json.loads(result.stdout)

            metadata: Dict[str, Any] = {
                "file_path": file_path,
                "file_size_bytes": os.path.getsize(file_path),
                "tracks": [],
            }

            if "media" in data and "track" in data["media"]:
                for track in data["media"]["track"]:
                    track_type = track.get("@type", "").lower()

                    if track_type == "general":
                        metadata["duration_seconds"] = float(track.get("Duration", 0))
                        metadata["format"] = track.get("Format", "")
                        metadata["file_size"] = track.get("FileSize", "")

                    elif track_type == "video":
                        metadata["video"] = {
                            "codec": track.get("Format", ""),
                            "width": track.get("Width", ""),
                            "height": track.get("Height", ""),
                            "frame_rate": track.get("FrameRate", ""),
                            "bit_depth": track.get("BitDepth", ""),
                        }

                    elif track_type == "audio":
                        metadata["tracks"].append(
                            {
                                "type": "audio",
                                "language": track.get("Language", "Unknown"),
                                "codec": track.get("Format", ""),
                                "channels": track.get("Channels", ""),
                                "sampling_rate": track.get("SamplingRate", ""),
                            }
                        )

                    elif track_type == "text":
                        metadata["tracks"].append(
                            {
                                "type": "subtitle",
                                "language": track.get("Language", "Unknown"),
                                "format": track.get("Format", ""),
                            }
                        )

            self.logger.info("Successfully extracted mediainfo")
            return metadata

        except subprocess.CalledProcessError as e:
            self.logger.error("MediaInfo error: %s", e)
            return None
        except Exception as e:
            self.logger.error("Error extracting mediainfo: %s", e)
            return None

    def extract_chapters(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Extract chapter information from a media file using ffprobe.

        Args:
            file_path: Path to media file

        Returns:
            List of chapter dicts (title, start, end).
        """
        self.logger.info("Extracting chapters from: %s", file_path)

        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_chapters",
                    file_path,
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            data = json.loads(result.stdout)
            chapters: List[Dict[str, Any]] = []

            for ch in data.get("chapters", []):
                chapters.append(
                    {
                        "title": ch.get("tags", {}).get("title", f"Chapter {len(chapters) + 1}"),
                        "start_time": float(ch.get("start_time", 0)),
                        "end_time": float(ch.get("end_time", 0)),
                    }
                )

            self.logger.info("Found %s chapters", len(chapters))
            return chapters

        except subprocess.CalledProcessError as e:
            self.logger.error("ffprobe error: %s", e)
            return []
        except Exception as e:
            self.logger.error("Error extracting chapters: %s", e)
            return []
