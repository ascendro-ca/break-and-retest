# Recurring Prompts

## New Chat Prompt
Use the `copilot.md` file as additional instructions for this chat.

## End of Chat Prompt
Summarize what we've worked on in this chat thread and add it to `context_summary.md`.

## Backtest Prompt comparison
1. Let's perform a backtest with the following options:
   - **Period:** Jan – Oct 2025
   - **Tickers:** default
   - **Level:** 1
2. Let's perform a backtest with the following options:
   - **Period:** Jan – Oct 2025
   - **Tickers:** default
   - **Level:** 2
3. Compare results from (1) and (2)

## Backtest ticker subset
> python backtest.py --symbols AAPL NVDA TSLA UBER --start 2025-01-01 --end 2025-10-31 --level 2
> python backtest.py --symbols AAPL NVDA TSLA UBER --start 2025-01-01 --end 2025-10-31 --level 2 --config-override initial_capital=30000

> python backtest.py --symbols AAPL NVDA TSLA UBER --start 2025-01-01 --end 2025-10-31 --level 2 --config-override initial_capital=30000

> python backtest.py --symbols AAPL NVDA TSLA UBER --start 2025-01-01 --end 2025-10-31 --level 1 --config-override initial_capital=30000

> python backtest.py --start 2025-01-01 --end 2025-10-31 --level 1 --config-override initial_capital=30000

> python backtest.py --start 2025-01-01 --end 2025-10-31 --level 1 --config-override min_rr_ratio=1.5

> python backtest.py --start 2025-01-01 --end 2025-10-31 --level 3
---

# Prompts TODO list

## Prompt 1

Here are the exact criteria applied at Level 1 that are not applied at Level 0:

Level 0 (Detection Only):

Detects all breakout/retest candidates that meet basic structural criteria.
No grading, risk, or trade quality filters.
No requirement for valid entry, stop, or target prices.
No position sizing or risk/reward checks.
No minimum grade or trade setup quality enforced.
Level 1 (Basic Trade Execution):

Only candidates with valid entry, stop, and target prices are promoted to trades.
Applies risk-based position sizing (calculates shares based on risk).
Requires that risk/reward can be calculated (i.e., entry, stop, and target are all present and logical).
Filters out setups where trade cannot be executed (e.g., missing prices, invalid structure).
No minimum grade requirement (A, B, and C grades are all accepted), but the trade must be executable.
Excludes signals that fail base trade rules (e.g., risk too high, stop/target not logical).
## Prompt 1
Ok, I would like to reserve detecting specific candle patterns for grades A and A+.

Grades B and C I would like the signal_grader.py to use the detect_candle_score() method from candle_patterns.py as follows:




## Prompt 2.1
What are some interesting questions to ask about the backtest results that collect data across 1000's of trade setups that could be visualized in a Jupyter Notebook compatible python script to help gain insight into the break and re-test detection pipeline effectiveness for developing a highly profitable trading system? Use the data in ./backtest_results
-

## Prompt 2.2
Generate a Jupyter Notebook compatible python script that uses the data in ./backtest_results to:
-

## Prompt 3
I don't think this option is useful anymore given the way levels 2-5 are now going to be tied to enforcing specific grade filtering or better. Can we remove this option and any affect it has on the trade setup detection pipeline? Or is the a reason to keep it?
    parser.add_argument(
        "--breakout-tier",
        choices=["A", "B", "C"],
        help="Only include signals with this specific breakout tier (filters after grade)",
    )

## Prompt 4
Move the data download weekend logging behavior from backtest.py to stockdata_retriever.py because it clutters the log during backtesting:

Relevant code snippet in backtest.py:
            # No provider download here; rely on cache populated by StockData.org tool
            # Suppress missing-cache logs on weekends (Saturday=5, Sunday=6)
            if current.weekday() < 5:
                print(f"No cached data for {symbol} {interval} on {date_str}")


## Prompt 5
I would like to be able to configure the R/R to use for trade setups at different grade levels. For example,

Level 1:
- use default R/R configured in config.json

Level 2: Grade C
- use default R/R configured in config.json

Level 3: Grade B
- (Default reward + 0.5):1 R/R
(for example, the default reward is 2.0 because the default R/R is 2:1)

Level 4: Grade A
- (Default reward + 0.7):1 R/R

Level 5: Grade A+
- (Default reward + 1.0):1 R/R


---


## Grade C Criteria Analysis from the code
(fixes required)
Grade C criteria by component
Breakout (5m)

