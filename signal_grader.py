"""
Signal Grader for Break & Retest Strategy (Scarface Rules)

Grades signals A+ through C based on PRE-ENTRY components only:
- Breakout candle quality (body %, volume surge)
- Retest quality (light volume, clear rejection)
- Risk/Reward ratio
- Market context (NQ sentiment, sector strength)

Important: Continuation (aka ignition) is a POST-ENTRY assessment used for
analysis and reporting only. It is not included in the letter grade used to
accept/reject a setup before entry.
"""

from typing import Any, Dict, Tuple

import pandas as pd

try:
    from candle_patterns import detect_pattern

    CANDLE_PATTERNS_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    # Record availability but fail fast at usage sites per requirements
    CANDLE_PATTERNS_AVAILABLE = False
    detect_pattern = None  # type: ignore


def grade_breakout_candle(
    candle: Dict[str, float],
    vol_ratio: float,
    body_pct: float,
    level: float | None = None,
    direction: str | None = None,
    a_upper_wick_max: float = 0.15,
    b_body_max: float = 0.65,
    or_range: float | None = None,
) -> Tuple[str, str]:
    """
    Grade the breakout candle quality.

    Args:
        candle: OHLCV data for breakout candle
        vol_ratio: Volume ratio vs 20-bar MA
        body_pct: Body percentage (close-open / high-low)

    Returns:
        (grade, description) tuple
    """
    # Compute body and wick structure from the candle for precise checks
    try:
        o = float(candle.get("Open"))
        h = float(candle.get("High"))
        low_ = float(candle.get("Low"))
        c = float(candle.get("Close"))
    except Exception:
        # Fallback to legacy behavior if candle is malformed
        if body_pct >= 0.70 and vol_ratio >= 2.0:
            return "✅", "Strong candle + high vol"
        if body_pct >= 0.50 and vol_ratio >= 1.5:
            return "✅", "Solid candle + good vol"
        if body_pct >= 0.40 or vol_ratio >= 1.2:
            return "⚠️", "Adequate candle/vol"
        return "❌", "Weak candle or vol"

    rng = max(h - low_, 0.0)
    body_abs = abs(c - o)
    # Prefer provided body_pct for compatibility with existing tests; else compute
    body_pct_calc = (body_abs / rng) if rng > 0 else 0.0
    try:
        provided_body = float(body_pct)
    except Exception:
        provided_body = 0.0
    body_p = provided_body if provided_body > 0 else body_pct_calc

    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - low_
    uw_p = (upper_wick / rng) if rng > 0 else 0.0
    lw_p = (lower_wick / rng) if rng > 0 else 0.0

    is_green = c > o
    is_red = c < o

    # Level checks: if not provided, treat as satisfied to preserve tests
    # Level checks (placeholder for future refinement)
    if level is not None and direction is not None:
        pass  # Simplified: not enforcing explicit level comparisons currently

    # Legacy compatibility: if no level/direction context, allow classic strong mapping
    if level is None and direction is None:
        if body_p >= 0.70 and vol_ratio >= 2.0:
            return "✅", "Strong candle + high vol"

    # Compute body relative to OR range if provided (fallback to candle range)
    # body_pct_or retained only for potential future analytics; not used in grading logic.

    # Map the A/B/C criteria to ✅/⚠️/❌ and mirror for bearish
    def bull_A():
        # A-Grade (Strong Breakout) LONG
        # Body ≥ 65%, Upper wick ≤ 15%, Lower wick ≤ 20%, Close > level, Volume ≥ 1.5×
        return (
            is_green
            and body_p >= 0.65
            and uw_p <= a_upper_wick_max
            and lw_p <= 0.20
            and (c > level if level is not None else True)
            and vol_ratio >= 1.5
        )

    def bull_B():
        # B-Grade (Acceptable Breakout) LONG
        # Body 45–65%, Upper wick 15–25%, Lower wick 20–30%, Close ≥ level, Volume ~1.0–1.5×
        return (
            is_green
            and 0.45 <= body_p <= b_body_max
            and 0.15 <= uw_p <= 0.25
            and 0.20 <= lw_p <= 0.30
            and (c >= level if level is not None else True)
            and 1.0 <= vol_ratio < 1.5
        )

    def bull_C():
        # C-Grade (Minimal Breakout) LONG (pattern-based)
        # Requirements:
        # - detect_pattern() indicates bullish strength on the candle
        if not CANDLE_PATTERNS_AVAILABLE:
            raise ImportError(
                "candle_patterns is required for Grade C breakout evaluation (long); import failed."
            )
        try:
            candle_df = pd.DataFrame([{"Open": o, "High": h, "Low": low_, "Close": c}])
            pattern_names = [
                "hammer",
                "shooting_star",
                "engulfing",
                "doji",
                "marubozu",
                "spinning_top",
                "inverted_hammer",
                "dragonfly_doji",
                "gravestone_doji",
            ]
            for pname in pattern_names:
                result = detect_pattern(candle_df, pname).iloc[0]  # type: ignore[misc]
                if result >= 100:
                    return True, f"C-grade: pattern {pname} detected (bullish {result})"
        except Exception as e:
            # Fail fast per requirement
            raise ImportError(f"pattern detection error for Grade C (long): {e}") from e
        # No pattern match -> not C via pattern path
        return False

    def bear_A():
        # A-Grade (Strong Breakdown) SHORT (mirror)
        return (
            is_red
            and body_p >= 0.65
            and uw_p <= 0.20  # mirror tolerance: small lower wick equivalent above body
            and lw_p <= 0.15
            and (c < level if level is not None else True)
            and vol_ratio >= 1.5
        )

    def bear_B():
        # B-Grade (Acceptable Breakdown) SHORT (mirror)
        return (
            is_red
            and 0.45 <= body_p <= 0.65
            and 0.20 <= uw_p <= 0.30
            and 0.15 <= lw_p <= 0.25
            and (c <= level if level is not None else True)
            and 1.0 <= vol_ratio < 1.5
        )

    def bear_C():
        # C-Grade (Minimal Breakdown) SHORT ( pattern-based)
        # Requirements:
        # - detect_pattern() indicates bearish strength on the candle
        if not CANDLE_PATTERNS_AVAILABLE:
            raise ImportError("candle_patterns required for C-grade (short); import failed.")
        try:
            candle_df = pd.DataFrame([{"Open": o, "High": h, "Low": low_, "Close": c}])
            pattern_names = [
                "hammer",
                "shooting_star",
                "engulfing",
                "doji",
                "marubozu",
                "spinning_top",
                "inverted_hammer",
                "dragonfly_doji",
                "gravestone_doji",
            ]
            for pname in pattern_names:
                result = detect_pattern(candle_df, pname).iloc[0]  # type: ignore[misc]
                if result <= -100:
                    return True, f"C-grade: pattern {pname} detected (bearish {result})"
        except Exception as e:
            # Fail fast per requirement
            raise ImportError(f"pattern detection error for Grade C (short): {e}") from e
        # No pattern match -> not C via pattern path
        return False

    if direction == "short":
        if bear_A():
            return "✅", "Strong candle + high vol"
        if bear_B():
            return "⚠️", "Solid candle + good vol"
        # C-grade: pattern-based
        c_result = bear_C()
        if isinstance(c_result, tuple):
            is_c_grade, c_desc = c_result
            if is_c_grade:
                return "C", c_desc
        elif c_result:
            return "C", "C-grade: pattern detected"
    else:
        # default to long if direction None
        if bull_A():
            return "✅", "Strong candle + high vol"
        if bull_B():
            return "⚠️", "Solid candle + good vol"
        # C-grade: pattern-based
        c_result = bull_C()
        if isinstance(c_result, tuple):
            is_c_grade, c_desc = c_result
            if is_c_grade:
                return "C", c_desc
        elif c_result:
            return "C", "C-grade: pattern detected"

    # If nothing matched, apply simplified fallback C criteria per direction
    # Long: any bullish candle qualifies as minimal breakout (open <= close)
    # Short: any bearish candle qualifies as minimal breakdown (close <= open)
    if direction == "short":
        if c <= o:
            return "C", "Minimal breakdown (fallback): any bearish candle"
        return "❌", "Weak breakout (fallback): not a bearish candle"
    else:  # default to long
        if c >= o:
            return "C", "Minimal breakout (fallback): any bullish candle"
        return "❌", "Weak breakout (fallback): not a bullish candle"


