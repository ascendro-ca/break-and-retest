# Break & Re-Test Strategy

A comprehensive trading system for detecting and trading Opening Range breakouts with retest confirmations on intraday timeframes.

## Overview

The Break & Re-Test strategy identifies high-probability intraday continuation setups by detecting:
1. **Opening Range** establishment (first 5-30 minutes)
2. **Breakout** above/below the range with volume and momentum confirmation
3. **Retest** of the breakout level on smaller timeframe (pullback + bounce)
4. **Ignition** continuation move in the breakout direction

This project provides a complete toolkit including detection algorithms, backtesting infrastructure, live scanning capabilities, and comprehensive analysis tools.

## Problem Statement

Traditional breakout trading suffers from:
- **False breakouts**: Price breaks a level but immediately reverses
- **Poor entry timing**: Entering too early (before confirmation) or too late (after the move)
- **Lack of confluence**: Single-indicator signals without multi-timeframe confirmation
- **No quality grading**: All signals treated equally regardless of setup strength

This system solves these problems by:
- Requiring **retest confirmation** on a faster timeframe (1-minute) after the initial breakout
- Using **multi-stage detection** with strict structural requirements at each phase
- Implementing **A/B/C quality grading** across 5 dimensions (breakout, retest, R/R, continuation, market context)
- Providing **memory-efficient backtesting** with on-demand data loading for accurate historical validation

## Documentation

### Strategy Documentation
- **[STRATEGY_SPEC.md](STRATEGY_SPEC.md)** — **What**: Complete rules, entry/exit criteria, and signal requirements
- **[STRATEGY_DESIGN.md](STRATEGY_DESIGN.md)** — **Why**: Design rationale, trade-offs, and grading philosophy
- **[STRATEGY_IMPLEMENTATION.md](STRATEGY_IMPLEMENTATION.md)** — **How**: Implementation details, formulas, thresholds, and pseudocode
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — System architecture, pipeline design, and module structure

### Additional Resources
- **[RETEST_EXAMPLES.md](RETEST_EXAMPLES.md)** — Real trade examples with annotated charts
- **[RETEST_UPDATE_SUMMARY.md](RETEST_UPDATE_SUMMARY.md)** — Historical updates to retest detection logic

## Capabilities

### 1. Detection Pipeline (4 Stages)
Multi-stage algorithmic detection with progressive filtering:
- **Stage 1: Opening Range** — Identifies consolidation in first 5-30 minutes
- **Stage 2: Breakout** — Detects 5-minute breakout
  - Base (Level 0/1): Open inside OR; Close ≥ OR high (long) or ≤ OR low (short); VWAP-aligned (Close > VWAP for long, < VWAP for short); not the first 5m candle
  - Note: Volume baseline is not enforced at base; it is enforced at Grade C (vol ≥ 1.0× 20-bar MA) when grading is used
- **Stage 3: Retest** — Finds 1-minute retest patterns (pullback + bounce)
- **Stage 4: Ignition** — Validates continuation after entry

### 2. Pipeline Levels (Quality Filtering)
- **Level 0**: Fast candidate discovery (Stages 1-3 only) — no trades executed
- **Level 1**: All trades meeting base structural criteria — no grade filtering
- **Level 2**: Enhanced filtering with A/B/C grading + Stage 4 ignition metadata

At Levels 0–1, Stage 2’s base filter is intentionally permissive and does not enforce volume; the baseline volume requirement (vol ≥ 1.0× 20-bar MA) now lives in Grade C breakout criteria when grading is applied.

**Grading System**: Each signal receives A/B/C/❌ grades across 5 dimensions:
- Breakout quality (momentum, volume, distance from range)
- Retest quality (pullback depth, bounce strength, timing)
- Risk/Reward ratio
- Continuation strength (post-entry momentum)
- Market context (trend alignment, volatility)

**C-Grade Philosophy**: Grade C represents the **minimum acceptable quality threshold**, not a weakness requirement. Level 2 accepts setups graded A, B, or C overall—even if individual components are stronger (e.g., C-grade retest + A-grade breakout = acceptable C overall). The filter enforces directional alignment (bullish candles for long, bearish for short) and rejects structural failures (❌).

