# Break and Retest Strategy - Scarface Rules

## Core Concept

The Break and Retest (B&R) strategy identifies high-probability intraday trading opportunities by waiting for:
1. An **Opening Range (OR)** to be established
2. A **5-minute breakout candle** that breaks above/below the OR
3. A **1-minute retest candle** that comes back to test the breakout level
4. A **1-minute ignition candle** that confirms continuation

---

## Step 1: Opening Range (OR)

**Timeframe**: First 5-minute candle of the trading day (09:30-09:35 ET)

**Definition**:
- **OR High**: The high of the first 5m candle
- **OR Low**: The low of the first 5m candle
- **Range**: OR High - OR Low

**Example** (AMZN Oct 8, 2025):
```
First 5m candle (09:30-09:35):
  High: 223.41
  Low:  222.16
  Range: $1.25
```

**Purpose**: The OR establishes key support/resistance levels that will be tested throughout the day. Institutional traders watch these levels closely.

---

## Step 2: Breakout Detection (5-minute candle)

**Timeframe**: Any 5-minute candle AFTER the opening range candle

**LONG Breakout**:
- A 5m candle that **closes above** the OR High (223.41)
- The OR High becomes **support** after the breakout

**SHORT Breakout**:
- A 5m candle that **closes below** the OR Low (222.16)
- The OR Low becomes **resistance** after the breakout

**Example** (AMZN Oct 8, 2025 SHORT):
```
Breakout candle (09:35-09:40):
  High:  222.57
  Low:   221.52  ← Broke below OR Low (222.16)
  Close: 221.60  ← Closed below OR Low

Result: SHORT breakout
Breakout level: 222.16 (OR Low, now resistance)
```

**Critical Rule**: The breakout candle MUST be a **complete 5-minute candle**. Do not use 1-minute candles for breakout detection.

---

## Step 3: Retest Detection (1-minute candle)

**Timeframe**: Look for 1m candles AFTER the 5m breakout candle completes

**LONG Retest**:
- After a LONG breakout (above OR High)
- Look for a 1m candle that comes back DOWN to test the OR High (now support)
- The 1m candle's **low wick** should touch or pierce the breakout level
- Close should hold **above** the breakout level

**SHORT Retest**:
- After a SHORT breakout (below OR Low)
- Look for a 1m candle that comes back UP to test the OR Low (now resistance)
- The 1m candle's **high wick** should touch or pierce the breakout level
- Close should hold **below** the breakout level

**Example** (AMZN Oct 8, 2025 - INCORRECT detection):
```
The 09:37 1m candle was INCORRECTLY identified as the retest because:
- It occurred at 09:37 (DURING the 09:35-09:40 5m breakout candle)
- The 5m breakout hadn't completed yet
- High: 222.30 (only 0.14 above the 222.16 level)
- This violates the rule that retest must occur AFTER the 5m breakout

The detection code should have waited until AFTER 09:40 (when the 5m candle completes)
to look for a 1m retest candle.
```

**Critical Rule**: The retest 1m candle MUST occur AFTER the 5m breakout candle completes. Do not detect retests on 1m candles that occur during the 5m breakout candle.

---

## Step 4: Precision Retest Grading

Once a valid retest is found (AFTER the 5m breakout), grade its quality:

### A-Grade: "Tap and Go" (Highest Probability)
- Wick **touches or slightly pierces** the breakout level
- Pierce depth ≤ 10% of the 1m candle's range
- Close near the opposite end (near high for LONG, near low for SHORT)
- Strong body (≥ 60%)
- Volume light (< 15% of breakout volume)

### B-Grade: Moderate Pierce (Acceptable)
- Wick touches/pierces the breakout level
- Pierce depth 10-30% of the 1m candle's range
- Close holds on correct side of level
- Moderate body (≥ 40%)
- Volume light (< 15% of breakout volume)

### C-Grade / Reject: Near-Miss or Too Far
- Wick does NOT actually touch the breakout level
- Even if it comes "close", it's not a valid retest
- **Reject the setup**

**Critical Measurement**:
- **LONG**: Pierce depth = how far the low wick went **below** the breakout level
- **SHORT**: Pierce depth = how far the high wick went **above** the breakout level

---

## Step 5: Ignition Candle (Post-Entry Confirmation)

