# Strategy Implementation — Break & Re-Test

This is the implementation companion to STRATEGY_SPEC.md. It defines concrete rules, formulas, thresholds, and pseudocode to ensure the backtest and live scanner share identical behavior.

- Scope: 5m breakout detection, 1m retest validation, 1m ignition grading, entry/exit math, config parameters.
- Principle: Keep detection strict and mechanical; apply “softness” in grading thresholds only.

## 1) Detection pipeline (sequencing)

1. Compute Opening Range (OR) from the first 5m candle after 09:30.
2. A 5m breakout occurs when the 5m close exceeds the OR boundary (with tolerance) in the breakout direction:
   - Long: 5m open ≤ OR High + 0.25% AND 5m close ≥ OR High - $0.01
   - Short: 5m open ≥ OR Low - 0.25% AND 5m close ≤ OR Low + $0.01
   - Tolerances allow gap continuation breakouts and near-miss closes that maintain momentum
   - Optional: breakout volume ≥ 1.0× session 5m average
3. Start the 1m retest search only after the breakout 5m candle closes:
   - retest_window_start = breakout_time + 5 minutes
4. The first 1m candle whose wick touches or pierces the breakout level, whose close holds on the correct side (with ≤1 tick epsilon on the close side only), and which aligns with VWAP (see below) is the valid retest.
5. The very next 1m candle is the ignition candidate; grade its quality.

## 2) Key formulas

- range = high − low (guard against zero; if zero, treat body/wick percentages as 0)
- body_pct = abs(close − open) / range
- upper_wick_pct = (high − max(open, close)) / range
- lower_wick_pct = (min(open, close) − low) / range
- distance_in_ranges = abs(level − wick_extreme) / max(range, tiny)
- Pierce depth percent (relative to candle range):
  - Long retest: pierce_pct = abs(min(low − level, 0)) / max(range, tiny)
  - Short retest: pierce_pct = max(high − level, 0) / max(range, tiny)

Notes:
- level is OR High for long breakouts; OR Low for short breakouts.
- wick_extreme is low for long retests, high for short retests.
- tiny is a small constant to avoid division-by-zero (e.g., 1e-6).

## 3) Retest validity and grading

Validity (hard requirements):
- Touch/pierce is required (no-touch = reject)
- Close must hold on the correct side of the breakout level; a ≤1-tick epsilon is allowed on the close side only
- Use the first valid 1m bar that satisfies these; later bars are ignored

Volume comparison base: 5m breakout candle volume.

Grades:
- A (✅)
  - pierce_pct ≤ 0.10 (tight probe)
  - body_pct ≥ 0.60 (decisive response)
  - Close near extreme (within 10% of the extreme in the direction of the trade)
  - retest_volume ≤ 0.30 × breakout_volume
- B (⚠️)
  - 0.10 < pierce_pct ≤ 0.30
  - body_pct ≥ 0.40
  - Close holds (respecting ≤1-tick epsilon)
  - retest_volume ≤ 0.60 × breakout_volume
- Reject (❌)
  - No touch (near-miss)
  - retest_volume > 0.60 × breakout_volume
  - distance_in_ranges > 2 (too far from level)
  - Close fails to hold beyond epsilon

## 4) Ignition grading (next 1m after valid retest)

Ignition candidate is strictly the bar immediately following the valid retest.

Inputs:
- retest extreme (low for long, high for short)
- session 1m average volume (rolling)
- retest 1m volume

Grades (mirror for short):
- A (🟢)
  - Intrabar break of the retest extreme
  - body_pct ≥ 0.70
  - upper_wick_pct ≤ 0.10 (long; for short, lower_wick_pct ≤ 0.10)
  - Close beyond the retest extreme
  - Volume surge: ignition_vol ≥ max(1.5 × retest_vol, 1.3 × session_1m_avg)
- B (🟡)
  - 0.50 ≤ body_pct < 0.70
  - Wick 10–30% of range
  - Close at/near retest extreme
  - Volume > retest and > session average
- C (🔴)
  - body_pct < 0.50 or wick > 30%
  - Weak close and/or volume

Helper:
- is_volume_surge(ign, ret, avg) := ign ≥ max(1.5×ret, 1.3×avg)

## 5) Entry, stop, targets, and sizing

### Entry Logic
- Default: intrabar break of the retest extreme on the ignition candle; fallback to ignition close if not broken.
- Aggressive (future option): retest close if retest grade == A.

