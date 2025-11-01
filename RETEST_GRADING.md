# Retest Grading Criteria - Scarface Rules Precision

# Deprecated

This content has moved to `STRATEGY_IMPLEMENTATION.md`.

# Retest Grading (Scarface Rules)
# Retest Grading Criteria - Scarface Rules Precision
## Overview

The retest grading system measures **how precisely** the retest candle interacts with the breakout level. This is critical because the quality of the retest directly impacts the probability of the trade working.

**Key Principle**: The closer the wick comes to the level AND the cleaner the rejection, the higher the probability of success.

---

## Grading Scale (Long Setups)

### ✅ A-Grade: "Tap and Go" (Highest Probability)

**What it looks like:**
- Wick **touches or slightly pierces** the breakout level (support)
- Pierce depth ≤ 10% of candle range (minimal penetration)
- Close near the high (within 10% of high)
- Strong bullish body (≥ 60%)
- Green candle showing buying strength

**Why it's A-grade:**
> "The cleanest setups wick into the level once, hold, and go. That's institutional support defending the breakout."

**Example:**
```
Breakout level: $100.00
Retest candle:
  High:  $100.45
  Low:   $99.85  ← Wick pierces $100.00 by $0.15
  Close: $100.40 ← Closes just above level, near high
  Range: $0.60
  Pierce: 25% of range → A-grade ✅
```

**Report Example:**
```
Retest: A-grade tap: wick touched level, clean rejection (pierce: 4.2%) ✅
```

---

### ⚠️ B-Grade: Pierces Slightly But Holds (Acceptable)

**What it looks like:**
- Wick **touches or pierces** the breakout level
- Pierce depth 10-30% of candle range (moderate penetration)
- Close holds above level (can use epsilon tolerance)
- Moderate body (≥ 40%)
- Green or balanced candle

**Why it's B-grade:**
> "This is acceptable, but not ideal — indicates some selling pressure. Needs strong ignition candle to confirm buyer strength."

**Example:**
```
Breakout level: $100.00
Retest candle:
  High:  $100.60
  Low:   $99.65  ← Wick pierces $100.00 by $0.35
  Close: $100.05 ← Closes above, but not near high
  Range: $0.95
  Pierce: 37% of range → B-grade ⚠️
```

**Report Example:**
```
Retest: B-grade pierce: deeper penetration (pierce: 15.8%), but close held ⚠️
```

---

### ❌ Rejected — Near-Miss (No Touch)

**What it looks like:**
- Wick **does NOT touch** the breakout level
- But comes within **1-2 candle widths** of the level
- Close holds above level (with epsilon tolerance)
- Has a lower wick (attempted to test)
- Green candle

**Why it's rejected:**
> "Can be taken with context confluence (e.g. strong uptrend, VWAP below, HTF support below), but NOT a clean A+ tap → requires judgment."

**Example:**
```
Breakout level: $100.00
Retest candle:
  High:  $101.20
  Low:   $100.50  ← Wick came within 0.5 candle widths
  Close: $101.10
  Range: $0.70
  Decision: Reject — No touch ❌
```

**Report Example:**
```
Retest: Reject — near-miss (no touch) ❌
```

---

## Flipped Logic for Short Setups

For **SHORT** trades, mirror all criteria:

| Criteria | Long (Support) | Short (Resistance) |
|----------|---------------|-------------------|
| Wick direction | Lower wick tests support | Upper wick tests resistance |
| Pierce measurement | `low - level` (negative if below) | `high - level` (positive if above) |
| Close requirement | Close above level | Close below level |
| A-grade close | Near high | Near low |
| Candle color | Green (bullish) | Red (bearish) |

---

## Hard Reject Criteria

Regardless of grade, the retest will be **rejected (❌)** if:

1. **Volume too high**: `retest_vol_ratio > 0.60` (60% of breakout volume)
   - High volume = supply/demand absorption, not a clean retest

2. **Wick too far from level**: Distance > 2 candle widths
   - Example: "Retest too far: 3.4x candle widths from level"

