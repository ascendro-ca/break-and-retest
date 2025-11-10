"""Ignition grader using profile thresholds (post-entry follow-through).

With name-only profile shells, missing fields default to permissive behavior
(no gating). Backward compatibility retained if thresholds are reintroduced.
"""

from __future__ import annotations

from typing import Dict, Tuple


def grade_ignition(
    ignition_candle: Dict[str, float],
    *,
    ignition_body_pct: float,
    ignition_vol_ratio: float,
    progress: float,
    profile: Dict,
) -> Tuple[bool, str]:
    th = profile.get("ignition", {})
    if not th:
        return True, "ok"
