"""Level 2 gating utilities.

Provides a testable function `apply_level2_gating` which encapsulates
points threshold enforcement and optional component minimums for
breakout pattern & volume based on profile fields.

Profile fields (optional):
  - breakout_pattern_score_min
  - breakout_volume_score_min

If absent, component minimums are not applied.
"""

from __future__ import annotations

from typing import Dict, List, Tuple


def apply_level2_gating(
    profile_name: str,
    grade_profile: Dict,
    graded_signals: List[Dict],
    *,
    verbose: bool = True,
) -> Tuple[List[Dict], Dict[str, float]]:
    """Apply Level 2 gating rules.

    Rules:
      1. Total points threshold determined by profile_name -> min percentage of 100.
      2. If profile has breakout_pattern_score_min and breakout_volume_score_min, enforce
         those minima against per-signal detailed breakout component scores
         (fields: points.breakout_pattern_pts, points.breakout_volume_pts).

    Returns filtered signals and stats dict.
    """
    # Map grade name to min percentage of full max (100)
    grade_min_pct = {"c": 0.56, "b": 0.70, "a": 0.86, "aplus": 0.95}
    min_pct = grade_min_pct.get(profile_name, 0.56)
    full_max = 100.0
    min_points = min_pct * full_max

    def _total_points(sig: Dict) -> float:
        pts = sig.get("points", {}) or {}
        return (
            float(pts.get("breakout", 0) or 0)
            + float(pts.get("retest", 0) or 0)
            + float(pts.get("ignition", 0) or 0)
            + float(pts.get("trend", 0) or 0)
        )

    before_total = len(graded_signals)
    filtered = [s for s in graded_signals if _total_points(s) >= min_points]
    after_total = len(filtered)

    # Component minima (optional)
    bp_min = float(grade_profile.get("breakout_pattern_score_min", -1))
    bv_min = float(grade_profile.get("breakout_volume_score_min", -1))
    applied_component_filter = bp_min >= 0 and bv_min >= 0

    before_comp = len(filtered)
    if applied_component_filter:

        def _passes(sig: Dict) -> bool:
            pts = sig.get("points", {}) or {}
            pat = float(pts.get("breakout_pattern_pts", 0) or 0)
            vol = float(pts.get("breakout_volume_pts", 0) or 0)
            return pat >= bp_min and vol >= bv_min

        filtered = [s for s in filtered if _passes(s)]
    after_comp = len(filtered)

    if verbose:
        print(
            (
                f"Level2 gating grade={profile_name} threshold>={min_points:.2f}/100 "
                f"signals {before_total}->{after_total}"
            )
        )
        if applied_component_filter:
            print(
                (
                    f"Component mins pattern>={bp_min} volume>={bv_min} "
                    f"signals {before_comp}->{after_comp}"
                )
            )

    stats = {
        "profile": profile_name,
        "threshold_points": min_points,
        "pre_total_count": before_total,
        "post_total_count": after_total,
        "component_filter_applied": applied_component_filter,
        "pattern_min": bp_min if applied_component_filter else None,
        "volume_min": bv_min if applied_component_filter else None,
        "pre_component_count": before_comp if applied_component_filter else None,
        "post_component_count": after_comp if applied_component_filter else None,
    }
    return filtered, stats


__all__ = ["apply_level2_gating"]