Primary C path (pattern-driven):
TA-Lib pattern detected on the breakout candle (e.g., hammer, shooting_star, engulfing, doji, marubozu, spinning_top, inverted_hammer, dragonfly_doji, gravestone_doji).
For shorts, code explicitly requires volume ≥ 0.7× 20-bar MA; longs return C on pattern without enforcing the 0.7× check in code.
Fallback C path (if no pattern match):
Minimal breakout body and volume:
Body ≥ 15% of OR range (if known) or ≥ 15% of the candle’s own range, and
Volume ≥ 0.7× 20-bar MA.
Fails are “❌” (rejected) if body is too small and volume < 0.7×.
Retest (1m)

Hard gate first: the close must hold on the correct side of the level (above for long, below for short), with a small epsilon allowed for B-tier; if this fails, it’s “❌”.
C-grade is very permissive once the close holds:
Near-miss allowed: wick doesn’t have to touch the level (“C: near miss”).
Or touched the level but didn’t meet A/B structural/volume strictness (“C: touched level”).
No extra volume requirement for C (A/B have volume caps; C does not).
In short: if the close holds on the right side but A/B structure isn’t met, it’s accepted as C.
Ignition (1m Stage 4, pre-entry gate at Level 2)

Grade mapping uses emojis: A = 🟢, B = 🟡, C = 🔴.
C (“🔴”) is the default when A/B are not met, i.e.:
Does not break the retest extreme with both intrabar break and close, or
Body < 50%, or
Opposite wick too large (beyond A/B allowances), or
Volume is not a surge vs retest and session-average.
There is no “❌” path from this function; the Level 2 pipeline rejects before grading if no ignition is detected at all (your “no ignition detected” bucket).
Risk/Reward (pre-entry)

≥ 3.0:1 → ✅
≥ 2.0:1 → ✅
≥ 1.5:1 → ⚠️
< 1.5:1 → ❌
For the Level 2 “C-or-better” gate, anything ≥ 1.5:1 passes; below 1.5:1 is rejected.
Market context

bullish → ✅
neutral or slightly_red → ⚠️
All current market outcomes are C-or-better (no ❌ path here), so market won’t cause a quality rejection in the current code.
Important nuances
The gate semantics for “C-or-better”
In this Scarface Rules grader, “C-or-better” effectively means “not ❌” for each component. Breakout and R/R are the usual sources of ❌. Retest can be ❌ only if the close fails to hold the level.
Pattern vs fallback for breakout C
If a TA-Lib pattern hits, that alone can produce a C (longs don’t enforce the 0.7× volume in code; shorts do). If no pattern, the minimal quantitative fallback applies: body ≥ 15% (OR or candle) and vol ≥ 0.7×.
Ignition vs Continuation
The Level 2 gate uses the Stage 4 ignition check (A/B/C as 🟢/🟡/🔴). The separate “continuation” function in signal_grader.py is post-entry reporting and not part of the acceptance gate.
If using the 100‑point system (docs mapping)
In the 100-point system (see GRADING_SYSTEMS.md and GRADING_USAGE.md), “C” overall is 56–69.
For the Level 2 pre-entry gate in that system: each of Breakout, Retest, Ignition is out of 30 points, and a component counts as “C-or-better” if it scores ≥ 16.8/30 (56%).
The current code in your branch is using the Scarface Rules grader (signal_grader.py) for the Level 2 quality filter; the above C criteria are the ones actually applied.
Want me to print a compact cheat sheet into GRADING_USAGE.md so this stays in sync with the code?

## Other prompts to run
Compare these backtest results to find out why using VWAP check on breakout and re-test candles has worse results than not applying the check:

With both VWAP checks:
- Total trades: 1072
- Winners: 358
- Win rate: 33.4%
- Total P&L: $-333.77
Results saved to backtest_results/level1_ALL_20250101_20250331_profile_2025-11-13T154905-0800.json
Summary saved to backtest_results/level1_ALL_20250101_20250331_profile_2025-11-13T154905-0800_summary.md
Runtime: 3.30m for 8 symbol(s) (2025-01-01 -> 2025-03-31), Level 1

With only re-test VWAP checks:
- Total trades: 1121
- Winners: 376
- Win rate: 33.5%
- Total P&L: $-123.72
Results saved to backtest_results/level1_ALL_20250101_20250331_profile_2025-11-13T155642-0800.json
Summary saved to backtest_results/level1_ALL_20250101_20250331_profile_2025-11-13T155642-0800_summary.md
Runtime: 2.85m for 8 symbol(s) (2025-01-01 -> 2025-03-31), Level 1
