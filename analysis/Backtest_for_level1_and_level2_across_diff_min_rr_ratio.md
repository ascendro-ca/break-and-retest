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

> python backtest.py --symbols AAPL NVDA TSLA UBER --start 2025-01-01 --end 2025-10-31 --level 2 --config-override initial_capital=30000 --config-override feature_level0_enable_vwap_check=false

> python backtest.py --symbols AAPL NVDA TSLA UBER --start 2025-01-01 --end 2025-10-31 --level 1 --config-override initial_capital=30000

> python backtest.py --start 2025-01-01 --end 2025-10-31 --level 1 --config-override initial_capital=30000

> python backtest.py --start 2025-01-01 --end 2025-10-31 --level 1 --config-override min_rr_ratio=1.5
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

## Prompt 3


## Prompt 4
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




