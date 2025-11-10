Config rr_ratio in config.json in min_rr_ratio property and make overridable in backtest.py options

LEVEL 1
=======
min_rr_ratio: 1.5
- Total trades: 1045
- Winners: 437
- Win rate: 41.8%
- Total P&L: $2781.57

min_rr_ratio: 2.0
- Total trades: 1041
- Winners: 369
- Win rate: 35.4%
- Total P&L: $3456.82

min_rr_ratio: 2.5
- Total trades: 1039
- Winners: 326
- Win rate: 31.4%
- Total P&L: $4799.58

min_rr_ratio: 3.0
- Total trades: 1036
- Winners: 300
- Win rate: 29.0%
- Total P&L: $7094.21

min_rr_ratio: 4.0
- Total trades: 1028
- Winners: 253
- Win rate: 24.6%
- Total P&L: $9799.38

min_rr_ratio: 5.0
- Total trades: 1012
- Winners: 205
- Win rate: 20.3%
- Total P&L: $9098.62

min_rr_ratio: 10.0
- Total trades: 937
- Winners: 73
- Win rate: 7.8%
- Total P&L: $-3710.00

LEVEL 2
=======
min_rr_ratio: 1.5
- Total trades: 153
- Winners: 68
- Win rate: 44.4%
- Total P&L: $1241.12

min_rr_ratio: 2.0
- Total trades: 152
- Winners: 59
- Win rate: 38.8%
- Total P&L: $1541.56

min_rr_ratio: 2.5
- Total trades: 152
- Winners: 53
- Win rate: 34.9%
- Total P&L: $1858.26

min_rr_ratio: 3.0
- Total trades: 152
- Winners: 48
- Win rate: 31.6%
- Total P&L: $2097.55

min_rr_ratio: 4.0
- Total trades: 151
- Winners: 38
- Win rate: 25.2%
- Total P&L: $2063.15

min_rr_ratio: 5.0
- Total trades: 149
- Winners: 30
- Win rate: 20.1%
- Total P&L: $1766.15

min_rr_ratio: 10.0
- Total trades: 140
- Winners: 16
- Win rate: 11.4%
- Total P&L: $1946.25

COMPARISON WITH LEVEL 1:
Ratio | L2 Win Rate | L1 Win Rate | L2 Avg P&L | L1 Avg P&L | L2 Trades | L1 Trades
------|-------------|-------------|------------|------------|----------|----------
  1.5 |        44.4% |        41.8% | $     8.11 | $     2.66 |      153 |     1045
  2.0 |        38.8% |        35.4% | $    10.14 | $     3.32 |      152 |     1041
  2.5 |        34.9% |        31.4% | $    12.23 | $     4.62 |      152 |     1039
  3.0 |        31.6% |        29.0% | $    13.80 | $     6.85 |      152 |     1036
  4.0 |        25.2% |        24.6% | $    13.66 | $     9.53 |      151 |     1028
  5.0 |        20.1% |        20.3% | $    11.85 | $     8.99 |      149 |     1012
 10.0 |        11.4% |         7.8% | $    13.90 | $    -3.96 |      140 |      937

The Level 2 results demonstrate that quality filtering is transformative - it converts a decent Level 1 strategy into a robust, high-quality trading approach with consistent profitability across different R/R expectations. The optimal 3.0 R/R ratio at Level 2 suggests this is the sweet spot for live implementation.
