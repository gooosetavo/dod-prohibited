"""
Loads substance overrides from overrides.yaml, allowing manual specification
of data (e.g., UNII codes) for substances that cannot be matched automatically.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_OVERRIDES_PATH = Path("overrides.yaml")


def load_overrides(path: Path = _DEFAULT_OVERRIDES_PATH) -> Dict[str, Any]:
    """
    Load substance overrides from a YAML file.

    Args:
        path: Path to the overrides YAML file. Defaults to overrides.yaml
              in the current working directory.

    Returns:
        Dictionary of overrides keyed by substance slug, or empty dict if
        the file does not exist or cannot be parsed.
    """
    if not path.exists():
        return {}

    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data or "substances" not in data:
            return {}
        return data["substances"] or {}
    except Exception as e:
        logger.warning("Could not load overrides from %s: %s", path, e)
        return {}


def get_unii_override(overrides: Dict[str, Any], slug: str) -> Optional[str]:
    """
    Return the UNII code override for a substance slug, or None if not set.

    Args:
        overrides: Overrides dict as returned by load_overrides().
        slug: URL-safe slug for the substance (e.g. "kratom").

    Returns:
        UNII code string, or None.
    """
    entry = overrides.get(slug)
    if not entry:
        return None
    return entry.get("unii")
