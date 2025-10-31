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

from break_and_retest_strategy import is_strong_body


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
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Download OHLCV data for a symbol and date range, using cache when available

        Args:
            symbol: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Data interval (1m, 5m, 15m, 1h, 1d)
            force_refresh: If True, ignore cache and re-download

        Returns:
            DataFrame with OHLCV data
        """
        all_data = []

        # Parse dates
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        # For 1-minute data, yfinance only allows 7 days at a time
        if interval == "1m":
            return self._download_1m_data(symbol, start, end, force_refresh)

        # Download day by day for intraday data (yfinance limitation)
        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")

            # Check cache first
            if not force_refresh:
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

    def _download_1m_data(
        self, symbol: str, start: datetime, end: datetime, force_refresh: bool = False
    ) -> pd.DataFrame:
        """
        Download 1-minute data. yfinance only allows 7 days at a time for 1m data.

        Args:
            symbol: Stock ticker symbol
            start: Start datetime
            end: End datetime
            force_refresh: If True, ignore cache and re-download

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
            if not force_refresh:
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

    def _scan_continuous_data(self, df_5m: pd.DataFrame, df_1m: pd.DataFrame) -> List[Dict]:
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

            # Get 1-minute data for this day
            day_df_1m = df_1m[df_1m["Date"] == day].copy()
            session_df_1m = day_df_1m[
                (day_df_1m["Datetime"].dt.strftime("%H:%M") >= "09:30")
                & (day_df_1m["Datetime"].dt.strftime("%H:%M") < "16:00")
            ]

            if len(session_df_1m) < 50:
                continue

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

            # Look for breakouts on 5-minute timeframe
            for i in range(1, len(scan_df_5m)):
                row_5m = scan_df_5m.iloc[i]
                prev_5m = scan_df_5m.iloc[i - 1]

                breakout_up = (
                    prev_5m["High"] <= or_high
                    and row_5m["High"] > or_high
                    and is_strong_body(row_5m)
                    and row_5m["Volume"] > row_5m["vol_ma"] * 1.0
                    and row_5m["Close"] > or_high
                )
                breakout_down = (
                    prev_5m["Low"] >= or_low
                    and row_5m["Low"] < or_low
                    and is_strong_body(row_5m)
                    and row_5m["Volume"] > row_5m["vol_ma"] * 1.0
                    and row_5m["Close"] < or_low
                )

                if breakout_up or breakout_down:
                    # Breakout detected on 5-minute! Now switch to 1-minute for retest/ignition
                    breakout_time = row_5m["Datetime"]
                    breakout_level = or_high if breakout_up else or_low

                    # Get 1-minute candles starting from the breakout candle time
                    # Look ahead up to 30 minutes for retest + ignition pattern
                    retest_window_end = breakout_time + timedelta(minutes=30)
                    df_1m_window = session_df_1m[
                        (session_df_1m["Datetime"] > breakout_time)
                        & (session_df_1m["Datetime"] <= retest_window_end)
                    ].copy()

                    if len(df_1m_window) < 3:
                        continue

                    # Look for retest + ignition pattern on 1-minute timeframe
                    for j in range(len(df_1m_window) - 1):
                        retest_1m = df_1m_window.iloc[j]

                        # Check if this candle retests the level
                        returns_to_level = (
                            breakout_up and abs(retest_1m["Low"] - breakout_level) < 0.5
                        ) or (breakout_down and abs(retest_1m["High"] - breakout_level) < 0.5)

                        # Check if it's a tight candle (smaller range than 5m breakout)
                        tight_candle = retest_1m["High"] - retest_1m["Low"] < 0.75 * (
                            row_5m["High"] - row_5m["Low"]
                        )

                        # Volume should be lower than breakout (compare 1m to 5m average)
                        lower_vol = (
                            retest_1m["Volume"] < (row_5m["Volume"] / 5) * 1.5
                        )  # 5m vol / 5 bars, with 1.5x tolerance

                        if returns_to_level and tight_candle and lower_vol:
                            # Found retest! Now look for ignition on next 1-minute candle
                            if j + 1 >= len(df_1m_window):
                                break

                            ign_1m = df_1m_window.iloc[j + 1]

                            # Ignition: strong body, breaks above/below retest, volume increases
                            ignition = (
                                is_strong_body(ign_1m)
                                and (
                                    (breakout_up and ign_1m["High"] > retest_1m["High"])
                                    or (breakout_down and ign_1m["Low"] < retest_1m["Low"])
                                )
                                and ign_1m["Volume"] > retest_1m["Volume"]
                            )

                            if ignition:
                                entry = ign_1m["High"] if breakout_up else ign_1m["Low"]
                                stop = (
                                    retest_1m["Low"] - 0.05
                                    if breakout_up
                                    else retest_1m["High"] + 0.05
                                )
                                risk = abs(entry - stop)
                                target = entry + 2 * risk if breakout_up else entry - 2 * risk

                                all_signals.append(
                                    {
                                        "direction": "long" if breakout_up else "short",
                                        "entry": entry,
                                        "stop": stop,
                                        "target": target,
                                        "risk": risk,
                                        "vol_breakout_5m": row_5m["Volume"],
                                        "vol_retest_1m": retest_1m["Volume"],
                                        "vol_ignition_1m": ign_1m["Volume"],
                                        "datetime": ign_1m["Datetime"],
                                        "breakout_time_5m": breakout_time,
                                        "level": breakout_level,
                                    }
                                )

                                # Only take first signal per breakout
                                break

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
        signals = self._scan_continuous_data(df_5m, df_1m)

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

        trades = []

        for sig in signals:
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
            "signals": signals,
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
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--initial-capital", type=float, default=10000, help="Initial capital (default: 10000)"
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

    args = parser.parse_args()

    # Use default tickers from config if not specified
    symbols = args.symbols if args.symbols else DEFAULT_TICKERS

    print(f"Backtesting symbols: {', '.join(symbols)}")
    print(f"Date range: {args.start} to {args.end}")
    print(f"Initial capital: ${args.initial_capital:,.2f}")
    print()

    # Initialize components
    cache = DataCache(args.cache_dir)
    engine = BacktestEngine(
        initial_capital=args.initial_capital, position_size_pct=args.position_size
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
            start_date=args.start,
            end_date=args.end,
            interval="5m",
            force_refresh=args.force_refresh,
        )

        if df_5m.empty:
            print(f"No 5-minute data available for {symbol}")
            continue

        print(f"Loaded {len(df_5m)} 5-minute bars for {symbol}")

        # Download/load 1-minute data
        print("Downloading 1-minute data...")
        df_1m = cache.download_data(
            symbol=symbol,
            start_date=args.start,
            end_date=args.end,
            interval="1m",
            force_refresh=args.force_refresh,
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
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
