"""
Configuration loading and validation for the MediaLibrary application.

Centralises config parsing so it happens once at startup rather than
redundantly in every component constructor.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from .constants import DEFAULT_CONFIG_PATH

# Required top-level keys and the sub-keys that must exist within them.
_REQUIRED_SCHEMA: Dict[str, List[str]] = {
    "output": [
        "base_directory",
        "format",
        "video_encoder",
        "quality",
        "audio_encoder",
        "audio_bitrate",
    ],
    "metadata": ["save_to_json"],
    "automation": ["auto_detect_disc"],
    "web_server": ["port", "host", "library_name"],
    "disc_detection": ["check_interval_seconds", "mount_path"],
    "auth": ["enabled"],
}

# Keys that must exist at the top level but need no sub-key validation.
_REQUIRED_TOP_KEYS: List[str] = [
    "output",
    "metadata",
    "automation",
    "web_server",
    "disc_detection",
    "auth",
]


class ConfigError(Exception):
    """Raised when the configuration file is missing or invalid."""


def load_config(config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """
    Load configuration from a JSON file and resolve ``${ENV_VAR:-default}``
    placeholders in all string values.

    Args:
        config_path: Path to the config file (relative to project root)

    Returns:
        Fully-resolved configuration dictionary.

    Raises:
        ConfigError: If the file cannot be read or parsed.
    """
    base_dir = Path(__file__).parent.parent
    full_path = base_dir / config_path

    if not full_path.exists():
        raise ConfigError(f"Configuration file not found: {full_path}")

    try:
        with open(full_path, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {full_path}: {exc}") from exc

    return _resolve(config)


def validate_config(config: Dict[str, Any]) -> List[str]:
    """
    Validate a config dict against the required schema.

    Returns:
        A list of human-readable error strings.  Empty means valid.
    """
    errors: List[str] = []

    for key in _REQUIRED_TOP_KEYS:
        if key not in config:
            errors.append(f"Missing required config section: '{key}'")

    for section, sub_keys in _REQUIRED_SCHEMA.items():
        if section not in config:
            continue  # already reported above
        for sub in sub_keys:
            if sub not in config[section]:
                errors.append(f"Missing required key '{sub}' in config section '{section}'")

    # Validate base_directory is not an unresolved placeholder
    base_dir = config.get("output", {}).get("base_directory", "")
    if base_dir.startswith("${"):
        errors.append(
            f"output.base_directory is an unresolved placeholder: '{base_dir}'. "
            "Set the MEDIA_ROOT environment variable."
        )

    return errors


# ── Private helpers ──────────────────────────────────────────────

_PLACEHOLDER_RE = re.compile(r"\$\{(\w+)(?::-([^}]*))?\}")


def _resolve(obj: Any) -> Any:
    """Recursively resolve ``${ENV_VAR:-default}`` in string values."""
    if isinstance(obj, str):
        return _PLACEHOLDER_RE.sub(_replace_match, obj)
    elif isinstance(obj, dict):
        return {k: _resolve(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve(v) for v in obj]
    return obj


def _replace_match(m: re.Match) -> str:
    var = m.group(1)
    default = m.group(2) if m.group(2) is not None else ""
    return os.environ.get(var, default)
