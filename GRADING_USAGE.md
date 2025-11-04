# Grading Systems Usage Guide

The backtest engine uses the **Points grading system** (100-point scoring) for evaluating trade setups, implementing the `Grader` protocol defined in `grading/base.py`.

## Points System (Default)

- **Module:** `grading/grading_points.py`
- **CLI flag:** `--grading-system points` (default)
- **Type:** Quantitative scoring (0-100) mapped to A+/A/B/C/D
- **Spec:** See `GRADING_SYSTEMS.md`

**Scoring:**
- **Breakout (30 pts):** Pattern base (8-20) + volume bonus (0-5)
- **Retest (30 pts):** Pattern base (7-18) + volume bonus (0-5)
- **Ignition (30 pts):** Pattern base (9-20) + volume bonus (0-5) — post-entry only
- **Context (10 pts):** VWAP (5) + trend (3) + HTF confluence (2)

**Pre-entry grading** (pipeline gate): Uses Breakout + Retest + Ignition (max 90 pts)
- Component thresholds (out of 30 each):
  - A+: ≥28.5 (95%)
  - A: ≥25.8 (86%)
  - B: ≥21 (70%)
  - C: ≥16.8 (56%)
  - D: <16.8 (❌)

**Report grading** (full 100-pt): Includes all four components
- A+: ≥95/100
- A: ≥86/100
- B: ≥70/100
- C: ≥56/100
- D: <56/100

---

## CLI Usage

### Run backtest with default grading:
```bash
python backtest.py --symbols AAPL --start 2025-07-01 --end 2025-07-31 --level 2
```

### Apply minimum grade filter:
```bash
python backtest.py --symbols AAPL --level 2 --min-grade B --last-days 30
```

---

## Pipeline Levels & Grading

- **Level 0:** Candidates only (no grading, no trades)
- **Level 1:** Trades with base criteria (grading computed, no filtering)
- **Level 2+:** Quality filters enforced
  - Breakout, Retest, and Ignition **must all be C or higher** (not ❌/D)
  - Entry occurs at Stage 4 ignition (after confirmed ignition candle)
  - Optional `--min-grade` filter to raise overall threshold

---

## Programmatic API

```python
from grading import get_grader

# Get grading system
grader = get_grader("basic")  # or "points"

# Grade components
breakout_grade, desc = grader.grade_breakout_candle(
    candle={"Open": 100, "High": 102, "Low": 100, "Close": 101.5, "Volume": 1000000},
    vol_ratio=1.5,
    body_pct=0.75,
    level=100.0,
    direction="long",
)

# Compute overall
overall = grader.calculate_overall_grade({
    "breakout": breakout_grade,
    "retest": retest_grade,
    "rr": "✅",
    "market": "⚠️",
})

# Generate report
report = grader.generate_signal_report(signal_dict)
print(report)
```

---

## Adding New Grading Systems

1. Implement `Grader` protocol in `grading/grading_<name>.py`
2. Register in `grading/__init__.py`:
   ```python
   from .grading_custom import CustomGrader
   _GRADERS["custom"] = CustomGrader()
   ```
3. Update CLI choices in `backtest.py`
4. Add unit tests in `test_grading_<name>.py`
5. Document here

---

## Testing

Run grading tests:
```bash
pytest test_grading_points.py -v
```

Run full test suite:
```bash
pytest -v  # All tests should pass
```

---

## Notes

- **Grading is stateful** per signal evaluation
- **Pre-entry** (Breakout + Retest + Ignition) gates pipeline at Level 2+
- **Post-entry** (Continuation) computed for first bar after ignition entry
- **Context** computed when data available (VWAP always 5 pts at Level 0+)
- **Level 2 entry** occurs at Stage 4 ignition (not at retest)

---

## References

- **100-point spec:** `GRADING_SYSTEMS.md`
- **Grader interface:** `grading/base.py`
- **Registry:** `grading/__init__.py`
- **Points implementation:** `grading/grading_points.py`
- **Unit tests:** `test_grading_points.py`