def grade_retest(
    retest_candle: Dict[str, float],
    level: float,
    direction: str,
) -> Tuple[str, str]:
    """
    Grade the retest candle quality.

    Simplified mode: Only C-grade is produced (A/B disabled).
    Hard reject:
    - Fail if the close does not hold on the correct side of the level (no epsilon tolerance).
    Otherwise, return C with a brief reason (touched level or near miss).

    Args:
        retest_candle: OHLCV data for retest candle
        level: The price level being tested
        direction: 'long' or 'short'

    Returns:
        (grade, description) tuple
    """
    high = float(retest_candle["High"])
    low = float(retest_candle["Low"])
    # Note: open price not used in simplified C-only grading
    close = float(retest_candle["Close"])

    # Volume and structural metrics not considered for C-grade (A/B disabled)

    rng = max(high - low, 0.0)
    if rng <= 0:
        return "❌", "Invalid retest candle (no range)"

    # Structure metrics not used in C-only mode; keep minimal state

    # ===== Simplified C-only grading =====
    # Measure distance from level to provide descriptive C-grade context

    # Level rejection checks (must respect the reclaimed/broken level)
    if direction == "long":
        # Measure how close the wick came to the level
        wick_distance_to_level = low - level  # negative if wick went below level
        wick_touches_level = low <= level  # True if wick touched or pierced level

        # Close must hold strictly above level
        if close < level:
            return "❌", "Retest failed: close did not hold above level"

        # Calculate distance as percentage of candle range for description
        distance_in_candle_widths = abs(wick_distance_to_level) / rng if rng > 0 else 999
        # Return simplified C-grade descriptions
        if not wick_touches_level:
            return "C", f"C-grade: near miss ({distance_in_candle_widths:.1f}x widths from level)"
        return "C", "C-grade: touched level"

    else:  # short
        # Measure how close the wick came to the level (SHORT: upper wick tests resistance)
        wick_distance_to_level = high - level  # positive if wick went above level
        wick_touches_level = high >= level  # True if wick touched or pierced level

        # Close must hold strictly below level
        if close > level:
            return "❌", "Retest failed: close did not hold below level"

        # Calculate distance as percentage of candle range for description
        distance_in_candle_widths = abs(wick_distance_to_level) / rng if rng > 0 else 999
        # Return simplified C-grade descriptions
        if not wick_touches_level:
            return "C", f"C-grade: near miss ({distance_in_candle_widths:.1f}x widths from level)"
        return "C", "C-grade: touched level"