Once a valid retest is identified (AFTER the 5m breakout candle completes), the very next 1‑minute candle is the ignition candidate. It should confirm continuation in the direction of the trade by breaking and holding beyond the retest extreme.

Measurement basics (per 1m ignition candle):
- Candle range = High − Low
- Body% = |Close − Open| / (High − Low)
- Upper wick% = (High − max(Open, Close)) / (High − Low)
- Volume context: compare to session distribution so far (percentile) and to the retest candle

Long trade case (mirror for short):

- Break criteria: Must break the retest high
   - A‑grade: High > retest_high + tick AND Close > retest_high
   - B‑grade: High ≥ retest_high AND Close ≥ retest_high − epsilon (tiny miss allowed)
   - C/Fail: Fails to break, or breaks intrabar but cannot close at/above retest_high

Grading

- ✅ Grade A — Textbook ignition
   - Body: ≥ 70% of candle range
   - Wick: Small upper wick (≤ 10%)
   - Close: Well above retest high and the breakout level
   - Volume: Surging (top 10–20% of session so far) or clearly elevated vs both session average and the retest candle
      - Practical proxy: volume ≥ max(1.5 × retest_volume, 1.3 × session_avg_volume_so_far)
   - Break: Clean, decisive break of retest high
   - Trade behavior: High conviction — entry allowed mid‑bar (aggressive) or on close (conservative)

- ⚠️ Grade B — Acceptable ignition
   - Body: 50–70% of candle range
   - Wick: Moderate upper wick (10–30%)
   - Close: At or just above retest high / breakout level
   - Volume: Above session average and above retest candle
   - Break: Clears retest high but barely; may need context confluence (trend/VWAP/HTF)
   - Trade behavior: Tradeable with confluence — reduce size and prefer close confirmation

- ❌ Grade C — Weak/Fail ignition
   - Body: < 50% (indecisive/small)
   - Wick: Long upper wick (> 30%) showing rejection
   - Close: At or below breakout level or below retest high (failure to hold)
   - Volume: Low or ≤ retest candle volume
   - Break: No clear break or intrabar pop that fails into the close
   - Trade behavior: Skip — no ignition, high failure risk

Short trade case (mirror)
- Replace “retest high” with “retest low”
- Replace “upper wick” with “lower wick”
- Replace “close above” with “close below” throughout

Timing rule (critical)
- The ignition candidate is the 1m candle immediately AFTER the accepted retest candle
- Do not evaluate ignition during the 5m breakout candle; sequencing is strictly: OR (5m) → Breakout (5m complete) → Retest (1m) → Ignition (next 1m)

Implementation notes (to be applied in code after review)
- Body%/wick% computed exactly as defined above
- Volume surge can be implemented as a percentile rank vs same‑session 1m bars up to that time and/or the simple proxy vs average and retest volume
- Clean break checks use instrument tick size (stocks: $0.01) and a tiny epsilon for close tests

Examples
- A‑grade long ignition: Body 78%, upper wick 6%, closes 10–20¢ above retest high, volume 90th percentile
- B‑grade long ignition: Body 58%, upper wick 18%, closes at/just above retest high, volume > average
- C‑grade long ignition: Body 34%, upper wick 40%, closes back at/below retest high, volume ~ retest


## Step 6: Entry and Risk Management

**Entry**:
- Enter on the **close** of the retest 1m candle
- Or enter on the **ignition candle** (next 1m candle after retest) if it confirms direction

**Stop Loss**:
- **LONG**: Place stop $0.05 below the retest candle's low
- **SHORT**: Place stop $0.05 above the retest candle's high

**Target**:
- Use 2:1 risk/reward ratio
- Target = Entry ± 2 × (Entry - Stop)

**Example** (AMZN Oct 8 - from backtest):
```
Entry:  221.85 (SHORT)
Stop:   222.40 (retest high + $0.05)
Target: 220.77 (2:1 R/R)
Risk:   $0.55
Reward: $1.08
```

---

## Step 7: Additional Filters

### VWAP Trend Filter
- **LONG**: Breakout 5m candle must close **above** VWAP
- **SHORT**: Breakout 5m candle must close **below** VWAP
- Ensures trade is aligned with intraday trend

### Volume Requirements
- **Breakout volume**: Should be elevated (≥ 1.0× average)
- **Retest volume**: Should be light (< 15% of breakout volume)
- Light retest volume indicates lack of supply/demand absorption

