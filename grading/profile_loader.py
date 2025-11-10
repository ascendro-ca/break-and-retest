"""Grade profile loader (simplified).

Loads JSON profiles from grading/profiles/grade_<name>.json and caches them.

Simplified schema:
{
    "name": "c"
}

All other threshold fields are intentionally removed to baseline behavior to
Level 1 (no profile-driven gating). Downstream graders will default to
permissive thresholds when fields are absent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

_CACHE: Dict[str, Dict[str, Any]] = {}


def load_profile(name: str) -> Dict[str, Any]:
    key = name.strip().lower()
    if key in _CACHE:
        return _CACHE[key]
    base_dir = Path(__file__).parent / "profiles"
    path = base_dir / f"grade_{key}.json"
    if not path.exists():
        raise FileNotFoundError(f"Grade profile '{name}' not found at {path}")
    data = json.loads(path.read_text())
    _CACHE[key] = data
    return data