3. **Close fails to hold**:
   - LONG: Close below level (even with epsilon)
   - SHORT: Close above level (even with epsilon)

---

## Configuration Parameters

These parameters control the grading thresholds:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `retest_vol_threshold` | 0.15 | Max retest volume ratio (hard fail if exceeded) |
| `b_level_epsilon_pct` | 0.10 | B-grade tolerance for close price (% of level) |
| `b_structure_soft` | true | Allow marginal body/wick structure for B-grade |

---

## Implementation Details

### Distance Calculation

**Candle widths** = How many candle ranges separate the wick from the level

```python
# LONG example
wick_distance_to_level = low - level  # negative if wick went below
distance_in_candle_widths = abs(wick_distance_to_level) / candle_range

# If level = $100.00, low = $100.60, range = $0.80:
# distance = 0.60 / 0.80 = 0.75 candle widths → C-grade (came close)
```

### Pierce Depth Calculation

**Pierce depth** = How far the wick penetrated past the level (as % of range)

```python
# LONG example
pierce_depth_pct = abs(min(wick_distance_to_level, 0)) / candle_range

# If level = $100.00, low = $99.88, range = $0.60:
# pierce = 0.12 / 0.60 = 0.20 (20% of range) → B-grade
```

---

## Why This Matters for Win Rate

Based on the AMZN short trade example you mentioned:

**Old Logic:**
- Checked if wick went below/above level (boolean: yes/no)
- Graded based on body/wick percentages
- Didn't measure **how close** the wick came to the level

**New Logic:**
- Measures exact distance from level
- Distinguishes between:
  - A: Clean tap (pierce ≤ 10%)
  - B: Moderate pierce (10-30%)
  - C: Near-miss (within 1-2 candle widths)
  - Reject: Too far (> 2 candle widths)

**Impact:**
- Setups where the retest doesn't come close to the level will now grade **C or lower**
- Forces you to wait for higher-quality retests (A/B grade)
- Reduces false signals from "kinda-sorta" retests

---

## Example Scenarios

### Scenario 1: Perfect A-Grade Long
```
Level: $517.69 (resistance → now support)
Retest:
  Low: $517.60 (tapped level, 9 cents below)
  Close: $517.85 (closed near high)
  Range: $0.30
  Pierce: 30% → A-grade ✅
```

### Scenario 2: Acceptable B-Grade Long
```
Level: $517.69
Retest:
  Low: $517.45 (pierced 24 cents below)
  Close: $517.72 (held above level)
  Range: $0.50
  Pierce: 48% → B-grade ⚠️
```

### Scenario 3: Rejected — No Touch (AMZN-like example)
```
Level: $517.69
Retest:
  Low: $518.20 (didn't touch level, 51 cents away)
  Close: $518.85
  Range: $0.70
  Decision: Reject — No touch ❌

Needs confluence: VWAP support, HTF uptrend, etc.
```

### Scenario 4: Rejected - Too Far
```
Level: $517.69
Retest:
  Low: $519.50 (way too far, $1.81 away)
  Range: $0.60
  Distance: 3.02 candle widths → REJECTED ❌

"Retest too far: 3.0x candle widths from level"
```

---

## How to Use This in Backtesting

When you run backtests, you'll now see:

```bash
python backtest.py --last-days 30 --min-grade B --breakout-tier B
```

**Before (old logic):**
- 15 trades, including "kinda-sorta" retests

**After (new logic):**
- Fewer trades, but higher quality
- A/B-grade retests have much higher win rates
- Near-miss retests (no touch) are rejected.

---

## Summary

The new retest grading measures **precision** and **distance**:

- **A-grade (✅)**: Wick taps level cleanly, minimal pierce, strong close → Take the trade
- **B-grade (⚠️)**: Moderate pierce but holds, acceptable → Take with confirmation
- **Rejected (❌)**: No touch (near-miss), too far from level, high volume (>60%), or close fails to hold
- **Rejected (❌)**: Too far away or breaks level → Don't trade

This ensures you're only taking setups where the market clearly respected the breakout level during the retest.
