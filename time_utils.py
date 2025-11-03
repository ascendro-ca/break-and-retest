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

import datetime
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

    Note: Returns the configured abbreviation (e.g., "PST") which represents the timezone family.
    For actual DST-aware abbreviations in reports, use get_timezone_label_for_date().
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


def get_timezone_label_for_date(
    tzinfo: ZoneInfo, sample_date: datetime.datetime | None = None
) -> str:
    """
    Get the actual timezone abbreviation (e.g., PST or PDT) for a given date.

    Args:
        tzinfo: The timezone to check
        sample_date: A representative date to check DST status. If None, uses current time.

    Returns:
        The timezone abbreviation (e.g., "PDT" or "PST")
    """
    import datetime

    if sample_date is None:
        sample_date = datetime.datetime.now(tz=tzinfo)
    elif sample_date.tzinfo is None:
        sample_date = sample_date.replace(tzinfo=tzinfo)
    else:
        sample_date = sample_date.astimezone(tzinfo)

    return sample_date.strftime("%Z")
