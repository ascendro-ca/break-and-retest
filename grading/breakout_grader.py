"""Breakout grader (pass-through).

Profiles are shells only; this grader no longer enforces thresholds and always
returns pass if the candle parses. Signature retained for compatibility.
"""

from __future__ import annotations

from typing import Dict, Tuple


def grade_breakout(candle: Dict[str, float], vol_ratio: float, profile: Dict) -> Tuple[bool, str]:
    # Thresholds removed entirely: validate candle shape only.
    try:
        float(candle.get("Open"))
        float(candle.get("High"))
        float(candle.get("Low"))
        float(candle.get("Close"))
    except Exception:
        return False, "invalid_candle"
    return True, "ok"