### 3. Apps and Tools

#### Live Scanner
Real-time detection on market hours:
```bash
python break_and_retest_live_scanner.py           # Single scan
./find_break_and_retest.sh                        # Continuous scanning (1-min intervals)
./find_break_and_retest.sh --interval 30s         # Custom scan frequency
```

#### Backtesting Engine
Memory-efficient historical testing with on-demand 1-minute data loading:
```bash
python backtest.py --symbols AAPL MSFT \
  --start 2025-07-01 --end 2025-10-31 \
  --level 2 --min-grade C \
  --output backtest_results/my_test.json
```

Features:
- Multi-symbol support with per-symbol and aggregate statistics
- Configurable capital allocation, position sizing, and leverage
- Pipeline level filtering (0/1/2+) with grade thresholds
- Cache-only data access (populate with `stockdata_retriever.py`)
- JSON output for downstream analysis

#### Visualization Tools
```bash
python visualize_results.py --ticker AAPL                    # Single ticker chart
python visualize_results.py --show-test                      # View test outputs
python visualize_results.py --demo --demo-scenario long      # Demo scenarios
```

Generates interactive HTML (Plotly) and static PNG snapshots with annotated entry/exit points.

#### Analysis Utilities
- **First-trade analysis**: Extract "first trade of day" patterns from backtest results
  ```bash
  python first_trade_analysis.py --input results.json --output analysis.md
  ```
- **Trade pattern analysis**: Study loss patterns, breakout characteristics, etc. (see `analyze_*.py`)

#### Data Management
```bash
# Populate cache from Stockdata.org API
python stockdata_retriever.py --symbols AAPL MSFT \
  --intervals 1m 5m \
  --start 2025-10-01 --end 2025-10-31 \
  --apikey $STOCK_DATA_API_KEY

# Repair cache integrity
python stockdata_retriever.py --repair-cache-splits
```

Cache structure: `cache/{SYMBOL}/{DATE}_{INTERVAL}.csv` (e.g., `cache/AAPL/2025-10-15_5m.csv`)

### 4. Testing Infrastructure
Comprehensive unit and functional tests:
```bash
make test                    # Run all tests
pytest test_backtest.py -v   # Backtest tests
pytest test_stage_modules.py # Stage detection tests
```

Test outputs automatically generate visualizations in `logs/test_*.html` and `logs/test_*.png`.

## Getting Started

### Requirements
- Python 3.8+
- Chrome/Chromium (automatically installed via `kaleido` for PNG generation)
- Stockdata.org API key for historical data

### Installation

1. **Clone and setup virtual environment**:
```bash
git clone <repository-url>
cd break-and-retest
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Populate data cache** (required for backtesting and analysis):
```bash
python stockdata_retriever.py --symbols AAPL MSFT NVDA \
  --intervals 1m 5m \
  --start 2025-10-01 --end 2025-10-31 \
  --apikey $STOCK_DATA_API_KEY
```

4. **Run tests** to verify installation:
```bash
make test
```

### Quick Examples

**Live scan** (checks current market conditions):
```bash
python break_and_retest_live_scanner.py
```

**Backtest** a single month:
```bash
python backtest.py --symbols AAPL --start 2025-10-01 --end 2025-10-31 --level 2
```

**Visualize** a specific ticker:
```bash
python visualize_results.py --ticker AAPL
```

**View demo scenarios**:
```bash
python visualize_results.py --demo --demo-scenario long
```

## Usage Guide

### Live Scanner

**Single scan** (checks current market and exits):
```bash
python break_and_retest_live_scanner.py
```

**Continuous scanning** (runs every minute until stopped):
```bash
./find_break_and_retest.sh
```

**Options**:
- `--once` — Run single scan and exit
- `--interval 30s` — Custom scan frequency
- `--daemon` — Run in background
- `--no-align` — Don't align to clock minutes

Press **Ctrl+C** to stop continuous scanning.

### Backtesting

**Basic backtest** (single symbol, default settings):
```bash
python backtest.py --symbols AAPL --start 2025-07-01 --end 2025-10-31
```

**Multi-symbol backtest** with custom parameters:
```bash
python backtest.py \
  --symbols AAPL MSFT NVDA AMZN \
  --start 2025-01-01 --end 2025-12-31 \
  --initial-capital 50000 \
  --position-size 0.05 \
  --level 2 \
  --min-grade C \
  --output backtest_results/q1_2025_level2.json
