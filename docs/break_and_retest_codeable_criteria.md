
# 🧠 Codeable Criteria — 5-Minute Break & Re-Test Strategy (Scarface Trades)

A complete, Python-friendly set of rules for automating the Breakout → Re-test → Ignition sequencing.

---

# 1️⃣ Breakout Detection (5-Minute Timeframe)

### 🎯 Goal
Identify the first 5m candle that *closes beyond the Opening Range (OR)* with strong body and volume.

### Inputs
```python
OR_high, OR_low = first_5m_high, first_5m_low
avg_vol_5m = df_5m['volume'].rolling(20).mean()
```

### LONG Breakout
```python
breakout_long = (
    (df_5m['close'] > OR_high) &
    ((df_5m['close'] - df_5m['open']) / (df_5m['high'] - df_5m['low']) >= 0.7) &
    ((df_5m['high'] - df_5m['close']) / (df_5m['high'] - df_5m['low']) <= 0.15) &
    (df_5m['volume'] >= 1.5 * avg_vol_5m)
)
```

### SHORT Breakout
```python
breakout_short = (
    (df_5m['close'] < OR_low) &
    ((df_5m['open'] - df_5m['close']) / (df_5m['high'] - df_5m['low']) >= 0.7) &
    ((df_5m['close'] - df_5m['low']) / (df_5m['high'] - df_5m['low']) <= 0.15) &
    (df_5m['volume'] >= 1.5 * avg_vol_5m)
)
```

### Optional VWAP Filter
```python
df_5m['breakout_valid'] = breakout_long & (df_5m['close'] > df_5m['vwap'])
```

---

# 2️⃣ Re-Test Detection (1-Minute Timeframe)

### 🎯 Goal
Detect the first 1m candle *after the breakout* that taps or nearly taps the breakout level and holds it.

### Inputs
```python
breakout_time = breakout_candle_end_time
retest_window = (df_1m['time'] > breakout_time) & (df_1m['time'] <= breakout_time + pd.Timedelta(minutes=5))
```

### LONG Re-test
```python
retest_long = (
    (retest_window) &
    (df_1m['low'] <= breakout_level_long * 1.0002) &
    (df_1m['close'] > breakout_level_long) &
    (df_1m['volume'] <= 0.3 * breakout_volume_5m)
)
```

### SHORT Re-test
```python
retest_short = (
    (retest_window) &
    (df_1m['high'] >= breakout_level_short * 0.9998) &
    (df_1m['close'] < breakout_level_short) &
    (df_1m['volume'] <= 0.3 * breakout_volume_5m)
)
```

### Optional “Near Miss” C-Grade Retest
```python
retest_near_touch = (
    (abs(df_1m['low'] - breakout_level_long) / breakout_level_long <= 0.0015) &
    (df_1m['close'] > breakout_level_long)
)
```

---

# 3️⃣ Ignition Detection (1-Minute Timeframe)

### 🎯 Goal
Identify the **next 1m candle** after a valid retest that confirms continuation.

### Inputs
```python
retest_time = retest_candle_time
ignition_window = df_1m['time'] > retest_time
```

### LONG Ignition
```python
ignition_long = (
    (ignition_window) &
    (df_1m['high'] > retest_high) &
    (df_1m['close'] > retest_high) &
    ((df_1m['close'] - df_1m['open']) / (df_1m['high'] - df_1m['low']) >= 0.7) &
    (df_1m['volume'] >= 1.5 * retest_volume)
)
```

### SHORT Ignition
```python
ignition_short = (
    (ignition_window) &
    (df_1m['low'] < retest_low) &
    (df_1m['close'] < retest_low) &
    ((df_1m['open'] - df_1m['close']) / (df_1m['high'] - df_1m['low']) >= 0.7) &
    (df_1m['volume'] >= 1.5 * retest_volume)
)
```

---

# 4️⃣ Stage Dependencies

```python
setup_long = breakout_long & retest_long & ignition_long
setup_short = breakout_short & retest_short & ignition_short
```

Ensures strict sequencing of
**Breakout → Re-test → Ignition**.

---

# 🧠 TL;DR Summary Table

| Stage | Key Condition | Volume | Timeframe |
|-------|---------------|---------|-----------|
| **Breakout** | 5m close beyond OR, body ≥70% | ≥1.5× avg | 5m |
| **Re-test** | 1m tap/pierce OR & close holds | ≤30% breakout vol | 1m |
| **Ignition** | Breaks retest high/low w/ strong body | ≥1.5× retest vol | 1m |
