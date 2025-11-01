# Visual Examples: Retest Grading (Long Setup)

## Setup Context


## ✅ A-Grade: "Tap and Go" - Clean Rejection

```
Price
$100.60 |                      ●────── Close (near high)
        |                      │
$100.40 |                      │
        |                      │
$100.20 |                      │
        |                      │
$100.00 |──────────────────────┼────── BREAKOUT LEVEL
        |                      ▼
 $99.80 |                      ● ←── Low (tapped level)

Measurements:

Grade: ✅ A-grade
Reason: Clean tap, minimal pierce, strong close
```

**Why A-grade works:**


## ⚠️ B-Grade: Moderate Pierce But Holds

```
Price
$100.70 |                      ●────── Close (above level but not near high)
        |                      │
$100.50 |                      │
        |                      │
$100.30 |                      │
        |                      │
$100.10 |                      │
        |                      │
$100.00 |──────────────────────┼────── BREAKOUT LEVEL
        |                      │
 $99.80 |                      │
        |                      │
 $99.60 |                      ▼
        |                      ● ←── Low (moderate pierce)

Measurements:

Grade: ⚠️ B-grade
Reason: Deeper pierce shows selling pressure, but buyers held
```

**Why B-grade is acceptable:**


## ❌ Rejected — Near-Miss (No Touch)

```
Price
$101.20 |                      ●────── Close
        |                      │
$101.00 |                      │
        |                      │
$100.80 |                      │
        |                      │
$100.60 |                      │
        |                      │
$100.40 |                      ▼
        |                      ● ←── Low (didn't reach level)
$100.20 |
        |
$100.00 |──────────────────────────── BREAKOUT LEVEL (not touched!)
        |
 $99.80 |

Measurements:

Decision: ❌ Rejected — No touch
Reason: Never tested the level, came within 0.54x candle widths
```

Why rejected:


## ❌ REJECTED: Too Far From Level

```
Price
$102.00 |                      ●────── Close
        |                      │
$101.50 |                      │
        |                      │
$101.00 |                      ▼
        |                      ● ←── Low (WAY too far from level)
$100.50 |
        |
$100.00 |──────────────────────────── BREAKOUT LEVEL (never tested!)
        |
 $99.50 |

Measurements:

Grade: ❌ REJECTED
Reason: "Retest too far: 1.0x candle widths from level"
```

**Why this is rejected:**


## SHORT Setup: Flipped Logic

For **SHORT** trades, flip everything vertically:

### ✅ A-Grade Short: Upper Wick Taps Resistance

```
Price
$100.20 |                      ● ←── High (tapped resistance)
        |                      ▲
$100.00 |──────────────────────┼────── BREAKOUT LEVEL (resistance)
        |                      │
 $99.80 |                      │
        |                      │
 $99.60 |                      │
        |                      │
 $99.40 |                      ●────── Close (near low)

```


## Key Takeaways

| Grade | Wick Behavior | Pierce Depth | Close Quality | Trade Decision |
|-------|---------------|--------------|---------------|----------------|
| **✅ A** | Taps level cleanly | ≤ 10% of range | Near high/low | **Take immediately** |
| **⚠️ B** | Moderate pierce | 10-30% of range | Holds level | **Take with confirmation** |
| **❌ C** | Comes close (1-2x widths) | N/A (doesn't touch) | Holds level | **Need confluence** |
| **❌ Reject** | Too far (> 2x widths) | N/A | N/A | **Don't trade** |


## Real-World Application

When scanning for setups, you should now see output like:

```
AAPL 5m Breakout & Retest (Scarface Rules)
Level: $100.00 resistance (VWAP: $99.85 ✅)
Breakout: Strong candle + high vol ✅
Retest: A-grade tap: wick touched level, clean rejection (pierce: 8.3%) ✅
Continuation: Good push (45% to target) ✅
R/R: 2.1:1 ($99.50 stop → $101.55 target) ✅
Grade: A+ — perfect structure, all criteria met

vs.

AMZN 5m Breakout & Retest (Scarface Rules)
Level: $517.69 resistance (VWAP: $517.10 ✅)
Breakout: Strong candle + high vol ✅
Retest: Reject — near-miss (no touch) ❌
Continuation: Good push (42% to target) ✅
R/R: 2.0:1 ($517.20 stop → $519.69 target) ✅
Grade: B — decent setup, minor concerns in execution
```

The AMZN setup would now be flagged as lower quality due to the weak retest (didn't touch the level).

# Deprecated

This document has been consolidated into `STRATEGY_IMPLEMENTATION.md`.
Please refer to the Implementation doc for examples and details.
- Grade: ✅ A-grade tap
