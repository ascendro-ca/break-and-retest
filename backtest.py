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
import time  # Added for runtime measurement
from collections import OrderedDict

import pandas as pd
import numpy as np
# Note: yfinance provider removed; keep import out to avoid unused import lint

from cache_utils import (
    get_cache_path,
    load_cached_day,
    save_day,
    integrity_check_range,
)
from config_utils import load_config, add_config_override_argument, apply_config_overrides
from grading.profile_loader import load_profile
from grading.breakout_grader import grade_breakout as profile_grade_breakout
from grading.retest_grader import grade_retest as profile_grade_retest
from grading.ignition_grader import grade_ignition as profile_grade_ignition
from grading.breakout_grader import score_breakout_details
from grading.retest_grader import score_retest
from grading.ignition_grader import score_ignition
from grading.trend_grader import score_trend

# Removed unused module-level imports of grader modules; scoring functions already imported.
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
BREAKOUT_B_BODY_MAX = CONFIG.get("breakout_B_body_max", 0.65)
RETEST_B_EPSILON = CONFIG.get("retest_B_level_epsilon_pct", 0.10)
RETEST_B_SOFT = CONFIG.get("retest_B_structure_soft", True)
# Deprecated grade filtering feature flags (feature_grade_[c|b|a|aplus]_filtering_enable) and
# points thresholds were removed as part of grading simplification. Profiles are now
# name-only shells; all Level 2 signals pass through without gating. Retest A+ evaluation
# previously retained for analytics has been removed to eliminate duplication; rely on
# retest grading and points instead.


