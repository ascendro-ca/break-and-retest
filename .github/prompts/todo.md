# TODO List

## Break and Retest Strategy Development

### High Priority

1. (DONE) **Add Minimum R/R to Configuration**
   - Add a minimum R/R to config.json (default 2.0:1)
   - Update the code to use it in all trades unless overridden in a particular trade setup pipeline level, stage or grade level

2. **Complete Grade C Criteria for Pipeline Level 2**
   - Review and validate current Grade C scoring implementation
   - Ensure breakout, retest, and ignition stages properly filter at Grade C threshold
   - Test and verify >= C criteria is working correctly for level 2 pipeline

3. **Develop Grade B Criteria for Pipeline Level 3**
   - Define Grade B scoring criteria for breakout stage
   - Define Grade B scoring criteria for retest stage
   - Define Grade B scoring criteria for ignition stage
   - Implement Grade B filtering logic
   - Test Grade B criteria with pipeline level 3

4. **Develop Grade A Criteria for Pipeline Level 4**
   - Define Grade A scoring criteria for breakout stage
   - Define Grade A scoring criteria for retest stage
   - Define Grade A scoring criteria for ignition stage
   - Implement Grade A filtering logic
   - Test Grade A criteria with pipeline level 4

5. **Develop Grade A+ Criteria for Pipeline Level 5**
   - Define Grade A+ scoring criteria for breakout stage
   - Define Grade A+ scoring criteria for retest stage
   - Define Grade A+ scoring criteria for ignition stage
   - Implement Grade A+ filtering logic
   - Test Grade A+ criteria with pipeline level 5

6. **Validate trade setups with real B & R trades during same period**
   - Determine how to measure, correlation? Some kind of overlap measure
   - Even just find same symbols traded on same day and count these

7. **Build a small optimize**
   - vary breakout grade threshold and RR minimum, recompute EV per trade from cached signals to find a Pareto set.

8. (REMOVED) **Grade specific filter toggling**
   - Deprecated. Grade-based filtering flags were removed; Level 2 uses name-only profiles for analytics only.

9. (DONE) **Backtest info loggin cleanup**
   - With level 2 pipeline only log trades to console when console-only
     option enabled

### Medium Priority

- Investigate and fix cache data integrity issues (822 errors, 1058 warnings reported)
- Add missing cache data for dates: 2025-05-26, 2025-07-04, 2025-09-01
- Review why Grade D signals are passing >= C filter (scoring calibration issue)

### Low Priority

- Optimize backtest performance for larger date ranges
