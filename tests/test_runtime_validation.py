"""
Runtime validation tests.
Verifies that ripped file durations closely match TMDB metadata runtimes.
"""

import json
import subprocess
import pytest
from pathlib import Path


def get_file_duration_seconds(file_path: str) -> float:
    """Get video file duration in seconds using mediainfo."""
    try:
        result = subprocess.run(
            ["mediainfo", "--Output=JSON", file_path], capture_output=True, text=True, check=True
        )
        data = json.loads(result.stdout)
        if data.get("media") and "track" in data["media"]:
            for track in data["media"]["track"]:
                if track.get("@type", "").lower() == "general":
                    return float(track.get("Duration", 0))
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        pass
    return 0.0


def load_metadata_for_file(file_path: str) -> dict:
    """Load the metadata JSON that corresponds to a media file."""
    from src.utils import get_data_dir

    metadata_dir = get_data_dir() / "metadata"
    stem = Path(file_path).stem
    meta_file = metadata_dir / f"{stem}.json"
    if meta_file.exists():
        with open(meta_file, "r") as f:
            return json.load(f)
    return {}


# ── Discover media files with metadata ───────────────────────────


def _discover_media_with_runtime():
    """Find all ripped files that have both a real file and TMDB runtime."""
    from src.utils import load_config

    config = load_config()
    library = Path(config["output"]["base_directory"])

    if not library.exists():
        return []

    pairs = []
    movies_dir = library / "movies"
    if not movies_dir.exists():
        return []
    for fp in movies_dir.iterdir():
        if fp.suffix.lower() not in (".mp4", ".mkv", ".m4v", ".avi", ".mov"):
            continue
        meta = load_metadata_for_file(str(fp))
        tmdb_runtime = (meta.get("tmdb") or {}).get("runtime_minutes")
        if tmdb_runtime:
            pairs.append((str(fp), tmdb_runtime))
    return pairs


_MEDIA_PAIRS = _discover_media_with_runtime()


# ── Tests ────────────────────────────────────────────────────────


@pytest.mark.skipif(not _MEDIA_PAIRS, reason="No media files with TMDB runtime found")
class TestRuntimeValidation:
    """Verify ripped file runtimes match their TMDB metadata."""

    TOLERANCE_MINUTES = 15  # allow ±15 min difference (accounts for disc extras, wrong TMDB match)

    @pytest.mark.parametrize(
        "file_path,expected_runtime_min", _MEDIA_PAIRS, ids=[Path(p).stem for p, _ in _MEDIA_PAIRS]
    )
    def test_runtime_matches_metadata(self, file_path, expected_runtime_min):
        """File duration should be within tolerance of TMDB runtime."""
        duration_sec = get_file_duration_seconds(file_path)
        assert duration_sec > 0, f"Could not read duration for {file_path}"

        actual_min = duration_sec / 60.0
        diff = abs(actual_min - expected_runtime_min)

        assert diff <= self.TOLERANCE_MINUTES, (
            f"Runtime mismatch for {Path(file_path).name}: "
            f"file={actual_min:.1f} min, TMDB={expected_runtime_min} min, "
            f"diff={diff:.1f} min (tolerance={self.TOLERANCE_MINUTES} min)"
        )

    @pytest.mark.parametrize(
        "file_path,expected_runtime_min", _MEDIA_PAIRS, ids=[Path(p).stem for p, _ in _MEDIA_PAIRS]
    )
    def test_file_is_not_truncated(self, file_path, expected_runtime_min):
        """File should be at least 50% of the expected runtime (not truncated)."""
        duration_sec = get_file_duration_seconds(file_path)
        if duration_sec == 0:
            pytest.skip("mediainfo not available")

        actual_min = duration_sec / 60.0
        min_acceptable = expected_runtime_min * 0.5

        assert actual_min >= min_acceptable, (
            f"File appears truncated: {Path(file_path).name} "
            f"is {actual_min:.1f} min but expected ~{expected_runtime_min} min"
        )


class TestRuntimeValidationUnit:
    """Unit tests for the runtime validation helpers."""

    def test_get_duration_nonexistent_file(self):
        """Should return 0 for missing files."""
        assert get_file_duration_seconds("/nonexistent/file.mp4") == 0.0

    def test_load_metadata_nonexistent(self):
        """Should return empty dict for files without metadata."""
        result = load_metadata_for_file("/tmp/nonexistent_file_xyz.mp4")
        assert result == {}

    def test_metadata_loads_for_real_files(self):
        """Metadata JSON files should be loadable and well-formed."""
        from src.utils import get_data_dir

        meta_dir = get_data_dir() / "metadata"
        if not meta_dir.exists():
            pytest.skip("No metadata directory")

        json_files = list(meta_dir.glob("*.json"))
        for jf in json_files:
            with open(jf, "r") as f:
                data = json.load(f)
            assert isinstance(data, dict), f"{jf.name} is not a valid JSON object"
            assert "source_file" in data or "tmdb" in data, f"{jf.name} missing expected keys"