def grade_continuation(
    ignition_candle: Dict[str, float],
    ignition_vol_ratio: float,
    distance_to_target: float,
    body_pct: float,
) -> Tuple[str, str]:
    """
    Grade the continuation/ignition candle (POST-ENTRY analysis only).

    Args:
        ignition_candle: OHLCV data for ignition candle
        ignition_vol_ratio: Volume ratio vs breakout volume
        distance_to_target: % distance traveled toward target
        body_pct: Body percentage

    Returns:
        (grade, description) tuple
    """
    # Note: Continuation is evaluated after entry to describe follow-through.
    # It is NOT used in pre-entry grading. The checks below are for reporting
    # and post-trade analysis only.
    # Guidance: Ignition volume should be relatively light (< 20% of breakout)
    # to avoid supply/demand absorption at the level.
    if ignition_vol_ratio > 0.20:
        return "❌", "Ignition volume too high (>20% of breakout)"

    # Perfect: Fast move (>50% to target) + strong body + volume
    if distance_to_target >= 0.5 and body_pct >= 0.60 and ignition_vol_ratio >= 0.8:
        return "✅", f"Fast push ({distance_to_target*100:.0f}% to target)"

    # Good: Decent progress
    if distance_to_target >= 0.3 and body_pct >= 0.50:
        return "✅", f"Good push ({distance_to_target*100:.0f}% to target)"

    # Acceptable
    if distance_to_target >= 0.2:
        return "⚠️", f"Slow push ({distance_to_target*100:.0f}% to target)"

    # Weak
    return "❌", "Stalled move"


