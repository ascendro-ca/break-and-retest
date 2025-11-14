"""
Trade Setup Pipeline
====================

Top-level orchestrator for the Break & Retest detection pipeline.
Similar to a Jenkins CI/CD pipeline, each stage is sequential and must pass
before the next stage runs.

Pipeline Levels:
- Level 0 (Base): Stages 1-3 only (OR → Breakout → Retest)
    - Uses the strict Level 0 retest filter (body at/beyond OR in trade direction)
    - No trades executed (candidates only)

- Level 1: Stages 1-3 with base criteria for trade execution
    - Uses the SAME retest filter as Level 0 (no additional retest filtering)
    - Trades entered on open of 1m candle after retest
    - Stage 4 (Ignition) NOT used at Level 1

- Level 2+: Enhanced filtering/grading
    - May include Stage 4 (Ignition) and additional quality criteria

Pipeline Stages:
1. Opening Range (OR) - Establishes the reference level
2. Breakout - Detects 5m candles that break beyond OR
3. Retest - Detects 1m candles that retest the breakout level
4. Ignition (Level 2+) - Detects ignition candle confirming continuation after entry

Usage:
    # Level 0: Base 3-stage pipeline (candidates only, no trades)
    pipeline = TradeSetupPipeline(pipeline_level=0)
    candidates = pipeline.run(session_df_5m, session_df_1m)

    # Level 1: Trade execution with base criteria (no ignition)
    pipeline = TradeSetupPipeline(pipeline_level=1)
    candidates = pipeline.run(session_df_5m, session_df_1m)

Architecture:
- Designed for both backtesting and live scanning
- Data-source agnostic (just feed it 5m and 1m OHLCV slices)
- Extensible via custom filter functions per stage
"""

from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

from stage_breakout import detect_breakouts
from stage_ignition import detect_ignition, retest_qualifies_as_ignition
from stage_opening_range import detect_opening_range
from stage_retest import detect_retest, level0_retest_filter


