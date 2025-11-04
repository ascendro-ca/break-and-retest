# Strategy Design — Break & Re-Test (Scarface Rules)

This document captures the design rationale and conceptual criteria behind the strategy. It explains what "good" looks like and why.

- Purpose: Translate trading edge into clear, testable design criteria.
- Scope: Multi-timeframe breakout-retest-ignition continuation trades.

## Backtesting Levels

The strategy employs a progressive filtering system across backtesting levels to incrementally improve:
1. Win rate
2. P&L
3. Trade quality (reducing noise through higher selectivity)

### Level 0 (Detection Only)
- No grading filters applied
- All valid setups that pass structural detection criteria are included
- Baseline for measuring improvement

### Level 1 (Basic Grading)
- Applies risk-based position sizing
- No minimum grade requirements
- Includes all A, B, and C grade setups

### Level 2 (Quality Filter)
- **Breakout (Stage 2)**: Minimum grade C or higher (not ❌/fail)
- **Retest (Stage 3)**: Minimum grade C or higher (not ❌/fail)
- **Candle Direction Filter**: For C-grade breakouts, candle direction must align with trade direction
  - Long trades require bullish breakout candles
  - Short trades require bearish breakout candles
  - All candle strength types (1-5) are accepted if direction-aligned
- **Goal**: Filter out structural failures and misaligned setups while accepting all quality grades (A, B, C)
- **Expected Impact**: Higher win rate, improved P&L, fewer but structurally-sound trades
- **Note**: A setup with C-grade retest + A-grade breakout is accepted; C is a minimum floor, not a weakness requirement

### Level 3+ (Reserved for Future Enhancement)
- May add minimum B-grade requirements
- Additional context filters (market regime, volatility, etc.)
- Multi-timeframe confirmation

## System Overview

- Timeframes: 5m for Opening Range (OR) and breakout, 1m for retest and ignition.
- Sequencing:
  1) First 5m sets OR high/low
  2) A later 5m candle closes beyond OR (breakout)
  3) After the breakout 5m closes, the next valid 1m retest must tap the level
  4) The following 1m is the ignition candidate
- Trend filter: VWAP-aligned breakout close (long: above VWAP, short: below VWAP).

## Retest Quality (Conceptual)

- Must touch or pierce the breakout level (no-touch = reject).
- A-grade (“Tap and Go”):
  - Minimal pierce (≤ 10% of 1m range)
  - Strong body (≥ 60%), close near the extreme
  - Light retest volume (≤ 30% of breakout volume)
  - Prefer first tap
- B-grade (Acceptable):
  - Moderate pierce (10–30%)
  - Body ≥ 40%, close holds level (≤ 1-tick epsilon OK for automation)
  - Retest volume ≤ 60% of breakout volume
- Rejected:
  - No touch (near-miss)
  - Close fails to hold on correct side (beyond epsilon)
  - Retest too far from level (> 2 candle widths)
  - Excessive retest volume (> 60% of breakout)

### Short (Mirror) Rules
- Upper wick tests resistance; close near low for A-grade.
- Same pierce/body/volume thresholds mirrored.

## Ignition (Conceptual)
- Next 1m after valid retest.
- A-grade ignition:
  - Breaks retest extreme intrabar
  - Body ≥ 70%, upper wick ≤ 10% (long case)
  - Close beyond retest extreme
  - Volume surge vs retest and session average (top decile acceptable proxy)
- B-grade ignition:
  - Body 50–70%, wick 10–30%
  - Close near retest extreme
  - Volume > retest and > session average
- C-grade ignition (skip):
  - Body < 50% or wick > 30%, weak close, weak volume

## Entry & Risk (Design)
- Entry options:
  - On retest close for A-grade retests
  - On ignition break intrabar (default), optional on-close confirmation
- Stop: Retest wick ± $0.05
- Target: 2:1 R:R minimum

## Example Scenarios (Design-Level)

- A-Grade Long Retest: clean tap, minimal pierce, strong close, light volume.
- B-Grade Long Retest: deeper pierce but defended, moderate body, acceptable volume.
- Rejected Near-Miss: didn’t touch level → not a valid retest.
- Rejected Too Far: > 2 candle widths from level.

## Pitfalls to Avoid (Design)
- Using 1m for breakout definitions.
- Detecting retests during the active breakout 5m candle.
- Allowing loose tolerances (e.g., fixed dollar thresholds) instead of structural precision.
- Entering on weak ignition.

## Grading Criteria Summary

### Grade C Thresholds (Minimum for Level 2)

#### Breakout Candle (Grade C)
**Long:**
- Body: 25-45% of range
- Upper wick > 25% OR lower wick ≥ 30%
- Close at or below the breakout level
- Volume < 1.0× session average
- Green candle or neutral with body ≥ 25%

**Short:**
- Body: 25-45% of range
- Upper wick ≥ 30% OR lower wick > 25%
- Close at or above the breakdown level
- Volume < 1.0× session average
- Red candle or neutral with body ≥ 25%

**Interpretation**: Weak breakout with significant rejection wicks, poor close relative to level, and below-average volume. Shows hesitation but maintains minimum structure.

#### Retest Candle (Grade C)
**Long:**
- Wick comes within 1-2 candle widths of support level but doesn't touch
- If touches: pierce depth > 30% of range OR weak structure
- Close holds above level (with epsilon tolerance allowed)
- Volume ≤ 60% of breakout volume

**Short:**
- Wick comes within 1-2 candle widths of resistance level but doesn't touch
- If touches: pierce depth > 30% of range OR weak structure
- Close holds below level (with epsilon tolerance allowed)
- Volume ≤ 60% of breakout volume

**Interpretation**: Near-miss retest or touched but with poor structure. Requires additional context/confluence to be tradeable. Not a clean "tap" of the level.

### Why Grade C is the Minimum for Level 2

**Important:** Grade C represents the **minimum acceptable quality threshold**, not a requirement for weakness.

Grade C means:
- The setup has minimum structural integrity
- Risk can be defined and managed
- The trade has a probabilistic edge when combined with other factors
- **The overall signal grade is at least C** (individual components can be A, B, or C)

#### C-Grade Philosophy

A signal with an **overall C-grade** can have mixed component grades. For example:
- C-grade retest + A-grade breakout = Overall C (acceptable)
- A-grade retest + C-grade breakout = Overall C (acceptable)
- C-grade retest + C-grade breakout = Overall C (acceptable)

**Key Point:** At Level 2, signals with C-grade individual components are NOT rejected if the direction and structure are valid. The filter enforces:
1. Breakout and retest must each be at least C-grade (not ❌/fail)
2. For C-grade breakouts: candle direction must match trade direction (bullish for long, bearish for short)
3. All valid candle strengths (1-5) are accepted if direction-aligned

This means **strong A/B-grade breakouts within C-grade overall setups are accepted**, not rejected.

Below Grade C (reject/fail ❌):
- Structural failures (e.g., close on wrong side of level)
- Excessive volume indicating distribution/absorption
- Distance > 2 candle widths from level (too far to be a valid test)
- No touch at all with insufficient proximity
- Direction misalignment (bullish candle on short, bearish candle on long)

## Notes
- The design focuses on structure and probability; strict rules reduce false positives.
- The implementation document details formulas, thresholds, and pseudocode.