### Stop Placement
- Long: `stop = retest_low − 0.05`
- Short: `stop = retest_high + 0.05`
- Stop buffer (0.05) is constant for now; could be made ATR-relative later.

### Target Calculation
- `risk = abs(entry − stop)`
- `target = entry ± rr_ratio * risk` where `rr_ratio` (a.k.a. `min_rr_ratio`) defaults to 2.0.
- Tick rounding occurs after raw prices are computed.

### Centralized Trade Planning (`trade_planner.py`)
Sizing and price derivation are delegated to `plan_trade` to keep math consistent between backtest and (future) live components.

Core sizing formula:
```
risk_per_trade = initial_capital * risk_pct_per_trade
stop_dist = abs(entry - stop)
shares_risk = floor(risk_per_trade / stop_dist)
max_shares_bp = floor((initial_capital * leverage) / entry)
shares = min(shares_risk, max_shares_bp)
```
Then:
```
target = entry ± rr_ratio * stop_dist
max_loss = shares * stop_dist          # ≈ configured dollar risk (may be lower if buying power caps)
max_win  = shares * rr_ratio * stop_dist
```

Reasons for centralization:
- Eliminates drift between different code paths.
- Facilitates auditing (planned vs effective risk tracked).
- Simplifies experimentation with dynamic leverage, partial exits, or adaptive buffers.

Edge cases handled:
- Zero or negative stop distance → reject trade.
- Buying power insufficient for at least 1 share at configured risk → skip trade.
- If no stop provided (not typical here) and feature enabled, stop distance is inferred (`risk_per_trade / max_shares_bp`).

All rounding to tick size happens last; distances are recomputed post-round to keep R calculations internally consistent.

## 6) VWAP alignment and breakout volume filters

- **VWAP alignment** is enforced at the **retest stage** (1m candle) with 0.05% buffer:
  - Long: retest close ≥ VWAP - (VWAP × 0.0005)
  - Short: retest close ≤ VWAP + (VWAP × 0.0005)
  - Rationale: Confirms institutional flow alignment at entry point while reducing false negatives at breakout
- **Breakout volume filter** (recommended): breakout_vol ≥ 1.0× session 5m average

## 7) Configuration parameters

- retest_volume_a_max_ratio = 0.30
- retest_volume_b_max_ratio = 0.60
- retest_close_epsilon_ticks = 1
- ignition_vol_retest_mult = 1.5
- ignition_vol_session_mult = 1.3
- rr_min = 2.0

## 8) Pseudocode summary

```python
# Breakout (5m)
for each 5m bar after OR:
    if long_breakout(close, or_high, vol, vol_ma):
        yield breakout(long, level=or_high, time=bar.time, breakout_vol=vol)
    if short_breakout(close, or_low, vol, vol_ma):
        yield breakout(short, level=or_low, time=bar.time, breakout_vol=vol)

# Retest (1m) — begins only after breakout 5m bar closes
start = breakout.time + timedelta(minutes=5)
for m1 in one_minute_bars_from(start):
    if wick_touches(level, side) and close_holds_with_epsilon(m1, level, side, eps=1_tick):
        # Check VWAP alignment at retest
        vwap_buffer = abs(m1.vwap) * 0.0005  # 0.05%
        if side == "long":
            vwap_aligned = m1.close >= (m1.vwap - vwap_buffer)
        else:  # short
            vwap_aligned = m1.close <= (m1.vwap + vwap_buffer)

        if not vwap_aligned:
            continue

        grade = grade_retest(m1, breakout)
        if grade in {A, B}:
            retest = m1
            break
else:
    continue  # no valid retest

# Ignition (next 1m)
ign = next_bar_after(retest)
ign_grade = grade_ignition(ign, retest, session_1m_vol_avg)

# Entry/Stop/Target
entry = intrabar_break_of_retest_extreme(ign, side) or ign.close
stop = retest.wick_extreme ± 0.05
risk = abs(entry - stop)
if risk <= 0: reject
rr_target = entry ± 2 * risk
```

## 9) Candle Pattern Recognition

Beyond basic body/wick measurements, we classify candles by their visual patterns to assess quality. This complements the existing grading system.

### Pattern Hierarchy (Strength Rankings)