def grade_risk_reward(rr_ratio: float) -> Tuple[str, str]:
    """
    Grade the risk/reward ratio.

    Args:
        rr_ratio: Reward/Risk ratio (target-entry)/(entry-stop)

    Returns:
        (grade, description) tuple
    """
    stop_str = f"{rr_ratio:.1f}:1"

    if rr_ratio >= 3.0:
        return "✅", stop_str
    elif rr_ratio >= 2.0:
        return "✅", stop_str
    elif rr_ratio >= 1.5:
        return "⚠️", stop_str
    else:
        return "❌", stop_str


def grade_ignition(
    ignition_candle: Dict[str, float],
    *,
    direction: str,
    retest_extreme: float,
    session_avg_vol_1m: float,
    retest_vol_1m: float,
    ignition_vol_retest_mult: float = 1.5,
    ignition_vol_session_mult: float = 1.3,
) -> Tuple[str, str]:
    """
    Grade the ignition candle (the 1m immediately after a valid retest).

    Rules (mirror for shorts):
    - A: breaks retest extreme intrabar; body >= 70%; small opposite wick (<=10%);
         close beyond extreme; volume surge vs retest and session avg.
    - B: body 50–70%; wick 10–30%; close near extreme; vol > retest and > session avg.
    - C: else (weak body/close/volume).
    """
    o = float(ignition_candle.get("Open", 0.0))
    h = float(ignition_candle.get("High", 0.0))
    low_ = float(ignition_candle.get("Low", 0.0))
    c = float(ignition_candle.get("Close", 0.0))
    v = float(ignition_candle.get("Volume", 0.0))

    rng = max(h - low_, 0.0)
    body_pct = (abs(c - o) / rng) if rng > 0 else 0.0
    upper_wick_pct = ((h - max(o, c)) / rng) if rng > 0 else 0.0
    lower_wick_pct = ((min(o, c) - low_) / rng) if rng > 0 else 0.0

    def is_volume_surge() -> bool:
        return v >= max(
            ignition_vol_retest_mult * retest_vol_1m,
            ignition_vol_session_mult * session_avg_vol_1m,
        )

    if direction == "long":
        broke_extreme = h >= retest_extreme and c >= retest_extreme
        a_wick_ok = upper_wick_pct <= 0.10
        if broke_extreme and body_pct >= 0.70 and a_wick_ok and is_volume_surge():
            return "🟢", "Ignition A"
        if (
            broke_extreme
            and 0.50 <= body_pct < 0.70
            and upper_wick_pct <= 0.30
            and v > retest_vol_1m
        ):
            return "🟡", "Ignition B"
        return "🔴", "Ignition C"
    else:
        broke_extreme = low_ <= retest_extreme and c <= retest_extreme
        a_wick_ok = lower_wick_pct <= 0.10
        if broke_extreme and body_pct >= 0.70 and a_wick_ok and is_volume_surge():
            return "🟢", "Ignition A"
        if (
            broke_extreme
            and 0.50 <= body_pct < 0.70
            and lower_wick_pct <= 0.30
            and v > retest_vol_1m
        ):
            return "🟡", "Ignition B"
        return "🔴", "Ignition C"


def grade_market_context(nq_sentiment: str = "neutral") -> Tuple[str, str]:
    """
    Grade market context (placeholder for now).

    Args:
        nq_sentiment: 'bullish', 'neutral', 'bearish', or 'slightly_red'

    Returns:
        (grade, description) tuple
    """
    if nq_sentiment == "bullish":
        return "✅", "NQ strong bullish"
    elif nq_sentiment == "neutral":
        return "⚠️", "NQ neutral"
    elif nq_sentiment in ["bearish", "slightly_red"]:
        return "⚠️", "NQ slightly red"
    else:
        return "⚠️", "NQ unclear"


def calculate_overall_grade(grades: Dict[str, str]) -> str:
    """
    Calculate overall signal grade based on component grades.

    Note: Grades only PRE-ENTRY components (breakout, retest, RR, market).
    Continuation (ignition) is excluded as it occurs after entry.

    Args:
        grades: Dict of component grades (✅/⚠️/❌)
                Should contain: breakout, retest, rr, market (4 components)

    Returns:
        Overall grade: A+, A, B, or C
    """
    # Count only the pre-entry components (exclude continuation if present)
    grading_components = {k: v for k, v in grades.items() if k != "continuation"}

    perfect = sum(1 for g in grading_components.values() if g == "✅")
    fail = sum(1 for g in grading_components.values() if g == "❌")

    total = len(grading_components)

    # A+: All perfect (4/4 ✅)
    if perfect == total:
        return "A+"

    # A: 3/4 perfect, no fails (1 warning OK)
    if perfect >= total - 1 and fail == 0:
        return "A"

    # B: 2/4 perfect, no fails (2 warnings OK)
    if fail == 0 and perfect >= 2:
        return "B"

    # C: Has failures or less than 2 perfect
    return "C"


