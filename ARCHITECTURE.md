# Break & Retest Strategy - Code Architecture

## Shared Code Principle

The backtest engine and live scanner share ALL detection and grading logic to ensure consistency. When you update signal grading criteria, the changes automatically apply to both systems.

## Module Structure

### 1. `signal_grader.py` - Signal Quality Assessment (SHARED)
**Purpose**: Grades individual components and calculates overall signal quality

**Functions**:
- `grade_breakout_candle()` - Grades breakout candle quality (A/B/C tiers)
- `grade_retest()` - **NEW: Precision-based retest grading with distance measurement**
  - A-grade: "Tap and Go" - Wick touches level, pierce ≤ 10% of range
  - B-grade: Moderate pierce (10-30%), close holds
  - C-grade: Comes close (1-2 candle widths) but doesn't touch
  - Rejects: Too far (> 2 candle widths) or high volume
- `grade_risk_reward()` - Grades R/R ratio (✅/⚠️/❌)
- `grade_market_context()` - Grades market conditions (✅/⚠️/❌)
- `grade_continuation()` - Grades ignition/continuation (POST-ENTRY only)
- `calculate_overall_grade()` - Combines pre-entry grades → A+/A/B/C
- `generate_signal_report()` - Formats human-readable signal report

**Documentation**: See `RETEST_GRADING.md` and `RETEST_EXAMPLES.md` for detailed criteria

**Used by**:
- ✅ `backtest.py`
- ✅ `break_and_retest_strategy.py` (live scanner)
- ✅ Unit tests

### 2. `break_and_retest_detection.py` - Pattern Detection (SHARED)
**Purpose**: Detects breakout, retest, and ignition patterns

**Functions**:
- `detect_breakout_5m()` - Finds breakouts on 5m timeframe with VWAP filter
- `detect_retest_and_ignition_1m()` - Finds retest+ignition on 1m timeframe
- `detect_retest_and_ignition_5m()` - Finds retest+ignition on 5m (fallback)
- `scan_for_setups()` - Main entry point that orchestrates detection
- `is_strong_body()` - Helper to check candle body strength

**Used by**:
- ✅ `backtest.py` (via `scan_for_setups()`)
- ✅ `break_and_retest_strategy.py` (via `scan_for_setups()`)

### 3. `backtest.py` - Backtesting Engine
**Purpose**: Historical simulation and performance analysis

**Key Features**:
- Downloads and caches 5m/1m historical data
- Calculates VWAP for each trading day
- Calls `scan_for_setups()` to find patterns
- Calls grading functions from `signal_grader.py`
- Simulates trade execution (first-hit stop/target)
- Filters by grade (--min-grade) and breakout tier (--breakout-tier)
- Generates performance reports and Markdown summaries

**Shared Code Used**:
- `scan_for_setups()` from `break_and_retest_detection.py`
- All grading functions from `signal_grader.py`

### 4. `break_and_retest_strategy.py` - Live Scanner
**Purpose**: Real-time market scanning and alert generation

**Key Features**:
- Downloads live 5m/1m intraday data
- Calculates VWAP for current session
- Calls `scan_for_setups()` to find patterns
- Calls grading functions from `signal_grader.py`
- Displays signals with formatted reports
- Can run on schedule or manually

**Shared Code Used**:
- `scan_for_setups()` from `break_and_retest_detection.py`
- All grading functions from `signal_grader.py`

### 5. `config.json` - Configuration (SHARED)
**Purpose**: Central configuration for all strategy parameters

**Shared Parameters**:
```json
{
  "tickers": ["AAPL", "AMZN", ...],
  "retest_volume_gate_ratio": 0.15,
  "retest_B_level_epsilon_pct": 0.10,
  "retest_B_structure_soft": true,
  "breakout_A_upper_wick_max": 0.20,
  "breakout_B_body_max": 0.72
}
```

**Used by**:
- ✅ `backtest.py`
- ✅ `break_and_retest_strategy.py`

## How to Update Grading Criteria

### ✅ CORRECT: Modify shared modules

1. **Update breakout criteria**: Edit `signal_grader.grade_breakout_candle()`
2. **Update retest criteria**: Edit `signal_grader.grade_retest()`
3. **Update detection logic**: Edit `break_and_retest_detection.py` functions
4. **Update config parameters**: Edit `config.json`

Changes automatically apply to BOTH backtest and live scanner.

### ❌ INCORRECT: Direct modification

- Don't add grading logic directly in `backtest.py`
- Don't add grading logic directly in `break_and_retest_strategy.py`
- Don't duplicate detection functions

## Testing Strategy

When updating grading criteria:

1. **Unit Tests**: Run `pytest test_signal_grader.py` to validate grading functions
2. **Backtest**: Run historical backtest to measure impact on performance
3. **Live Test**: Run live scanner to verify real-time behavior matches backtest

All three use the same shared code, ensuring consistency.

## VWAP Filter Implementation

**Shared Location**: `break_and_retest_detection.detect_breakout_5m()`

**Filter Logic**:
```python
# LONG trades: close > VWAP
vwap_aligned_long = (vwap is None) or (row["Close"] > vwap)

# SHORT trades: close < VWAP
vwap_aligned_short = (vwap is None) or (row["Close"] < vwap)
```

**Applied by**:
- ✅ Backtest engine (calculates VWAP per day in `_scan_continuous_data()`)
- ✅ Live scanner (calculates VWAP per session in `scan_ticker()`)

## Summary

**Single Source of Truth**:
- Detection logic: `break_and_retest_detection.py`
- Grading logic: `signal_grader.py`
- Configuration: `config.json`

**Consistency Guarantee**: When you update shared modules, both backtest and live scanner automatically use the new criteria. No duplicate code exists.
