# Break & Re-Test Strategy

Scanner, backtester, and modular pipeline for a 5‑minute Opening‑Range break and 1‑minute retest continuation setup.

## Strategy docs
- `STRATEGY_SPEC.md` — What the strategy is (rules and criteria)
- `STRATEGY_DESIGN.md` — Why the rules exist (rationale and trade-offs)
- `STRATEGY_IMPLEMENTATION.md` — How to implement (formulas, thresholds, pseudocode)

## Features
- 4‑stage detection pipeline (Opening Range → Breakout → Retest → Ignition)
- Pipeline levels:
  - Level 0: Candidates only (Stages 1‑3) — fast discovery/no trades
  - Level 1: Trades on base criteria (Stages 1‑3), no ignition required
  - Level 2+: Enhanced filtering incl. Stage 4 ignition
- Memory‑efficient, on‑demand 1‑minute loading during backtests
- Local, per‑day cache with integrity checks (1m/5m)
- Stockdata.org fetcher with 1m→5m resampling to fill cache
- First‑trade‑of‑day analysis utility
- Optional visualization from tests (HTML+PNG), grouped viewer via `--show-test`

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

2. Populate the cache (Stockdata.org; requires API key):

```bash
python stockdata_retriever.py --symbols AAPL MSFT --intervals 1m 5m \
  --start 2025-10-15 --end 2025-10-16 --apikey $STOCK_DATA_API_KEY
```

3. Run live scanner from CLI for default tickers:

```bash
python break_and_retest_live_scanner.py
```

4. Scan a single ticker and save a chart:

```bash
python visualize_results.py --ticker AAPL
```

5. Run unit tests and generate visualizations:

```bash
pytest test_break_and_retest_strategy.py
```

6. View test visualizations:

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
- Core pipeline
  - `stage_opening_range.py` — Stage 1 (OR)
  - `stage_breakout.py` — Stage 2 (5m breakout with VWAP + vol SMA)
  - `stage_retest.py` — Stage 3 (1m post‑breakout retest)
  - `stage_ignition.py` — Stage 4 (post‑entry continuation)
  - `trade_setup_pipeline.py` — Orchestrates Stages 1–4 and levels
- Strategy and grading
  - `signal_grader.py` — A/B/C grading for breakout/retest/ignition + overall
  - `break_and_retest_strategy.py` — live scanner wiring
- Backtesting and data
  - `backtest.py` — backtesting engine with on‑demand 1m loading
  - `cache_utils.py` — cache I/O + integrity verification
  - `stockdata_retriever.py` — Stockdata.org cache populator and integrity reporter
- Analysis and tooling
  - `first_trade_analysis.py` — “first trade of day” analysis
  - `visualize_results.py` — plot HTML/PNG; grouped test viewer
- Tests (examples)
  - `test_stage_modules.py`, `test_trade_setup_pipeline.py`, `test_cache_integrity.py`, `test_backtest.py`
  - functional: `test_functional.py`

## Backtesting

The backtesting engine allows you to test the Break & Re-Test strategy on historical data.

### Features
- Memory‑efficient: loads 1‑minute windows on demand only when a 5m breakout is found
- Cache‑only data access (populate via `stockdata_retriever.py` first)
- Multi‑symbol backtests with per‑symbol and overall stats
- Configurable: initial capital, position sizing, pipeline level, grade filters

### Basic Usage

Prerequisite: fill `cache/` using Stockdata.org (see Quick Start step 2).

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

Run with pipeline levels and grade filters:
```bash
python backtest.py --symbols AAPL MSFT \
  --start 2025-09-01 --end 2025-09-30 \
  --level 0                # Level 0: candidates only (Stages 1–3)
  --min-grade A            # optional: A or better
```

Save results to JSON:
```bash
python backtest.py --symbols AAPL MSFT --start 2024-01-01 --end 2024-12-31 --output results.json
```

### Data Caching

Cache is organized per symbol and per day using canonical intervals (`1m`, `5m`):
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

Populate or repair cache with the Stockdata.org tool:
```bash
# Populate 1m and 5m (5m is resampled from 1m when missing)
python stockdata_retriever.py --symbols AAPL MSFT --intervals 1m 5m \
  --start 2025-10-15 --end 2025-10-16 --apikey $STOCK_DATA_API_KEY

# Repair any accidental multi-day files in canonical cache
python stockdata_retriever.py --repair-cache-splits
```

Force refresh cached data in backtest (clears cache dir first):
```bash
python backtest.py --symbols AAPL --start 2024-01-01 --end 2024-01-31 --force-refresh
```

### Running Backtest Tests

```bash
pytest test_backtest.py -v
```

### Backtest Parameters (subset)

- `--symbols`: Stock symbols (space-separated)
- `--start` / `--end`: Date range (YYYY-MM-DD)
- `--initial-capital`: Starting capital (default from `config.json` or 7500)
- `--position-size`: Position size as % of capital (default: 0.1 = 10%)
- `--leverage`: Max notional leverage (1.0 = no leverage). Caps shares so entry*shares <= cash*leverage
- `--level`: Pipeline level (0=candidates only; 1=trades; 2+=enhanced)
- `--min-grade`: Minimum overall grade to include (A+/A/B/C)
- `--breakout-tier`: Filter by breakout tier (A/B/C)
- `--cache-dir`: Cache directory path (default: cache)
- `--force-refresh`: Clear cache dir before run
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
- Data provider: Stockdata.org for intraday (minute/hour). Use `stockdata_retriever.py` to populate cache.
- Canonical cache intervals are `1m` and `5m`. Legacy `*_1min/*_5min` can be normalized via `--normalize-cache`.
- Backtester loads 1‑minute windows on demand only after detecting a 5m breakout.
- Timestamps are normalized to America/New_York in cache for session alignment.
- PNG generation requires Chrome/Chromium (installed automatically via `kaleido`).

## First trade of day analysis

Analyze “first trade per calendar day” variants from a backtest results JSON:

```bash
python first_trade_analysis.py \
  --input backtest_results/full_jul_oct2025_level1.json \
  --output backtest_results/full_jul_oct2025_level1_first_trade.md
```

Options:
- `--global-only` — single earliest trade across all symbols per day
- `--symbol-only` — earliest trade per symbol per day

## License
MIT-style (for personal use)