---

## Key Differences: 5m vs 1m Roles

| Aspect | 5-Minute Candle | 1-Minute Candle |
|--------|-----------------|-----------------|
| **Opening Range** | Defines OR High/Low | Not used |
| **Breakout** | Identifies breakout (close above/below OR) | Not used for breakout |
| **Retest** | Not used for retest detection | Identifies retest after 5m breakout |
| **Entry** | Not used for entry | Entry on retest or ignition candle |
| **Stop Placement** | Not used | Stop based on retest candle wick |

---

## Common Pitfalls (Issues Found in Current Code)

### ❌ Pitfall 1: Using 1m candles for breakout detection
**Wrong**: Treating the first 1m candle that breaks OR as the "breakout"
**Correct**: Only 5m candles can be breakouts

### ❌ Pitfall 2: Detecting retest during the 5m breakout candle
**Wrong**: Looking for 1m retest candles that occur during the 5m breakout window
**Correct**: Only look for 1m retest candles AFTER the 5m breakout completes

**Example of the error**:
```
5m breakout candle: 09:35-09:40 (breaks below OR)
1m candle at 09:37: High = 222.30 (touches level)

ERROR: The 09:37 candle is DURING the 09:35-09:40 window
       It should NOT be considered a valid retest

CORRECT: Wait until after 09:40, then look for 1m retest
```

### ❌ Pitfall 3: Using generous distance tolerance
**Wrong**: Accepting retest if wick is within $0.50 of level (too loose)
**Correct**: Wick must actually touch or pierce the level (no tolerance)

---

## Summary Flow

```
1. Market opens (09:30)
   ↓
2. First 5m candle completes (09:35)
   → OR established: [OR Low, OR High]
   ↓
3. Wait for a 5m candle to break above OR High or below OR Low
   → Breakout detected
   → Breakout level = OR High (LONG) or OR Low (SHORT)
   ↓
4. After 5m breakout completes, scan 1m candles for retest
   → Look for 1m wick that touches breakout level
   → Close must hold on correct side
   ↓
5. Grade the retest quality (A/B/Reject)
   → A: Pierce ≤ 10% of range
   → B: Pierce 10-30% of range
   → Reject: Didn't touch level
   ↓
6. Evaluate ignition (next 1m) — grade ✅/⚠️/❌ per criteria above
   → Prefer A (can enter mid‑bar); B only with confluence; skip C
   ↓
7. Enter per rules (retest close or ignition), manage risk
   → Stop: Retest wick ± $0.05
   → Target: 2:1 R/R
```

---

## Detection Code Implications

The current detection code needs fixes:

1. **`detect_breakout_5m()`**: ✅ Correctly uses 5m candles for breakout
2. **`detect_retest_and_ignition_1m()`**: ❌ Needs fix
   - Currently searches for 1m retest starting from `breakout_time`
   - Should search starting from `breakout_time + 5 minutes` (after 5m candle completes)
   - Change: `df_1m["Datetime"] > breakout_time` → `df_1m["Datetime"] >= breakout_time + timedelta(minutes=5)`

3. **Retest level check**: ✅ Fixed
   - Changed from `abs(high - level) < 0.5` tolerance
   - To `high >= level` (SHORT) or `low <= level` (LONG)

---

## Example: AMZN Oct 8, 2025 (Correct Analysis)

**Opening Range** (09:30-09:35):
- High: 223.41
- Low: 222.16

**Breakout** (09:35-09:40 5m candle):
- Close: 221.60 (below OR Low of 222.16)
- Breakout type: SHORT
- Breakout level: 222.16 (now resistance)

**Retest Search Window**:
- Start: 09:40 (AFTER 5m breakout completes)
- Look for 1m candles with high >= 222.16

**Current (Incorrect) Behavior**:
- Found retest at 09:37 (during breakout candle)
- This violates the timing rule

**Expected (Correct) Behavior**:
- Ignore all 1m candles from 09:35-09:40
- Search starting at 09:40
- Find first valid 1m retest candle after 09:40

---

## Next Steps

1. Fix `detect_retest_and_ignition_1m()` to start search AFTER 5m breakout completes
2. Run backtest to see if AMZN Oct 8 trade gets filtered out
3. Verify all other trades follow proper 5m → 1m sequencing
4. Document any trades that violate the timing rule
