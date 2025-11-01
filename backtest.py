#!/usr/bin/env python3
"""
Backtesting engine for Break & Re-Test strategy

Usage:
    python backtest.py --start 2024-01-01 --end 2024-12-31
    python backtest.py --symbols AAPL MSFT --start 2024-01-01 --end 2024-12-31
    python backtest.py --symbols AAPL --start 2024-01-01 --end 2024-12-31 --initial-capital 10000
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf
from zoneinfo import ZoneInfo

from break_and_retest_detection_mt import scan_for_setups
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
        symbol_dir = self.cache_dir / symbol
        symbol_dir.mkdir(exist_ok=True)
        return symbol_dir / f"{date}_{interval}.csv"

    def get_cached_data(self, symbol: str, date: str, interval: str) -> Optional[pd.DataFrame]:
        """Load cached data if available"""
        cache_path = self._get_cache_path(symbol, date, interval)
        if cache_path.exists():
            df = pd.read_csv(cache_path, parse_dates=["Datetime"])
            return df
        return None

    def cache_data(self, symbol: str, date: str, interval: str, df: pd.DataFrame):
        """Save data to cache"""
        cache_path = self._get_cache_path(symbol, date, interval)
        df.to_csv(cache_path, index=False)

    def download_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "5m",
    ) -> pd.DataFrame:
        """
        Download OHLCV data for a symbol and date range, using cache when available

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

        # For 1-minute data, yfinance only allows 7 days at a time
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

            # Download from yfinance
            try:
                ticker = yf.Ticker(symbol)
                next_day = current + timedelta(days=1)
                df = ticker.history(
                    start=current.strftime("%Y-%m-%d"),
                    end=next_day.strftime("%Y-%m-%d"),
                    interval=interval,
                    prepost=False,
                )

                if not df.empty:
                    # Standardize column names
                    df = df.reset_index()
                    df.columns = [
                        col.replace("Datetime", "Datetime") if "Datetime" in col else col
                        for col in df.columns
                    ]
                    if "index" in df.columns:
                        df = df.rename(columns={"index": "Datetime"})

                    # Ensure required columns
                    required_cols = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
                    if all(col in df.columns for col in required_cols):
                        df = df[required_cols]

                        # Cache the data
                        self.cache_data(symbol, date_str, interval, df)
                        all_data.append(df)
                        print(f"Downloaded {symbol} data for {date_str} ({len(df)} bars)")
                    else:
                        print(f"Warning: Missing columns for {symbol} on {date_str}")
                else:
                    print(f"No data for {symbol} on {date_str}")

            except Exception as e:
                print(f"Error downloading {symbol} for {date_str}: {e}")

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
        Download 1-minute data. yfinance only allows 7 days at a time for 1m data.

        Args:
            symbol: Stock ticker symbol
            start: Start datetime
            end: End datetime

        Returns:
            DataFrame with 1-minute OHLCV data
        """
        all_data = []

        # Download in 7-day chunks
        current = start
        while current <= end:
            chunk_end = min(current + timedelta(days=7), end + timedelta(days=1))

            # Check cache for each day in the chunk
            chunk_start_date = current.strftime("%Y-%m-%d")

            # Try cache first
            cached_df = self.get_cached_data(symbol, chunk_start_date, "1m")
            if cached_df is not None and not cached_df.empty:
                all_data.append(cached_df)
                current = chunk_end
                continue

            # Download from yfinance
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(
                    start=current.strftime("%Y-%m-%d"),
                    end=chunk_end.strftime("%Y-%m-%d"),
                    interval="1m",
                    prepost=False,
                )

                if not df.empty:
                    # Standardize column names
                    df = df.reset_index()
                    df.columns = [
                        col.replace("Datetime", "Datetime") if "Datetime" in col else col
                        for col in df.columns
                    ]
                    if "index" in df.columns:
                        df = df.rename(columns={"index": "Datetime"})

                    # Ensure required columns
                    required_cols = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
                    if all(col in df.columns for col in required_cols):
                        df = df[required_cols]

                        # Cache the data
                        self.cache_data(symbol, chunk_start_date, "1m", df)
                        all_data.append(df)
                        print(
                            f"Downloaded {symbol} 1m data for {chunk_start_date} ({len(df)} bars)"
                        )
                    else:
                        print(
                            f"Warning: Missing columns for {symbol} 1m data on {chunk_start_date}"
                        )
                else:
                    print(f"No 1m data for {symbol} starting {chunk_start_date}")

            except Exception as e:
                print(f"Error downloading {symbol} 1m data for {chunk_start_date}: {e}")

            current = chunk_end

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
        max_positions: int = 3,
        scan_window_minutes: int = 180,
        min_grade: Optional[str] = None,
        breakout_tier_filter: Optional[str] = None,
        display_tzinfo=None,
        tz_label: str = "UTC",
        retest_vol_threshold: float = 0.15,
    ):
        """
        Initialize backtest engine

        Args:
            initial_capital: Starting capital
            position_size_pct: Percentage of capital per trade (0.1 = 10%)
            max_positions: Maximum number of concurrent positions
            scan_window_minutes: Rolling window for scanning (default: 180 = 3 hours)
        """
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
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

    def _scan_continuous_data(
        self, symbol: str, df_5m: pd.DataFrame, df_1m: pd.DataFrame
    ) -> List[Dict]:
        """
        Scan data using multi-timeframe approach:
        - Use 5-minute candles to identify opening range and breakouts
        - Switch to 1-minute candles for retest and ignition entry

        Relaxed criteria for backtesting (vs live scanning):
        - Volume threshold: 1.0x MA (vs 1.2x)
        - Returns to level: within $0.50 (vs $0.10)
        - Tight candle: < 75% of breakout range (vs 50%)

        Args:
            df_5m: DataFrame with 5-minute OHLCV data
            df_1m: DataFrame with 1-minute OHLCV data

        Returns:
            List of all detected signals
        """
        all_signals = []

        # Calculate 10-bar volume MA on 5-minute data (for breakout volume ratio)
        df_5m = df_5m.copy()
        df_5m["vol_ma"] = df_5m["Volume"].rolling(window=10, min_periods=1).mean()
        df_5m["Date"] = df_5m["Datetime"].dt.date

        # Prepare 1-minute data
        df_1m = df_1m.copy()
        df_1m["Date"] = df_1m["Datetime"].dt.date
        available_1m_dates = set(df_1m["Date"].unique())

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

            # Check if we have 1-minute data for this day
            has_1m_data = day in available_1m_dates

            # Get 1-minute data for this day (if available)
            if has_1m_data:
                day_df_1m = df_1m[df_1m["Date"] == day].copy()
                session_df_1m = day_df_1m[
                    (day_df_1m["Datetime"].dt.strftime("%H:%M") >= "09:30")
                    & (day_df_1m["Datetime"].dt.strftime("%H:%M") < "16:00")
                ]

                if len(session_df_1m) < 50:
                    has_1m_data = False  # Not enough 1m data, fall back to 5m only
            else:
                session_df_1m = pd.DataFrame()

            # Use first 5-minute candle as opening range
            or_high = session_df_5m.iloc[0]["High"]
            or_low = session_df_5m.iloc[0]["Low"]

            # Scan the first 90 minutes of 5-minute data for breakouts (18 bars)
            start_time = session_df_5m["Datetime"].iloc[0]
            end_time = start_time + timedelta(minutes=90)
            scan_df_5m = session_df_5m[
                (session_df_5m["Datetime"] >= start_time) & (session_df_5m["Datetime"] < end_time)
            ].copy()

            if len(scan_df_5m) < 10:
                continue

            # Require 1m data; skip day if missing
            if not has_1m_data:
                continue

            # Use shared detection module to find setups (multi-timeframe only)
            setups = scan_for_setups(
                df_5m=scan_df_5m,
                df_1m=session_df_1m,
                or_high=or_high,
                or_low=or_low,
                vol_threshold=1.0,  # Backtest uses relaxed 1.0x threshold
            )

            for setup in setups:
                breakout_candle = setup["breakout"]["candle"]
                retest_candle = setup["retest"]
                ignition_candle = setup["ignition"]
                direction = setup["direction"]
                level = setup["level"]
                breakout_time = setup["breakout"]["time"]

                breakout_up = direction == "long"

                # Calculate entry, stop, target
                entry = ignition_candle["High"] if breakout_up else ignition_candle["Low"]
                stop = retest_candle["Low"] - 0.05 if breakout_up else retest_candle["High"] + 0.05
                risk = abs(entry - stop)
                target = entry + 2 * risk if breakout_up else entry - 2 * risk

                # Calculate grading metadata
                breakout_body_pct = abs(breakout_candle["Close"] - breakout_candle["Open"]) / (
                    breakout_candle["High"] - breakout_candle["Low"]
                )
                breakout_vol_ratio = breakout_candle["Volume"] / breakout_candle["vol_ma"]
                retest_vol_ratio = retest_candle["Volume"] / breakout_candle["Volume"]
                ignition_body_pct = abs(ignition_candle["Close"] - ignition_candle["Open"]) / (
                    ignition_candle["High"] - ignition_candle["Low"]
                )
                ignition_vol_ratio = ignition_candle["Volume"] / breakout_candle["Volume"]

                # Calculate distance to target achieved by ignition
                if breakout_up:
                    distance_to_target = (ignition_candle["High"] - entry) / (target - entry)
                else:
                    distance_to_target = (entry - ignition_candle["Low"]) / (entry - target)

                all_signals.append(
                    {
                        "ticker": symbol,
                        "direction": direction,
                        "entry": entry,
                        "stop": stop,
                        "target": target,
                        "risk": risk,
                        "level": level,
                        "datetime": ignition_candle["Datetime"],
                        "breakout_time_5m": breakout_time,
                        "vol_breakout_5m": breakout_candle["Volume"],
                        "vol_retest_1m": retest_candle["Volume"],
                        "vol_ignition_1m": ignition_candle["Volume"],
                        "vwap": setup.get("vwap"),  # VWAP at breakout time
                        # Grading metadata
                        "breakout_candle": {
                            "Open": breakout_candle["Open"],
                            "High": breakout_candle["High"],
                            "Low": breakout_candle["Low"],
                            "Close": breakout_candle["Close"],
                            "Volume": breakout_candle["Volume"],
                        },
                        "retest_candle": {
                            "Open": retest_candle["Open"],
                            "High": retest_candle["High"],
                            "Low": retest_candle["Low"],
                            "Close": retest_candle["Close"],
                            "Volume": retest_candle["Volume"],
                        },
                        "ignition_candle": {
                            "Open": ignition_candle["Open"],
                            "High": ignition_candle["High"],
                            "Low": ignition_candle["Low"],
                            "Close": ignition_candle["Close"],
                            "Volume": ignition_candle["Volume"],
                        },
                        "breakout_body_pct": breakout_body_pct,
                        "breakout_vol_ratio": breakout_vol_ratio,
                        "retest_vol_ratio": retest_vol_ratio,
                        "ignition_body_pct": ignition_body_pct,
                        "ignition_vol_ratio": ignition_vol_ratio,
                        "distance_to_target": distance_to_target,
                    }
                )

        return all_signals

    def run_backtest(self, symbol: str, df_5m: pd.DataFrame, df_1m: pd.DataFrame) -> Dict:
        """
        Run backtest on a single symbol's data using multi-timeframe approach

        Args:
            symbol: Stock ticker
            df_5m: DataFrame with 5-minute OHLCV data
            df_1m: DataFrame with 1-minute OHLCV data

        Returns:
            Dictionary with backtest results
        """
        # Get signals using multi-timeframe scanning approach
        signals = self._scan_continuous_data(symbol, df_5m, df_1m)

        if not signals:
            return {
                "symbol": symbol,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "total_pnl": 0,
                "win_rate": 0,
                "signals": [],
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

        graded_signals = [compute_grades(dict(sig)) for sig in signals]

        # Apply min_grade filter if provided
        if self.min_grade:
            order = {"C": 0, "B": 1, "A": 2, "A+": 3}
            threshold = order.get(self.min_grade, 0)
            graded_signals = [
                s for s in graded_signals if order.get(s.get("overall_grade", "C"), 0) >= threshold
            ]

        # Apply breakout tier filter if specified
        if self.breakout_tier_filter:
            graded_signals = [
                s for s in graded_signals if s.get("breakout_tier") == self.breakout_tier_filter
            ]

        trades = []

        for sig in graded_signals:
            # Track real price movement after signal
            entry_price = sig["entry"]
            stop_price = sig["stop"]
            target_price = sig["target"]
            direction = sig["direction"]
            entry_datetime = pd.to_datetime(sig["datetime"])

            # Calculate position size
            risk_per_trade = self.cash * self.position_size_pct
            risk_per_share = abs(entry_price - stop_price)
            shares = int(risk_per_trade / risk_per_share) if risk_per_share > 0 else 0

            if shares == 0:
                continue

            # Get price bars after entry to track if stop or target hit
            future_bars = df_1m[df_1m["Datetime"] > entry_datetime].copy()
            # Ensure time-ascending order
            if not future_bars.empty:
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

            # Generate and print Scarface Rules report for this signal
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

    for res in results:
        output.append(f"\n{res['symbol']}:")
        output.append(f"  Total Trades: {res['total_trades']}")
        output.append(f"  Winners: {res['winning_trades']}")
        output.append(f"  Losers: {res['losing_trades']}")
        output.append(f"  Win Rate: {res['win_rate']:.1%}")
        output.append(f"  Total P&L: ${res['total_pnl']:.2f}")

        total_trades += res["total_trades"]
        total_winners += res["winning_trades"]
        total_pnl += res["total_pnl"]

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
        f"| Date ({tz_label}) | Time | Symbol | Dir | Entry | Stop | Target | Exit | Outcome | "
        "P&L | Shares |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|")

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
        "--initial-capital", type=float, default=7500, help="Initial capital (default: 7500)"
    )
    parser.add_argument(
        "--position-size",
        type=float,
        default=0.1,
        help="Position size as %% of capital (default: 0.1)",
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

    print(f"Backtesting symbols: {', '.join(symbols)}")
    print(f"Date range: {start_date} to {end_date}")
    print(f"Initial capital: ${args.initial_capital:,.2f}")
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
        min_grade=args.min_grade,
        breakout_tier_filter=args.breakout_tier,
        display_tzinfo=display_tz,
        tz_label=tz_label,
        retest_vol_threshold=RETEST_VOL_GATE,
    )

    results = []

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

        # Download/load 1-minute data (limited to last 30 days due to Yahoo Finance constraint)
        print("Downloading 1-minute data...")
        # Calculate the actual 1m data window (last 30 days max)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        start_1m_dt = max(
            datetime.strptime(start_date, "%Y-%m-%d"),
            end_dt - timedelta(days=29),  # 30 days including end date
        )
        start_1m_date = start_1m_dt.strftime("%Y-%m-%d")

        if start_1m_date != start_date:
            print(f"Note: 1m data limited to last 30 days ({start_1m_date} to {end_date})")

        df_1m = cache.download_data(
            symbol=symbol,
            start_date=start_1m_date,
            end_date=end_date,
            interval="1m",
        )

        if df_1m.empty:
            print(f"No 1-minute data available for {symbol}")
            continue

        print(f"Loaded {len(df_1m)} 1-minute bars for {symbol}")

        # Run backtest
        result = engine.run_backtest(symbol, df_5m, df_1m)
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