class TradeSetupPipeline:
    """
    Sequential pipeline for Break & Retest trade setup detection.

    Pipeline Levels:
    - Level 0: Candidates only (Stages 1-3: OR, Breakout, Retest)
        - Level 1: Trade execution with base criteria (Stages 1-3, no ignition);
            Level 1 uses the same retest filter as Level 0
    - Level 2+: Enhanced filtering, may include Stage 4 (Ignition)
    """

    def __init__(
        self,
        breakout_window_minutes: int = 90,
        retest_lookahead_minutes: int = 30,
        ignition_lookahead_minutes: int = 30,
        pipeline_level: int = 0,
        breakout_filter: Optional[
            Callable[[pd.Series, pd.Series, float, float], Optional[Tuple[str, float]]]
        ] = None,
        retest_filter: Optional[Callable[[pd.Series, str, float], bool]] = None,
        ignition_filter: Optional[Callable[[pd.Series, str, float, float], bool]] = None,
        enable_vwap_check: bool = True,
        # New: separate VWAP flags per stage (default False via run_pipeline wrapper)
        enable_vwap_breakout_check: bool = False,
        enable_vwap_retest_check: bool = False,
        retest_require_wick_contact: bool = True,
        wick_tolerance_bps: float = 0.0,
        wick_contact_mode: str = "either",
        wick_pierce_max_bps: Optional[float] = None,
    ) -> None:
        """
        Initialize the pipeline.

        Args:
            breakout_window_minutes: Minutes from session open to scan for breakouts
            retest_lookahead_minutes: Minutes after breakout close to search for retest
            ignition_lookahead_minutes: Minutes after retest to search for ignition
            pipeline_level: Pipeline strictness level (0=candidates only, 1=trades, 2+=enhanced)
            breakout_filter: Optional custom Stage 2 filter
            retest_filter: Optional custom Stage 3 filter
            ignition_filter: Optional custom Stage 4 filter
            enable_vwap_check: Deprecated. Ignition no longer enforces VWAP; kept for
                internal API compatibility. Use per-stage flags
                `enable_vwap_breakout_check` and `enable_vwap_retest_check` instead.
        """
        self.breakout_window_minutes = int(breakout_window_minutes)
        self.retest_lookahead_minutes = int(retest_lookahead_minutes)
        self.ignition_lookahead_minutes = int(ignition_lookahead_minutes)
        self.pipeline_level = int(pipeline_level)
        self.breakout_filter = breakout_filter
        self.retest_filter = retest_filter
        self.ignition_filter = ignition_filter
        self.enable_vwap_check = enable_vwap_check
        self.enable_vwap_breakout_check = bool(enable_vwap_breakout_check)
        self.enable_vwap_retest_check = bool(enable_vwap_retest_check)

        # Stage 3 additional requirement: wick must touch or pierce OR
        self.retest_require_wick_contact = bool(retest_require_wick_contact)
        self.wick_tolerance_bps = float(wick_tolerance_bps)
        self.wick_contact_mode = str(wick_contact_mode or "either").lower()
        self.wick_pierce_max_bps = wick_pierce_max_bps

    def run(self, session_df_5m: pd.DataFrame, session_df_1m: pd.DataFrame) -> List[Dict]:
        """
        Run the full 4-stage pipeline on a trading session.

        Args:
            session_df_5m: 5-minute OHLCV data for the session, sorted ascending
            session_df_1m: 1-minute OHLCV data for the session, sorted ascending

        Returns:
            List of candidate setups that passed all 4 stages.
            Each dict contains: direction, level, breakout_time, retest_time,
            ignition_time, breakout_candle, retest_candle, ignition_candle
        """
        if session_df_5m is None or session_df_1m is None:
            return []
        if session_df_5m.empty or session_df_1m.empty:
            return []

        # Ensure sorted
        session_df_5m = session_df_5m.sort_values("Datetime").copy()
        session_df_1m = session_df_1m.sort_values("Datetime").copy()

        # =====================================
        # STAGE 1: Opening Range
        # =====================================
        or_result = detect_opening_range(session_df_5m)
        or_high = or_result["high"]
        or_low = or_result["low"]

        if or_high == 0.0 or or_low == 0.0:
            return []

        # =====================================
        # STAGE 2: Breakout Detection
        # =====================================
        breakouts = detect_breakouts(
            session_df_5m=session_df_5m,
            or_high=or_high,
            or_low=or_low,
            breakout_window_minutes=self.breakout_window_minutes,
            breakout_filter=self.breakout_filter,
            enable_vwap_check=self.enable_vwap_breakout_check,
        )

        if not breakouts:
            return []

        # =====================================
        # STAGE 3: Retest Detection
        # =====================================
        candidates = []
        for brk in breakouts:
            retest_result = detect_retest(
                session_df_1m=session_df_1m,
                breakout_time=brk["time"],
                direction=brk["direction"],
                level=brk["level"],
                retest_lookahead_minutes=self.retest_lookahead_minutes,
                retest_filter=self.retest_filter,
                enable_vwap_check=self.enable_vwap_check,
                retest_require_wick_contact=self.retest_require_wick_contact,
                wick_tolerance_bps=self.wick_tolerance_bps,
                wick_contact_mode=self.wick_contact_mode,
                wick_pierce_max_bps=self.wick_pierce_max_bps,
            )

            if retest_result is None:
                continue

            # Base candidate dict (Stage 1-3 complete)
            candidate = {
                "direction": brk["direction"],
                "level": brk["level"],
                "breakout_time": brk["time"],
                "retest_time": retest_result["time"],
                "breakout_candle": brk["candle"],
                "prev_breakout_candle": brk.get("prev_candle"),
                "retest_candle": retest_result["candle"],
            }

            # =====================================
            # STAGE 4: Ignition (Level 2+)
            # =====================================
            if self.pipeline_level >= 2:
                # Case 2: Check if retest candle qualifies as ignition
                retest_is_ignition = retest_qualifies_as_ignition(
                    retest_candle=retest_result["candle"],
                    direction=brk["direction"],
                    breakout_candle=brk["candle"],
                    session_df_1m=session_df_1m,
                )

                if retest_is_ignition:
                    # Case 2: Retest qualifies as ignition - enter at next 1m candle open
                    # Find the next 1m candle after retest
                    next_candles = session_df_1m[session_df_1m["Datetime"] > retest_result["time"]]
                    if not next_candles.empty:
                        next_candle = next_candles.iloc[0]
                        # Use next candle as "ignition" for entry timing
                        candidate["ignition_time"] = next_candle["Datetime"]
                        candidate["ignition_candle"] = next_candle
                        candidate["retest_is_ignition"] = True
                else:
                    # Case 1: Retest doesn't qualify - search for Stage 4 ignition
                    ignition_result = detect_ignition(
                        session_df_1m=session_df_1m,
                        retest_time=retest_result["time"],
                        retest_candle=retest_result["candle"],
                        direction=brk["direction"],
                        ignition_lookahead_minutes=self.ignition_lookahead_minutes,
                        ignition_filter=self.ignition_filter,
                        enable_vwap_check=self.enable_vwap_check,
                    )

                    if ignition_result is not None:
                        candidate["ignition_time"] = ignition_result["time"]
                        candidate["ignition_candle"] = ignition_result["candle"]
                        candidate["retest_is_ignition"] = False

            candidates.append(candidate)

        return candidates


