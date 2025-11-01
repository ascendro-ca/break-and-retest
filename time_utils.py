"""
Centralized timezone handling for reporting.

- Accepts 2-3 letter timezone abbreviations via config.json
- Maps to IANA timezones for conversion
- Defaults to PDT (America/Los_Angeles) if not configured

Supported keys in config.json:
{
  "timezone": "PDT"  # or PT, PST, PDT, ET, EST, EDT, CT, CST, CDT, MT, MST, MDT, UTC
}
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from zoneinfo import ZoneInfo

# Map common US abbreviations to IANA zones
_ABBREV_TO_IANA: Dict[str, str] = {
    # Pacific
    "PDT": "America/Los_Angeles",
    "PST": "America/Los_Angeles",
    "PT": "America/Los_Angeles",
    # Mountain
    "MDT": "America/Denver",
    "MST": "America/Denver",
    "MT": "America/Denver",
    # Central
    "CDT": "America/Chicago",
    "CST": "America/Chicago",
    "CT": "America/Chicago",
    # Eastern
    "EDT": "America/New_York",
    "EST": "America/New_York",
    "ET": "America/New_York",
    # UTC
    "UTC": "UTC",
}

_DEFAULT_ABBREV = "PDT"


def _load_config(config_path: Path) -> dict:
    if config_path.exists():
        try:
            import json

            with open(config_path, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def get_display_timezone(config_dir: Path | None = None) -> Tuple[ZoneInfo, str]:
    """
    Returns a pair (tzinfo, label_abbrev) for reporting.

    Reads config.json in the provided directory (or the script directory if None).
    Defaults to PDT if not configured or unmapped.
    """
    base_dir = config_dir if config_dir is not None else Path(__file__).parent
    config = _load_config(base_dir / "config.json")

    # Support both "timezone" and legacy "timezone_abbrev"
    abbrev = str(config.get("timezone") or config.get("timezone_abbrev") or _DEFAULT_ABBREV).upper()

    iana = _ABBREV_TO_IANA.get(abbrev)
    if not iana:
        # Fallback to default
        abbrev = _DEFAULT_ABBREV
        iana = _ABBREV_TO_IANA[_DEFAULT_ABBREV]

    try:
        tzinfo = ZoneInfo(iana)
    except Exception:
        tzinfo = ZoneInfo("UTC")
        abbrev = "UTC"

    return tzinfo, abbrev
