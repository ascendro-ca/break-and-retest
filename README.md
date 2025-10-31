# Break & Re-Test Scalp Strategy

Small scanner that looks for a 5-minute "break and re-test" scalp setup on a list of tickers.

## Features
- Uses the first 5-minute candle after market open as the opening range
- Detects breakout (strong body + above-average volume)
- Detects re-test (returns to level, tight candle, lower volume)
- Detects ignition (strong body breaking re-test, rising volume)
- Restricts detection to the first 90 minutes after open
- **Automatic visualization generation** from unit tests with PNG snapshots
- **Minute-grouped test output viewer** with `--show-test`
- **CI-safe mode** with `--no-open` flag

## Requirements
- Python 3.8+
- Chrome/Chromium (automatically installed via `kaleido` for PNG generation)
- See `requirements.txt` for exact packages.

## Quick Start

1. Install dependencies (prefer a virtualenv):

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. Run scanner from CLI for default tickers:

```bash
python break_and_retest_strategy.py
```

3. Scan a single ticker and save a chart:

```bash
python visualize_results.py --ticker AAPL
```

4. Run unit tests and generate visualizations:

```bash
pytest test_break_and_retest_strategy.py
```

5. View test visualizations:

```bash
python visualize_results.py --show-test
```

## Continuous Scanning

Run the scanner continuously (every 1 minute) until you stop it:

```bash
./find_break_and_retest.sh
```

Options:
- `--once` - Run a single scan and exit
- `--interval 30s` - Run every 30 seconds
- `--daemon` - Run in background
- `--no-align` - Don't align to clock minutes

Press **Ctrl+C** to stop the continuous scanner.

## Visualization Options

### Demo Mode
Test the visualization with built-in scenarios:

```bash
python visualize_results.py --demo --demo-scenario long
python visualize_results.py --demo --demo-scenario short
python visualize_results.py --demo --demo-scenario long_fail
python visualize_results.py --demo --demo-scenario short_fail
```

### CI/Headless Mode
Generate visualizations without opening browser:

```bash
python visualize_results.py --show-test --no-open
python visualize_results.py --demo --no-open
```

### Test Outputs
Unit tests automatically generate:
- **HTML files** - Interactive Plotly charts in `logs/test_*.html`
- **PNG snapshots** - Static images in `logs/test_*.png`

The `--show-test` command groups and opens all test files from the same test run (minute-level grouping).

## Files
- `break_and_retest_strategy.py` — main scanner + CLI
- `visualize_results.py` — create Plotly HTML/PNG charts for found signals
- `test_break_and_retest_strategy.py` — unit tests for detection logic with auto-visualization
- `backtest.py` — backtesting engine with data caching
- `test_backtest.py` — unit tests for backtesting functionality
- `find_break_and_retest.sh` — continuous scanner wrapper script
- `conftest.py` — pytest configuration
- `pytest.ini` — pytest settings

## Backtesting

The backtesting engine allows you to test the Break & Re-Test strategy on historical data.

### Features
- **Data Caching**: Downloads and caches OHLCV data organized by symbol and date
- **Multiple Symbols**: Backtest across multiple stocks simultaneously  
- **Configurable Parameters**: Adjust initial capital, position sizing, and date ranges
- **Performance Metrics**: Win rate, P&L, trade statistics per symbol and overall

### Basic Usage

Backtest a single symbol:
```bash
python backtest.py --symbols AAPL --start 2024-01-01 --end 2024-03-31
```

Backtest multiple symbols:
```bash
python backtest.py --symbols AAPL MSFT NVDA --start 2024-01-01 --end 2024-12-31
```

With custom parameters:
```bash
python backtest.py --symbols AAPL \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --initial-capital 50000 \
  --position-size 0.05 \
  --interval 5m
```

Save results to JSON:
```bash
python backtest.py --symbols AAPL MSFT --start 2024-01-01 --end 2024-12-31 --output results.json
```

### Data Caching

The backtest engine caches downloaded data in the `cache/` directory:
```
cache/
├── AAPL/
│   ├── 2024-01-01_5m.csv
│   ├── 2024-01-02_5m.csv
│   └── ...
└── MSFT/
    ├── 2024-01-01_5m.csv
    └── ...
```

Force refresh cached data:
```bash
python backtest.py --symbols AAPL --start 2024-01-01 --end 2024-01-31 --force-refresh
```

### Running Backtest Tests

```bash
pytest test_backtest.py -v
```

### Backtest Parameters

- `--symbols`: Stock ticker symbols (space-separated)
- `--start`: Start date (YYYY-MM-DD)
- `--end`: End date (YYYY-MM-DD)
- `--interval`: Data interval (default: 5m) - Options: 1m, 5m, 15m, 1h, 1d
- `--initial-capital`: Starting capital (default: 10000)
- `--position-size`: Position size as % of capital (default: 0.1 = 10%)
- `--cache-dir`: Cache directory path (default: cache)
- `--force-refresh`: Force re-download of cached data
- `--output`: Save results to JSON file

### Example Output

```
============================================================
BACKTEST RESULTS
============================================================

AAPL:
  Total Trades: 45
  Winners: 28
  Losers: 17
  Win Rate: 62.2%
  Total P&L: $2,450.00

MSFT:
  Total Trades: 38
  Winners: 23
  Losers: 15
  Win Rate: 60.5%
  Total P&L: $1,890.50

------------------------------------------------------------
OVERALL:
  Total Trades: 83
  Winners: 51
  Overall Win Rate: 61.4%
  Total P&L: $4,340.50
============================================================
```

## Notes & Caveats
- The scanner uses `yfinance` to download intraday data. Data availability depends on the provider and may be incomplete. The scanner includes simple retry logic.
- The script returns an empty signal list when data is insufficient; it does not raise on network errors.
- PNG generation requires Chrome/Chromium (installed automatically via `kaleido`).

## License
MIT-style (for personal use)
