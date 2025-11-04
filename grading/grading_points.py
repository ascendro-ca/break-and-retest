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
      scaled to A+/A/B/C thresholds at 90%/80%/70% of 60, respectively.
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
    ) -> Tuple[str, str]:
        # New signal: reset state for a fresh scoring round
        self._reset_state()

        s = pd.Series(candle)
        cls = classify_candle_strength(s)
        base = 0

        # Pattern-based base points (approximate mapping)
        c_body = float(cls.get("body_pct", 0.0))
        uw = float(cls.get("upper_wick_pct", 0.0))
        lw = float(cls.get("lower_wick_pct", 0.0))
        ctype = str(cls.get("type", "unknown"))
        # cdir = str(cls.get("direction", "neutral"))  # Reserved for directional validation

        # expected_dir = (  # Reserved for future directional matching
        #     "bullish" if direction == "long" else ("bearish" if direction == "short" else None)
        # )
        # dir_match = (expected_dir is None) or (cdir == expected_dir)  # Reserved for future use

        if ctype in ("bullish_marubozu", "bearish_marubozu"):
            base = 20
        else:
            # WRB approximation: big body, not full marubozu
            if c_body >= 0.70:
                base = 17
            # Belt hold approximation: strong open-close directionality, one small opposite wick
            elif c_body >= 0.65 and (
                (direction == "long" and lw <= 0.10) or (direction == "short" and uw <= 0.10)
            ):
                base = 15
            elif c_body >= 0.60:
                base = 13
            else:
                # Messy/overlapping
                base = 10 if c_body >= 0.40 else 8

        # Volume bonus (vol_ratio is vs 20-SMA proxy)
        bonus = 0
        if vol_ratio > 1.5:
            bonus = 5
        elif vol_ratio >= 1.2:
            bonus = 3
        elif vol_ratio >= 1.0:
            bonus = 2

        pts = min(base + bonus, 30)
        self._state["breakout_pts"] = pts

        # Map to symbol for component visualization
        # Scaled thresholds (out of 30): A+ ≥28.5, A ≥25.8, B ≥21, C ≥16.8, D <16.8
        symbol = "❌"  # D grade
        if pts >= 28.5:
            symbol = "A+"
        elif pts >= 25.8:
            symbol = "A"
        elif pts >= 21:
            symbol = "B"
        elif pts >= 16.8:
            symbol = "C"

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

        # Pattern-based base points (1m retest)
        base = 0
        if direction == "long":
            if lw >= 0.45 and c_body <= 0.35:  # hammer-like
                base = 18
            elif ctype in ("doji", "dragonfly_doji") and lw >= 0.35:
                base = 15
            elif c_body <= 0.30:  # tight hold / inside-like
                base = 12
            else:
                base = 9 if lw >= 0.15 else 7
        else:  # short
            if uw >= 0.45 and c_body <= 0.35:  # inverted hammer / shooting-star-like
                base = 18
            elif ctype in ("doji", "gravestone_doji") and uw >= 0.35:
                base = 15
            elif c_body <= 0.30:
                base = 12
            else:
                base = 9 if uw >= 0.15 else 7

        # Volume bonus vs breakout
        bonus = 0
        if retest_vol_ratio < 0.15:
            bonus = 5
        elif retest_vol_ratio < 0.30:
            bonus = 3

        pts = min(base + bonus, 30)
        self._state["retest_pts"] = pts

        # Scaled thresholds (out of 30): A+ ≥28.5, A ≥25.8, B ≥21, C ≥16.8, D <16.8
        symbol = "❌"  # D grade
        if pts >= 28.5:
            symbol = "A+"
        elif pts >= 25.8:
            symbol = "A"
        elif pts >= 21:
            symbol = "B"
        elif pts >= 16.8:
            symbol = "C"

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

        base = 0
        if c_body >= 0.90:
            base = 20  # marubozu-like
        elif c_body >= 0.70:
            base = 18  # WRB-like
        elif c_body >= 0.60:
            base = 15  # belt-hold-like
        elif c_body >= 0.45:
            base = 13  # other momentum
        else:
            base = 9

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

        # Scaled thresholds (out of 30): A+ ≥28.5, A ≥25.8, B ≥21, C ≥16.8, D <16.8
        symbol = "❌"  # D grade
        if pts >= 28.5:
            symbol = "A+"
        elif pts >= 25.8:
            symbol = "A"
        elif pts >= 21:
            symbol = "B"
        elif pts >= 16.8:
            symbol = "C"

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

        # VWAP alignment is guaranteed by base breakout filter at Level 0
        # Award 5 points automatically since all signals have VWAP aligned
        context_pts = 5

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