```

**Key Parameters**:
- `--symbols`: Space-separated ticker symbols
- `--start` / `--end`: Date range (YYYY-MM-DD)
- `--initial-capital`: Starting capital (default: 7500)
- `--position-size`: Position size as % of capital (default: 0.1 = 10%)
- `--leverage`: Max notional leverage (default: 1.0 = no leverage)
- `--level`: Pipeline level (0=candidates, 1=all trades, 2+=graded filtering)
- `--min-grade`: Minimum overall grade (A+/A/B/C)
- `--breakout-tier`: Filter by breakout component grade (A/B/C)
- `--output`: Save results to JSON file
- `--force-refresh`: Clear cache before run

**Level 2 Filtering**: At `--level 2`, signals are filtered by overall grade. `--min-grade C` accepts setups graded A, B, or C overall. Remember: **C-grade is a minimum quality threshold**, not a weakness requirement. A C-grade setup can have A-grade components (e.g., strong breakout + weaker retest). All candle strength types (1=marubozu → 5=doji) are accepted as long as direction aligns with the trade (bullish for long, bearish for short).

**Example Output**:
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

### Visualization

**Single ticker chart**:
```bash
python visualize_results.py --ticker AAPL
```

**View test outputs** (grouped by test run):
```bash
python visualize_results.py --show-test
```

**Demo mode** with built-in scenarios:
```bash
python visualize_results.py --demo --demo-scenario long
python visualize_results.py --demo --demo-scenario short
python visualize_results.py --demo --demo-scenario long_fail
python visualize_results.py --demo --demo-scenario short_fail
```

**CI/headless mode** (generate files without opening browser):
```bash
python visualize_results.py --ticker AAPL --no-open
python visualize_results.py --show-test --no-open
```

Test runs automatically generate:
- **HTML files**: Interactive Plotly charts in `logs/test_*.html`
- **PNG snapshots**: Static images in `logs/test_*.png`

### Data Management

**Populate cache** from Stockdata.org:
```bash
python stockdata_retriever.py \
  --symbols AAPL MSFT NVDA \
  --intervals 1m 5m \
  --start 2025-10-01 --end 2025-10-31 \
  --apikey $STOCK_DATA_API_KEY
```

**Cache structure**:
```
cache/
├── AAPL/
│   ├── 2025-10-01_1m.csv
│   ├── 2025-10-01_5m.csv
│   ├── 2025-10-02_1m.csv
│   ├── 2025-10-02_5m.csv
│   └── ...
└── MSFT/
    └── ...
```

**Repair cache** (normalize legacy formats):
```bash
python stockdata_retriever.py --repair-cache-splits
```

**Force refresh** in backtest (clears and repopulates):
```bash
python backtest.py --symbols AAPL --start 2025-10-01 --end 2025-10-31 --force-refresh
```

### Analysis Tools

**First-trade analysis** (extract "first trade of day" patterns):
```bash
python first_trade_analysis.py \
  --input backtest_results/my_backtest.json \
  --output backtest_results/my_backtest_first_trade.md