class DataCache:
    """Manages cached OHLCV data organized by symbol and date"""

    def __init__(self, cache_dir: str = "cache", max_mem_items: int = 256):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        # Simple in-memory LRU to avoid repeated disk reads for the same (symbol, date, interval)
        self._mem: "OrderedDict[tuple, Optional[pd.DataFrame]]" = OrderedDict()
        self._mem_max = int(max_mem_items)

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
        """Load cached data using on-disk cache with an in-memory LRU layer."""
        key = (symbol, date, interval)
        if key in self._mem:
            # Move to end (recently used) and return
            df = self._mem.pop(key)
            self._mem[key] = df
            return df
        df = load_cached_day(self.cache_dir, symbol, date, interval)
        # Insert into LRU and evict oldest if needed
        self._mem[key] = df
        if len(self._mem) > self._mem_max:
            self._mem.popitem(last=False)
        return df

    def cache_data(self, symbol: str, date: str, interval: str, df: pd.DataFrame):
        """Save data to cache"""
        save_day(self.cache_dir, symbol, date, interval, df)
        # Update in-memory cache as well
        key = (symbol, date, interval)
        self._mem[key] = df
        if len(self._mem) > self._mem_max:
            self._mem.popitem(last=False)

    def download_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "5m",
    ) -> pd.DataFrame:
        """Load OHLCV data for a symbol and date range from local cache only.

        Cache must be pre-populated using the StockData.org retriever (stockdata_retriever.py).
        No live downloads are performed here.
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
        risk_pct_per_trade: Optional[float] = None,
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
            risk_pct_per_trade: Percentage of capital risked per trade (e.g. 0.005 = 0.5%).
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
        # Determine effective risk percent per trade
        provided_val = risk_pct_per_trade if risk_pct_per_trade is not None else 0.005

        # Normalize and clamp input:
        # - Accept fractional (e.g., 0.005 = 0.5%)
        # - If user passes a value > 1, interpret as percent (e.g., 2 -> 2% = 0.02)
        try:
            _ps = float(provided_val)
        except Exception:
            _ps = 0.005
        if _ps > 1.0:
            _ps = _ps / 100.0
        # Clamp to [0, 1]
        _ps = max(0.0, min(_ps, 1.0))
        # Canonical attribute
        self.risk_pct_per_trade = _ps
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
        # Profile-based grading (simplified). Points grader removed.
        self.grade_profile_name = None
        self.grade_profile = None
        # Removed points-based continuation grader; use profile ignition metrics only
        self.grader = None
        # Cache configuration (set during run_backtest). A shared DataCache with in-memory LRU
        # is created lazily in run_backtest so tests can override cache_dir per invocation.
        self.cache_dir = "cache"
        self.data_cache: Optional[DataCache] = None

    def _load_1m_window(
        self, symbol: str, center_time: pd.Timestamp, window_minutes: int = 90
    ) -> pd.DataFrame:
        """Deprecated helper retained for backward compatibility; now delegates to warmed sessions.

        We keep this method to avoid breaking external references, but the performance path
        reuses the preloaded per‑day session data (with prior-day tail) rather than reloading
        overlapping windows per trade. If needed (e.g., spanning multiple days), we still fall
        back to the original multi-day load logic.
        """
        cache = self.data_cache or DataCache(self.cache_dir)
        start_time = center_time - timedelta(minutes=window_minutes)
        end_time = center_time + timedelta(minutes=window_minutes)
        current = start_time.date()
        end_date = end_time.date()
        dates_needed: List[date] = []
        while current <= end_date:
            if current.weekday() < 5:
                dates_needed.append(current)
            current += timedelta(days=1)
        dfs: List[pd.DataFrame] = []
        for current_date in dates_needed:
            date_str = current_date.strftime("%Y-%m-%d")
            cached = cache.get_cached_data(symbol, date_str, "1m")
            if cached is not None and not cached.empty:
                dfs.append(cached)
        if not dfs:
            return pd.DataFrame()
        df = pd.concat(dfs, ignore_index=True)
        df["Datetime"] = pd.to_datetime(df["Datetime"], utc=True)
        df = df.sort_values("Datetime").reset_index(drop=True)
        return df[(df["Datetime"] >= start_time) & (df["Datetime"] <= end_time)]

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
        # Ensure a shared DataCache exists (with LRU) for this engine instance
        if self.data_cache is None:
            self.data_cache = DataCache(self.cache_dir)

        # Ensure 20-bar volume MA on 5-minute data (for breakout volume ratio)
        df_5m = df_5m.copy()
        if "vol_ma_20" not in df_5m.columns:
            df_5m["Volume"] = pd.to_numeric(df_5m["Volume"], errors="coerce")
            df_5m["vol_ma_20"] = df_5m["Volume"].rolling(window=20, min_periods=20).mean()
        df_5m["Date"] = df_5m["Datetime"].dt.date

        trading_days = df_5m["Date"].unique()

        def _get_or_preload_session_1m(day: date) -> pd.DataFrame:
            """Load today's 1m session warmed with prior day's tail to compute vol_ma_20."""
            key = (symbol, day)
            if hasattr(self, "_session_1m_by_day") and key in self._session_1m_by_day:
                return self._session_1m_by_day[key]
            cache_local = self.data_cache or DataCache(self.cache_dir)
            # Load today's session
            day_str = day.strftime("%Y-%m-%d")
            today_df = cache_local.get_cached_data(symbol, day_str, "1m")
            if today_df is None or today_df.empty:
                warmed = pd.DataFrame()
                if hasattr(self, "_session_1m_by_day"):
                    self._session_1m_by_day[key] = warmed
                return warmed
            df1 = today_df.copy()
            df1["Datetime"] = pd.to_datetime(df1["Datetime"], errors="coerce")
            if getattr(df1["Datetime"].dt, "tz", None) is None:
                df1["Datetime"] = df1["Datetime"].dt.tz_localize("UTC")
            # Restrict to regular session in UTC using ET anchors
            try:
                et_tz = ZoneInfo("America/New_York")
            except Exception:
                et_tz = None
            if et_tz is not None and not df1.empty:
                et_local = df1["Datetime"].dt.tz_convert(et_tz)
                sess_date_et = et_local.iloc[0].date()
                open_et = datetime.combine(sess_date_et, datetime.min.time()).replace(
                    hour=9, minute=30, tzinfo=et_tz
                )
                close_et = datetime.combine(sess_date_et, datetime.min.time()).replace(
                    hour=16, minute=0, tzinfo=et_tz
                )
                open_utc = open_et.astimezone(ZoneInfo("UTC"))
                close_utc = close_et.astimezone(ZoneInfo("UTC"))
                df1 = df1[(df1["Datetime"] >= open_utc) & (df1["Datetime"] < close_utc)].copy()

            # Previous trading day tail for warm-up
            prev = day - timedelta(days=1)
            while prev.weekday() >= 5:
                prev -= timedelta(days=1)
            prev_str = prev.strftime("%Y-%m-%d")
            prev_df = cache_local.get_cached_data(symbol, prev_str, "1m")
            tail = None
            if prev_df is not None and not prev_df.empty:
                prev_df = prev_df.copy()
                prev_df["Datetime"] = pd.to_datetime(prev_df["Datetime"], errors="coerce")
                if getattr(prev_df["Datetime"].dt, "tz", None) is None:
                    prev_df["Datetime"] = prev_df["Datetime"].dt.tz_localize("UTC")
                tail = prev_df.sort_values("Datetime").tail(30)
            if tail is not None and not tail.empty:
                work = pd.concat([tail, df1], ignore_index=True)
            else:
                work = df1.copy()
            # Compute warmed 1m vol_ma_20 and vwap
            work["Volume"] = pd.to_numeric(work["Volume"], errors="coerce")
            work["vol_ma_20"] = work["Volume"].rolling(window=20, min_periods=20).mean()
            work["typical_price"] = (work["High"] + work["Low"] + work["Close"]) / 3
            work["tp_volume"] = work["typical_price"] * work["Volume"]
            work["vwap"] = work["tp_volume"].cumsum() / work["Volume"].cumsum()
            if tail is not None and not tail.empty:
                work = work.iloc[len(tail) :].copy()
            work = work.sort_values("Datetime").reset_index(drop=True)
            if not hasattr(self, "_session_1m_by_day"):
                self._session_1m_by_day = {}
            self._session_1m_by_day[key] = work
            return work

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
                # Timestamps are enforced tz-aware UTC; convert directly to ET for session slicing
                local_et = day_df_5m["Datetime"].dt.tz_convert(et_tz)
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
                    # Convert to ET (tz-aware)
                    first_bar_et = fb.astimezone(et_tz)
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
            # Time index for fast lookups later
            if session_df_5m.index.name != "Datetime":
                session_df_5m = session_df_5m.sort_values("Datetime")
                session_df_5m = session_df_5m.set_index("Datetime", drop=False)
            times_5m = session_df_5m.index.values

            # Scan only the configured first N minutes of 5-minute data for
            # breakouts. Default remains 90 if not present in CONFIG.
            market_open_minutes = int(CONFIG.get("market_open_minutes", 90))
            # Anchor breakout scan to the *expected* session open instead of
            # the first available (which may be mid‑session on truncated days).
            # Expected open (5m bar label) ~09:35 ET; we'll anchor at 09:30 ET
            # and still allow the pipeline to define OR from the first bar we pass.
            if et_tz is not None:
                sess_date_et = first_bar_et.date() if first_bar_et else day
                expected_open_et = datetime.combine(sess_date_et, datetime.min.time()).replace(
                    hour=9, minute=30, tzinfo=et_tz
                )
                expected_open_utc = expected_open_et.astimezone(ZoneInfo("UTC"))
                end_time = expected_open_utc + timedelta(minutes=market_open_minutes)
                # Ensure session_df_5m Datetime is UTC-aware for comparison
                session_df_5m["Datetime"] = session_df_5m["Datetime"].dt.tz_convert(ZoneInfo("UTC"))
                scan_df_5m = session_df_5m[
                    (session_df_5m["Datetime"] >= expected_open_utc)
                    & (session_df_5m["Datetime"] < end_time)
                ].copy()
            if len(scan_df_5m) < 10:
                continue

            # Prepare warmed 1m session
            if getattr(self, "_inline_df_1m", None) is not None:
                # Inline 1m already UTC-aware; slice regular session (09:30-16:00 ET in UTC)
                df1 = self._inline_df_1m.copy()  # type: ignore[attr-defined]
                et_tz = ZoneInfo("America/New_York")
                open_et = datetime.combine(day, datetime.min.time()).replace(
                    hour=9, minute=30, tzinfo=et_tz
                )
                close_et = datetime.combine(day, datetime.min.time()).replace(
                    hour=16, minute=0, tzinfo=et_tz
                )
                open_utc = open_et.astimezone(ZoneInfo("UTC"))
                close_utc = close_et.astimezone(ZoneInfo("UTC"))
                session_df_1m = df1[
                    (df1["Datetime"] >= open_utc) & (df1["Datetime"] < close_utc)
                ].copy()
                session_df_1m = session_df_1m.sort_values("Datetime")
                session_df_1m["Volume"] = pd.to_numeric(session_df_1m["Volume"], errors="coerce")
                session_df_1m["vol_ma_20"] = (
                    session_df_1m["Volume"].rolling(window=20, min_periods=20).mean()
                )
                session_df_1m["typical_price"] = (
                    session_df_1m["High"] + session_df_1m["Low"] + session_df_1m["Close"]
                ) / 3
                session_df_1m["tp_volume"] = (
                    session_df_1m["typical_price"] * session_df_1m["Volume"]
                )
                session_df_1m["vwap"] = (
                    session_df_1m["tp_volume"].cumsum() / session_df_1m["Volume"].cumsum()
                )
            else:
                session_df_1m = _get_or_preload_session_1m(day)

            if session_df_1m.empty or len(session_df_1m) < 50:
                # No 1m data available for this day, skip
                continue

            # Ensure time index and cache arrays for fast lookups
            if session_df_1m.index.name != "Datetime":
                session_df_1m = session_df_1m.sort_values("Datetime")
                session_df_1m = session_df_1m.set_index("Datetime", drop=False)
            times_1m = session_df_1m.index.values
            close_1m = session_df_1m["Close"].to_numpy(dtype=float, copy=False)
            volma20_1m = session_df_1m.get(
                "vol_ma_20", pd.Series(index=session_df_1m.index)
            ).to_numpy(dtype=float, copy=False)
            vwap_1m = session_df_1m.get("vwap", pd.Series(index=session_df_1m.index)).to_numpy(
                dtype=float, copy=False
            )

            # Helper utilities
            def _ts64(ts):
                t = pd.to_datetime(ts)
                return t.to_datetime64()

            def first_index_after(times, ts):
                return int(times.searchsorted(_ts64(ts), side="right"))

            def lookup_col_at(df, ts, col, times, arr):
                try:
                    val = df.loc[ts, col]
                    if isinstance(val, pd.Series):
                        val = val.iloc[0]
                    return float(val)
                except Exception:
                    try:
                        pos = times.searchsorted(_ts64(ts))
                        if 0 <= pos < len(times) and times[pos] == _ts64(ts):
                            return float(arr[pos])
                    except Exception:
                        pass
                return None

            if self.pipeline_level == 0:
                # Level 0: Base pipeline - Delegate Stage 1-3 detection to shared pipeline
                # (Ignition detection disabled at Level 0)
                # Level 0 now uses level0_retest_filter for retest detection (body at/beyond OR)
                df5_for_pipeline = scan_df_5m.copy()
                df5_for_pipeline.index.name = None
                df1_for_pipeline = session_df_1m.copy()
                df1_for_pipeline.index.name = None
                candidates = run_pipeline(
                    session_df_5m=df5_for_pipeline,
                    session_df_1m=df1_for_pipeline,
                    breakout_window_minutes=market_open_minutes,
                    retest_lookahead_minutes=30,
                    pipeline_level=0,
                    enable_vwap_check=False,  # VWAP check disabled for Level 0
                )

                for c in candidates:
                    breakout_candle = c.get("breakout_candle", {})
                    retest_candle = c.get("retest_candle", {})
                    # Attach VWAP snapshots when possible
                    try:
                        bt = pd.to_datetime(c.get("breakout_time"))
                        vwap5_val = (
                            lookup_col_at(
                                session_df_5m,
                                bt,
                                "vwap",
                                times_5m,
                                session_df_5m["vwap"].to_numpy(),
                            )
                            if not session_df_5m.empty
                            else None
                        )
                        if hasattr(breakout_candle, "__setitem__"):
                            breakout_candle["vwap"] = vwap5_val
                    except Exception:
                        pass
                    try:
                        rt = pd.to_datetime(c.get("retest_time"))
                        vwap1_val = (
                            lookup_col_at(session_df_1m, rt, "vwap", times_1m, vwap_1m)
                            if not session_df_1m.empty
                            else None
                        )
                        if hasattr(retest_candle, "__setitem__"):
                            retest_candle["vwap"] = vwap1_val
                    except Exception:
                        pass
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
                                "vwap": breakout_candle.get("vwap")
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
                                "vwap": retest_candle.get("vwap")
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

            df5_for_pipeline = scan_df_5m.copy()
            df5_for_pipeline.index.name = None
            df1_for_pipeline = session_df_1m.copy()
            df1_for_pipeline.index.name = None
            pipeline_candidates = run_pipeline(
                session_df_5m=df5_for_pipeline,
                session_df_1m=df1_for_pipeline,
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

                # Attach VWAP snapshots to the OHLC dicts for trend grading
                try:
                    if hasattr(breakout_candle, "__setitem__") and not session_df_5m.empty:
                        vwap5_val = lookup_col_at(
                            session_df_5m,
                            breakout_time,
                            "vwap",
                            times_5m,
                            session_df_5m["vwap"].to_numpy(),
                        )
                        breakout_candle["vwap"] = vwap5_val
                except Exception:
                    pass
                try:
                    if hasattr(retest_candle, "__setitem__") and not session_df_1m.empty:
                        vwap1_val = lookup_col_at(
                            session_df_1m,
                            retest_time,
                            "vwap",
                            times_1m,
                            vwap_1m,
                        )
                        retest_candle["vwap"] = vwap1_val
                except Exception:
                    pass

                # Level 2+: Entry at ignition (Stage 4); Level 1: Entry at next bar after retest
                ignition_bar = None  # We'll always try to capture an ignition candle for analytics
                if self.pipeline_level >= 2:
                    # Entry logic at Level 2 (parity with Level 1):
                    # require the first 1m close beyond the retest close,
                    # then enter on the open of the next bar. Ignition is
                    # attached for analytics only (not gating) for all
                    # name-only profiles (c, b, a, aplus).
                    if self.grade_profile_name in {
                        "c",
                        "b",
                        "a",
                        "aplus",
                    }:
                        retest_close = float(retest_candle.get("Close", 0.0))
                        breakout_up = direction == "long"
                        start_idx = first_index_after(times_1m, retest_time)
                        slice_closes = close_1m[start_idx:]
                        cond = (
                            slice_closes > retest_close
                            if breakout_up
                            else slice_closes < retest_close
                        )
                        ignition_idx = None
                        if cond.size and cond.any():
                            ignition_idx = int(start_idx + int(np.argmax(cond)))
                        if ignition_idx is None:
                            continue
                        ignition_time = session_df_1m.iloc[ignition_idx]["Datetime"]
                        ignition_bar = session_df_1m.iloc[ignition_idx]
                        if ignition_idx + 1 >= len(session_df_1m):
                            continue
                        entry_bar = session_df_1m.iloc[ignition_idx + 1]
                        entry_time = entry_bar["Datetime"]
                        entry = float(entry_bar.get("Open"))
                    else:
                        # Non-Grade-C profiles: require ignition (Stage 4) as usual
                        ignition_time_raw = cand.get("ignition_time")
                        if not ignition_time_raw:
                            continue
                        ignition_time = pd.to_datetime(ignition_time_raw)
                        # Find the 1m bar immediately after the ignition candle for entry
                        next_bars = session_df_1m[session_df_1m["Datetime"] > ignition_time]
                        if next_bars.empty:
                            continue
                        entry_bar = next_bars.iloc[0]
                        entry_time = entry_bar["Datetime"]
                        entry = float(entry_bar.get("Open"))
                        # For unified schema capture the actual ignition bar
                        # (prefer pipeline-provided if present)
                        ignition_bar = session_df_1m[session_df_1m["Datetime"] == ignition_time]
                        if not ignition_bar.empty:
                            ignition_bar = ignition_bar.iloc[0]
                        else:
                            ignition_bar = None
                else:
                    # Level 1: Wait for first 1m candle after retest that closes above
                    # (long) or below (short) retest close, then enter on open of next candle
                    retest_close = float(retest_candle.get("Close", 0.0))
                    ignition_idx = None
                    breakout_up = direction == "long"
                    start_idx = first_index_after(times_1m, retest_time)
                    slice_closes = close_1m[start_idx:]
                    cond = (
                        slice_closes > retest_close if breakout_up else slice_closes < retest_close
                    )
                    if cond.size and cond.any():
                        ignition_idx = int(start_idx + int(np.argmax(cond)))
                    if ignition_idx is None:
                        continue  # No ignition found, skip
                    ignition_time = session_df_1m.iloc[ignition_idx]["Datetime"]
                    ignition_bar = session_df_1m.iloc[ignition_idx]
                    if ignition_idx + 1 >= len(session_df_1m):
                        continue
                    entry_bar = session_df_1m.iloc[ignition_idx + 1]
                    entry_time = entry_bar["Datetime"]
                    entry = float(entry_bar.get("Open"))

                # CRITICAL: Only enter trades within the configured first
                # market_open_minutes window. Normalize to UTC-aware for comparison.
                try:
                    if getattr(entry_time, "tzinfo", None) is None and et_tz is not None:
                        entry_time_cmp = entry_time.tz_localize(et_tz).tz_convert(ZoneInfo("UTC"))
                    elif getattr(entry_time, "tzinfo", None) is not None:
                        entry_time_cmp = entry_time.tz_convert(ZoneInfo("UTC"))
                    else:
                        entry_time_cmp = entry_time
                    end_time_cmp = end_time
                except Exception:
                    entry_time_cmp = entry_time
                    end_time_cmp = end_time
                if entry_time_cmp >= end_time_cmp:
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
                                session_df_5m["Datetime"] == breakout_time, "vol_ma_20"
                            ].iloc[0]
                        ),
                        1e-9,
                    )
                except Exception:
                    breakout_vol_ratio = 0.0
                # Retest volume ratio vs 1m vol_ma_20
                try:
                    retest_ma = lookup_col_at(
                        session_df_1m, retest_time, "vol_ma_20", times_1m, volma20_1m
                    )
                    retest_vol_ratio = float(retest_candle["Volume"]) / max(
                        float(retest_ma or 0.0), 1e-9
                    )
                except Exception:
                    retest_ma = None
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
                    # Preserve retest timing for grading
                    "retest_time": retest_time,
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
                        # 1m ignition volume ratio vs vol_ma_20 at ignition time
                        try:
                            ign_ma = lookup_col_at(
                                session_df_1m,
                                ign_source.get("Datetime") or ignition_time,
                                "vol_ma_20",
                                times_1m,
                                volma20_1m,
                            )
                        except Exception:
                            ign_ma = None
                        ignition_vol_ratio = (
                            float(ign_vol) / float(ign_ma) if ign_ma and float(ign_ma) > 0 else 0.0
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

        # Normalize df_5m to UTC tz-aware; interpret tz-naive as ET then convert to UTC
        try:
            df_5m = df_5m.copy()
            df_5m["Datetime"] = pd.to_datetime(df_5m["Datetime"], errors="coerce")
            if getattr(df_5m["Datetime"].dt, "tz", None) is None:
                et_tz = ZoneInfo("America/New_York")
                df_5m["Datetime"] = (
                    df_5m["Datetime"].dt.tz_localize(et_tz).dt.tz_convert(ZoneInfo("UTC"))
                )
            else:
                df_5m["Datetime"] = df_5m["Datetime"].dt.tz_convert(ZoneInfo("UTC"))
        except Exception:
            pass

        # Normalize inline 1m to UTC tz-aware if provided; interpret tz-naive as ET
        if inline_1m is not None:
            try:
                inline_1m = inline_1m.copy()
                inline_1m["Datetime"] = pd.to_datetime(inline_1m["Datetime"], errors="coerce")
                if getattr(inline_1m["Datetime"].dt, "tz", None) is None:
                    et_tz = ZoneInfo("America/New_York")
                    inline_1m["Datetime"] = (
                        inline_1m["Datetime"].dt.tz_localize(et_tz).dt.tz_convert(ZoneInfo("UTC"))
                    )
                else:
                    inline_1m["Datetime"] = inline_1m["Datetime"].dt.tz_convert(ZoneInfo("UTC"))
            except Exception:
                pass

        # Guards: enforce tz-aware (UTC) after normalization
        try:
            if getattr(df_5m["Datetime"].dt, "tz", None) is None:
                raise ValueError("df_5m.Datetime must be tz-aware (UTC)")
            if inline_1m is not None and getattr(inline_1m["Datetime"].dt, "tz", None) is None:
                raise ValueError("inline 1m Datetime must be tz-aware (UTC)")
        except Exception:
            pass

        # Stash inline 1m for the scan (used when provided by tests)
        self._inline_df_1m = inline_1m
        # Initialize shared DataCache (once) for performance improvements 1 & 2
        if self.data_cache is None:
            self.data_cache = DataCache(selected_cache_dir)

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

        # Ensure default grade profile 'c' loaded for analytics and default filtering
        if self.pipeline_level == 2 and self.grade_profile is None:
            try:
                self.grade_profile_name = "c"
                self.grade_profile = load_profile("c")
            except Exception:
                self.grade_profile_name = None
                self.grade_profile = None

        # Minimal analytics grading for Level 1 & 2: attach component_grades and overall_grade
        def attach_basic_grades(sig: Dict) -> Dict:
            # RR symbol mapping (match legacy thresholds)
            entry = sig.get("entry")
            stop = sig.get("stop")
            target = sig.get("target")
            try:
                rr_ratio = abs(target - entry) / abs(entry - stop) if entry != stop else 0.0
            except Exception:
                rr_ratio = 0.0
            rr_symbol = "✅" if rr_ratio >= 2.0 else ("⚠️" if rr_ratio >= 1.5 else "❌")

            # Breakout/retest pass using C profile for analytics
            prof = self.grade_profile or load_profile("c")
            bo_ok, _ = profile_grade_breakout(
                sig.get("breakout_candle", {}), sig.get("breakout_vol_ratio", 0.0), prof
            )
            rt_ok, _ = profile_grade_retest(
                sig.get("retest_candle", {}),
                level=float(sig.get("level", 0.0)),
                direction=str(sig.get("direction", "long")),
                breakout_time=sig.get("breakout_time_5m"),
                retest_time=sig.get("retest_time"),
                breakout_volume=float(sig.get("vol_breakout_5m", 0.0)),
                retest_volume=float(sig.get("vol_retest_1m", 0.0)),
                breakout_candle=sig.get("breakout_candle", {}),
                profile=prof,
            )
            sig["component_grades"] = {
                "breakout": "✅" if bo_ok else "❌",
                "retest": "✅" if rt_ok else "❌",
                "rr": rr_symbol,
                "market": "⚠️",
            }
            # Legacy compatibility: provide breakout_tier (was A/B/C previously)
            # Using fixed 'C' when breakout passes under default profile; 'none' otherwise.
            sig["breakout_tier"] = "C" if bo_ok else "none"
            sig["overall_grade"] = {"aplus": "A+", "a": "A", "b": "B", "c": "C"}.get(
                self.grade_profile_name or "c", "C"
            )
            sig["rr_ratio"] = rr_ratio
            # A+ retest legacy analytics removed; rely on core retest grading & points.
            # --------------------------------------------------
            # Points-based scoring (stub) – no filtering applied
            # --------------------------------------------------
            breakout_details = {}
            try:
                breakout_details = score_breakout_details(
                    sig.get("breakout_candle", {}),
                    sig.get("breakout_vol_ratio", 0.0),
                    prof,
                    direction=str(sig.get("direction", None)),
                )
                breakout_pts = int(breakout_details.get("total", 0))
            except Exception:
                breakout_pts = 0
            try:
                retest_pts = score_retest(
                    sig.get("retest_candle", {}),
                    level=float(sig.get("level", 0.0)),
                    direction=str(sig.get("direction", "long")),
                    breakout_time=sig.get("breakout_time_5m"),
                    retest_time=sig.get("retest_time"),
                    breakout_volume=float(sig.get("vol_breakout_5m", 0.0)),
                    retest_volume=float(sig.get("vol_retest_1m", 0.0)),
                    breakout_candle=sig.get("breakout_candle", {}),
                    profile=prof,
                )
            except Exception:
                retest_pts = 0
            try:
                ignition_pts = score_ignition(
                    sig.get("ignition_candle", {}),
                    ignition_body_pct=float(sig.get("ignition_body_pct", 0.0)),
                    ignition_vol_ratio=float(sig.get("ignition_vol_ratio", 0.0)),
                    progress=float(sig.get("distance_to_target", 0.0)),
                    profile=prof,
                )
            except Exception:
                ignition_pts = 0
            try:
                trend_pts = score_trend(sig, prof)
            except Exception:
                trend_pts = 0
            total_points = breakout_pts + retest_pts + ignition_pts + trend_pts
            # Letter mapping (aligned with GRADING_SYSTEMS.md)
            # 95–100 A+, 86–94 A, 70–85 B, 56–69 C, <55 D
            if total_points >= 95:
                points_letter = "A+"
            elif total_points >= 86:
                points_letter = "A"
            elif total_points >= 70:
                points_letter = "B"
            elif total_points >= 56:
                points_letter = "C"
            else:
                points_letter = "D"
            sig["points"] = {
                "breakout": breakout_pts,
                "retest": retest_pts,
                "ignition": ignition_pts,
                "trend": trend_pts,
                "total": total_points,
                "letter": points_letter,
                "breakout_pattern_pts": breakout_details.get("pattern_pts"),
                "breakout_volume_pts": breakout_details.get("volume_pts"),
                "breakout_ctype": breakout_details.get("ctype"),
                "breakout_body_pct": breakout_details.get("body_pct"),
                "breakout_upper_wick_pct": breakout_details.get("upper_wick_pct"),
                "breakout_lower_wick_pct": breakout_details.get("lower_wick_pct"),
            }
            return sig

        graded_signals = [attach_basic_grades(dict(sig)) for sig in signals]

        # Legacy rejection counters removed (no longer used)

        # Level 2: Apply selected grade profile and enforce total points threshold per --grade
        pre_filter_count = len(graded_signals) if self.pipeline_level == 2 else 0
        if self.pipeline_level == 2 and self.grade_profile is not None:
            profile_name = self.grade_profile.get("name", "unknown")
            # Name-only profiles: stage checks pass, but we now gate by total points threshold
            for s in graded_signals:
                s["grade_profile"] = profile_name
                s["stage_results"] = {
                    "breakout": {"pass": True, "reason": "profile_shell"},
                    "retest": {"pass": True, "reason": "profile_shell"},
                    "ignition": {"pass": True, "reason": "profile_shell"},
                }
                mapping = {"aplus": "A+", "a": "A", "b": "B", "c": "C"}
                s["overall_grade"] = mapping.get(profile_name, "C")
                s["component_grades"] = {
                    "breakout": "✅",
                    "retest": "✅",
                    "rr": "✅",  # RR handled separately
                    "market": "⚠️",
                }

            # Shell profiles (name-only) provide labeling parity.
            # Simplified gating: no special handling for global-disabled state.

            # Points-based gating always runs at Level 2. Disabled component filters
            # award their max points (legacy behavior), so we keep the denominator
            # at the full maximum (100) to preserve parity when everything is disabled.
            # Delegate gating (total threshold + optional component mins) to utility for reuse
            from gating_utils import apply_level2_gating  # local import to avoid circulars

            graded_signals, gating_stats = apply_level2_gating(
                profile_name, self.grade_profile, graded_signals, verbose=True
            )

        trades = []

        for sig in graded_signals:
            # Track real price movement after signal
            entry_price = sig["entry"]
            stop_price = sig["stop"]
            target_price = sig["target"]
            direction = sig["direction"]
            entry_datetime = pd.to_datetime(sig["datetime"])
            # Ensure entry_datetime is UTC-aware for downstream comparisons
            try:
                if getattr(entry_datetime, "tzinfo", None) is None:
                    entry_datetime = entry_datetime.tz_localize(
                        ZoneInfo("America/New_York")
                    ).tz_convert(ZoneInfo("UTC"))
                else:
                    entry_datetime = entry_datetime.tz_convert(ZoneInfo("UTC"))
            except Exception:
                pass

            # Use centralized trade planner for stop/target/shares sizing
            from trade_planner import plan_trade

            eff_leverage = max(1.0, min(float(DEFAULT_LEVERAGE), 3.0))
            # Use configured/signal rr ratio directly (min_rr_ratio drives target distance).
            rr_ratio_source = sig.get("rr_ratio")
            if rr_ratio_source is None:
                rr_ratio_source = getattr(self, "min_rr_ratio", 2.0)
            try:
                rr_ratio_source = float(rr_ratio_source)
            except Exception:
                rr_ratio_source = getattr(self, "min_rr_ratio", 2.0)
            if rr_ratio_source <= 0:
                rr_ratio_source = getattr(self, "min_rr_ratio", 2.0)

            try:
                tp = plan_trade(
                    side=direction,
                    entry=entry_price,
                    initial_capital=float(self.initial_capital),
                    risk_pct=float(self.risk_pct_per_trade),
                    rr_ratio=rr_ratio_source,
                    leverage=eff_leverage,
                    stop_price=stop_price,
                    tick_size=0.01,
                )
            except ValueError:
                # Skip trades that cannot be sized (e.g., zero distance or
                # insufficient buying power)
                continue

            # Override stop/target/shares with planned values (may differ by tick rounding)
            stop_price = tp.stop
            target_price = tp.target
            shares = tp.shares
            risk_per_share = tp.stop_dist
            risk_per_trade = tp.risk_per_trade
            if shares == 0:
                continue

            # Reuse warmed per-day 1m session instead of per-trade window loads
            if getattr(self, "_inline_df_1m", None) is not None:
                session_source = self._inline_df_1m
            else:
                # Derive day key from entry time (UTC → ET for session anchor) and pull warmed data
                et_tz = ZoneInfo("America/New_York")
                entry_et = entry_datetime.tz_convert(et_tz)
                day_key = entry_et.date()
                # _session_1m_by_day populated earlier via _get_or_preload_session_1m
                session_source = None
                if hasattr(self, "_session_1m_by_day"):
                    session_source = self._session_1m_by_day.get((symbol, day_key))
                if session_source is None or (
                    isinstance(session_source, pd.DataFrame) and session_source.empty
                ):
                    # Fallback to legacy window loader (cross-day or missing warm data)
                    session_source = self._load_1m_window(
                        symbol=symbol,
                        center_time=entry_datetime + timedelta(minutes=195),
                        window_minutes=200,
                    )
            future_bars = pd.DataFrame()
            if session_source is not None and not session_source.empty:
                future_bars = session_source[session_source["Datetime"] > entry_datetime].copy()
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

                # Grade continuation using profile ignition thresholds (reuse ignition pass concept)
                ign_ok, ign_reason = profile_grade_ignition(
                    {
                        "Open": ignition_open,
                        "High": ignition_high,
                        "Low": ignition_low,
                        "Close": ignition_close,
                        "Volume": ignition_vol,
                    },
                    ignition_body_pct=ignition_body_pct,
                    ignition_vol_ratio=ignition_vol_ratio,
                    progress=distance_to_target,
                    profile=self.grade_profile or load_profile("c"),
                )
                cont_grade = "✅" if ign_ok else "❌"
                cont_desc = f"ignition_profile_eval:{ign_reason}"

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
            # If neither stop nor target was hit, force exit at session close (last bar close)
            if exit_price is None:
                try:
                    last_bar = future_bars.iloc[-1]
                    exit_price = float(last_bar.get("Close"))
                    exit_time = last_bar.get("Datetime")
                    outcome = "forced"
                except Exception:
                    continue

            # Calculate P&L (treat forced close as normal exit at last close)
            if direction == "long":
                pnl = (exit_price - entry_price) * shares
            else:  # short
                pnl = (entry_price - exit_price) * shares

            # Effective risk actually deployed (can be less than configured risk_per_trade
            # if notional leverage cap reduced position size)
            effective_risk_amount = shares * risk_per_share

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
                "forced_close": outcome == "forced",
                # Report the effective dollar risk deployed for this trade
                # (shares * per-share risk). This aligns the displayed Risk with
                # realized P&L multiples (loss ≈ -Risk, win ≈ RR * Risk).
                "risk_amount": effective_risk_amount,
                # Also include the configured/planned risk for auditing
                "risk_amount_planned": risk_per_trade,
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
                print("\n" + "=" * 70)
                print(f"{symbol} Profile {self.grade_profile_name or 'n/a'} Trade Summary")
                sr = sig.get("stage_results", {})
                b_pass = sr.get("breakout", {}).get("pass", True)
                r_pass = sr.get("retest", {}).get("pass", True)
                i_pass = sr.get("ignition", {}).get("pass", True)
                print(f"Breakout pass={b_pass} Retest pass={r_pass} Ignition pass={i_pass}")
                print(f"RR={sig.get('rr_ratio', 0.0):.2f} Overall={sig.get('overall_grade', 'C')}")
                print("=" * 70 + "\n")

        # Calculate statistics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.get("outcome") == "win")
        losing_trades = sum(1 for t in trades if t.get("outcome") == "loss")
        forced_closes = sum(1 for t in trades if t.get("outcome") == "forced")
        total_pnl = sum(t["pnl"] for t in trades)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        result = {
            "symbol": symbol,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "forced_closes": forced_closes,
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "signals": graded_signals,
            "trades": trades,
            "candidate_count": candidate_count,
            "filter_config": {
                "grade_profile": self.grade_profile_name,
                "profile_breakout": self.grade_profile.get("breakout")
                if self.grade_profile
                else None,
                "profile_retest": self.grade_profile.get("retest") if self.grade_profile else None,
                "profile_ignition": self.grade_profile.get("ignition")
                if self.grade_profile
                else None,
            },
        }
        if self.pipeline_level == 2 and self.grade_profile is not None:
            result["level2_filtering_stats"] = {
                "pre_filter_count": pre_filter_count,
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
    total_forced = 0

    for res in results:
        output.append(f"\n{res['symbol']}:")
        output.append(f"  Total Trades: {res['total_trades']}")
        output.append(f"  Winners: {res['winning_trades']}")
        output.append(f"  Losers: {res['losing_trades']}")
        if res.get("forced_closes"):
            output.append(f"  Forced closes: {res['forced_closes']}")
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
        total_forced += res.get("forced_closes", 0)

    output.append("\n" + "-" * 60)
    output.append("OVERALL:")
    output.append(f"  Total Trades: {total_trades}")
    output.append(f"  Winners: {total_winners}")
    output.append(
        f"  Overall Win Rate: {total_winners/total_trades:.1%}"
        if total_trades > 0
        else "  Overall Win Rate: N/A"
    )
    if total_forced:
        output.append(f"  Forced closes: {total_forced}")
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

  # Override config values example
  python backtest.py --start 2025-10-01 --end 2025-10-31 \
      --config-override initial_capital=10000

  # Multiple config overrides
  python backtest.py --start 2025-10-01 --end 2025-10-31 \
      --config-override leverage=1.5 \
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

    # Removed CLI control for risk percent; use config.json (overridable via --config-override)
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
        choices=["profile"],
        default="profile",
        help="Grading system (profile-based: breakout/retest/ignition thresholds)",
    )
    parser.add_argument(
        "--grade",
        choices=["aplus", "a", "b", "c"],
        default=None,
        help=(
            "Grade profile to apply at Level 2 filtering. One profile active at a time. "
            "If omitted, defaults to the value of default_grade in config.json (e.g., 'c')."
        ),
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

    # ------------------------------------------------------------------
    # Runtime timer start (wall-clock) – minimal performance visibility
    # ------------------------------------------------------------------
    overall_t0 = time.perf_counter()

    # Apply config overrides from command line via utility function
    apply_config_overrides(CONFIG, args.config_override or [])

    # Update config-derived options and feature flags after overrides
    # no-op: removed legacy VWAP Level 0 flag

    # Runtime values resolved from CONFIG (do not mutate module-level defaults here)
    runtime_results_dir = CONFIG.get("backtest_results_dir", DEFAULT_RESULTS_DIR)
    runtime_retest_vol_gate = CONFIG.get("retest_volume_gate_ratio", RETEST_VOL_GATE)
    min_rr_ratio = CONFIG.get("min_rr_ratio", 2.0)
    default_grade_cfg = str(CONFIG.get("default_grade", "c")).lower()
    if default_grade_cfg not in {"aplus", "a", "b", "c"}:
        default_grade_cfg = "c"
    risk_pct_cfg = float(CONFIG.get("risk_pct_per_trade", 0.005))

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
        risk_pct_per_trade=risk_pct_cfg,
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
    # Load grade profile if provided and Level 2
    if pipeline_level == 2:
        effective_grade = args.grade if args.grade else default_grade_cfg
        try:
            engine.grade_profile_name = effective_grade
            engine.grade_profile = load_profile(effective_grade)
            print(f"Loaded grade profile: {effective_grade}")
        except Exception as e:
            print(f"Failed to load grade profile '{args.grade}': {e}")
            engine.grade_profile_name = None
            engine.grade_profile = None

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

    # ------------------------------------------------------------------
    # Runtime timer end + report
    # ------------------------------------------------------------------
    elapsed_sec = time.perf_counter() - overall_t0
    # Human-friendly formatting
    if elapsed_sec < 120:
        elapsed_str = f"{elapsed_sec:.2f}s"
    else:
        elapsed_str = f"{elapsed_sec/60.0:.2f}m"
    try:
        symbol_count = len(symbols)
    except Exception:
        symbol_count = 0
    grade_suffix = ""
    if pipeline_level == 2 and getattr(engine, "grade_profile_name", None):
        grade_suffix = f', Grade "{engine.grade_profile_name}"'
    print(
        f"Runtime: {elapsed_str} for {symbol_count} symbol(s) "
        f"({start_date} -> {end_date}), Level {pipeline_level}{grade_suffix}"
    )


if __name__ == "__main__":
    main()
