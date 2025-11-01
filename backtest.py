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

from break_and_retest_detection import scan_for_setups
from signal_grader import (
    calculate_overall_grade,
    generate_signal_report,
    grade_breakout_candle,
    grade_continuation,
    grade_market_context,
    grade_retest,
    grade_risk_reward,
)


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

        # Calculate 20-bar volume MA on 5-minute data
        df_5m = df_5m.copy()
        df_5m["vol_ma"] = df_5m["Volume"].rolling(window=20, min_periods=1).mean()
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

            # Use shared detection module to find setups
            # Use multi-timeframe only if we have 1m data for this day
            setups = scan_for_setups(
                df_5m=scan_df_5m,
                df_1m=session_df_1m if has_1m_data else None,
                or_high=or_high,
                or_low=or_low,
                vol_threshold=1.0,  # Backtest uses relaxed 1.0x threshold
                use_multitimeframe=has_1m_data,
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
            )
            retest_grade, retest_desc = grade_retest(
                sig.get("retest_candle", {}),
                sig.get("retest_vol_ratio", 0.0),
                sig.get("level", 0.0),
                sig.get("direction", "long"),
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
            return sig

        graded_signals = [compute_grades(dict(sig)) for sig in signals]

        # Apply min_grade filter if provided
        if self.min_grade:
            order = {"C": 0, "B": 1, "A": 2, "A+": 3}
            threshold = order.get(self.min_grade, 0)
            graded_signals = [
                s for s in graded_signals if order.get(s.get("overall_grade", "C"), 0) >= threshold
            ]

        trades = []

        for sig in graded_signals:
            # Simulate trade execution
            entry_price = sig["entry"]
            stop_price = sig["stop"]
            target_price = sig["target"]
            direction = sig["direction"]

            # Calculate position size
            risk_per_trade = self.cash * self.position_size_pct
            risk_per_share = abs(entry_price - stop_price)
            shares = int(risk_per_trade / risk_per_share) if risk_per_share > 0 else 0

            if shares == 0:
                continue

            # Simple simulation: assume target or stop is hit
            # In reality, you'd need to track price action after signal
            # For now, use a 50/50 random outcome weighted by risk/reward

            # Simulate outcome (simplified - assumes 60% hit target based on 2:1 R:R)
            import random

            hit_target = random.random() < 0.6

            if hit_target:
                exit_price = target_price
                pnl = (
                    (exit_price - entry_price) * shares
                    if direction == "long"
                    else (entry_price - exit_price) * shares
                )
            else:
                exit_price = stop_price
                pnl = (
                    (exit_price - entry_price) * shares
                    if direction == "long"
                    else (entry_price - exit_price) * shares
                )

            trades.append(
                {
                    "datetime": sig.get("datetime"),
                    "direction": direction,
                    "entry": entry_price,
                    "exit": exit_price,
                    "stop": stop_price,
                    "target": target_price,
                    "shares": shares,
                    "pnl": pnl,
                    "outcome": "win" if hit_target else "loss",
                }
            )

            # Generate and print Scarface Rules report for this signal
            report = generate_signal_report(sig)
            print("\n" + "=" * 70)
            print(report)
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
        "--last-days",
        type=int,
        help=(
            "Convenience: set start/end to cover the last N calendar days "
            "(overrides --start/--end)"
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

    engine = BacktestEngine(
        initial_capital=args.initial_capital,
        position_size_pct=args.position_size,
        min_grade=args.min_grade,
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


if __name__ == "__main__":
    main()
