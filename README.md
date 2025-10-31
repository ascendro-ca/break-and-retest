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
- `find_break_and_retest.sh` — continuous scanner wrapper script
- `conftest.py` — pytest configuration
- `pytest.ini` — pytest settings

## Notes & Caveats
- The scanner uses `yfinance` to download intraday data. Data availability depends on the provider and may be incomplete. The scanner includes simple retry logic.
- The script returns an empty signal list when data is insufficient; it does not raise on network errors.
- PNG generation requires Chrome/Chromium (installed automatically via `kaleido`).

## License
MIT-style (for personal use)