def run_pipeline(
    session_df_5m: pd.DataFrame,
    session_df_1m: pd.DataFrame,
    breakout_window_minutes: int = 90,
    retest_lookahead_minutes: int = 30,
    ignition_lookahead_minutes: int = 30,
    pipeline_level: int = 0,
    enable_vwap_check: bool = True,
    enable_vwap_breakout_check: bool = False,
    enable_vwap_retest_check: bool = False,
    retest_require_wick_contact: bool = True,
    wick_tolerance_bps: float = 0.0,
    wick_contact_mode: str = "either",
    wick_pierce_max_bps: Optional[float] = None,
    **_extras,
) -> List[Dict]:
    """
    Convenience function to run the pipeline with default settings.

    This is the primary entry point for both backtesting and live scanning.

    Args:
        session_df_5m: 5-minute OHLCV data
        session_df_1m: 1-minute OHLCV data
        breakout_window_minutes: Minutes from session open to scan for breakouts
        retest_lookahead_minutes: Minutes after breakout close to search for retest
        ignition_lookahead_minutes: Minutes after retest to search for ignition
        pipeline_level: Pipeline strictness level
                       Level 0: Candidates only (Stages 1-3, no trades)
                       Level 1: Trade execution with base criteria (Stages 1-3, no ignition)
                       Level 2+: Enhanced filtering, may include Stage 4 (Ignition)
        enable_vwap_check: Deprecated. Ignition no longer enforces VWAP; kept for internal
            API compatibility. Use `enable_vwap_breakout_check` and `enable_vwap_retest_check`.

    Returns:
        List of candidates that passed all required stages
    """

    # Use the strict Level 0 retest filter for both Level 0 (candidates)
    # and Level 1 (trades with base criteria). Level 2+ may add further
    # quality filters but Stage 3 detection remains consistent.
    # Unify retest criteria: Level 2+ now also uses the strict Level 0 retest filter.
    # This removes the previous Level 2 reliance on base_retest_filter (VWAP + close-only).
    # Rationale: enforce parity across levels and rebuild L2-specific refinements later.
    # Choose retest filter based on VWAP setting
    def _vwap_parity_retest_filter(m1, direction: str, level: float) -> bool:
        """Strict parity (body at/beyond level) plus VWAP side check (no buffer)."""
        o = float(m1.get("Open", 0.0))
        c = float(m1.get("Close", 0.0))
        vwap = m1.get("vwap")
        try:
            vwap = float(vwap)
        except Exception:
            return False
        if direction == "long":
            return (o >= level and c >= level) and (c >= vwap)
        elif direction == "short":
            return (o <= level and c <= level) and (c <= vwap)
        return False

    retest_filter = _vwap_parity_retest_filter if enable_vwap_retest_check else level0_retest_filter
    # Accept and ignore any future keyword extensions via **_extras to keep
    # backtest code forward-compatible with pipeline evolution without failing.
    pipeline = TradeSetupPipeline(
        breakout_window_minutes=breakout_window_minutes,
        retest_lookahead_minutes=retest_lookahead_minutes,
        ignition_lookahead_minutes=ignition_lookahead_minutes,
        pipeline_level=pipeline_level,
        retest_filter=retest_filter,
        enable_vwap_check=enable_vwap_check,
        enable_vwap_breakout_check=enable_vwap_breakout_check,
        enable_vwap_retest_check=enable_vwap_retest_check,
        retest_require_wick_contact=retest_require_wick_contact,
        wick_tolerance_bps=wick_tolerance_bps,
        wick_contact_mode=wick_contact_mode,
        wick_pierce_max_bps=wick_pierce_max_bps,
    )
    return pipeline.run(session_df_5m, session_df_1m)
