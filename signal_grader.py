"""
Signal Grader for Break & Retest Strategy (Scarface Rules)

Grades signals A+ through C based on:
- Breakout candle quality (body %, volume surge)
- Retest quality (light volume, clear rejection)
- Continuation strength (fast move, volume confirmation)
- Risk/Reward ratio
- Market context (NQ sentiment, sector strength)
"""

from typing import Any, Dict, Tuple


def grade_breakout_candle(
    candle: Dict[str, float], vol_ratio: float, body_pct: float
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
    # Perfect: Strong body (>70%) + huge volume (>2x)
    if body_pct >= 0.70 and vol_ratio >= 2.0:
        return "✅", "Strong candle + high vol"

    # Good: Decent body (>50%) + good volume (>1.5x)
    if body_pct >= 0.50 and vol_ratio >= 1.5:
        return "✅", "Solid candle + good vol"

    # Acceptable: Moderate body or volume
    if body_pct >= 0.40 or vol_ratio >= 1.2:
        return "⚠️", "Adequate candle/vol"

    # Weak
    return "❌", "Weak candle or vol"


def grade_retest(
    retest_candle: Dict[str, float],
    retest_vol_ratio: float,
    level: float,
    direction: str,
) -> Tuple[str, str]:
    """
    Grade the retest quality.

    Args:
        retest_candle: OHLCV data for retest candle
        retest_vol_ratio: Volume ratio vs breakout volume
        level: Support/resistance level being retested
        direction: 'long' or 'short'

    Returns:
        (grade, description) tuple
    """
    close = retest_candle["Close"]
    low = retest_candle["Low"]
    high = retest_candle["High"]

    if direction == "long":
        # Check for clear rejection (wick below level, close above)
        wick_below = low < level < close
        close_above = close > level
        light_vol = retest_vol_ratio < 0.5

        if wick_below and close_above and light_vol:
            return "✅", "Light vol pullback, clear rejection"
        elif close_above and light_vol:
            return "✅", "Light vol pullback"
        elif close_above:
            return "⚠️", "Pullback but heavy vol"
        else:
            return "❌", "Weak retest"
    else:  # short
        # Check for clear rejection (wick above level, close below)
        wick_above = high > level > close
        close_below = close < level
        light_vol = retest_vol_ratio < 0.5

        if wick_above and close_below and light_vol:
            return "✅", "Light vol pullback, clear rejection"
        elif close_below and light_vol:
            return "✅", "Light vol pullback"
        elif close_below:
            return "⚠️", "Pullback but heavy vol"
        else:
            return "❌", "Weak retest"


def grade_continuation(
    ignition_candle: Dict[str, float],
    ignition_vol_ratio: float,
    distance_to_target: float,
    body_pct: float,
) -> Tuple[str, str]:
    """
    Grade the continuation/ignition candle.

    Args:
        ignition_candle: OHLCV data for ignition candle
        ignition_vol_ratio: Volume ratio vs breakout volume
        distance_to_target: % distance traveled toward target
        body_pct: Body percentage

    Returns:
        (grade, description) tuple
    """
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

    Args:
        grades: Dict of component grades (✅/⚠️/❌)

    Returns:
        Overall grade: A+, A, B, or C
    """
    perfect = sum(1 for g in grades.values() if g == "✅")
    warning = sum(1 for g in grades.values() if g == "⚠️")
    fail = sum(1 for g in grades.values() if g == "❌")

    total = len(grades)

    # A+: All perfect
    if perfect == total:
        return "A+"

    # A: Mostly perfect, max 1 warning
    if perfect >= total - 1 and fail == 0:
        return "A"

    # B: Some warnings, no fails
    if fail == 0 and warning <= 2:
        return "B"

    # C: Has failures or too many warnings
    return "C"


def generate_signal_report(signal: Dict[str, Any]) -> str:
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
        signal.get("breakout_candle", {}), vol_ratio, body_pct
    )

    retest_vol_ratio = signal.get("retest_vol_ratio", 0.3)
    retest_grade, retest_desc = grade_retest(
        signal.get("retest_candle", {}), retest_vol_ratio, level, direction
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

    report = f"""{ticker} {setup_type}
Level: {level:.2f} {level_type} / VWAP confluence {breakout_grade}
Breakout: {breakout_desc} {breakout_grade}
Retest: {retest_desc} {retest_grade}
Continuation: {continuation_desc} {continuation_grade}
R/R: {rr_desc} ({stop:.2f} stop → {target:.2f} target) {rr_grade}
Context: {market_desc} {market_grade}
Grade: {overall_grade} — {grade_explanation}""".strip()

    return report
