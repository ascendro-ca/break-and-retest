# Strategy Design — Break & Re-Test (Scarface Rules)

This document captures the design rationale and conceptual criteria behind the strategy. It explains what “good” looks like and why.

- Purpose: Translate trading edge into clear, testable design criteria.
- Scope: Multi-timeframe breakout-retest-ignition continuation trades.

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

## Notes
- The design focuses on structure and probability; strict rules reduce false positives.
- The implementation document details formulas, thresholds, and pseudocode.