**Bullish Candles** (most → least bullish):
1. **Bullish Marubozu** (strength=1) — Strong bullish candle with minimal wicks
   - body_pct ≥ 0.90, upper_wick_pct ≤ 0.05, lower_wick_pct ≤ 0.05
   - Indicates strong buying pressure with no rejection
2. **Hammer / Dragonfly Doji** (strength=2) — Long lower wick, small body near high
   - lower_wick_pct ≥ 0.50, body_pct ≤ 0.20, upper_wick_pct ≤ 0.20
   - Dragonfly Doji if body_pct ≤ 0.05
   - Shows rejection of lower prices, bullish reversal signal
3. **Normal Bullish Candle** (strength=3) — Standard green candle
   - Close > Open with moderate body (not marubozu or hammer)
   - Steady bullish pressure
4. **Spinning Top (bullish close)** (strength=4) — Small body, long wicks both sides
   - body_pct ≤ 0.20, upper_wick_pct ≥ 0.30, lower_wick_pct ≥ 0.30
   - Indecision candle with slight bullish bias
5. **Inverted Hammer (weak bullish)** (strength=5) — Long upper wick, small body near low
   - upper_wick_pct ≥ 0.50, body_pct ≤ 0.20, lower_wick_pct ≤ 0.20
   - Weakest bullish signal, potential reversal but needs confirmation

**Bearish Candles** (most → least bearish):
1. **Bearish Marubozu** (strength=1) — Strong bearish candle with minimal wicks
   - body_pct ≥ 0.90, upper_wick_pct ≤ 0.05, lower_wick_pct ≤ 0.05
   - Indicates strong selling pressure with no rejection
2. **Shooting Star / Gravestone Doji** (strength=2) — Long upper wick, small body near low
   - upper_wick_pct ≥ 0.50, body_pct ≤ 0.20, lower_wick_pct ≤ 0.20
   - Gravestone Doji if body_pct ≤ 0.05
   - Shows rejection of higher prices, bearish reversal signal
3. **Normal Bearish Candle** (strength=3) — Standard red candle
   - Close < Open with moderate body (not marubozu or shooting star)
   - Steady bearish pressure
4. **Spinning Top (bearish close)** (strength=4) — Small body, long wicks both sides
   - body_pct ≤ 0.20, upper_wick_pct ≥ 0.30, lower_wick_pct ≥ 0.30
   - Indecision candle with slight bearish bias
5. **Inverted Hammer (weak bearish)** (strength=5) — Long lower wick despite bearish close
   - lower_wick_pct ≥ 0.50, body_pct ≤ 0.20, upper_wick_pct ≤ 0.20
   - Weakest bearish signal in this context

### Usage in Strategy

**Pattern Detection Module**: `candle_patterns.py`
- `classify_candle_strength(candle)` — Returns pattern type, direction, strength (1-5)
- `get_candle_strength_score(candle, direction)` — Returns 0.0-1.0 score for expected direction
- `analyze_candle_patterns(df)` — Batch classify all candles in DataFrame

**Integration Points**:
- **Breakout Candle**: Prefer marubozu or strong-bodied patterns (strength 1-3)
- **Retest Candle**: Hammer (long) or Shooting Star (short) are ideal reversal patterns (strength 2)
- **Ignition Candle**: Marubozu or strong directional candle confirms momentum (strength 1-2)

**Grading Enhancement**:
- Pattern classification can inform future grade adjustments
- Strong patterns (strength 1-2) matching expected direction boost confidence
- Weak patterns (strength 4-5) or opposite direction may warrant grade penalty
- Currently informational; integration into grading system is future work

### Implementation Notes

- Uses TA-Lib library for industry-standard pattern detection (60+ patterns available)
- Fallback to pure-Python pandas-ta if TA-Lib unavailable
- Pattern classification is rule-based using body/wick percentages
- All patterns tested with comprehensive unit tests (16 tests, 100% passing)
- Pattern data persisted in analysis for pattern-based post-analysis

## 10) Implementation notes

- Share detection + grading modules between backtest and live scanner to guarantee parity.
- Persist diagnostics (body_pct, pierce_pct, volume ratios, flags) for audit and analytics.
- Detection stays strict: timing (post-5m close), touch requirement, correct-side close with epsilon.
- Grading owns tightness and volume gates; adjust only via config parameters.
- Pattern recognition adds qualitative assessment layer on top of quantitative metrics.

````
