# 📊 100-Point Trade Setup Scoring System

### Total: **100 points**

| Category                | Max Points |
|-------------------------|------------|
| 🔹 Breakout Quality     | 30 pts     |
| 🔹 Re-test Quality      | 30 pts     |
| 🔹 Ignition Quality     | 30 pts     |
| 🔸 VWAP/Trend Context   | 10 pts     |

---

## 🔹 1. Breakout Quality (Max 30 pts)

Score based on the **type of breakout candle** (5-minute) and **volume confirmation**.

### ✅ Candle Pattern-Based Scoring (max 20 points)

| Candle Pattern              | Points | Notes |
|----------------------------|--------|-------|
| **Marubozu / Shaved Candle** | +20     | Strong momentum, no hesitation |
| **Engulfing Candle**         | +18     | Strong reversal through OR level |
| **Wide-Range Breakout Candle (WRB)** | +17 | Large body breaking key level |
| **Belt Hold**               | +15     | Gap-and-go with conviction |
| **Other Clean Candle (≥ 60% body)** | +13 | Solid breakout but not textbook |
| **Messy/overlapping candle** | +7–10  | Breakout exists but lacks clarity |

### 📈 Volume (max 10 points)

| Volume Relative to 5m Average | Bonus |
|------------------------------|--------|
| > 1.5× average               | +10 pts |
| 1.2× – 1.5× average          | +5 pts |
| 1.0× – 1.2× average          | +2 pts |
| < 1.0×                       | 0 pts  |

**Example**: Marubozu breakout (+20) with 1.4× volume (+5) = **25/30**

---

## 🔹 2. Re-test Quality (Max 30 pts)

Score based on **re-test candle type** (1-minute) and whether the wick clearly taps/pierces the breakout level.

### ✅ Candle Pattern-Based Scoring (max 20 points)

| Candle Pattern              | Points | Notes |
|----------------------------|--------|-------|
| **Hammer / Inverted Hammer** | +20     | Wick rejection and clean hold |
| **Pin Bar**                 | +18     | Sharp rejection wick + tight body |
| **Doji w/ long rejection wick** | +17  | Tap and hesitation, still valid |
| **Inside Bar**             | +13     | Tight base + support hold |
| **Other small-wick hold**  | +10–12  | Clean, but not textbook |
| **Wick fails to touch level** | +5–9 | Near miss or weak |

### 📉 Volume Filter (max 10 points)

| Volume Relative to Breakout | Bonus |
|-----------------------------|--------|
| < 15% of breakout volume    | +10 pts |
| 15–30%                      | +5 pts |
| > 30%                       | 0 pts  |

**Example**: Hammer re-test (+20) with light volume (+10) = **30/30**

---

## 🔹 3. Ignition Quality (Max 30 pts)

Score based on **1-minute ignition candle** type and volume.

### ✅ Candle Pattern-Based Scoring

| Candle Pattern             | Points | Notes |
|---------------------------|--------|-------|
| **Bullish/Bearish Marubozu** | 20   | Strongest ignition — pure momentum |
| **Wide-Range Candle (WRB)** | 18   | Breaks past re-test extreme cleanly |
| **Engulfing Candle**       | 17     | Breaks structure and confirms |
| **Belt Hold**              | 15     | Strong open-close directionality |
| **Other momentum candle**  | 12–14  | Valid but minor hesitation |
| **Wick or indecisive body** | 7–10  | Weak ignition or false start |

### 🔥 Volume Confirmation

| Volume vs session avg & re-test candle | Bonus |
|----------------------------------------|--------|
| ≥ 1.5× retest volume AND > 90th percentile | +5 pts |
| ≥ 1.3× retest volume AND > average       | +3 pts |
| > retest volume but < average            | +1 pt  |
| ≤ retest volume                          | 0 pts  |

**Example**: WRB ignition (+18) with 1.4× retest volume and > avg volume (+3) = **21/30**

---

## 🔸 4. VWAP/Trend Context (Max 10 pts)

| Condition                                      | Points |
|-----------------------------------------------|--------|
| Retest candle closes aligned with VWAP (≥ VWAP - 0.05% for long / ≤ VWAP + 0.05% for short) | +5 |
| Overall trend (15m/30m HTF) aligns with trade direction                         | +3 |
| Pre-market / HTF level confluence (optional)                                   | +2 |

**Note**: VWAP alignment is checked at the retest stage (entry point) rather than breakout stage to reduce false negatives while confirming institutional flow alignment.

**Example**: VWAP aligned at retest (+5), HTF trend aligned (+3), HTF level matches breakout (+2) = **10/10**

---

## 🎯 Scoring Summary

| Total Score | Grade     | Interpretation                 |
|-------------|-----------|--------------------------------|
| 95–100      | A+        | Elite, high-probability setup  |
| 86–95       | A         | Strong, tradeable setup        |
| 70–85       | B         | Moderate confidence, needs confluence |
| 56-69       | C         | Weak setup, should avoid or wait      |
| < 55        | D / Reject| Very weak setup, definitely avoid or wait      |

---

## 📝 Example: AMZN SHORT Setup (Hypothetical)

- **Breakout**: Engulfing candle (+18), 1.3× volume (+3) → **21**
- **Re-test**: Inverted hammer tap (+18), light volume (+5) → **23**
- **Ignition**: Marubozu (+20), volume > 90th percentile (+5) → **25**
- **VWAP/Trend**: All aligned → **10**

**Total**: **21 + 23 + 25 + 10 = 89/100 → Grade A**
