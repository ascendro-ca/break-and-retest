import pytest

from gating_utils import apply_level2_gating


def _make_sig(pattern_pts, volume_pts, retest=30, ignition=25, trend=10):
    return {
        "points": {
            "breakout": pattern_pts + volume_pts,  # total breakout points
            "retest": retest,
            "ignition": ignition,
            "trend": trend,
            "breakout_pattern_pts": pattern_pts,
            "breakout_volume_pts": volume_pts,
        }
    }


def test_a_grade_component_mins_filtering():
    profile_name = "a"
    base_profile = {
        "name": "a",
        "breakout_pattern_score_min": 15,
        "breakout_volume_score_min": 5,
    }
    # Signals spanning below/above thresholds
    sigs = [
        _make_sig(13, 5),  # pattern below min -> filtered
        _make_sig(15, 2),  # volume below min -> filtered
        _make_sig(15, 5),  # meets mins
        _make_sig(20, 10),  # strong
    ]
    # All have same other component points; compute total >= 86 rule check
    # Total points for first sig: (13+5)+30+25+10=83 (<86) so filtered by threshold anyway
    # Second: (15+2)+30+25+10=82 (<86) filtered by threshold
    # Third: (15+5)+30+25+10=85 (<86) still fails threshold; ensure gating handles both rules
    # Fourth: (20+10)+30+25+10=95 passes all
    filtered, stats = apply_level2_gating(profile_name, base_profile, sigs, verbose=False)
    # Expect only last signal survives (index 3)
    assert len(filtered) == 1
    assert filtered[0]["points"]["breakout_pattern_pts"] == 20
    assert stats["component_filter_applied"] is True
    assert stats["pattern_min"] == 15
    assert stats["volume_min"] == 5


def test_no_component_mins_when_fields_absent():
    profile_name = "b"
    base_profile = {"name": "b"}  # no min fields
    sigs = [
        _make_sig(10, 0),  # low
        _make_sig(13, 2),
        _make_sig(15, 5),
        _make_sig(18, 10),
    ]
    # Apply gating; only threshold matters (B threshold = 70 points)
    filtered, stats = apply_level2_gating(profile_name, base_profile, sigs, verbose=False)
    # Compute totals to reason: (10+0)+30+25+10=75 passes, (13+2)+30+25+10=80 passes,
    # (15+5)+30+25+10=85 passes, (18+10)+30+25+10=93 passes -> all 4 survive
    assert len(filtered) == 4
    assert stats["component_filter_applied"] is False
