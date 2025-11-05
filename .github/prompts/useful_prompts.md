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
backtest.py --symbols AAPL NVDA TSLA UBER --start 2025-01-01 --end 2025-10-31 --level 2

---

# Prompts TODO list

## Prompt 1
I like how you put the points grading stuff under the `./grading` folder.
Suggest a logical organizational structure for the code in this code repository based on the knowledge in this project's docs.

## Prompt 3
What determines the R/R in the backtest?

## Prompt 4
New feature request: I would like to be able to configure the R/R to use for trade setups at different grade levels. For example,
- Grade C: 2:1 R/R
- Grade B: 2.5:1 R/R
- Grade A: 2.7:1 R/R
- Grade A+: 3:1 R/R
