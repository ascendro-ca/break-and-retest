#!/usr/bin/env python3
"""
Backtesting engine for Break & Re-Test strategy

Usage:
    python backtest.py --start 2024-01-01 --end 2024-12-31
    python backtest.py --symbols AAPL MSFT --start 2024-01-01 --end 2024-12-31
    python backtest.py --symbols AAPL --start 2024-01-01 --end 2024-12-31 --initial-capital 10000
"""

import argparse
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd
# Note: yfinance provider removed; keep import out to avoid unused import lint

from cache_utils import (
    get_cache_path,
    load_cached_day,
    save_day,
    integrity_check_range,
)
from signal_grader import (
    calculate_overall_grade,
    generate_signal_report,
    grade_breakout_candle,
    grade_continuation,
    grade_market_context,
    grade_retest,
    grade_risk_reward,
)
from time_utils import get_display_timezone
from trade_setup_pipeline import run_pipeline


def load_config():
    """Load configuration from config.json"""
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        with open(config_path, "r") as f:
            return json.load(f)
    else:
        # Default config if file doesn't exist
        return {"tickers": ["AAPL", "AMZN", "META", "MSFT", "NVDA", "TSLA", "SPOT", "UBER"]}


CONFIG = load_config()
DEFAULT_TICKERS = CONFIG["tickers"]
DEFAULT_INITIAL_CAPITAL = CONFIG.get("initial_capital", 7500)
DEFAULT_LEVERAGE = CONFIG.get("leverage", 2.0)
RETEST_VOL_GATE = CONFIG.get("retest_volume_gate_ratio", 0.20)
BREAKOUT_A_UW_MAX = CONFIG.get("breakout_A_upper_wick_max", 0.15)
BREAKOUT_B_BODY_MAX = CONFIG.get("breakout_B_body_max", 0.65)
RETEST_B_EPSILON = CONFIG.get("retest_B_level_epsilon_pct", 0.10)
RETEST_B_SOFT = CONFIG.get("retest_B_structure_soft", True)


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
        min_grade: Optional[str] = None,
        breakout_tier_filter: Optional[str] = None,
        display_tzinfo=None,
        tz_label: str = "UTC",
        retest_vol_threshold: float = 0.15,
        pipeline_level: int = 0,
        no_trades: bool = False,
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
                           Level 0: Candidates only (no trades, Stages 1-3)
                           Level 1: Trades with base criteria (Stages 1-3, no ignition)
                           Level 2+: Enhanced filtering (may include Stage 4)
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
        # Optional minimum grade filter (A+, A, B, C)
        self.min_grade = min_grade
        # Optional breakout tier filter (A, B, or C)
        self.breakout_tier_filter = breakout_tier_filter
        # Reporting timezone for printing
        self.display_tz = display_tzinfo
        self.tz_label = tz_label
        self.retest_vol_threshold = retest_vol_threshold

        # Pipeline level determines filtering strictness and trade behavior
        # Level 0: Candidates only (no trades ever)
        # Level 1+: Can execute trades (unless no_trades=True)
        self.pipeline_level = int(pipeline_level)
        self.no_trades = no_trades if pipeline_level > 0 else True  # Level 0 always no trades

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
        for date in dates_needed:
            date_str = date.strftime("%Y-%m-%d")
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
            # Get 5-minute data for this day during market hours (09:30-16:00)
            day_df_5m = df_5m[df_5m["Date"] == day].copy()
            session_df_5m = day_df_5m[
                (day_df_5m["Datetime"].dt.strftime("%H:%M") >= "09:30")
                & (day_df_5m["Datetime"].dt.strftime("%H:%M") < "16:00")
            ]

            if len(session_df_5m) < 10:
                continue

            # Calculate VWAP for the session
            session_df_5m = session_df_5m.copy()
            session_df_5m["typical_price"] = (
                session_df_5m["High"] + session_df_5m["Low"] + session_df_5m["Close"]
            ) / 3
            session_df_5m["tp_volume"] = session_df_5m["typical_price"] * session_df_5m["Volume"]
            session_df_5m["vwap"] = (
                session_df_5m["tp_volume"].cumsum() / session_df_5m["Volume"].cumsum()
            )

            # Scan the first 90 minutes of 5-minute data for breakouts (18 bars)
            start_time = session_df_5m["Datetime"].iloc[0]
            end_time = start_time + timedelta(minutes=90)
            scan_df_5m = session_df_5m[
                (session_df_5m["Datetime"] >= start_time) & (session_df_5m["Datetime"] < end_time)
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

            if session_df_1m.empty or len(session_df_1m) < 50:
                # No 1m data available for this day, skip
                continue

            if self.pipeline_level == 0:
                # Level 0: Base pipeline - Delegate Stage 1-3 detection to shared pipeline
                # (Ignition detection disabled at Level 0)
                candidates = run_pipeline(
                    session_df_5m=session_df_5m,
                    session_df_1m=session_df_1m,
                    breakout_window_minutes=90,
                    retest_lookahead_minutes=30,
                    pipeline_level=0,
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
            pipeline_candidates = run_pipeline(
                session_df_5m=session_df_5m,
                session_df_1m=session_df_1m,
                breakout_window_minutes=90,
                retest_lookahead_minutes=30,
                pipeline_level=self.pipeline_level,
            )

            for cand in pipeline_candidates:
                direction = cand.get("direction")
                level = cand.get("level")
                breakout_time = cand.get("breakout_time")
                breakout_candle = cand.get("breakout_candle", {})
                retest_candle = cand.get("retest_candle", {})
                retest_time = pd.to_datetime(cand.get("retest_time"))

                # Entry at the open of the next 1m candle after retest (Level 1 design)
                next_bars = session_df_1m[session_df_1m["Datetime"] > retest_time]
                if next_bars.empty:
                    continue
                entry_bar = next_bars.iloc[0]
                entry_time = entry_bar["Datetime"]
                entry = float(entry_bar.get("Open"))

                breakout_up = direction == "long"
                # Stop below/above retest candle with a 5c buffer
                stop = (
                    float(retest_candle.get("Low", entry)) - 0.05
                    if breakout_up
                    else float(retest_candle.get("High", entry)) + 0.05
                )
                risk = abs(entry - stop)
                if risk == 0 or not pd.notna(risk):
                    continue
                target = entry + 2 * risk if breakout_up else entry - 2 * risk

                # Grading metadata from breakout/retest only (ignition is post-entry)
                try:
                    breakout_body_pct = abs(
                        float(breakout_candle.get("Close")) - float(breakout_candle.get("Open"))
                    ) / max(
                        float(breakout_candle.get("High")) - float(breakout_candle.get("Low")),
                        1e-9,
                    )
                except Exception:
                    breakout_body_pct = 0.0
                try:
                    breakout_vol_ratio = float(breakout_candle.get("Volume", 0.0)) / max(
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
                    retest_vol_ratio = float(retest_candle.get("Volume", 0.0)) / max(
                        float(breakout_candle.get("Volume", 0.0)), 1e-9
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
                    "vol_breakout_5m": breakout_candle.get("Volume"),
                    "vol_retest_1m": retest_candle.get("Volume"),
                    # Grading metadata
                    "breakout_candle": breakout_candle,
                    "retest_candle": retest_candle,
                    "breakout_body_pct": breakout_body_pct,
                    "breakout_vol_ratio": breakout_vol_ratio,
                    "retest_vol_ratio": retest_vol_ratio,
                }

                # If Level 2+, attach ignition info when available (post-entry diagnostic only)
                if self.pipeline_level >= 2 and "ignition_candle" in cand:
                    ign = cand.get("ignition_candle")
                    if ign is not None:
                        signal.update(
                            {
                                "ignition_candle": ign,
                                "vol_ignition_1m": (
                                    ign.get("Volume") if isinstance(ign, dict) else ign["Volume"]
                                ),
                                # Post-entry metrics will be computed later at trade simulation
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
                try:
                    bt = pd.to_datetime(c.get("breakout_time_5m"))
                    rt = pd.to_datetime(c.get("datetime"))
                except Exception:
                    bt = c.get("breakout_time_5m")
                    rt = c.get("datetime")
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

        # Compute grades for each signal and optionally filter by min_grade
        def compute_grades(sig: Dict) -> Dict:
            entry = sig["entry"]
            stop = sig["stop"]
            target = sig["target"]
            rr_ratio = abs(target - entry) / abs(entry - stop) if entry != stop else 0.0

            breakout_grade, breakout_desc = grade_breakout_candle(
                sig.get("breakout_candle", {}),
                sig.get("breakout_vol_ratio", 0.0),
                sig.get("breakout_body_pct", 0.0),
                sig.get("level", None),
                sig.get("direction", None),
                a_upper_wick_max=BREAKOUT_A_UW_MAX,
                b_body_max=BREAKOUT_B_BODY_MAX,
            )
            retest_grade, retest_desc = grade_retest(
                sig.get("retest_candle", {}),
                sig.get("retest_vol_ratio", 0.0),
                sig.get("level", 0.0),
                sig.get("direction", "long"),
                retest_volume_a_max_ratio=0.30,
                retest_volume_b_max_ratio=0.60,
                b_level_epsilon_pct=RETEST_B_EPSILON,
                b_structure_soft=RETEST_B_SOFT,
            )
            continuation_grade, continuation_desc = grade_continuation(
                sig.get("ignition_candle", {}),
                sig.get("ignition_vol_ratio", 0.0),
                sig.get("distance_to_target", 0.0),
                sig.get("ignition_body_pct", 0.0),
            )
            rr_grade, rr_desc = grade_risk_reward(rr_ratio)
            market_grade, market_desc = grade_market_context("slightly_red")

            grades = {
                "breakout": breakout_grade,
                "retest": retest_grade,
                "continuation": continuation_grade,
                "rr": rr_grade,
                "market": market_grade,
            }
            overall = calculate_overall_grade(grades)
            # Attach fields to signal
            sig["overall_grade"] = overall
            sig["component_grades"] = grades
            sig["rr_ratio"] = rr_ratio
            sig["breakout_tier"] = (
                "A" if breakout_grade == "✅" else ("B" if breakout_grade == "⚠️" else "C")
            )
            return sig

        # Level 0 and 1: No grading, use base criteria only (stages 1-3)
        # Level 2+: Apply grading and filters
        if self.pipeline_level >= 2:
            graded_signals = [compute_grades(dict(sig)) for sig in signals]

            # Apply min_grade filter if provided
            if self.min_grade:
                order = {"C": 0, "B": 1, "A": 2, "A+": 3}
                threshold = order.get(self.min_grade, 0)
                graded_signals = [
                    s
                    for s in graded_signals
                    if order.get(s.get("overall_grade", "C"), 0) >= threshold
                ]

            # Apply breakout tier filter if specified
            if self.breakout_tier_filter:
                graded_signals = [
                    s for s in graded_signals if s.get("breakout_tier") == self.breakout_tier_filter
                ]
        else:
            # Level 0 or 1: Pass signals through without grading (convert to dicts)
            graded_signals = [dict(sig) for sig in signals]

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

                # Volume ratio vs breakout 5m volume (if available on signal)
                breakout_vol = sig.get("vol_breakout_5m")
                try:
                    breakout_vol_f = float(breakout_vol) if breakout_vol is not None else 0.0
                except Exception:
                    breakout_vol_f = 0.0
                ignition_vol_ratio = ignition_vol / breakout_vol_f if breakout_vol_f > 0 else 0.0

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
                cont_grade, cont_desc = grade_continuation(
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

            trades.append(
                {
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
                    # Continuation diagnostics (post-entry informational only)
                    **{k: v for k, v in continuation_diag.items() if v is not None},
                }
            )

            # Generate and print Scarface Rules report (Level 2+ only)
            if self.pipeline_level >= 2:
                report = generate_signal_report(
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
                        ign_ts_str = ign_ts_local.strftime("%Y-%m-%d %H:%M:%S ") + self.tz_label
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

        return {
            "symbol": symbol,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "signals": graded_signals,
            "trades": trades,
            "candidate_count": candidate_count,
        }


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
        "Symbol | Dir | Entry | Stop | Target | Exit | Outcome | P&L | Shares |"
    )
    lines.append("|---|---|---|---:|---|---:|---:|---:|---:|---:|---|---:|---:|")

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
        "--initial-capital",
        type=float,
        default=DEFAULT_INITIAL_CAPITAL,
        help=f"Initial capital (default: {DEFAULT_INITIAL_CAPITAL} from config.json if set)",
    )
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
    parser.add_argument("--cache-dir", default="cache", help="Cache directory (default: cache)")
    parser.add_argument("--force-refresh", action="store_true", help="Force refresh cached data")
    parser.add_argument("--output", help="Output JSON file for results")
    parser.add_argument(
        "--min-grade",
        choices=["A+", "A", "B", "C"],
        help="Only include signals with this minimum grade or better",
    )
    parser.add_argument(
        "--breakout-tier",
        choices=["A", "B", "C"],
        help="Only include signals with this specific breakout tier (filters after grade)",
    )
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
            "Level 2+: Enhanced filtering (may include Stage 4: Ignition)."
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

    args = parser.parse_args()

    # Use default tickers from config if not specified
    symbols = args.symbols if args.symbols else DEFAULT_TICKERS

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
    print(f"Initial capital: ${args.initial_capital:,.2f}")
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
        initial_capital=args.initial_capital,
        position_size_pct=args.position_size,
        leverage=args.leverage,
        min_grade=args.min_grade,
        breakout_tier_filter=args.breakout_tier,
        display_tzinfo=display_tz,
        tz_label=tz_label,
        retest_vol_threshold=RETEST_VOL_GATE,
        pipeline_level=pipeline_level,
        no_trades=args.no_trades,
    )

    results = []

    # Run cache integrity check for the requested symbols/date range before processing
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

    # Print Markdown trade summary (controlled by --one-per-day flag; default: all entries)
    md_summary = generate_markdown_trade_summary(
        results, tzinfo=display_tz, tz_label=tz_label, one_per_day=args.one_per_day
    )
    print(md_summary)

    # Save results if output file specified
    if args.output:
        # Create backtest_results directory if it doesn't exist
        results_dir = Path("backtest_results")
        results_dir.mkdir(exist_ok=True)

        # Construct output path in backtest_results directory
        output_path = results_dir / args.output

        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Results saved to {output_path}")

        # Also save Markdown summary next to JSON
        md_path = output_path.with_suffix("")
        md_path = md_path.with_name(md_path.name + "_summary.md")
        with open(md_path, "w") as f:
            f.write(md_summary + "\n")
        print(f"Summary saved to {md_path}")


if __name__ == "__main__":
    main()