```

Options:
- `--global-only`: Single earliest trade across all symbols per day
- `--symbol-only`: Earliest trade per symbol per day

**Trade pattern analysis**:
- `analyze_trade_patterns.py`: Study win/loss patterns
- `analyze_breakout_patterns.py`: Examine breakout characteristics
- `analyze_losses.py`: Deep-dive into losing trades

### Testing

**Run all tests**:
```bash
make test
```

**Run specific test suites**:
```bash
pytest test_backtest.py -v               # Backtest engine tests
pytest test_stage_modules.py -v          # Stage detection tests
pytest test_break_and_retest_strategy.py # Strategy integration tests
pytest test_cache_integrity.py           # Cache validation tests
```

**Generate coverage report**:
```bash
pytest --cov=. --cov-report=html
```

## Project Structure

### Core Pipeline Modules
- **`stage_opening_range.py`** — Stage 1: Opening Range detection
- **`stage_breakout.py`** — Stage 2: 5-minute breakout with volume confirmation
- **`stage_retest.py`** — Stage 3: 1-minute retest pattern detection with VWAP alignment (0.05% buffer)
- **`stage_ignition.py`** — Stage 4: Post-entry continuation validation
- **`trade_setup_pipeline.py`** — Orchestrates all 4 stages and pipeline levels

### Strategy & Grading
- **`signal_grader.py`** — A/B/C grading across 5 dimensions (breakout, retest, R/R, continuation, context)
- **`break_and_retest_strategy.py`** — Live scanner integration and signal generation

### Backtesting & Data
- **`backtest.py`** — Backtesting engine with memory-efficient on-demand data loading
- **`cache_utils.py`** — Cache I/O, integrity verification, and validation
- **`stockdata_retriever.py`** — Stockdata.org API client for cache population

### Analysis & Visualization
- **`visualize_results.py`** — Generate HTML/PNG charts with annotated signals
- **`visualize_trade_results.py`** — Trade-specific visualization
- **`first_trade_analysis.py`** — Extract "first trade of day" patterns
- **`analyze_trade_patterns.py`** — Win/loss pattern analysis
- **`analyze_breakout_patterns.py`** — Breakout characteristic analysis
- **`analyze_losses.py`** — Deep-dive into losing trades

### Utilities
- **`time_utils.py`** — Time zone handling and market hours
- **`candle_patterns.py`** — Candle classification and pattern detection

### Test Suites
- **`test_stage_modules.py`** — Unit tests for each stage module
- **`test_trade_setup_pipeline.py`** — Pipeline integration tests
- **`test_backtest.py`** — Backtesting engine tests
- **`test_break_and_retest_strategy.py`** — Strategy integration tests
- **`test_cache_integrity.py`** — Cache validation tests
- **`test_signal_grader.py`** — Grading system tests
- **`test_functional.py`** — End-to-end functional tests

### Configuration
- **`config.json`** — Default settings (capital, position size, tickers, etc.)
- **`requirements.txt`** — Python dependencies
- **`pytest.ini`** — Test configuration
- **`Makefile`** — Common commands (test, clean, etc.)

## Technical Notes
```


### Data Provider
- Uses Stockdata.org API for intraday minute-level data
- Cache organized per symbol/day with canonical intervals (`1m`, `5m`)
- Timestamps normalized to America/New_York for market session alignment

### Memory Efficiency
- Backtester loads 1-minute windows on-demand only after detecting 5-minute breakout
- Avoids loading full multi-day 1-minute datasets into memory
- Cache-only access prevents repeated API calls

### Cache Management
- Canonical format: `cache/{SYMBOL}/{DATE}_{INTERVAL}.csv`
- Legacy formats (`*_1min`, `*_5min`) can be normalized with `--normalize-cache`
- Integrity checks detect corrupted or multi-day files
- Use `stockdata_retriever.py --repair-cache-splits` to fix issues

### Visualization
- PNG generation requires Chrome/Chromium (auto-installed via `kaleido`)
- HTML outputs use Plotly for interactive charts
- Test runs automatically generate both HTML and PNG

## Contributing

This is currently a personal project. If you'd like to contribute:
1. Review the strategy documentation (STRATEGY_SPEC.md, STRATEGY_DESIGN.md)
2. Run the test suite: `make test`
3. Follow existing code patterns and add tests for new features

## License

MIT-style (for personal use)

---

**For detailed strategy rules and implementation details, see:**
- [STRATEGY_SPEC.md](STRATEGY_SPEC.md) — Complete rules and criteria
- [STRATEGY_DESIGN.md](STRATEGY_DESIGN.md) — Design rationale and philosophy
- [STRATEGY_IMPLEMENTATION.md](STRATEGY_IMPLEMENTATION.md) — Implementation formulas and pseudocode
- [ARCHITECTURE.md](ARCHITECTURE.md) — System architecture and design patterns
