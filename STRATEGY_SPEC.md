# 🧠 Break and Re-Test Strategy – Scarface Rules (Refined)

A ruleset for algorithmic detection and elite discretionary execution of high-probability breakout continuation trades.

---

## 1. 🎯 Core Concept

Wait for:

1. **Opening Range (OR)** to form via first 5-minute candle
2. A **5-minute breakout candle** that **closes beyond OR**
3. A **1-minute re-test** of the breakout level (post 5-min close)
4. A **1-minute ignition candle** that confirms continuation

---

## 2. 🕰️ Step 1: Opening Range (OR)

- **Timeframe**: First 5-minute candle (09:30–09:35 ET)
- **OR High** = High of the candle
- **OR Low** = Low of the candle
- **Range** = OR High − OR Low

> These levels act as dynamic S/R for the rest of the session.

---

## 3. 🚀 Step 2: Breakout Detection (5-Min Candle)

- Must be a **full 5-min candle**, **after 09:35**
- **LONG**: Closes above OR High → OR High becomes **support**
- **SHORT**: Closes below OR Low → OR Low becomes **resistance**

### Example:
```
Breakout candle (09:35–09:40):
  - OR Low: 222.16
  - Close: 221.60 → Valid SHORT breakout
```

> ⚠️ Do NOT use 1m candles for breakout detection.

---

## 4. 🔁 Step 3: Retest Detection (1-Min Candle)

- Begins after breakout 5-min candle **closes**
- Search for **first 1m candle** that:
  - **Touches or pierces** the breakout level
  - **Closes on the correct side** (above for long, below for short)
  - Allows **≤ 1 tick** tolerance in automation

### Timing Rule:
```python
start_time = breakout_time + timedelta(minutes=5)
```

---

## 5. 🧪 Step 4: Retest Quality Grading

### ✅ A-Grade Retest – "Tap and Go"
- Wick touches/pierces breakout level
- Pierce depth ≤ 10% of 1m candle range
- Body ≥ 60% of range
- Close near high (long) or low (short)
- Volume ≤ 30% of breakout candle volume
- **First tap only** (optionally enforce)

### ⚠️ B-Grade Retest – Acceptable
- Wick touches/pierces level
- Pierce depth 10–30%
- Body ≥ 40%
- Close on correct side
- Volume ≤ 60% of breakout candle

### ❌ C-Grade / Reject
- Wick does not touch level
- Body < 40%, volume high
- Close on wrong side
- Multi-tap re-tests (optional rejection)

---

## 6. 🔥 Step 5: Ignition Candle

The **next 1m candle** after a valid re-test.

### 🟢 Grade A — Textbook Ignition
- Breaks retest high/low intrabar
- Body ≥ 70% of range
- Upper wick ≤ 10%
- Close clearly past retest high
- Volume ≥ max(1.5 × retest_volume, 1.3 × session_avg_volume_so_far)
- OR: Volume in top 10–20% of 1m bars so far
- Trade behavior: ✅ Mid-bar entry allowed (or on close)

### 🟡 Grade B — Acceptable Ignition
- Body 50–70%
- Wick 10–30%
- Close = near retest high
- Volume > retest candle and session average
- Trade behavior: ⚠️ Reduce size, confirm on close or use confluence (VWAP, trend)

### 🔴 Grade C — Weak Ignition
- Body < 50%
- Upper wick > 30%
- Close at/below breakout level or retest high
- Volume low or equal to retest
- Trade behavior: ❌ Skip the trade

### Volume Rules (Automation-Friendly):
```python
def is_volume_surge(ignition_volume, retest_volume, session_avg):
    return ignition_volume >= max(1.5 * retest_volume, 1.3 * session_avg)
```

---

## 7. 🎯 Step 6: Entry & Risk

**Entry Options**:
- On **retest close** (if A-grade with strong rejection)
- On **ignition candle break intrabar**
  - Enter as it breaks retest high (long) or low (short)
  - Optional confirmation: volume ramp + speed breakout

**Stop-Loss**:
- **Long**: $0.05 below retest low
- **Short**: $0.05 above retest high

**Target**:
- Use 2:1 R:R minimum
```python
target = entry ± 2 × (entry − stop)
```

---

## 8. 🧰 Step 7: Additional Filters

### ✅ VWAP Trend Filter
- Long: Breakout candle must close **above VWAP**
- Short: Must close **below VWAP**

```python
valid_trend = (breakout_close > VWAP) if long else (breakout_close < VWAP)
```

### ✅ Breakout Candle Volume Filter
- Breakout candle volume ≥ 1.0 × session average

---

## 9. 🧠 Optional Enhancements (Advanced)

### ➕ Candle Speed (Momentum Measure)
```python
ignition_speed = (ignition_high − retest_high) / candle_duration_seconds
```
Use to detect **momentum surges intrabar**

### ➕ Re-test Count Filter
- Reject setups with more than 2 re-tests to the same breakout level

```python
if retest_count_for_level[level] > 2:
    skip_trade = True
```

---

## 10. ❌ Pitfalls to Avoid

| Mistake | Why it's a problem |
|--------|---------------------|
| 1. Using 1m for breakout | Breakouts must be defined on 5m closes |
| 2. Re-test detected during 5m breakout | Invalid sequencing |
| 3. Loose retest tolerance (e.g. $0.50) | Violates structural precision |
| 4. Entry on weak ignition candle | Low probability, easily traps |

---

## 11. 📉 Summary Flow

```
[09:30] → Market Opens
  ↓
[09:35] → First 5m candle defines OR
  ↓
Breakout → 5m candle closes outside OR
  ↓
[Wait] → Until 5m candle fully closes
  ↓
Scan 1m candles for re-test (must wick to breakout level)
  ↓
Grade re-test: A/B/Reject
  ↓
Next 1m = ignition candidate
  ↓
Grade ignition: A (strong entry), B (cautious), C (skip)
  ↓
Entry: Mid-bar break of retest high (or retest close if A-grade)
  ↓
Risk: Stop = retest wick ± $0.05
  ↓
Target: 2:1 R:R
```
