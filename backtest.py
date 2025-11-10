#!/usr/bin/env python3
"""
Backtesting engine for Break & Re-Test strategy

Usage:
    python backtest.py --start 2024-01-01 --end 2024-12-31
    python backtest.py --symbols AAPL MSFT --start 2024-01-01 --end 2024-12-31
    python backtest.py --symbols AAPL --start 2024-01-01 --end 2024-12-31 --initial-capital 10000
"""

import argparse
import sys
from datetime import datetime, timedelta, date
import json
import math
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
import re

import pandas as pd
# Note: yfinance provider removed; keep import out to avoid unused import lint

from cache_utils import (
    get_cache_path,
    load_cached_day,
    save_day,
    integrity_check_range,
)
from config_utils import load_config, add_config_override_argument, apply_config_overrides
from grading import get_grader
from time_utils import get_display_timezone, get_timezone_label_for_date
from trade_setup_pipeline import run_pipeline
from stage_opening_range import detect_opening_range

CONFIG = load_config()
DEFAULT_TICKERS = CONFIG["tickers"]
DEFAULT_INITIAL_CAPITAL = CONFIG.get("initial_capital", 7500)
DEFAULT_LEVERAGE = CONFIG.get("leverage", 2.0)
DEFAULT_RESULTS_DIR = CONFIG.get("backtest_results_dir", "backtest_results")
RETEST_VOL_GATE = CONFIG.get("retest_volume_gate_ratio", 0.20)
BREAKOUT_A_UW_MAX = CONFIG.get("breakout_A_upper_wick_max", 0.15)
FEATURE_LEVEL0_ENABLE_VWAP_CHECK = CONFIG.get("feature_level0_enable_vwap_check", True)
BREAKOUT_B_BODY_MAX = CONFIG.get("breakout_B_body_max", 0.65)
RETEST_B_EPSILON = CONFIG.get("retest_B_level_epsilon_pct", 0.10)
RETEST_B_SOFT = CONFIG.get("retest_B_structure_soft", True)
FEATURE_GRADE_C_FILTERING_ENABLE = CONFIG.get("feature_grade_c_filtering_enable", True)
FEATURE_GRADE_B_FILTERING_ENABLE = CONFIG.get("feature_grade_b_filtering_enable", True)
FEATURE_GRADE_A_FILTERING_ENABLE = CONFIG.get("feature_grade_a_filtering_enable", True)
GRADE_B_MIN_POINTS = CONFIG.get("grade_b_min_points", 70)
GRADE_A_MIN_POINTS = CONFIG.get("grade_a_min_points", 85)


