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


def grade_breakout_candle(
    candle: Dict[str, float],
    vol_ratio: float,
    body_pct: float,
    level: float | None = None,
    direction: str | None = None,
    a_upper_wick_max: float = 0.15,
    b_body_max: float = 0.65,
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
    level_ok_long = True
    level_ok_short = True
    if level is not None and direction is not None:
        if direction == "long":
            level_ok_long = c >= level  # A requires strictly >, B allows >=
        else:
            level_ok_short = c <= level  # A requires strictly <, B allows <=

    # Legacy compatibility: if no level/direction context, allow classic strong mapping
    if level is None and direction is None:
        if body_p >= 0.70 and vol_ratio >= 2.0:
            return "✅", "Strong candle + high vol"

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
        # C-Grade (Weak/Risky Breakout) LONG
        # Body 25–45%, Upper wick > 25% or long lower wick, Close ≤/at level, Volume < avg
        long_lower_wick = lw_p >= 0.30
        close_at_or_below = (c <= level) if level is not None else True
        return (
            (is_green or (not is_red and body_p >= 0.25))
            and (0.25 <= body_p <= 0.45)
            and (uw_p > 0.25 or long_lower_wick)
            and close_at_or_below
            and (vol_ratio < 1.0)
        )

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
        # C-Grade (Weak/Risky Breakdown) SHORT (mirror)
        long_upper_wick = uw_p >= 0.30
        close_at_or_above = (c >= level) if level is not None else True
        return (
            (is_red or (not is_green and body_p >= 0.25))
            and (0.25 <= body_p <= 0.45)
            and (long_upper_wick or lw_p > 0.25)
            and close_at_or_above
            and (vol_ratio < 1.0)
        )

    if direction == "short":
        if bear_A():
            return "✅", "Strong candle + high vol"
        if bear_B():
            return "⚠️", "Solid candle + good vol"
        if bear_C():
            return "❌", "Weak candle or vol"
    else:
        # default to long if direction None
        if bull_A():
            return "✅", "Strong candle + high vol"
        if bull_B():
            return "⚠️", "Solid candle + good vol"
        if bull_C():
            return "❌", "Weak candle or vol"

    # If nothing matched, fallback to a reasonable legacy mapping
    if (
        body_p >= 0.50
        and vol_ratio >= 1.5
        and (
            (direction == "long" and level_ok_long)
            or (direction == "short" and level_ok_short)
            or direction is None
        )
    ):
        return "✅", "Solid candle + good vol"
    if body_p >= 0.40 or vol_ratio >= 1.2:
        return "⚠️", "Adequate candle/vol"
    return "❌", "Weak candle or vol"


def grade_retest(
    retest_candle: Dict[str, float],
    retest_vol_ratio: float,
    level: float,
    direction: str,
    *,
    retest_volume_a_max_ratio: float = 0.30,
    retest_volume_b_max_ratio: float = 0.60,
    b_level_epsilon_pct: float = 0.10,
    b_structure_soft: bool = True,
) -> Tuple[str, str]:
    """
    Grade the retest candle quality based on Scarface Rules precision criteria.

    A-grade: "Tap and Go" - Wick touches/pierces level, closes just above (Long) or below (Short)
    B-grade: Pierces slightly but closes on correct side (shows some selling/buying pressure)
    C-grade: Comes close (within 1-2 candle widths) but doesn't touch - needs context confluence

    Args:
        retest_candle: OHLCV data for retest candle
        retest_vol_ratio: Volume ratio vs breakout volume
        level: The price level being tested
        direction: 'long' or 'short'
        retest_vol_threshold: Max acceptable retest vol ratio (default 0.15)
        b_level_epsilon_pct: For B-tier, allow close within this % of level (default 0.10%)
        b_structure_soft: If True, soften A/B boundaries to accept marginal structure as ⚠️

    Returns:
        (grade, description) tuple
    """
    high = float(retest_candle["High"])
    low = float(retest_candle["Low"])
    open_ = float(retest_candle.get("Open", (high + low) / 2))
    close = float(retest_candle["Close"])

    # Volume gates (vs breakout volume):
    # - A requires retest_vol_ratio ≤ retest_volume_a_max_ratio (default 30%)
    # - B requires retest_vol_ratio ≤ retest_volume_b_max_ratio (default 60%)
    # - > B gate: reject
    if retest_vol_ratio > retest_volume_b_max_ratio:
        pct = int(round(retest_volume_b_max_ratio * 100))
        return "❌", f"Retest volume too high (>{pct}% of breakout)"

    rng = max(high - low, 0.0)
    if rng <= 0:
        return "❌", "Invalid retest candle (no range)"

    body = abs(close - open_)
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low

    body_pct = body / rng if rng > 0 else 0.0
    upper_wick_pct = upper_wick / rng if rng > 0 else 0.0
    lower_wick_pct = lower_wick / rng if rng > 0 else 0.0

    is_green = close > open_
    is_red = close < open_

    # Helpers
    close_near_high = (high - close) <= 0.1 * rng
    close_near_low = (close - low) <= 0.1 * rng

    def within(x: float, a: float, b: float) -> bool:
        return (x >= a) and (x <= b)

    # Level epsilon for B-tier tolerance
    eps = level * (b_level_epsilon_pct / 100.0) if b_level_epsilon_pct > 0 else 0.0

    # ===== SCARFACE RULES: RETEST PRECISION CRITERIA =====
    # Measure distance from level to assess "tap quality"
    # - A-grade: Wick touches or slightly pierces level
    # - B-grade: Pierces more but closes on correct side (some pressure)
    # - C-grade: Comes within 1-2 candle widths but doesn't touch


    # ===== SCARFACE RULES: RETEST PRECISION CRITERIA =====
    # Measure distance from level to assess "tap quality"
    # - A-grade: Wick touches or slightly pierces level
    # - B-grade: Pierces more but closes on correct side (some pressure)
    # - C-grade: Comes within 1-2 candle widths but doesn't touch

    # Level rejection checks (must respect the reclaimed/broken level)
    if direction == "long":
        # Measure how close the wick came to the level
        wick_distance_to_level = low - level  # negative if wick went below level
        wick_touches_level = low <= level  # True if wick touched or pierced level

        # Close must hold above level (with epsilon tolerance for B-grade)
        close_above = close > level
        close_above_with_eps = close >= (level - eps)  # B-tier allows small miss

        if not close_above_with_eps:
            return "❌", "Retest failed: close did not hold above level"

        # Track if we used epsilon tolerance
        used_epsilon = (not close_above) and close_above_with_eps

        # Calculate distance as percentage of candle range for C-grade assessment
        # C-grade: Comes within 1-2 candle widths (100-200% of range) but doesn't touch
        distance_in_candle_widths = abs(wick_distance_to_level) / rng if rng > 0 else 999

        # ===== A-GRADE: "TAP AND GO" =====
        # Wick touches/pierces level, small wick (clean rejection), closes just above level
        # Requirements:
        # - Wick must touch or pierce the level
        # - If it pierces, should be minimal (< 10% of range below level)
        # - Close near the high (< 10% from high)
        # - Body strong (≥ 60%)
        # - Green candle showing buying strength
        pierce_depth_pct = abs(min(wick_distance_to_level, 0)) / rng if rng > 0 else 0
    # clean tap helper (no longer used directly; left for clarity)
    # clean_tap = wick_touches_level and pierce_depth_pct <= 0.10

        bull_A = (
            is_green
            and wick_touches_level
            and pierce_depth_pct <= 0.10  # Minimal pierce (< 10% of range)
            and close_near_high  # Close near high (within 10%)
            and body_pct >= 0.60  # Strong body
            and close_above  # Must close strictly above (A-grade = precision)
        )
        # Apply A-volume gate
        if bull_A and retest_vol_ratio > retest_volume_a_max_ratio:
            bull_A = False  # Downgrade: cannot be A if volume too high

        # ===== B-GRADE: PIERCES BUT CLOSES ABOVE =====
        # Wick pierces below level more significantly but close still holds above
        # Shows some selling pressure but buyers defended
        # Requirements:
        # - Wick must touch/pierce the level
        # - Pierce can be deeper (10-30% of range below level)
        # - Close above level (can use epsilon tolerance)
        # - Body moderate (40-70%)
        # - Green or balanced candle
        moderate_pierce = wick_touches_level and 0.10 < pierce_depth_pct <= 0.30

        bull_B = (
            (is_green or body_pct <= 0.20)  # Green or doji-ish
            and wick_touches_level
            and moderate_pierce  # Moderate pierce (10-30% of range)
            and close_above_with_eps  # B-tier can use epsilon
            and body_pct >= 0.40  # Moderate body
        )

        # Optional: Classic hammer-style (legacy support)
        hammer_alt = (
            is_green
            and wick_touches_level
            and lower_wick_pct >= 0.45  # Long lower wick
            and body_pct >= 0.15
            and upper_wick_pct <= 0.30
            and close >= (low + 0.45 * rng)
            and close_above
        )

        # Return grade based on criteria
        if bull_A:
            return "✅", f"A-grade: clean rejection (pierce {pierce_depth_pct*100:.1f}%)"

        if hammer_alt:
            return "✅", "A-grade hammer: long lower-wick rejection, strong buying"

        if bull_B:
            suffix = " (eps)" if used_epsilon else ""
            return "⚠️", f"B-grade: deeper pierce ({pierce_depth_pct*100:.1f}%), close held{suffix}"

        # REJECT: Wick didn't touch the level - not a valid retest
        # Even if it comes "close", it's not actually testing the breakout level
        if not wick_touches_level:
            if distance_in_candle_widths <= 2.0:
                return "❌", f"No touch (within {distance_in_candle_widths:.1f}x widths)"
            else:
                return "❌", f"Too far ({distance_in_candle_widths:.1f}x widths)"

        # Fallback: Touched level but didn't match A/B criteria (treat as weak)
        if wick_touches_level and close_above:
            return "❌", "Weak bullish retest: touched level but poor structure"

        if close_above_with_eps:
            return "⚠️", "Weak bullish retest: marginal structure"

        return "❌", "Retest failed: close did not hold above level"

    else:  # short
        # Measure how close the wick came to the level (SHORT: upper wick tests resistance)
        wick_distance_to_level = high - level  # positive if wick went above level
        wick_touches_level = high >= level  # True if wick touched or pierced level

        # Close must hold below level (with epsilon tolerance for B-grade)
        close_below = close < level
        close_below_with_eps = close <= (level + eps)  # B-tier allows small miss

        if not close_below_with_eps:
            return "❌", "Retest failed: close did not hold below level"

        # Track if we used epsilon tolerance
        used_epsilon = (not close_below) and close_below_with_eps

        # Calculate distance as percentage of candle range for C-grade assessment
        distance_in_candle_widths = abs(wick_distance_to_level) / rng if rng > 0 else 999

        # ===== A-GRADE: "TAP AND GO" (SHORT) =====
        # Wick touches/pierces resistance level, clean rejection, closes just below level
        pierce_depth_pct = max(wick_distance_to_level, 0) / rng if rng > 0 else 0
    # clean tap helper (no longer used directly)
    # clean_tap = wick_touches_level and pierce_depth_pct <= 0.10

        bear_A = (
            is_red
            and wick_touches_level
            and pierce_depth_pct <= 0.10  # Minimal pierce (< 10% of range)
            and close_near_low  # Close near low (within 10%)
            and body_pct >= 0.60  # Strong body
            and close_below  # Must close strictly below (A-grade = precision)
        )
        # Apply A-volume gate (short)
        if bear_A and retest_vol_ratio > retest_volume_a_max_ratio:
            bear_A = False

        # ===== B-GRADE: PIERCES BUT CLOSES BELOW (SHORT) =====
        # Wick pierces above resistance more significantly but close still holds below
        moderate_pierce = wick_touches_level and 0.10 < pierce_depth_pct <= 0.30

        bear_B = (
            (is_red or body_pct <= 0.20)  # Red or doji-ish
            and wick_touches_level
            and moderate_pierce  # Moderate pierce (10-30% of range)
            and close_below_with_eps  # B-tier can use epsilon
            and body_pct >= 0.40  # Moderate body
        )

        # Optional: Inverted hammer-style (legacy support)
        inverted_hammer_alt = (
            is_red
            and wick_touches_level
            and upper_wick_pct >= 0.45  # Long upper wick
            and body_pct >= 0.15
            and lower_wick_pct <= 0.30
            and close <= (high - 0.45 * rng)
            and close_below
        )

        # Return grade based on criteria
        if bear_A:
            return "✅", f"A-grade: clean rejection (pierce {pierce_depth_pct*100:.1f}%)"

        if inverted_hammer_alt:
            return "✅", "A-grade inverted-hammer: long upper-wick rejection, strong selling"

        if bear_B:
            suffix = " (eps)" if used_epsilon else ""
            return "⚠️", f"B-grade: deeper pierce ({pierce_depth_pct*100:.1f}%), close held{suffix}"

        # REJECT: Wick didn't touch the level - not a valid retest
        # Even if it comes "close", it's not actually testing the breakout level
        if not wick_touches_level:
            if distance_in_candle_widths <= 2.0:
                return "❌", f"No touch (within {distance_in_candle_widths:.1f}x widths)"
            else:
                return "❌", f"Too far ({distance_in_candle_widths:.1f}x widths)"

        # Fallback: Touched level but didn't match A/B criteria (treat as weak)
        if wick_touches_level and close_below:
            return "❌", "Weak bearish retest: touched resistance but poor structure"

        if close_below_with_eps:
            return "⚠️", "Weak bearish retest: marginal structure"

        return "❌", "Retest failed: close did not hold below level"


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
    b_level_epsilon_pct: float = 0.10,
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
    )

    retest_vol_ratio = signal.get("retest_vol_ratio", 0.3)
    retest_grade, retest_desc = grade_retest(
        signal.get("retest_candle", {}),
        retest_vol_ratio,
        level,
        direction,
        retest_volume_a_max_ratio=retest_volume_a_max_ratio,
        retest_volume_b_max_ratio=retest_volume_b_max_ratio,
        b_level_epsilon_pct=b_level_epsilon_pct,
        b_structure_soft=b_structure_soft,
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
