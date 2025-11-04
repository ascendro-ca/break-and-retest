# Break & Retest Strategy — Architecture

## Shared Code Principle

The backtester and live scanner share ALL detection and grading logic. Update once, used everywhere.

## Pipeline Overview (Stages 1–4)

- Stage 1 — Opening Range: `stage_opening_range.detect_opening_range()`
- Stage 2 — Breakout (5m): `stage_breakout.detect_breakouts()`
  - Enforces volume >= 20‑SMA by default
  - Relaxed criteria with tolerance for gap continuations:
    - Open tolerance: ≤ OR high + 0.25% (long) or ≥ OR low - 0.25% (short)
    - Close tolerance: ≥ OR high - $0.01 (long) or ≤ OR low + $0.01 (short)
- Stage 3 — Retest (1m): `stage_retest.detect_retest()`
  - Retest search strictly after breakout 5m candle closes
  - Enforces VWAP alignment with 0.05% price buffer
- Stage 4 — Ignition (1m): `stage_ignition.detect_ignition()` (Level 2+)
  - Post‑entry continuation; not required for Level 0/1

Orchestration: `trade_setup_pipeline.TradeSetupPipeline`

- Levels:
  - 0 — Candidates only (Stages 1‑3)
  - 1 — Trade execution with base criteria (Stages 1‑3)
  - 2+ — Enhanced filtering (includes Stage 4 ignition)

## Module Structure

### 1) `trade_setup_pipeline.py` — Orchestrator (SHARED)
Runs the stages in sequence and applies level‑dependent logic. Accepts optional custom filter callables for each stage.

### 2) Stage modules (SHARED)
- `stage_opening_range.py` — OR detection
- `stage_breakout.py` — 5m breakout with VWAP + `vol_ma_20`
- `stage_retest.py` — 1m retest after breakout close
- `stage_ignition.py` — 1m ignition after retest (Level 2+)

### 3) `signal_grader.py` — Grading (SHARED)
Grades breakout, retest, ignition, R/R, and market context. See `RETEST_GRADING.md` and `RETEST_EXAMPLES.md`.

### 4) `backtest.py` — Backtesting Engine
Cache‑only historical simulation with on‑demand 1m loading:
- Loads 5m sessions per day to scan for breakouts
- Only when a breakout is found, loads a small 1m window to find retest/ignition
- Uses `TradeSetupPipeline` and `signal_grader.py`
- Supports grade/tier filters, pipeline level, JSON output

### 5) `break_and_retest_strategy.py` — Live Scanner
Feeds recent 5m and 1m slices into `TradeSetupPipeline`, applies grading, and produces real‑time candidates/alerts.

### 6) `cache_utils.py` — Cache & Integrity
Unified helpers for reading/writing `cache/<SYMBOL>/<YYYY-MM-DD>_{1m|5m}.csv` and validating:
- Interval canonicalization (`1m`, `5m`, `1h`)
- Day‑file normalization and timestamp ordering
- Gap/duplication/misalignment checks and cross‑interval 1m→5m consistency

### 7) `stockdata_retriever.py` — Data Loader/Verifier
Stockdata.org fetcher that populates canonical cache and resamples 1m→5m when needed. Includes full‑cache integrity report and coverage summary.

## Configuration (`config.json`)

Shared parameters (subset):
```json
{
  "tickers": ["AAPL", "AMZN", "META", "MSFT", "NVDA", "TSLA", "SPOT", "UBER"],
  "initial_capital": 7500,
  "retest_volume_gate_ratio": 0.15,
  "retest_B_level_epsilon_pct": 0.20,
  "retest_B_structure_soft": true,
  "breakout_A_upper_wick_max": 0.20,
  "breakout_B_body_max": 0.72
}
```

## Updating Logic Safely

Do:
- Adjust detection in stage modules
- Adjust grading in `signal_grader.py`
- Tune parameters in `config.json`

Avoid:
- Duplicating detection/grading in `backtest.py` or live scanner

## Testing

- Unit tests for stages/pipeline: `test_stage_modules.py`, `test_trade_setup_pipeline.py`
- Cache integrity: `test_cache_integrity.py`
- Backtest coverage: `test_backtest.py`

## Volume Filter (Stage 2) & VWAP Alignment (Stage 3)

**Stage 2 - Breakout Volume Filter** applied in `stage_breakout.detect_breakouts()`:
```python
vol_ok = float(row["Volume"]) >= float(row.get("vol_ma_20", 0.0))
brk_long = prev["High"] <= or_high and row["Close"] > or_high and vol_ok
```

**Stage 3 - VWAP Alignment Filter** applied in `stage_retest.detect_retest()`:
```python
vwap_buffer = abs(vwap_val) * 0.0005  # 0.05% price tolerance
if direction == "long":
    vwap_aligned = c >= (vwap_val - vwap_buffer)
else:  # short
    vwap_aligned = c <= (vwap_val + vwap_buffer)
```

**Rationale**: Moving VWAP alignment to the retest stage reduces false negatives at breakout while still ensuring institutional alignment at entry point. The 0.05% buffer provides reasonable tolerance for intrabar price action.

## Summary

Single sources of truth:
- Detection: Stage modules + `trade_setup_pipeline`
- Grading: `signal_grader.py`
- Data: canonical cache via `cache_utils.py` and `stockdata_retriever.py`
