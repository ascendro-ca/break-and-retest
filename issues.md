### Issues
1. Side-by-side markdown summary (combined overview doc)
Benefit: Fast human review—centralizes key metrics (trades, win rate, P&L, average holding time, symbol distribution) without opening two separate files.
Secondary Gain: Serves as an audit artifact for strategy evolution; can be versioned for historical comparisons.
Effort: Very low (parse two JSON files, write one Markdown).
Risk: None.

2. Investigate why the trades print out for level 0 backtest but not for levels 1 and 2. They're more useful for 1 and 2. Are the results of each trade output to the file but not the console?