class DataCache:
    """Manages cached OHLCV data organized by symbol and date"""

    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

    def clear_cache(self):
        """Clear all cached data"""
        import shutil

        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(exist_ok=True)
            print(f"Cache cleared: {self.cache_dir}")

    def _get_cache_path(self, symbol: str, date: str, interval: str) -> Path:
        """Generate cache file path for a symbol and date"""
        return get_cache_path(self.cache_dir, symbol, date, interval)

    def get_cached_data(self, symbol: str, date: str, interval: str) -> Optional[pd.DataFrame]:
        """Load cached data if available"""
        return load_cached_day(self.cache_dir, symbol, date, interval)

    def cache_data(self, symbol: str, date: str, interval: str, df: pd.DataFrame):
        """Save data to cache"""
        save_day(self.cache_dir, symbol, date, interval, df)

    def download_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "5m",
    ) -> pd.DataFrame:
        """
            Load OHLCV data for a symbol and date range from local cache only.
        This tool no longer downloads from Yahoo Finance; populate cache via
        the StockData.org fetcher (stockdata_retriever.py) before running.

            Args:
                symbol: Stock ticker symbol
                start_date: Start date (YYYY-MM-DD)
                end_date: End date (YYYY-MM-DD)
                interval: Data interval (1m, 5m, 15m, 1h, 1d)

            Returns:
                DataFrame with OHLCV data
        """
        all_data = []

        # Parse dates
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        # 1m path uses same cache-only logic
        if interval == "1m":
            return self._download_1m_data(symbol, start, end)

        # Download day by day for intraday data (yfinance limitation)
        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")

            # Check cache first
            cached_df = self.get_cached_data(symbol, date_str, interval)
            if cached_df is not None and not cached_df.empty:
                all_data.append(cached_df)
                current += timedelta(days=1)
                continue

            # No provider download here; rely on cache populated by StockData.org tool
            # Suppress missing-cache logs on weekends (Saturday=5, Sunday=6)
            if current.weekday() < 5:
                print(f"No cached data for {symbol} {interval} on {date_str}")

            current += timedelta(days=1)

        # Combine all data
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            combined_df["Datetime"] = pd.to_datetime(combined_df["Datetime"], utc=True)
            combined_df = combined_df.sort_values("Datetime").reset_index(drop=True)
            return combined_df
        else:
            return pd.DataFrame()

    def _download_1m_data(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        """
        Load 1-minute data from local cache only.

            Args:
                symbol: Stock ticker symbol
                start: Start datetime
                end: End datetime

            Returns:
                DataFrame with 1-minute OHLCV data
        """
        all_data = []

        # Download day by day for 1-minute as well, staying within Yahoo's 30-day limit
        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")

            # Check cache only (supports 1m and legacy 1min)
            cached_df = self.get_cached_data(symbol, date_str, "1m")
            if cached_df is not None and not cached_df.empty:
                all_data.append(cached_df)
                current += timedelta(days=1)
                continue

            # No provider download here; rely on cache populated by StockData.org tool
            # Suppress missing-cache logs on weekends (Saturday=5, Sunday=6)
            if current.weekday() < 5:
                print(f"No cached 1m data for {symbol} on {date_str}")

            current += timedelta(days=1)

        # Combine all data
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            combined_df["Datetime"] = pd.to_datetime(combined_df["Datetime"], utc=True)
            combined_df = combined_df.sort_values("Datetime").reset_index(drop=True)
            return combined_df
        else:
            return pd.DataFrame()


class BacktestEngine:
    """Backtest the Break & Re-Test strategy"""

    def __init__(
        self,
        initial_capital: float = 10000,
        position_size_pct: float = 0.1,
        leverage: float = 1.0,
        max_positions: int = 3,
        scan_window_minutes: int = 180,
        # Removed: min_grade and breakout_tier_filter parameters
        display_tzinfo=None,
        tz_label: str = "UTC",
        retest_vol_threshold: float = 0.15,
        pipeline_level: int = 0,
        no_trades: bool = False,
        grading_system: str = "points",
        min_rr_ratio: float = 2.0,
        console_only: bool = False,
    ):
        """
        Initialize backtest engine

        Args:
            initial_capital: Starting capital
            position_size_pct: Percentage of capital risked per trade (0.1 = 10%)
            max_positions: Maximum number of concurrent positions
            scan_window_minutes: Rolling window for scanning (default: 180 = 3 hours)
            leverage: Max notional leverage (1.0 = no leverage).
                      Caps shares by notional <= cash * leverage
            pipeline_level: Pipeline strictness level
                - Level 0: Candidates only (no trades, Stages 1-3)
                - Level 1: Trades with base criteria (Stages 1-3, no ignition)
                - Level 2: Enhanced filtering – Breakout and RR >= C (Stage 4)
                - Level 3+: Stricter filtering – components >= C and overall grade >= B
            no_trades: If True, only identify candidates without executing trades (Level 1+ only)
        """
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.leverage = max(0.0, float(leverage))
        self.max_positions = max_positions
        self.scan_window_minutes = scan_window_minutes
        self.cash = initial_capital
        self.positions = []
        self.closed_trades = []
        self.equity_curve = []
        # Removed filtering attributes (min_grade, breakout_tier_filter)
        # Reporting timezone for printing
        self.display_tz = display_tzinfo
        self.tz_label = tz_label
        self.retest_vol_threshold = retest_vol_threshold
        self.min_rr_ratio = min_rr_ratio
        # Control console verbosity at Level 2: suppress trade-level detail unless --console-only
        self.console_only = console_only

        # Pipeline level determines filtering strictness and trade behavior
        # Level 0: Candidates only (no trades ever)
        # Level 1+: Can execute trades (unless no_trades=True)
        self.pipeline_level = int(pipeline_level)
        self.no_trades = no_trades if pipeline_level > 0 else True  # Level 0 always no trades
        # Grading system
        self.grader = get_grader(grading_system)

    def _load_1m_window(
        self, symbol: str, center_time: pd.Timestamp, window_minutes: int = 90
    ) -> pd.DataFrame:
        """
        Load 1-minute data for a window around a specific time (e.g., breakout).
        Handles market close/open boundaries by loading multiple days if needed.

        Args:
            symbol: Stock ticker
            center_time: The center time (e.g., breakout time)
            window_minutes: Minutes to load before and after center_time

        Returns:
            DataFrame with 1-minute OHLCV data for the window
        """
        cache = DataCache(self.cache_dir)

        # Calculate the date range we need (may span multiple days)
        start_time = center_time - timedelta(minutes=window_minutes)
        end_time = center_time + timedelta(minutes=window_minutes)

        # Get unique dates we need to load
        current = start_time.date()
        end_date = end_time.date()
        dates_needed = []

        while current <= end_date:
            # Skip weekends
            if current.weekday() < 5:
                dates_needed.append(current)
            current += timedelta(days=1)

        # Load all needed days
        dfs = []
        for current_date in dates_needed:
            date_str = current_date.strftime("%Y-%m-%d")
            cached = cache.get_cached_data(symbol, date_str, "1m")
            if cached is not None and not cached.empty:
                dfs.append(cached)

        if not dfs:
            return pd.DataFrame()

        # Combine and filter to window
        df = pd.concat(dfs, ignore_index=True)
        df["Datetime"] = pd.to_datetime(df["Datetime"], utc=True)
        df = df.sort_values("Datetime").reset_index(drop=True)

        # Filter to the actual time window
        df = df[(df["Datetime"] >= start_time) & (df["Datetime"] <= end_time)]

        return df

    def _scan_continuous_data(
        self, symbol: str, df_5m: pd.DataFrame, cache_dir: str = "cache"
    ) -> List[Dict]:
        """
        Scan data using multi-timeframe approach with on-demand 1m loading:
        - Use 5-minute candles to identify opening range and breakouts
        - Load 1-minute data on-demand when breakout detected
        - Switch to 1-minute candles for retest and ignition entry

        Relaxed criteria for backtesting (vs live scanning):
        - Volume threshold: 1.0x MA (vs 1.2x)
        - Returns to level: within $0.50 (vs $0.10)
        - Tight candle: < 75% of breakout range (vs 50%)

        Args:
            symbol: Stock ticker
            df_5m: DataFrame with 5-minute OHLCV data
            cache_dir: Cache directory for loading 1m data on-demand

        Returns:
            List of all detected signals
        """
        all_signals = []
        self.cache_dir = cache_dir  # Store for _load_1m_window

        # Calculate 10-bar volume MA on 5-minute data (for breakout volume ratio)
        df_5m = df_5m.copy()
        df_5m["vol_ma"] = df_5m["Volume"].rolling(window=10, min_periods=1).mean()
        df_5m["Date"] = df_5m["Datetime"].dt.date

        trading_days = df_5m["Date"].unique()

        for day in trading_days:
            # Get 5-minute data for this day during regular market hours (09:30-16:00 ET).
            # Data is stored in UTC; convert to America/New_York for session slicing to avoid
            # confusion with config display timezone (e.g., PST used only for reporting).
            day_df_5m = df_5m[df_5m["Date"] == day].copy()
            try:
                et_tz = ZoneInfo("America/New_York")
            except Exception:
                et_tz = None

            # Resolve configured session boundaries (strings "HH:MM")
            # Prefer new ET session boundary keys with fallback to legacy names
            sess_start_str = str(CONFIG.get("session_start_et", "09:30")).strip()
            sess_end_str = str(CONFIG.get("session_end_et", "16:00")).strip()

            # Convert timestamps to ET for hour:minute comparisons (DST-safe)
            if et_tz is not None:
                # Handle tz-naive: tests may pass ET-like naive timestamps.
                # Localize as America/New_York to preserve 09:30–16:00 session window.
                dt_series = day_df_5m["Datetime"]
                try:
                    if dt_series.dt.tz is None:
                        # Interpret naive timestamps as America/New_York (market local time)
                        dt_series = dt_series.dt.tz_localize(et_tz)
                    else:
                        dt_series = dt_series.dt.tz_convert(et_tz)
                except Exception:
                    # Fallback: leave as-is if any localization error
                    pass
                local_et = dt_series
                session_df_5m = day_df_5m[
                    (local_et.dt.strftime("%H:%M") >= sess_start_str)
                    & (local_et.dt.strftime("%H:%M") < sess_end_str)
                ]
            else:
                # Fallback: compare as strings in current tz (should be UTC) – less precise
                session_df_5m = day_df_5m[
                    (day_df_5m["Datetime"].dt.strftime("%H:%M") >= sess_start_str)
                    & (day_df_5m["Datetime"].dt.strftime("%H:%M") < sess_end_str)
                ]

            if len(session_df_5m) < 10:
                continue

            # -------------------------------------------------------------
            # Session completeness & anchored open handling
            # -------------------------------------------------------------
            # Some cached intraday days are truncated (e.g. start mid-session
            # around 14:30 ET instead of the expected 09:30–09:35 ET first 5m
            # bar). When that happens the existing logic incorrectly treats
            # the first available 5m candle as the session "open" and runs the
            # 90‑minute breakout window from mid‑day, producing false candidates
            # and trades well beyond the intended early-session window.
            #
            # We detect truncation by comparing the first 5m candle's ET time
            # to the expected opening range bar time. Because 5m resampling
            # uses label='right', the first 5m bar covering 09:31–09:35 prints
            # at 09:35 ET. We accept any first bar between 09:30 and 09:40 ET
            # (allowing a missing initial bar), but if the first bar is later
            # than 10:00 ET we treat the day as incomplete and skip it rather
            # than mis-anchor the breakout window.
            try:
                first_bar_et = None
                if et_tz is not None:
                    fb = session_df_5m.iloc[0]["Datetime"]
                    # If first bar is tz-naive treat it as local ET.
                    # Tests often supply naive times.
                    # Localize to America/New_York (not UTC) to avoid a 5h shift.
                    if getattr(fb, "tzinfo", None) is None:
                        fb = fb.tz_localize(et_tz)
                    else:
                        fb = fb.astimezone(et_tz)
                    first_bar_et = fb
                if first_bar_et is not None:
                    if first_bar_et.hour > 10 or (
                        first_bar_et.hour == 10 and first_bar_et.minute > 0
                    ):
                        print(
                            "Skipping {} {} (truncated; first 5m {} ET)".format(
                                symbol, day, first_bar_et.strftime("%H:%M")
                            )
                        )
                        continue
            except Exception:
                # If any conversion error occurs, proceed without the safeguard.
                pass

            # Calculate VWAP for the session
            session_df_5m = session_df_5m.copy()
            session_df_5m["typical_price"] = (
                session_df_5m["High"] + session_df_5m["Low"] + session_df_5m["Close"]
            ) / 3
            session_df_5m["tp_volume"] = session_df_5m["typical_price"] * session_df_5m["Volume"]
            session_df_5m["vwap"] = (
                session_df_5m["tp_volume"].cumsum() / session_df_5m["Volume"].cumsum()
            )

            # Scan only the configured first N minutes of 5-minute data for
            # breakouts. Default remains 90 if not present in CONFIG.
            market_open_minutes = int(CONFIG.get("market_open_minutes", 90))
            # Anchor breakout scan to the *expected* session open instead of
            # the first available (which may be mid‑session on truncated days).
            # Expected open (5m bar label) ~09:35 ET; we'll anchor at 09:30 ET
            # and still allow the pipeline to define OR from the first bar we pass.
            if et_tz is not None:
                sess_date_et = first_bar_et.date() if first_bar_et else day
                # 09:30 ET anchor in UTC
                expected_open_et = datetime.combine(sess_date_et, datetime.min.time()).replace(
                    hour=9, minute=30, tzinfo=et_tz
                )
                expected_open_utc = expected_open_et.astimezone(ZoneInfo("UTC"))
                end_time = expected_open_utc + timedelta(minutes=market_open_minutes)

                # Ensure session_df_5m Datetime is tz-aware UTC for safe comparison.
                dt_cmp = session_df_5m["Datetime"]
                try:
                    if getattr(dt_cmp.dt, "tz", None) is None:
                        # Treat naive times as ET (already sliced by ET clock) then convert to UTC
                        dt_cmp = dt_cmp.dt.tz_localize(et_tz).dt.tz_convert(ZoneInfo("UTC"))
                    else:
                        dt_cmp = dt_cmp.dt.tz_convert(ZoneInfo("UTC"))
                    session_df_5m["Datetime"] = dt_cmp
                except Exception:
                    # Fallback: conversion failed; assume naive timestamps are UTC and localize
                    if getattr(session_df_5m["Datetime"].dt, "tz", None) is None:
                        session_df_5m["Datetime"] = session_df_5m["Datetime"].dt.tz_localize("UTC")

                scan_df_5m = session_df_5m[
                    (session_df_5m["Datetime"] >= expected_open_utc)
                    & (session_df_5m["Datetime"] < end_time)
                ].copy()
            else:
                start_time = session_df_5m["Datetime"].iloc[0]
                end_time = start_time + timedelta(minutes=market_open_minutes)
                scan_df_5m = session_df_5m[
                    (session_df_5m["Datetime"] >= start_time)
                    & (session_df_5m["Datetime"] < end_time)
                ].copy()

            if len(scan_df_5m) < 10:
                continue

            # Prepare 1m data for this day
            # Prefer inline 1m (tests) else load on-demand from cache
            session_start = session_df_5m["Datetime"].iloc[0]
            if getattr(self, "_inline_df_1m", None) is not None:
                df1 = self._inline_df_1m.copy()  # type: ignore[attr-defined]
                df1["Datetime"] = pd.to_datetime(df1["Datetime"], errors="coerce")
                # Filter by calendar day and typical session hours
                session_df_1m = df1[
                    (df1["Datetime"].dt.date == day)
                    & (df1["Datetime"].dt.strftime("%H:%M") >= "09:00")
                    & (df1["Datetime"].dt.strftime("%H:%M") <= "16:00")
                ].copy()
            else:
                # Load 1m data with a window from 30 min before open to end of session
                session_df_1m = self._load_1m_window(
                    symbol=symbol,
                    center_time=session_start + timedelta(minutes=195),  # Mid-session
                    window_minutes=240,  # Cover full session plus buffer
                )

            # Normalize 1m to the regular session window [09:30, 16:00) ET so that
            # Stage 3 (retest) anchors market_open consistently at 09:30 when it
            # reads session_df_1m.iloc[0]. This avoids early/late pre/post market bars
            # shifting the 90-minute window.
            if et_tz is not None and not session_df_1m.empty:
                # Deterministic tz normalization:
                # 1) Interpret tz-naive as America/New_York, then convert to UTC
                # 2) If tz-aware, convert to UTC
                dt_sr = pd.to_datetime(session_df_1m["Datetime"], errors="coerce")
                if getattr(dt_sr.dt, "tz", None) is None:
                    dt_sr_utc = dt_sr.dt.tz_localize(et_tz).dt.tz_convert(ZoneInfo("UTC"))
                else:
                    dt_sr_utc = dt_sr.dt.tz_convert(ZoneInfo("UTC"))
                session_df_1m["Datetime"] = dt_sr_utc

                # Build ET anchors from the same calendar session
                et_local = dt_sr_utc.dt.tz_convert(et_tz)
                sess_date_et = et_local.iloc[0].date()
                expected_open_et = datetime.combine(sess_date_et, datetime.min.time()).replace(
                    hour=9, minute=30, tzinfo=et_tz
                )
                expected_close_et = datetime.combine(sess_date_et, datetime.min.time()).replace(
                    hour=16, minute=0, tzinfo=et_tz
                )
                open_utc = expected_open_et.astimezone(ZoneInfo("UTC"))
                close_utc = expected_close_et.astimezone(ZoneInfo("UTC"))
                session_df_1m = session_df_1m[
                    (session_df_1m["Datetime"] >= open_utc)
                    & (session_df_1m["Datetime"] < close_utc)
                ].copy()

            if session_df_1m.empty or len(session_df_1m) < 50:
                # No 1m data available for this day, skip
                continue

            if self.pipeline_level == 0:
                # Level 0: Base pipeline - Delegate Stage 1-3 detection to shared pipeline
                # (Ignition detection disabled at Level 0)
                # Level 0 now uses level0_retest_filter for retest detection (body at/beyond OR)
                candidates = run_pipeline(
                    session_df_5m=scan_df_5m,
                    session_df_1m=session_df_1m,
                    breakout_window_minutes=market_open_minutes,
                    retest_lookahead_minutes=30,
                    pipeline_level=0,
                    enable_vwap_check=False,  # VWAP check disabled for Level 0
                )

                for c in candidates:
                    breakout_candle = c.get("breakout_candle", {})
                    retest_candle = c.get("retest_candle", {})
                    all_signals.append(
                        {
                            "ticker": symbol,
                            "direction": c.get("direction"),
                            "entry": None,
                            "stop": None,
                            "target": None,
                            "risk": None,
                            "level": c.get("level"),
                            "datetime": c.get("retest_time"),
                            "breakout_time_5m": c.get("breakout_time"),
                            "vol_breakout_5m": getattr(breakout_candle, "Volume", None)
                            if hasattr(breakout_candle, "__getitem__")
                            else None,
                            "vol_retest_1m": getattr(retest_candle, "Volume", None)
                            if hasattr(retest_candle, "__getitem__")
                            else None,
                            "breakout_candle": {
                                "Open": breakout_candle.get("Open")
                                if hasattr(breakout_candle, "get")
                                else None,
                                "High": breakout_candle.get("High")
                                if hasattr(breakout_candle, "get")
                                else None,
                                "Low": breakout_candle.get("Low")
                                if hasattr(breakout_candle, "get")
                                else None,
                                "Close": breakout_candle.get("Close")
                                if hasattr(breakout_candle, "get")
                                else None,
                                "Volume": breakout_candle.get("Volume")
                                if hasattr(breakout_candle, "get")
                                else None,
                            },
                            "prev_breakout_candle": c.get("prev_breakout_candle")
                            if isinstance(c, dict)
                            else None,
                            "retest_candle": {
                                "Open": retest_candle.get("Open")
                                if hasattr(retest_candle, "get")
                                else None,
                                "High": retest_candle.get("High")
                                if hasattr(retest_candle, "get")
                                else None,
                                "Low": retest_candle.get("Low")
                                if hasattr(retest_candle, "get")
                                else None,
                                "Close": retest_candle.get("Close")
                                if hasattr(retest_candle, "get")
                                else None,
                                "Volume": retest_candle.get("Volume")
                                if hasattr(retest_candle, "get")
                                else None,
                            },
                        }
                    )

                # Proceed to next day
                continue

            # Use shared pipeline for Level 1+ (Stages 1-3; Stage 4 only at Level 2+)
            # Compute Opening Range once for the session (for OR-relative grading)
            or_info = detect_opening_range(session_df_5m)
            or_range = float(or_info.get("high", 0.0)) - float(or_info.get("low", 0.0))

            pipeline_candidates = run_pipeline(
                session_df_5m=scan_df_5m,
                session_df_1m=session_df_1m,
                breakout_window_minutes=market_open_minutes,
                retest_lookahead_minutes=30,
                pipeline_level=self.pipeline_level,
                # VWAP check disabled for all levels (0/1/2+) for now
                enable_vwap_check=False,
            )

            for cand in pipeline_candidates:
                direction = cand.get("direction")
                level = cand.get("level")
                breakout_time = cand.get("breakout_time")
                breakout_candle = cand.get("breakout_candle", {})
                retest_candle = cand.get("retest_candle", {})
                retest_time = pd.to_datetime(cand.get("retest_time"))

                # Level 2+: Entry at ignition (Stage 4); Level 1: Entry at next bar after retest
                ignition_bar = None  # We'll always try to capture an ignition candle for analytics
                if self.pipeline_level >= 2:
                    # Wait for ignition before entering (or skip if no ignition detected)
                    ignition_time_raw = cand.get("ignition_time")
                    if not ignition_time_raw:
                        continue  # No ignition detected, skip this signal
                    ignition_time = pd.to_datetime(ignition_time_raw)

                    # Find the 1m bar immediately after the ignition candle for entry
                    next_bars = session_df_1m[session_df_1m["Datetime"] > ignition_time]
                    if next_bars.empty:
                        continue
                    entry_bar = next_bars.iloc[0]
                    entry_time = entry_bar["Datetime"]
                    entry = float(entry_bar.get("Open"))
                    # For unified schema capture the actual ignition bar (from pipeline if present)
                    ignition_bar = session_df_1m[session_df_1m["Datetime"] == ignition_time]
                    if not ignition_bar.empty:
                        ignition_bar = ignition_bar.iloc[0]
                    else:
                        ignition_bar = None
                else:
                    # Level 1: Wait for first 1m candle after retest that closes above
                    # (long) or below (short) retest close, then enter on open of next candle
                    retest_close = float(retest_candle.get("Close", 0.0))
                    after_retest = session_df_1m[session_df_1m["Datetime"] > retest_time]
                    ignition_idx = None
                    breakout_up = direction == "long"
                    for idx, row in after_retest.iterrows():
                        close = float(row.get("Close", 0.0))
                        if (breakout_up and close > retest_close) or (
                            not breakout_up and close < retest_close
                        ):
                            ignition_idx = idx
                            break
                    if ignition_idx is None:
                        continue  # No ignition found, skip
                    # Get the next bar after ignition for entry
                    ignition_time = after_retest.loc[ignition_idx, "Datetime"]
                    # Capture ignition bar for Level 1 as well (unified analytics)
                    ignition_bar = after_retest.loc[ignition_idx]
                    next_bars = session_df_1m[session_df_1m["Datetime"] > ignition_time]
                    if next_bars.empty:
                        continue
                    entry_bar = next_bars.iloc[0]
                    entry_time = entry_bar["Datetime"]
                    entry = float(entry_bar.get("Open"))

                # CRITICAL: Only enter trades within the configured first
                # market_open_minutes window. Market opens at 09:30 ET; the
                # window ends at 09:30 + market_open_minutes. This enforces
                # identical temporal logic for all levels using the config.
                if entry_time >= end_time:
                    continue

                breakout_up = direction == "long"
                # Stop below/above retest candle with a 0.5% buffer of the breakout distance
                if breakout_up:
                    breakout_distance = abs(entry - float(retest_candle.get("Low", entry)))
                    buffer = 0.005 * breakout_distance  # 0.5% of breakout distance
                    stop = float(retest_candle.get("Low", entry)) - buffer
                else:
                    breakout_distance = abs(entry - float(retest_candle.get("High", entry)))
                    buffer = 0.005 * breakout_distance  # 0.5% of breakout distance
                    stop = float(retest_candle.get("High", entry)) + buffer
                # Ensure stop is not more than 0.5% of entry price away
                # (cap risk per share at 0.5% of entry)
                max_stop_distance = 0.005 * abs(entry)
                if breakout_up:
                    stop = max(stop, entry - max_stop_distance)
                else:
                    stop = min(stop, entry + max_stop_distance)
                risk = abs(entry - stop)
                if risk == 0 or not pd.notna(risk):
                    continue
                target = (
                    entry + self.min_rr_ratio * risk
                    if breakout_up
                    else entry - self.min_rr_ratio * risk
                )

                # Grading metadata from breakout/retest only (ignition is post-entry)
                try:
                    breakout_body_pct = abs(
                        float(breakout_candle["Close"]) - float(breakout_candle["Open"])
                    ) / max(
                        float(breakout_candle["High"]) - float(breakout_candle["Low"]),
                        1e-9,
                    )
                except Exception:
                    breakout_body_pct = 0.0
                try:
                    breakout_vol_ratio = float(breakout_candle["Volume"]) / max(
                        float(
                            session_df_5m.loc[
                                session_df_5m["Datetime"] == breakout_time, "vol_ma"
                            ].iloc[0]
                        ),
                        1e-9,
                    )
                except Exception:
                    breakout_vol_ratio = 0.0
                try:
                    retest_vol_ratio = float(retest_candle["Volume"]) / max(
                        float(breakout_candle["Volume"]), 1e-9
                    )
                except Exception:
                    retest_vol_ratio = 0.0

                signal = {
                    "ticker": symbol,
                    "direction": direction,
                    "entry": entry,
                    "stop": stop,
                    "target": target,
                    "risk": risk,
                    "level": level,
                    "datetime": entry_time,
                    "breakout_time_5m": breakout_time,
                    "vol_breakout_5m": breakout_candle["Volume"],
                    "vol_retest_1m": retest_candle["Volume"],
                    # Grading metadata
                    "breakout_candle": breakout_candle,
                    "prev_breakout_candle": cand.get("prev_breakout_candle"),
                    "retest_candle": retest_candle,
                    "breakout_body_pct": breakout_body_pct,
                    "breakout_vol_ratio": breakout_vol_ratio,
                    "retest_vol_ratio": retest_vol_ratio,
                    # Opening Range (for body% of OR in Grade C checks)
                    "or_range": or_range,
                }

                # Unified ignition analytics (Level 1 & 2): attach ignition info if we have a bar
                # For Level 2 we prefer pipeline-provided ignition_candle (cand['ignition_candle']).
                # For Level 1 we synthesized 'ignition_bar'.
                ign_source = None
                if "ignition_candle" in cand and cand.get("ignition_candle") is not None:
                    ign_source = cand.get("ignition_candle")
                elif ignition_bar is not None:
                    # Build dict from the captured ignition bar (Series)
                    try:
                        ign_source = {
                            "Datetime": ignition_bar.get("Datetime"),
                            "Open": ignition_bar.get("Open"),
                            "High": ignition_bar.get("High"),
                            "Low": ignition_bar.get("Low"),
                            "Close": ignition_bar.get("Close"),
                            "Volume": ignition_bar.get("Volume"),
                        }
                    except Exception:
                        ign_source = None

                if ign_source is not None:
                    ign_vol = ign_source.get("Volume") if isinstance(ign_source, dict) else None
                    signal.update(
                        {
                            "ignition_candle": ign_source,
                            "vol_ignition_1m": ign_vol,
                        }
                    )
                    # Compute ignition metrics for grading (robust to missing)
                    try:
                        ign_open = float(ign_source.get("Open"))
                        ign_high = float(ign_source.get("High"))
                        ign_low = float(ign_source.get("Low"))
                        ign_close = float(ign_source.get("Close"))
                        ign_range = max(ign_high - ign_low, 1e-9)
                        ignition_body_pct = abs(ign_close - ign_open) / ign_range
                        retest_vol_f = float(retest_candle.get("Volume", 0.0))
                        ignition_vol_ratio = (
                            float(ign_vol) / retest_vol_f if retest_vol_f > 0 else 0.0
                        )
                        # Distance to target measured at ignition close vs target progression
                        if direction == "long":
                            denom = target - entry
                            progress = (ign_close - entry) / denom if denom != 0 else 0.0
                        else:
                            denom = entry - target
                            progress = (entry - ign_close) / denom if denom != 0 else 0.0
                        distance_to_target = max(0.0, min(1.0, float(progress)))
                        signal.update(
                            {
                                "ignition_body_pct": ignition_body_pct,
                                "ignition_vol_ratio": ignition_vol_ratio,
                                "distance_to_target": distance_to_target,
                            }
                        )
                    except Exception:
                        signal.update(
                            {
                                "ignition_body_pct": 0.0,
                                "ignition_vol_ratio": 0.0,
                                "distance_to_target": 0.0,
                            }
                        )

                all_signals.append(signal)

        return all_signals

    def run_backtest(
        self, symbol: str, df_5m: pd.DataFrame, cache_dir: Optional[object] = "cache"
    ) -> Dict:
        """
        Run backtest on a single symbol's data using multi-timeframe approach.
        1-minute data is loaded on-demand when breakouts are detected.

        Args:
            symbol: Stock ticker
            df_5m: DataFrame with 5-minute OHLCV data
            cache_dir: Either a cache directory (str, default "cache") or an inline
                1m DataFrame (used by unit tests). Accepts positional DataFrame as third arg
                for unit tests or keyword 'cache_dir' for CLI runs.

        Returns:
            Dictionary with backtest results
        """
        # Configure 1m source (inline DataFrame for tests or cache directory)
        inline_1m: Optional[pd.DataFrame] = None
        selected_cache_dir = "cache"
        if isinstance(cache_dir, pd.DataFrame):
            inline_1m = cache_dir
        elif isinstance(cache_dir, str):
            selected_cache_dir = cache_dir
        else:
            selected_cache_dir = "cache"

        # Stash inline 1m for the scan (used when provided by tests)
        self._inline_df_1m = inline_1m

        # Get signals using multi-timeframe scanning approach with on-demand 1m loading
        signals = self._scan_continuous_data(symbol, df_5m, selected_cache_dir)

        # Track candidates for all levels
        candidates = [
            {
                "datetime": s.get("datetime"),
                "direction": s.get("direction"),
                "level": s.get("level"),
                "breakout_time_5m": s.get("breakout_time_5m"),
            }
            for s in signals
        ]
        candidate_count = len(candidates)

        # Level 0 OR no_trades: candidates only (no trades executed)
        if self.no_trades:
            level_msg = f"Level {self.pipeline_level}"
            if self.pipeline_level > 0:
                level_msg += " (no trades)"
            print(f"Found {len(candidates)} candidates for {symbol} ({level_msg})")
            for c in candidates[:10]:  # print first 10 per symbol for brevity

                def _fmt_local(ts):
                    try:
                        t = pd.to_datetime(ts)
                        if getattr(t, "tzinfo", None) is None:
                            t = t.tz_localize("UTC")
                        t_local = t.tz_convert(self.display_tz)
                        return t_local.strftime("%Y-%m-%d %H:%M:%S %Z")
                    except Exception:
                        return str(ts)

                bt = _fmt_local(c.get("breakout_time_5m"))
                rt = _fmt_local(c.get("datetime"))
                print(f"  - {c.get('direction')} | level {c.get('level')} | 5m {bt} -> 1m {rt}")
            return {
                "symbol": symbol,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
                "signals": signals,
                "trades": [],
                "candidates": candidates,
                "candidate_count": candidate_count,
            }

        if not signals:
            return {
                "symbol": symbol,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "total_pnl": 0,
                "win_rate": 0,
                "signals": [],
                "candidate_count": 0,
            }

        # Compute grades for each signal (no min_grade filtering)
        def compute_grades(sig: Dict) -> Dict:
            entry = sig["entry"]
            stop = sig["stop"]
            target = sig["target"]
            rr_ratio = abs(target - entry) / abs(entry - stop) if entry != stop else 0.0

            # Ensure breakout_candle is a dict
            breakout_candle_data = sig.get("breakout_candle", {})
            if hasattr(breakout_candle_data, "to_dict"):
                breakout_candle_data = breakout_candle_data.to_dict()

            # Ensure prev_candle is a dict
            prev_candle_data = sig.get("prev_breakout_candle", None)
            if prev_candle_data is not None and hasattr(prev_candle_data, "to_dict"):
                prev_candle_data = prev_candle_data.to_dict()

            breakout_grade, breakout_desc = self.grader.grade_breakout_candle(
                breakout_candle_data,
                sig.get("breakout_vol_ratio", 1.5),
                sig.get("breakout_body_pct", 0.0),
                sig.get("level", None),
                sig.get("direction", None),
                a_upper_wick_max=BREAKOUT_A_UW_MAX,
                b_body_max=BREAKOUT_B_BODY_MAX,
                prev_candle=prev_candle_data,
            )
            # Ensure retest_candle is a dict
            retest_candle_data = sig.get("retest_candle", {})
            if hasattr(retest_candle_data, "to_dict"):
                retest_candle_data = retest_candle_data.to_dict()

            retest_grade, retest_desc = self.grader.grade_retest(
                retest_candle_data,
                sig.get("retest_vol_ratio", 0.3),
                sig.get("level", 0.0),
                sig.get("direction", "long"),
                retest_volume_a_max_ratio=0.30,
                retest_volume_b_max_ratio=0.60,
                b_level_epsilon_pct=RETEST_B_EPSILON,
                b_structure_soft=RETEST_B_SOFT,
            )
            # Ensure ignition_candle is a dict
            ignition_candle_data = sig.get("ignition_candle", {})
            if hasattr(ignition_candle_data, "to_dict"):
                ignition_candle_data = ignition_candle_data.to_dict()

            continuation_grade, continuation_desc = self.grader.grade_continuation(
                ignition_candle_data,
                sig.get("ignition_vol_ratio", 1.0),
                sig.get("distance_to_target", 0.5),
                sig.get("ignition_body_pct", 0.6),
            )
            rr_grade, rr_desc = self.grader.grade_risk_reward(rr_ratio)
            market_grade, market_desc = self.grader.grade_market_context("slightly_red")

            grades = {
                "breakout": breakout_grade,
                "retest": retest_grade,
                "continuation": continuation_grade,
                "rr": rr_grade,
                "market": market_grade,
            }
            overall = self.grader.calculate_overall_grade(grades)
            # Attach fields to signal
            sig["overall_grade"] = overall
            sig["component_grades"] = grades
            sig["rr_ratio"] = rr_ratio
            sig["breakout_tier"] = (
                "A" if breakout_grade == "✅" else ("B" if breakout_grade == "⚠️" else "C")
            )  # analytics only
            # Attach points for Level 3 filtering
            sig["breakout_points"] = float(self.grader._state.get("breakout_pts", 0.0))
            sig["retest_points"] = float(self.grader._state.get("retest_pts", 0.0))
            sig["ignition_points"] = float(self.grader._state.get("ignition_pts", 0.0))
            sig["context_points"] = float(self.grader._state.get("context_pts", 0.0))
            return sig

        # Compute grades for all levels so we can analyze score distributions at Level 1
        # (Filtering still only applied for Level 2+ below). This enables downstream
        # exports (e.g., breakout score histograms overlayed with Level 2 pass/fail.)
        graded_signals = [compute_grades(dict(sig)) for sig in signals]

        # Legacy rejection counters removed (no longer used)

        # Level 2: Sequential grade filtering via config toggles (C -> B -> A)
        pre_filter_count = len(graded_signals) if self.pipeline_level == 2 else 0
        rejected_c = 0
        rejected_b = 0
        rejected_a = 0
        if self.pipeline_level == 2:
            debug_tpl = (
                "DEBUG: Level 2 filtering {n} graded signals | Active filters: "
                "C={c}, B={b} (min={bmin}), A={a} (min={amin})"
            )
            print(
                debug_tpl.format(
                    n=len(graded_signals),
                    c="on" if FEATURE_GRADE_C_FILTERING_ENABLE else "off",
                    b="on" if FEATURE_GRADE_B_FILTERING_ENABLE else "off",
                    bmin=GRADE_B_MIN_POINTS,
                    a="on" if FEATURE_GRADE_A_FILTERING_ENABLE else "off",
                    amin=GRADE_A_MIN_POINTS,
                )
            )
            filtered_signals = graded_signals

            # Grade C filter
            if FEATURE_GRADE_C_FILTERING_ENABLE:
                tmp = []
                for s in filtered_signals:
                    cg = s.get("component_grades", {})
                    breakout_ok = cg.get("breakout", "❌") != "❌"
                    rr_ok = cg.get("rr", "❌") != "❌"
                    if breakout_ok and rr_ok:
                        tmp.append(s)
                    else:
                        rejected_c += 1
                filtered_signals = tmp

            # Grade B filter (points threshold)
            if FEATURE_GRADE_B_FILTERING_ENABLE:
                tmp = []
                for s in filtered_signals:
                    total_points = (
                        s.get("breakout_points", 0)
                        + s.get("retest_points", 0)
                        + s.get("ignition_points", 0)
                        + s.get("context_points", 0)
                    )
                    if total_points >= GRADE_B_MIN_POINTS:
                        tmp.append(s)
                    else:
                        rejected_b += 1
                filtered_signals = tmp

            # Grade A filter (higher points threshold)
            if FEATURE_GRADE_A_FILTERING_ENABLE:
                tmp = []
                for s in filtered_signals:
                    total_points = (
                        s.get("breakout_points", 0)
                        + s.get("retest_points", 0)
                        + s.get("ignition_points", 0)
                        + s.get("context_points", 0)
                    )
                    if total_points >= GRADE_A_MIN_POINTS:
                        tmp.append(s)
                    else:
                        rejected_a += 1
                filtered_signals = tmp

            graded_signals = filtered_signals

            # Diagnostics summary
            print(f"  Level 2 Quality Filter for {symbol}:")
            print(f"    Before filter: {pre_filter_count} signals")
            if FEATURE_GRADE_C_FILTERING_ENABLE:
                print(f"    Rejected (Grade C gate): {rejected_c}")
            else:
                print("    Grade C gate: disabled")
            if FEATURE_GRADE_B_FILTERING_ENABLE:
                print(f"    Rejected (Grade B gate < {GRADE_B_MIN_POINTS} pts): {rejected_b}")
            else:
                print("    Grade B gate: disabled")
            if FEATURE_GRADE_A_FILTERING_ENABLE:
                print(f"    Rejected (Grade A gate < {GRADE_A_MIN_POINTS} pts): {rejected_a}")
            else:
                print("    Grade A gate: disabled")
            print(f"    After filter: {len(graded_signals)} signals")

        # Removed: previous Level 3+ logic consolidated into Level 2 grade toggles

        trades = []

        for sig in graded_signals:
            # Track real price movement after signal
            entry_price = sig["entry"]
            stop_price = sig["stop"]
            target_price = sig["target"]
            direction = sig["direction"]
            entry_datetime = pd.to_datetime(sig["datetime"])

            # Calculate position size: risk 0.5% of initial capital per trade
            # shares = (initial_capital * 0.005) / abs(entry - stop)
            risk_per_trade = self.initial_capital * 0.005  # Fixed 0.5% risk
            risk_per_share = abs(entry_price - stop_price)
            shares = int(risk_per_trade / risk_per_share) if risk_per_share > 0 else 0

            if shares == 0:
                continue

            # Load 1m data for this trade: from entry time forward for a reasonable window
            # to track exits. Load up to 1 day (390 market minutes) or until we find an exit.
            future_bars = self._load_1m_window(
                symbol=symbol,
                center_time=entry_datetime + timedelta(minutes=195),  # Mid-day from entry
                window_minutes=200,  # Cover rest of session plus next day if needed
            )

            # Filter to bars after entry
            if not future_bars.empty:
                future_bars = future_bars[future_bars["Datetime"] > entry_datetime].copy()
                future_bars = future_bars.sort_values("Datetime")

            if future_bars.empty:
                # No data after signal - skip this trade
                continue

            # Track which level was hit first (stop or target)
            exit_price = None
            exit_time = None
            outcome = None

            # Continuation (ignition) diagnostics captured at the first 1m bar after entry
            continuation_diag = {
                "continuation_grade": None,
                "continuation_desc": None,
                "ignition_vol_ratio": None,
                "ignition_body_pct": None,
                "distance_to_target": None,
                "ignition_time": None,
            }

            # Compute continuation metrics from the first bar after entry (post-entry info)
            if not future_bars.empty:
                ignition_bar = future_bars.iloc[0]
                ignition_open = float(ignition_bar.get("Open", float("nan")))
                ignition_high = float(ignition_bar.get("High", float("nan")))
                ignition_low = float(ignition_bar.get("Low", float("nan")))
                ignition_close = float(ignition_bar.get("Close", float("nan")))
                ignition_vol = float(ignition_bar.get("Volume", 0.0))

                # Body percent: |close-open| / (high-low)
                range_ = max(ignition_high - ignition_low, 0.0)
                ignition_body_pct = (
                    abs(ignition_close - ignition_open) / range_ if range_ > 0 else 0.0
                )

                # Volume ratio vs RETEST 1m volume (per spec, not breakout)
                retest_vol = sig.get("vol_retest_1m")
                try:
                    retest_vol_f = float(retest_vol) if retest_vol is not None else 0.0
                except Exception:
                    retest_vol_f = 0.0
                ignition_vol_ratio = ignition_vol / retest_vol_f if retest_vol_f > 0 else 0.0

                # Distance to target progress at ignition close
                if direction == "long":
                    denom = target_price - entry_price
                    progress = (ignition_close - entry_price) / denom if denom != 0 else 0.0
                else:
                    denom = entry_price - target_price
                    progress = (entry_price - ignition_close) / denom if denom != 0 else 0.0
                # Clamp between 0 and 1 for reporting
                distance_to_target = max(0.0, min(1.0, float(progress)))

                # Grade continuation (post-entry analysis only)
                cont_grade, cont_desc = self.grader.grade_continuation(
                    {
                        "Open": ignition_open,
                        "High": ignition_high,
                        "Low": ignition_low,
                        "Close": ignition_close,
                        "Volume": ignition_vol,
                    },
                    ignition_vol_ratio,
                    distance_to_target,
                    ignition_body_pct,
                )

                continuation_diag.update(
                    {
                        "continuation_grade": cont_grade,
                        "continuation_desc": cont_desc,
                        "ignition_vol_ratio": ignition_vol_ratio,
                        "ignition_body_pct": ignition_body_pct,
                        "distance_to_target": distance_to_target,
                        # store timestamp for timezone-aware printing later
                        "ignition_time": ignition_bar.get("Datetime"),
                    }
                )

            for idx, bar in future_bars.iterrows():
                if direction == "long":
                    # Check if stop hit (price went below stop)
                    if bar["Low"] <= stop_price:
                        exit_price = stop_price
                        exit_time = bar["Datetime"]
                        outcome = "loss"
                        break
                    # Check if target hit (price went above target)
                    if bar["High"] >= target_price:
                        exit_price = target_price
                        exit_time = bar["Datetime"]
                        outcome = "win"
                        break
                else:  # short
                    # Check if stop hit (price went above stop)
                    if bar["High"] >= stop_price:
                        exit_price = stop_price
                        exit_time = bar["Datetime"]
                        outcome = "loss"
                        break
                    # Check if target hit (price went below target)
                    if bar["Low"] <= target_price:
                        exit_price = target_price
                        exit_time = bar["Datetime"]
                        outcome = "win"
                        break

            # If neither stop nor target was hit, skip this trade
            if exit_price is None:
                continue

            # Calculate P&L
            if direction == "long":
                pnl = (exit_price - entry_price) * shares
            else:  # short
                pnl = (entry_price - exit_price) * shares

            # Build trade dict with all available information
            trade_dict = {
                "datetime": sig.get("datetime"),
                "direction": direction,
                "entry": entry_price,
                "exit": exit_price,
                "exit_time": str(exit_time),
                "stop": stop_price,
                "target": target_price,
                "shares": shares,
                "pnl": pnl,
                "outcome": outcome,
                "risk_amount": risk_per_trade,  # Dollar amount risked per position
                # Continuation diagnostics (post-entry informational only)
                **{k: v for k, v in continuation_diag.items() if v is not None},
            }

            # Add grading information if available (Level 2+)
            if "component_grades" in sig:
                trade_dict["breakout_grade"] = sig["component_grades"].get("breakout")
                trade_dict["retest_grade"] = sig["component_grades"].get("retest")
                trade_dict["rr_grade"] = sig["component_grades"].get("rr")
                trade_dict["context_grade"] = sig["component_grades"].get("market")
                trade_dict["overall_grade"] = sig.get("overall_grade")
                trade_dict["rr_ratio"] = sig.get("rr_ratio", 0.0)

                # Add detailed descriptions
                if "component_descriptions" in sig:
                    trade_dict["breakout_desc"] = sig["component_descriptions"].get("breakout")
                    trade_dict["retest_desc"] = sig["component_descriptions"].get("retest")

            trades.append(trade_dict)

            # Generate and print grading report (Level 2+ only)
            # Print per-trade grading block only for Level 2 when console-only is active
            if self.pipeline_level >= 2 and self.console_only:
                report = self.grader.generate_signal_report(
                    sig,
                    retest_volume_a_max_ratio=0.30,
                    retest_volume_b_max_ratio=0.60,
                    a_upper_wick_max=BREAKOUT_A_UW_MAX,
                    b_body_max=BREAKOUT_B_BODY_MAX,
                    b_level_epsilon_pct=RETEST_B_EPSILON,
                    b_structure_soft=RETEST_B_SOFT,
                )
                print("\n" + "=" * 70)
                print(report)
                # Print continuation diagnostics at exit for information purposes
                if continuation_diag["continuation_grade"] is not None:
                    # Format ignition time in reporting timezone
                    ign_ts = continuation_diag["ignition_time"]
                    try:
                        ign_ts = pd.to_datetime(ign_ts)
                        if getattr(ign_ts, "tzinfo", None) is None:
                            ign_ts = ign_ts.tz_localize("UTC")
                        ign_ts_local = ign_ts.tz_convert(self.display_tz)
                        ign_ts_str = ign_ts_local.strftime("%Y-%m-%d %H:%M:%S %Z")
                    except Exception:
                        ign_ts_str = str(ign_ts)
                    info_line = (
                        f"Continuation (post-entry): {continuation_diag['continuation_desc']} "
                        f"{continuation_diag['continuation_grade']} | "
                        f"progress={continuation_diag['distance_to_target']:.0%}, "
                        f"ign_vol_ratio={continuation_diag['ignition_vol_ratio']:.2f} at "
                        f"{ign_ts_str}"
                    )
                    print(info_line)
                print("=" * 70 + "\n")

        # Calculate statistics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t["outcome"] == "win")
        losing_trades = total_trades - winning_trades
        total_pnl = sum(t["pnl"] for t in trades)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        result = {
            "symbol": symbol,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "signals": graded_signals,
            "trades": trades,
            "candidate_count": candidate_count,
            "filter_config": {
                "grade_c": FEATURE_GRADE_C_FILTERING_ENABLE,
                "grade_b": FEATURE_GRADE_B_FILTERING_ENABLE,
                "grade_a": FEATURE_GRADE_A_FILTERING_ENABLE,
                "grade_b_min_points": GRADE_B_MIN_POINTS,
                "grade_a_min_points": GRADE_A_MIN_POINTS,
            },
        }
        if self.pipeline_level == 2:
            result["level2_filtering_stats"] = {
                "pre_filter_count": pre_filter_count,
                "rejected_c": rejected_c,
                "rejected_b": rejected_b,
                "rejected_a": rejected_a,
                "post_filter_count": len(graded_signals),
            }
        return result


def format_results(results: List[Dict]) -> str:
    """Format backtest results for display"""
    output = []
    output.append("\n" + "=" * 60)
    output.append("BACKTEST RESULTS")
    output.append("=" * 60)

    total_trades = 0
    total_winners = 0
    total_pnl = 0
    total_candidates = 0

    for res in results:
        output.append(f"\n{res['symbol']}:")
        output.append(f"  Total Trades: {res['total_trades']}")
        output.append(f"  Winners: {res['winning_trades']}")
        output.append(f"  Losers: {res['losing_trades']}")
        output.append(f"  Win Rate: {res['win_rate']:.1%}")
        output.append(f"  Total P&L: ${res['total_pnl']:.2f}")
        if "candidate_count" in res:
            output.append(f"  Candidates: {res['candidate_count']}")

        total_trades += res["total_trades"]
        total_winners += res["winning_trades"]
        total_pnl += res["total_pnl"]
        if "candidate_count" in res:
            try:
                total_candidates += int(res["candidate_count"])
            except Exception:
                pass

    output.append("\n" + "-" * 60)
    output.append("OVERALL:")
    output.append(f"  Total Trades: {total_trades}")
    output.append(f"  Winners: {total_winners}")
    output.append(
        f"  Overall Win Rate: {total_winners/total_trades:.1%}"
        if total_trades > 0
        else "  Overall Win Rate: N/A"
    )
    output.append(f"  Total P&L: ${total_pnl:.2f}")
    if total_candidates > 0:
        output.append(f"  Candidates: {total_candidates}")
    output.append("=" * 60 + "\n")

    return "\n".join(output)


def generate_markdown_trade_summary(
    results: List[Dict], tzinfo=None, tz_label: str = "UTC", one_per_day: bool = False
) -> str:
    """Generate a Markdown summary of trades across all symbols.

    Rules:
    - Order trades by entry datetime ascending
    - If one_per_day is True: only one trade per calendar day (in display timezone). If multiple,
      keep the earliest entry for that day.
    - If one_per_day is False: include all trades (no daily grouping).
    """
    # Resolve reporting timezone
    if tzinfo is None:
        tzinfo = ZoneInfo("UTC")
        tz_label = "UTC"

    # Flatten all trades with symbol
    all_trades = []
    for res in results:
        symbol = res.get("symbol")
        for t in res.get("trades", []) or []:
            # Parse entry datetime
            try:
                entry_dt = pd.to_datetime(t.get("datetime"))
                if getattr(entry_dt, "tzinfo", None) is None:
                    entry_dt = entry_dt.tz_localize("UTC")
                entry_dt_local = entry_dt.tz_convert(tzinfo)
            except Exception:
                entry_dt_local = None

            if entry_dt_local is None:
                continue

            all_trades.append({"symbol": symbol, **t, "_entry_dt": entry_dt_local})

    if not all_trades:
        return "\n_No trades to summarize._\n"

    # Sort by entry datetime asc
    all_trades.sort(key=lambda x: x["_entry_dt"])

    # Determine actual timezone label (PST vs PDT, EST vs EDT, etc.) based on first trade date
    if all_trades and tz_label != "UTC":
        sample_date = all_trades[0]["_entry_dt"]
        tz_label = get_timezone_label_for_date(tzinfo, sample_date)

    # Optionally keep only one per day in specified timezone – earliest already due to sorting
    trades_for_summary = all_trades
    if one_per_day:
        seen_days = set()
        unique_daily_trades = []
        for tr in all_trades:
            day_key = tr["_entry_dt"].date()
            if day_key in seen_days:
                continue
            seen_days.add(day_key)
            unique_daily_trades.append(tr)
        trades_for_summary = unique_daily_trades

    # Build Markdown
    lines = []
    if one_per_day:
        lines.append("\n## Trade summary (one per day, earliest entry)\n")
    else:
        lines.append("\n## Trade summary (all entries)\n")
    lines.append(f"_Timezone: {tz_label}_\n")
    lines.append(
        f"| Date ({tz_label}) | Entry Time | Exit Time | Time in trade (min) | "
        "Symbol | Dir | Entry | Stop | Target | Exit | Outcome | Risk | R/R | P&L | Shares |"
    )
    lines.append("|---|---|---|---:|---|---:|---:|---:|---:|---:|---|---:|---:|---:|")

    total = 0
    winners = 0
    total_pnl = 0.0

    for tr in trades_for_summary:
        total += 1
        if tr.get("outcome") == "win":
            winners += 1
        pnl = float(tr.get("pnl", 0.0))
        total_pnl += pnl

        dt = tr["_entry_dt"].strftime("%Y-%m-%d")
        tm = tr["_entry_dt"].strftime("%H:%M:%S")

        # Resolve exit time in requested timezone (best-effort)
        exit_tm = ""
        exit_dt_local = None
        try:
            raw_exit = tr.get("exit_time")
            if raw_exit is not None:
                exit_dt = pd.to_datetime(raw_exit)
                if getattr(exit_dt, "tzinfo", None) is None:
                    exit_dt = exit_dt.tz_localize("UTC")
                exit_dt_local = exit_dt.tz_convert(tzinfo)
                exit_tm = exit_dt_local.strftime("%H:%M:%S")
        except Exception:
            exit_tm = str(tr.get("exit_time", ""))

        # Compute time in trade in whole minutes (ceil for sub-minute trades)
        time_in_min = ""
        try:
            if exit_dt_local is not None and tr.get("_entry_dt") is not None:
                delta = exit_dt_local - tr["_entry_dt"]
                secs = max(0.0, float(delta.total_seconds()))
                time_in_min = str(int(math.ceil(secs / 60.0)))
        except Exception:
            time_in_min = ""
        sym = tr.get("symbol", "?")
        dirn = tr.get("direction", "?")

        def f(x):
            try:
                return f"{float(x):.2f}"
            except Exception:
                return str(x)

        lines.append(
            "| "
            + " | ".join(
                [
                    dt,
                    tm,
                    exit_tm,
                    time_in_min,
                    sym,
                    dirn,
                    f(tr.get("entry")),
                    f(tr.get("stop")),
                    f(tr.get("target")),
                    f(tr.get("exit")),
                    tr.get("outcome", ""),
                    f(tr.get("risk_amount")),
                    f(tr.get("rr_ratio", "")),
                    f(tr.get("pnl")),
                    str(tr.get("shares", "")),
                ]
            )
            + " |"
        )

    win_rate = (winners / total) if total > 0 else 0.0
    lines.append("")
    if one_per_day:
        lines.append(f"- Total days/trades: {total}")
    else:
        lines.append(f"- Total trades: {total}")
    lines.append(f"- Winners: {winners}")
    lines.append(f"- Win rate: {win_rate:.1%}")
    lines.append(f"- Total P&L: ${total_pnl:.2f}")

    return "\n".join(lines)


def _convert_times_to_timezone(results: List[Dict], tzinfo, tz_label: str) -> List[Dict]:
    """Convert datetime-like fields in results to strings in the configured timezone.

    Fields converted (when present):
    - In signals: datetime, breakout_time_5m, ignition_time
    - In candidates: datetime, breakout_time_5m
    - In trades: datetime, exit_time, ignition_time

    Also converts pandas Series objects to dicts for JSON serialization.
    """

    def to_local_str(ts):
        try:
            t = pd.to_datetime(ts)
            if getattr(t, "tzinfo", None) is None:
                t = t.tz_localize("UTC")
            t_local = t.tz_convert(tzinfo)
            # ISO-8601 with offset for machine-readability
            return t_local.isoformat(timespec="seconds")
        except Exception:
            return str(ts)

    def convert_value(obj):
        """Recursively convert pandas objects and timestamps for JSON serialization"""
        if isinstance(obj, pd.Series):
            return {k: convert_value(v) for k, v in obj.to_dict().items()}
        elif isinstance(obj, (pd.Timestamp, datetime, date)):
            return to_local_str(obj)
        elif isinstance(obj, dict):
            return {k: convert_value(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_value(item) for item in obj]
        return obj

    out: List[Dict] = []
    for res in results:
        r = dict(res)
        # Convert signals times
        sigs = []
        for s in r.get("signals", []) or []:
            s2 = dict(s)
            if "datetime" in s2:
                s2["datetime"] = to_local_str(s2["datetime"])
            if "breakout_time_5m" in s2:
                s2["breakout_time_5m"] = to_local_str(s2["breakout_time_5m"])
            if "ignition_time" in s2:
                s2["ignition_time"] = to_local_str(s2["ignition_time"])
                # Recursively convert all nested objects
            if "breakout_candle" in s2:
                s2["breakout_candle"] = convert_value(s2["breakout_candle"])
            if "retest_candle" in s2:
                s2["retest_candle"] = convert_value(s2["retest_candle"])
            if "ignition_candle" in s2:
                s2["ignition_candle"] = convert_value(s2["ignition_candle"])
            sigs.append(s2)
        if sigs:
            r["signals"] = sigs

        # Convert candidates times
        cands = []
        for c in r.get("candidates", []) or []:
            c2 = dict(c)
            if "datetime" in c2:
                c2["datetime"] = to_local_str(c2["datetime"])
            if "breakout_time_5m" in c2:
                c2["breakout_time_5m"] = to_local_str(c2["breakout_time_5m"])
            cands.append(c2)
        if cands:
            r["candidates"] = cands

        # Convert trades times
        trs = []
        for t in r.get("trades", []) or []:
            t2 = dict(t)
            if "datetime" in t2:
                t2["datetime"] = to_local_str(t2["datetime"])
            if "exit_time" in t2 and t2["exit_time"] is not None:
                t2["exit_time"] = to_local_str(t2["exit_time"])
            if "ignition_time" in t2 and t2["ignition_time"] is not None:
                t2["ignition_time"] = to_local_str(t2["ignition_time"])
            trs.append(t2)
        if trs:
            r["trades"] = trs

        # Final recursive sweep to convert any remaining nested pandas/datetime/date objects
        out.append(convert_value(r))
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Backtest Break & Re-Test strategy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  # Backtest all configured tickers
  python backtest.py --start 2025-10-01 --end 2025-10-31

  # Backtest specific symbols
  python backtest.py --symbols AAPL MSFT --start 2025-10-01 --end 2025-10-31

  # Custom capital and save results
  python backtest.py --start 2025-10-01 --end 2025-10-31 \
      --initial-capital 50000 --output results.json

  # Override config values (toggle VWAP check off)
  python backtest.py --start 2025-10-01 --end 2025-10-31 \
      --config-override feature_level0_enable_vwap_check=false

  # Multiple config overrides
  python backtest.py --start 2025-10-01 --end 2025-10-31 \
      --config-override feature_level0_enable_vwap_check=false \
      --config-override initial_capital=10000

Default tickers from config.json: {', '.join(DEFAULT_TICKERS)}
        """,
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help=f"Stock symbols to backtest (default: all from config.json)",
    )
    parser.add_argument("--start", required=False, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=False, default=None, help="End date (YYYY-MM-DD)")

    parser.add_argument(
        "--position-size",
        type=float,
        default=0.1,
        help="Risk per trade as %% of capital (default: 0.1)",
    )
    parser.add_argument(
        "--leverage",
        type=float,
        default=DEFAULT_LEVERAGE,
        help=(
            f"Max notional leverage (default: {DEFAULT_LEVERAGE}). "
            "Caps shares so entry*shares <= cash*leverage"
        ),
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=None,
        help=(
            "Override initial capital (default comes from config.json). "
            "Example: --initial-capital 25000"
        ),
    )
    parser.add_argument("--cache-dir", default="cache", help="Cache directory (default: cache)")
    parser.add_argument("--force-refresh", action="store_true", help="Force refresh cached data")
    parser.add_argument(
        "--output", help="Output JSON file for results (saves to backtest_results/ by default)"
    )
    parser.add_argument(
        "--console-only",
        action="store_true",
        help=(
            "Only output to console, do not save files. "
            "At Level 2: trade-level rows are printed only if this flag is set; "
            "without it, trade details are suppressed in console and only written to file. "
            "Default: False (saves results)."
        ),
    )
    # Removed CLI args: --min-grade, --breakout-tier
    parser.add_argument(
        "--last-days",
        type=int,
        help=(
            "Convenience: set start/end to cover the last N calendar days "
            "(overrides --start/--end)"
        ),
    )
    parser.add_argument(
        "--one-per-day",
        action="store_true",
        default=False,
        help=(
            "If set, the Markdown trade summary groups to one trade per calendar day "
            "(earliest entry). "
            "Default: disabled (all trades listed)."
        ),
    )
    parser.add_argument(
        "--level",
        type=int,
        default=0,
        choices=[0, 1, 2, 3, 4, 5],
        help=(
            "Pipeline level (0-5, default: 0): "
            "Level 0: Candidates only (Stages 1-3: OR, Breakout, Retest), no trades. "
            "Level 1: Trades with base criteria (Stages 1-3), entry on open after retest. "
            "Level 2: Quality filter - Require C or better in each component (reject D-grades). "
            "Level 3: Stricter filtering - Require C or better in each component "
            "and overall grade B or higher."
        ),
    )
    parser.add_argument(
        "--grading-system",
        choices=["points"],
        default="points",
        help="Grading system (default: points - 100-point scoring system)",
    )
    parser.add_argument(
        "--no-trades",
        action="store_true",
        default=False,
        help=(
            "For Level 1+: identify candidates without executing trades. "
            "Level 0 always runs in no-trades mode."
        ),
    )

    # Add config override support via utility function
    add_config_override_argument(parser)

    args = parser.parse_args()

    # Apply config overrides from command line via utility function
    apply_config_overrides(CONFIG, args.config_override or [])

    # Update config-derived options and feature flags after overrides
    global FEATURE_LEVEL0_ENABLE_VWAP_CHECK
    FEATURE_LEVEL0_ENABLE_VWAP_CHECK = CONFIG.get(
        "feature_level0_enable_vwap_check",
        FEATURE_LEVEL0_ENABLE_VWAP_CHECK,
    )

    # Runtime values resolved from CONFIG (do not mutate module-level defaults here)
    runtime_results_dir = CONFIG.get("backtest_results_dir", DEFAULT_RESULTS_DIR)
    runtime_retest_vol_gate = CONFIG.get("retest_volume_gate_ratio", RETEST_VOL_GATE)
    min_rr_ratio = CONFIG.get("min_rr_ratio", 2.0)

    # If leverage wasn't explicitly provided, allow config override to drive it
    if "--leverage" not in sys.argv and "leverage" in CONFIG:
        args.leverage = float(CONFIG["leverage"])

    # Use default tickers from config if not specified
    symbols = args.symbols if args.symbols else CONFIG.get("tickers", DEFAULT_TICKERS)

    # Determine date range
    start_date = args.start
    end_date = args.end
    if args.last_days and args.last_days > 0:
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        start_dt = datetime.utcnow() - timedelta(days=args.last_days)
        start_date = start_dt.strftime("%Y-%m-%d")

    # Validate date range
    if not start_date or not end_date:
        parser.error("Either provide --start and --end, or use --last-days N")

    pipeline_level = args.level

    print(f"Backtesting symbols: {', '.join(symbols)}")
    print(f"Date range: {start_date} to {end_date}")
    effective_initial_capital = (
        args.initial_capital
        if args.initial_capital is not None
        else float(CONFIG.get("initial_capital", DEFAULT_INITIAL_CAPITAL))
    )
    print(f"Initial capital: ${effective_initial_capital:,.2f}")
    print(f"Leverage: {args.leverage}x")
    print(f"Pipeline Level: {pipeline_level}")
    if args.no_trades and pipeline_level > 0:
        print("Mode: Candidates only (no trades)")
    print()

    # Initialize components
    cache = DataCache(args.cache_dir)

    # Clear cache if force refresh is requested
    if args.force_refresh:
        cache.clear_cache()

    # Resolve display timezone from central config
    display_tz, tz_label = get_display_timezone(Path(__file__).parent)

    engine = BacktestEngine(
        initial_capital=effective_initial_capital,
        position_size_pct=args.position_size,
        leverage=args.leverage,
        display_tzinfo=display_tz,
        tz_label=tz_label,
        retest_vol_threshold=runtime_retest_vol_gate,
        pipeline_level=pipeline_level,
        no_trades=args.no_trades,
        grading_system=args.grading_system,
        min_rr_ratio=min_rr_ratio,
        console_only=args.console_only,
    )

    results = []

    # Run cache integrity check for the requested symbols/date range before processing
    if CONFIG.get("feature_cache_check_integrity", False):
        try:
            ic_summary = integrity_check_range(
                cache_dir=Path(args.cache_dir),
                symbols=symbols,
                start_date=start_date,
                end_date=end_date,
                intervals=["1m", "5m"],
                cross_interval=True,
                skip_weekends=True,
            )
            print(
                "Cache integrity (requested range): "
                f"checked={ic_summary.get('checked_files')} errors={ic_summary.get('errors')} "
                f"warnings={ic_summary.get('warnings')} missing={ic_summary.get('missing_files')}"
            )
        except Exception as e:
            print(f"Cache integrity check skipped due to error: {e}")
    else:
        print("Cache integrity check disabled (feature_cache_check_integrity=false)")

    # Run backtest for each symbol
    for symbol in symbols:
        print(f"\n{'='*60}")
        print(f"Backtesting {symbol}")
        print(f"{'='*60}")

        # Download/load 5-minute data
        print("Downloading 5-minute data...")
        df_5m = cache.download_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval="5m",
        )

        if df_5m.empty:
            print(f"No 5-minute data available for {symbol}")
            continue

        print(f"Loaded {len(df_5m)} 5-minute bars for {symbol}")
        print("Note: 1-minute data will be loaded on-demand when breakouts are detected")

        # Run backtest with on-demand 1m loading
        result = engine.run_backtest(symbol, df_5m, cache_dir=args.cache_dir)
        results.append(result)

    # Display results
    print(format_results(results))

    # Generate Markdown trade summary (controlled by --one-per-day flag; default: all entries)
    md_summary = generate_markdown_trade_summary(
        results, tzinfo=display_tz, tz_label=tz_label, one_per_day=args.one_per_day
    )

    # Level 2 trade-level console logging rule:
    # - If --console-only provided: print trade summary (current behavior)
    # - Else (saving to file): suppress trade-level rows (still save them to file below)
    if not (pipeline_level == 2 and not args.console_only):
        print(md_summary)
    else:
        # Provide a compact notice so users know trades were captured and where to find them
        suppression_msg = (
            "\n[Level 2] Trade details suppressed (use --console-only to display). "
            "Will be saved to file.\n"
        )
        print(suppression_msg)

    # Save results by default unless --console-only is specified
    if not args.console_only:
        # Create backtest_results directory if it doesn't exist
        results_dir = Path(runtime_results_dir)
        results_dir.mkdir(exist_ok=True)

        # Always include a timestamp suffix in the configured timezone to ensure unique filenames
        now_local = datetime.now(tz=display_tz)
        # Use ISO 8601 format with timezone (sanitized for filename)
        ts_iso = now_local.isoformat(timespec="seconds")
        # Replace colons and plus signs for filesystem compatibility
        ts_str = ts_iso.replace(":", "").replace("+", "")

        # Generate filename (append timestamp for both auto and user-provided names)
        if args.output:
            # Preserve user-provided name but append timestamp before extension if not present
            user_path = Path(args.output)
            stem = user_path.stem
            suffix = user_path.suffix  # includes leading dot or empty
            # Avoid double-appending if a timestamp suffix already exists in the stem
            # Updated pattern to match ISO format: _YYYY-MM-DDTHHMMSS-HHMM or _YYYYMMDD_HHMMSS
            if not re.search(r"_\d{4}-\d{2}-\d{2}T\d{6}-\d{4}$", stem) and not re.search(
                r"_\d{8}_\d{6}$", stem
            ):
                stem = f"{stem}_{ts_str}"
            output_filename = f"{stem}{suffix}"
        else:
            # Auto-generate filename based on parameters
            symbols_str = "_".join(symbols) if len(symbols) <= 3 else "ALL"
            start_str = start_date.replace("-", "")
            end_str = end_date.replace("-", "")
            level_str = f"level{args.level}"
            grading_str = args.grading_system
            output_filename = (
                f"{level_str}_{symbols_str}_{start_str}_{end_str}_{grading_str}_{ts_str}.json"
            )

        # Construct output path in backtest_results directory
        output_path = results_dir / output_filename

        # Convert datetime fields to configured timezone for JSON output
        results_local = _convert_times_to_timezone(results, display_tz, tz_label)
        with open(output_path, "w") as f:
            json.dump(results_local, f, indent=2)
        print(f"Results saved to {output_path}")

        # Also save Markdown summary next to JSON
        md_path = output_path.with_suffix("")
        md_path = md_path.with_name(md_path.name + "_summary.md")
        with open(md_path, "w") as f:
            f.write(md_summary + "\n")
        print(f"Summary saved to {md_path}")


if __name__ == "__main__":
    main()