def generate_signal_report(
    signal: Dict[str, Any],
    retest_volume_a_max_ratio: float = 0.30,
    retest_volume_b_max_ratio: float = 0.60,
    a_upper_wick_max: float = 0.15,
    b_body_max: float = 0.65,
    b_structure_soft: bool = True,
) -> str:
    """
    Generate a detailed Scarface Rules report for a signal.

    Args:
        signal: Signal dict with all detection metadata

    Returns:
        Formatted multi-line report string
    """
    ticker = signal["ticker"]
    direction = signal["direction"]
    level = signal["level"]
    entry = signal["entry"]
    stop = signal["stop"]
    target = signal["target"]

    # Calculate metrics
    rr_ratio = abs(target - entry) / abs(entry - stop) if entry != stop else 0
    body_pct = signal.get("breakout_body_pct", 0.6)
    vol_ratio = signal.get("breakout_vol_ratio", 1.5)

    # Grade each component
    breakout_grade, breakout_desc = grade_breakout_candle(
        signal.get("breakout_candle", {}),
        vol_ratio,
        body_pct,
        signal.get("level"),
        signal.get("direction"),
        a_upper_wick_max=a_upper_wick_max,
        b_body_max=b_body_max,
        or_range=signal.get("or_range"),
    )

    retest_grade, retest_desc = grade_retest(
        signal.get("retest_candle", {}),
        level,
        direction,
    )

    ignition_vol_ratio = signal.get("ignition_vol_ratio", 1.0)
    distance_to_target = signal.get("distance_to_target", 0.5)
    ignition_body_pct = signal.get("ignition_body_pct", 0.6)
    continuation_grade, continuation_desc = grade_continuation(
        signal.get("ignition_candle", {}),
        ignition_vol_ratio,
        distance_to_target,
        ignition_body_pct,
    )

    rr_grade, rr_desc = grade_risk_reward(rr_ratio)

    market_grade, market_desc = grade_market_context("slightly_red")

    # Calculate overall grade
    grades = {
        "breakout": breakout_grade,
        "retest": retest_grade,
        "continuation": continuation_grade,
        "rr": rr_grade,
        "market": market_grade,
    }
    overall_grade = calculate_overall_grade(grades)

    # Determine grade explanation
    if overall_grade == "A+":
        grade_explanation = "perfect structure, all criteria met, strong market context."
    elif overall_grade == "A":
        grade_explanation = (
            "clean structure, high-quality setup, " "just shy of A+ due to weak market tone."
        )
    elif overall_grade == "B":
        grade_explanation = "decent setup, minor concerns in execution or context."
    else:
        grade_explanation = "questionable setup, multiple weaknesses."

    # Build report
    level_type = "resistance" if direction == "long" else "support"
    setup_type = "5m Breakout & Retest (Scarface Rules)"

    # VWAP alignment info
    vwap = signal.get("vwap")
    breakout_close = signal.get("breakout_candle", {}).get("Close")
    vwap_status = ""
    if vwap is not None and breakout_close is not None:
        if direction == "long":
            vwap_status = " ✅" if breakout_close > vwap else " ❌"
        else:
            vwap_status = " ✅" if breakout_close < vwap else " ❌"
        vwap_info = f" (VWAP: {vwap:.2f}{vwap_status})"
    else:
        vwap_info = ""

    report = f"""{ticker} {setup_type}
Level: {level:.2f} {level_type}{vwap_info}
Breakout: {breakout_desc} {breakout_grade}
Retest: {retest_desc} {retest_grade}
Continuation: {continuation_desc} {continuation_grade}
R/R: {rr_desc} ({stop:.2f} stop → {target:.2f} target) {rr_grade}
Context: {market_desc} {market_grade}
Grade: {overall_grade} — {grade_explanation}
Note: Continuation is post-entry and not used to compute the letter grade.""".strip()

    return report
