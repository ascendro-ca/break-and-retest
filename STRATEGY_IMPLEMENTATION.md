# Strategy Implementation — Break & Re-Test

This is the implementation companion to STRATEGY_SPEC.md. It defines concrete rules, formulas, thresholds, and pseudocode to ensure the backtest and live scanner share identical behavior.

- Scope: 5m breakout detection, 1m retest validation, 1m ignition grading, entry/exit math, config parameters.
- Principle: Keep detection strict and mechanical; apply “softness” in grading thresholds only.

## 1) Detection pipeline (sequencing)

1. Compute Opening Range (OR) from the first 5m candle after 09:30.
2. A 5m breakout occurs when the 5m close exceeds the OR boundary in the breakout direction and aligns with VWAP:
   - Long: 5m close > OR High and 5m close > VWAP
   - Short: 5m close < OR Low and 5m close < VWAP
   - Optional: breakout volume ≥ 1.0× session 5m average
3. Start the 1m retest search only after the breakout 5m candle closes:
   - retest_window_start = breakout_time + 5 minutes
4. The first 1m candle whose wick touches or pierces the breakout level and whose close holds on the correct side (with ≤1 tick epsilon on the close side only) is the valid retest.
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

## 5) Entry, stop, and targets

- Entry (configurable):
  - Default: on ignition break of the retest extreme intrabar; fallback to ignition close if not broken
  - Aggressive option: on retest close if grade == A
- Stop:
  - Long: stop = retest_low − 0.05
  - Short: stop = retest_high + 0.05
- Target:
  - target = entry ± 2 × (entry − stop)  # 2:1 R/R by default

## 6) VWAP and breakout volume filters

- VWAP alignment is enforced on breakout candle (5m):
  - Long: breakout close > VWAP
  - Short: breakout close < VWAP
- Breakout volume filter (recommended): breakout_vol ≥ 1.0× session 5m average

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
    if long_breakout(close, or_high, vwap, vol, vol_ma):
        yield breakout(long, level=or_high, time=bar.time, breakout_vol=vol)
    if short_breakout(close, or_low, vwap, vol, vol_ma):
        yield breakout(short, level=or_low, time=bar.time, breakout_vol=vol)

# Retest (1m) — begins only after breakout 5m bar closes
start = breakout.time + timedelta(minutes=5)
for m1 in one_minute_bars_from(start):
    if wick_touches(level, side) and close_holds_with_epsilon(m1, level, side, eps=1_tick):
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

## 9) Implementation notes

- Share detection + grading modules between backtest and live scanner to guarantee parity.
- Persist diagnostics (body_pct, pierce_pct, volume ratios, flags) for audit and analytics.
- Detection stays strict: timing (post-5m close), touch requirement, correct-side close with epsilon.
- Grading owns tightness and volume gates; adjust only via config parameters.
