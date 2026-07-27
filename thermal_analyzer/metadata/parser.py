"""Parse operating conditions from run filenames."""

from pathlib import Path
import re
from typing import Any, Mapping


_NUMBER = r"([-+]?\d+(?:\.\d+)?)"
DEFAULT_PATTERNS: dict[str, str] = {
    "VAC": rf"{_NUMBER}\s*VAC",
    "HV": rf"{_NUMBER}\s*VHV",
    "LV_current": rf"{_NUMBER}\s*ALV",
    "ambient_temp": rf"{_NUMBER}\s*(?:Degree|DegC|°C)",
}


def parse_metadata(
    filename: str,
    patterns: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Extract numeric metadata using configurable, case-insensitive patterns."""
    stem = Path(filename).stem
    parsed: dict[str, Any] = {}
    for key, pattern in (patterns or DEFAULT_PATTERNS).items():
        match = re.search(pattern, stem, re.IGNORECASE)
        if not match:
            continue
        value = match.group(1)
        try:
            parsed[key] = float(value)
        except (TypeError, ValueError):
            parsed[key] = value
    return parsed
