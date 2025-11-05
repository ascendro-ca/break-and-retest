from __future__ import annotations

from typing import Any, Dict, Tuple

import pandas as pd

from candle_patterns import classify_candle_strength

from .base import Grader


class PointsGrader(Grader):
    """
    100-point grading system adapter.

    Notes:
        - Pre-entry overall grade is computed from Breakout (30) + Retest (30) only (max 60),
            thresholds per GRADING_SYSTEMS.md: A+ ≥95%, A ≥86%, B ≥70%, C ≥56% of 60.
    - VWAP/Trend context (+10) and Ignition (+30) are computed for reporting if data is present.
    - Volume proxies:
        * Breakout volume ratio: provided vol_ratio vs 20-SMA (used as 5m avg proxy)
        * Retest volume ratio: retest_vol_ratio vs breakout volume
        * Ignition volume ratio: ignition_vol_ratio (proxy), thresholds adapted accordingly
    """

    def __init__(self) -> None:
        self._state: Dict[str, Any] = {}

    def _reset_state(self) -> None:
        self._state = {
            "breakout_pts": 0.0,
            "retest_pts": 0.0,
            "ignition_pts": 0.0,
            "context_pts": 0.0,
        }

    # ---------- Helpers ----------
    @staticmethod
    def _component_symbol(pts: float, max_pts: float = 30.0) -> str:
        """
        Map a component score (out of max_pts) to a letter grade symbol using
        GRADING_SYSTEMS.md thresholds scaled by max.

        Thresholds (percent of max):
        - A+ ≥ 95%
        - A  ≥ 86%
        - B  ≥ 70%
        - C  ≥ 56%
        - else D (❌)
        """
        a_plus = 0.95 * max_pts
        a = 0.86 * max_pts
        b = 0.70 * max_pts
        c = 0.56 * max_pts

        if pts >= a_plus:
            return "A+"
        if pts >= a:
            return "A"
        if pts >= b:
            return "B"
        if pts >= c:
            return "C"
        return "❌"

    # ---------- Breakout ----------
    def grade_breakout_candle(
        self,
        candle: Dict[str, float],
        vol_ratio: float,
        body_pct: float,
        level: float | None = None,
        direction: str | None = None,
        *,
        a_upper_wick_max: float = 0.15,
        b_body_max: float = 0.65,
        or_range: float | None = None,
        prev_candle: Dict[str, float] | None = None,
    ) -> Tuple[str, str]:
        # New signal: reset state for a fresh scoring round
        self._reset_state()

        s = pd.Series(candle)
        cls = classify_candle_strength(s)
        base = 0

        # Pattern-based base points using detected pattern types per GRADING_SYSTEMS.md
        c_body = float(cls.get("body_pct", 0.0))
        uw = float(cls.get("upper_wick_pct", 0.0))
        lw = float(cls.get("lower_wick_pct", 0.0))
        ctype = str(cls.get("type", "unknown"))
        cdir = str(cls.get("direction", "neutral"))

        # Verify directional alignment
        expected_dir = "bullish" if direction == "long" else "bearish"
        dir_match = (cdir == expected_dir) or (cdir == "neutral")

        # Map to GRADING_SYSTEMS.md breakout patterns:
        # 1. Marubozu / Shaved Candle (20 pts)
        if ctype in ("bullish_marubozu", "bearish_marubozu"):
            base = 20 if dir_match else 13  # Penalize wrong-direction marubozu

        # 2. Engulfing Candle (18 pts) - true detection using prior 5m candle when provided
        if prev_candle is not None:
            try:
                from candle_patterns import detect_engulfing

                prev_s = pd.Series(prev_candle)
                engulf = detect_engulfing(prev_s, s)
                if engulf.get("detected"):
                    if (direction == "long" and engulf.get("direction") == "bullish") or (
                        direction == "short" and engulf.get("direction") == "bearish"
                    ):
                        base = 18
            except Exception:
                pass  # Engulfing detection failed, continue with other patterns
        if base == 0:  # not engulfing
            # 3. Wide-Range Breakout Candle (17 pts) - body ≥70%
            if c_body >= 0.70 and dir_match:
                base = 17
            # 4. Belt Hold (15 pts)
            elif (
                c_body >= 0.65
                and dir_match
                and ((direction == "long" and lw <= 0.10) or (direction == "short" and uw <= 0.10))
            ):
                base = 15
            # 5. Other Clean Candle (13 pts)
            elif c_body >= 0.60 and dir_match:
                base = 13
            # 6. Messy/overlapping candle (7-10 pts)
            else:
                if c_body >= 0.40:
                    base = 10
                elif c_body >= 0.30:
                    base = 9
                elif c_body >= 0.20:
                    base = 8
                else:
                    base = 7

        # Volume bonus (vol_ratio is vs 20-SMA proxy)
        # Updated per GRADING_SYSTEMS.md: max 10 points instead of 5
        bonus = 0
        if vol_ratio > 1.5:
            bonus = 10
        elif vol_ratio >= 1.2:
            bonus = 5
        elif vol_ratio >= 1.0:
            bonus = 2

        pts = min(base + bonus, 30)
        self._state["breakout_pts"] = pts

        # Map to symbol for component visualization per GRADING_SYSTEMS.md (scaled)
        symbol = self._component_symbol(pts, max_pts=30.0)

        desc = (
            f"Breakout score: base {base} + vol {bonus} = {pts}/30 "
            f"(type={ctype}, body={c_body:.2f})"
        )
        return symbol, desc

    # ---------- Retest ----------
    def grade_retest(
        self,
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
        s = pd.Series(retest_candle)
        cls = classify_candle_strength(s)
        c_body = float(cls.get("body_pct", 0.0))
        uw = float(cls.get("upper_wick_pct", 0.0))
        lw = float(cls.get("lower_wick_pct", 0.0))
        ctype = str(cls.get("type", "unknown"))

        # Pattern-based base points per GRADING_SYSTEMS.md
        base = 0

        if direction == "long":
            # 1. Hammer / Inverted Hammer (20 pts)
            if ctype in ("hammer", "dragonfly_doji", "inverted_hammer_bullish"):
                base = 20
            # 2. Pin Bar (18 pts) - sharp rejection wick + tight body
            elif lw >= 0.50 and c_body <= 0.25:
                base = 18
            # 3. Doji w/ long rejection wick (17 pts)
            elif ctype == "doji" and lw >= 0.35:
                base = 17
            # 4. Inside Bar (13 pts) - tight base + support hold
            elif c_body <= 0.30:
                base = 13
            # 5. Other small-wick hold (10-12 pts)
            elif lw >= 0.15 and c_body <= 0.50:
                base = 12 if lw >= 0.25 else 10
            # 6. Wick fails to touch level (5-9 pts)
            else:
                base = 9 if lw >= 0.12 else 7 if lw >= 0.08 else 5

        else:  # short
            # 1. Shooting Star / Gravestone Doji (20 pts) - bearish equivalents
            if ctype in ("shooting_star", "gravestone_doji", "inverted_hammer_bearish"):
                base = 20
            # 2. Pin Bar (18 pts) - sharp rejection wick + tight body
            elif uw >= 0.50 and c_body <= 0.25:
                base = 18
            # 3. Doji w/ long rejection wick (17 pts)
            elif ctype == "doji" and uw >= 0.35:
                base = 17
            # 4. Inside Bar (13 pts) - tight base + resistance hold
            elif c_body <= 0.30:
                base = 13
            # 5. Other small-wick hold (10-12 pts)
            elif uw >= 0.15 and c_body <= 0.50:
                base = 12 if uw >= 0.25 else 10
            # 6. Wick fails to touch level (5-9 pts)
            else:
                base = 9 if uw >= 0.12 else 7 if uw >= 0.08 else 5

        # Volume bonus vs breakout (per GRADING_SYSTEMS.md)
        bonus = 0
        if retest_vol_ratio < 0.15:
            bonus = 10
        elif retest_vol_ratio < 0.30:
            bonus = 5

        pts = min(base + bonus, 30)
        self._state["retest_pts"] = pts

        # Map to symbol for component visualization per GRADING_SYSTEMS.md (scaled)
        symbol = self._component_symbol(pts, max_pts=30.0)

        desc = f"Retest score: base {base} + vol {bonus} = {pts}/30 (type={ctype})"
        return symbol, desc

    # ---------- Continuation / Ignition ----------
    def grade_continuation(
        self,
        ignition_candle: Dict[str, float],
        ignition_vol_ratio: float,
        distance_to_target: float,
        body_pct: float,
    ) -> Tuple[str, str]:
        # Build a Series safely and guard against missing OHLC
        try:
            s = pd.Series(ignition_candle)
        except Exception:
            self._state["ignition_pts"] = 0.0
            return "❌", "Ignition N/A"

        required = ("Open", "High", "Low", "Close")
        try:
            if any((k not in s.index) or pd.isna(s.get(k)) for k in required):
                self._state["ignition_pts"] = 0.0
                return "❌", "Ignition N/A"
        except Exception:
            self._state["ignition_pts"] = 0.0
            return "❌", "Ignition N/A"

        try:
            cls = classify_candle_strength(s)
            c_body = float(cls.get("body_pct", 0.0))
            ctype = str(cls.get("type", "unknown"))
            cdir = str(cls.get("direction", "neutral"))
        except Exception:
            # Fallback to direct computation if classification fails
            try:
                o = float(s.get("Open", 0.0))
                h = float(s.get("High", 0.0))
                low = float(s.get("Low", 0.0))
                c = float(s.get("Close", 0.0))
                rng = max(h - low, 0.0)
                c_body = abs(c - o) / rng if rng > 0 else 0.0
            except Exception:
                c_body = 0.0
            ctype = "unknown"
            cdir = "neutral"

        # Map detected patterns to points per GRADING_SYSTEMS.md
        base = 0

        # 1. Bullish/Bearish Marubozu (20 pts) - strongest ignition
        if ctype in ("bullish_marubozu", "bearish_marubozu"):
            base = 20

        # 2. Wide-Range Candle / WRB (18 pts) - body ≥70%
        elif c_body >= 0.70:
            base = 18

        # 3. Engulfing Candle (17 pts) - proxy: body ≥75% with direction
        elif c_body >= 0.75 and cdir != "neutral":
            base = 17

        # 4. Belt Hold (15 pts) - body ≥60%
        elif c_body >= 0.60:
            base = 15

        # 5. Other momentum candle (12-14 pts) - body ≥45%
        elif c_body >= 0.45:
            base = 14 if c_body >= 0.55 else 13 if c_body >= 0.50 else 12

        # 6. Wick or indecisive body (7-10 pts)
        else:
            if c_body >= 0.30:
                base = 10
            elif c_body >= 0.20:
                base = 8
            else:
                base = 7

        bonus = 0
        # ignition_vol_ratio: ignition volume / retest volume (per GRADING_SYSTEMS.md spec)
        # Spec requires comparison to retest volume AND session percentile
        # Current implementation uses ratio thresholds as proxy
        if ignition_vol_ratio >= 1.5:
            bonus = 5
        elif ignition_vol_ratio >= 1.3:
            bonus = 3
        elif ignition_vol_ratio > 1.0:
            bonus = 1

        pts = min(base + bonus, 30)
        self._state["ignition_pts"] = pts

        # Map to symbol for component visualization per GRADING_SYSTEMS.md (scaled)
        symbol = self._component_symbol(pts, max_pts=30.0)

        desc = f"Ignition score: base {base} + vol {bonus} = {pts}/30 (type={ctype})"
        return symbol, desc

    # ---------- Risk/Reward (not part of 100-pt table) ----------
    def grade_risk_reward(self, rr_ratio: float) -> Tuple[str, str]:
        # Keep existing symbol mapping for compatibility
        if rr_ratio >= 3.0:
            return "✅", f"{rr_ratio:.1f}:1"
        elif rr_ratio >= 2.0:
            return "✅", f"{rr_ratio:.1f}:1"
        elif rr_ratio >= 1.5:
            return "⚠️", f"{rr_ratio:.1f}:1"
        else:
            return "❌", f"{rr_ratio:.1f}:1"

    # ---------- Market/Context ----------
    def grade_market_context(self, nq_sentiment: str = "neutral") -> Tuple[str, str]:
        # Symbol for display only; context points computed in report if signal has VWAP/trend
        if nq_sentiment == "bullish":
            return "✅", "NQ strong bullish"
        elif nq_sentiment == "neutral":
            return "⚠️", "NQ neutral"
        elif nq_sentiment in ["bearish", "slightly_red"]:
            return "⚠️", "NQ slightly red"
        else:
            return "⚠️", "NQ unclear"

    # ---------- Overall ----------
    def calculate_overall_grade(self, grades: Dict[str, str]) -> str:
        # Use pre-entry points only (breakout + retest), each out of 30
        total_pre = float(self._state.get("breakout_pts", 0.0)) + float(
            self._state.get("retest_pts", 0.0)
        )
        # max_pre = 60.0  # Reserved for potential future use
        # Thresholds scaled from 100-pt system per GRADING_SYSTEMS.md:
        # A+: 95% of 60 = 57, A: 86% of 60 = 51.6, B: 70% of 60 = 42, C: 56% of 60 = 33.6, D: <33.6
        if total_pre >= 57.0:  # 95%
            return "A+"
        if total_pre >= 51.6:  # 86%
            return "A"
        if total_pre >= 42.0:  # 70%
            return "B"
        if total_pre >= 33.6:  # 56%
            return "C"
        return "D"

    def generate_signal_report(self, signal: Dict[str, Any], **kwargs: Any) -> str:
        # Compute context points (if signal has vwap and trend info)
        context_pts = 0
        # Only award VWAP points if explicitly indicated by the signal
        vwap_aligned = signal.get("vwap_aligned")  # optional bool
        if isinstance(vwap_aligned, bool) and vwap_aligned:
            context_pts += 5

        # HTF trend and confluence are not available – leave at 0 unless provided
        trend_align = signal.get("trend_align")  # optional bool
        if isinstance(trend_align, bool) and trend_align:
            context_pts += 3
        htf_confluence = signal.get("htf_confluence")  # optional bool
        if isinstance(htf_confluence, bool) and htf_confluence:
            context_pts += 2
        context_pts = min(context_pts, 10)
        self._state["context_pts"] = context_pts

        breakout_pts = float(self._state.get("breakout_pts", 0.0))
        retest_pts = float(self._state.get("retest_pts", 0.0))
        ignition_pts = float(self._state.get("ignition_pts", 0.0))

        total = breakout_pts + retest_pts + context_pts + ignition_pts
        # Determine final grade vs 100-pt scale for reporting (per GRADING_SYSTEMS.md)
        # A+: 95-100, A: 86-94, B: 70-85, C: 56-69, D: <56
        if total >= 95:
            report_grade = "A+"
        elif total >= 86:
            report_grade = "A"
        elif total >= 70:
            report_grade = "B"
        elif total >= 56:
            report_grade = "C"
        else:
            report_grade = "D"

        # Build report string
        ticker = signal.get("ticker", "")
        direction = signal.get("direction", "long")
        level = float(signal.get("level", 0.0))
        level_type = "resistance" if direction == "long" else "support"
        rr_ratio = float(signal.get("rr_ratio", 0.0))

        lines = []
        lines.append(f"{ticker} 5m Breakout & Retest — 100-Point Scoring")
        lines.append(f"Level: {level:.2f} {level_type}")
        lines.append(
            f"Breakout: {breakout_pts:.0f}/30 | Retest: {retest_pts:.0f}/30 | "
            f"Ignition: {ignition_pts:.0f}/30 | Context: {context_pts:.0f}/10"
        )
        lines.append(f"Total: {total:.0f}/100 → Grade {report_grade}")
        lines.append(f"R/R: {rr_ratio:.1f}:1 (informational)")
        return "\n".join(lines)
