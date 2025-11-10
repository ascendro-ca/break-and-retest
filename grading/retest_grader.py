"""Retest grader (pass-through).

Profiles are shells only; this grader no longer enforces thresholds and always
returns pass if the retest candle parses. Signature retained for compatibility.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple


def grade_retest(
    retest_candle: Dict[str, float],
    *,
    level: float,
    direction: str,
    breakout_time,
    retest_time,
    breakout_volume: float,
    retest_volume: float,
    breakout_candle: Optional[Dict[str, float]] = None,
    profile: Dict,
) -> Tuple[bool, str]:
    # Thresholds removed entirely: validate candle shape only.
    try:
        float(retest_candle.get("Open"))
        float(retest_candle.get("High"))
        float(retest_candle.get("Low"))
        float(retest_candle.get("Close"))
    except Exception:
        return False, "invalid_candle"
    return True, "ok"
