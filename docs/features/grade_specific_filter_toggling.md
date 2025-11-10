# Feature Spec: Grade-specific Filter Toggling

Last updated: 2025-11-09
Status: Proposed → Implementing
Owner: Backtest/Signals

## Summary
Introduce configurable, per-grade filtering for the Break & Re-Test backtest pipeline at Level 2, allowing toggling of Grade C, B, and A filters independently via `config.json`.

- Levels simplified to 0/1/2
  - Level 0: Detect candidates only (no trades, no grade filtering)
  - Level 1: Execute trades with base pipeline (Stages 1–3); compute grades for analytics but do not filter by grade
  - Level 2: Apply grade filters in sequence, controlled by toggles
- New config keys enable/disable each grade filter independently
- Default settings preserve current behavior

## Motivation
- Give researchers precise control over quality gates during backtests without editing code
- Enable quick experiments: e.g., run only B/A gates, or only A gate, or C gate only
- Simplify pipeline semantics by collapsing Level 3+ into Level 2 with toggles

## Scope
In-scope:
- Config-driven toggles for Grade C, B, and A filtering applied at Level 2
- Diagnostic output and results metadata indicating which filters were active
- Removal of prior Level 3+ branches (their behavior subsumed by toggles)

Out-of-scope (for now):
- Structural A/A+ component-specific criteria beyond points thresholds
- UI/Notebook visualizations (separate effort)

## Configuration
New `config.json` keys and defaults:
- `feature_grade_c_filtering_enable` (bool, default: true)
- `feature_grade_b_filtering_enable` (bool, default: true)
- `feature_grade_a_filtering_enable` (bool, default: true)
- `grade_b_min_points` (number, default: 70)
- `grade_a_min_points` (number, default: 85)

Examples (CLI overrides supported):
- `--config-override feature_grade_c_filtering_enable=false`
- `--config-override grade_a_min_points=88`

## Level semantics (simplified)
- Level 0: Detection only. No trades, no grade filters.
- Level 1: Trades allowed (Stages 1–3). Grades computed for analytics. No grade filters applied.
- Level 2: Grade filters applied in order (C → B → A), each controlled by its toggle. If a toggle is disabled, that step is skipped.

## Filter definitions
All grading computed by `self.grader` as today. Filters use those computed results.

- Grade C filter (preserves current Level 2 simplified gate):
  - Require component grades: breakout != "❌" AND rr != "❌".
  - Retest/context/continuation are not enforced at this step.

- Grade B filter:
  - Require total points (breakout + retest + ignition + context) >= `grade_b_min_points` (default 70).
  - Does NOT implicitly re-apply C checks if C filter was disabled.

- Grade A filter:
  - Require total points >= `grade_a_min_points` (default 85).
  - Future option: layer in A-tier structural constraints; for now points-only for consistency.

Notes:
- If C filter is disabled, component grades may include ❌; the B/A checks still operate purely on points thresholds.
- If all toggles are false, Level 2 behaves like Level 1 (no grade filtering).

## Processing order (Level 2)
1. Start with all graded signals.
2. If `feature_grade_c_filtering_enable` is true, keep only signals passing Grade C filter.
3. If `feature_grade_b_filtering_enable` is true, keep only signals with points >= `grade_b_min_points`.
4. If `feature_grade_a_filtering_enable` is true, keep only signals with points >= `grade_a_min_points`.

Pseudo-code:
```
filtered = graded_signals
if cfg.C_enabled:
    filtered = [s for s in filtered if s.breakout != ❌ and s.rr != ❌]
if cfg.B_enabled:
    filtered = [s for s in filtered if s.total_points >= cfg.b_min]
if cfg.A_enabled:
    filtered = [s for s in filtered if s.total_points >= cfg.a_min]
```

## Diagnostics & reporting
- Print once per symbol at Level 2:
  - Active grade filters: `C={on|off}, B={on|off} (min={b_min}), A={on|off} (min={a_min})`
  - Counts: before, rejected_by_c, rejected_by_b, rejected_by_a, after
- Include in per-symbol results dict:
  - `"filter_config": { "grade_c": bool, "grade_b": bool, "grade_a": bool, "grade_b_min_points": number, "grade_a_min_points": number }`

## Backward compatibility
- Default config preserves current behavior (C and B on, A on but effectively redundant unless its threshold is below B’s or equal).
- Prior Level 3+ functionality (points >= 70) now expressed as Level 2 with `feature_grade_b_filtering_enable=true`.
- No CLI changes required; `--config-override` already supported.

## Acceptance criteria
- When C is disabled and B/A enabled, signals skip the C gate and are filtered only by B then A.
- When C enabled and B disabled, A enabled, signals are filtered by C then A.
- When all toggles disabled, Level 2 passes all graded signals (no grade-based rejections).
- Diagnostics show accurate counts and active filter summary.
- Existing tests pass; new toggle tests cover key permutations.

## Test plan
Unit tests (pytest):
1. Level 2, C on vs off: verify pass counts differ when some signals fail C.
2. Level 2, B off (C on): verify only C gate enforced; signals < 70 pts but >= C pass.
3. Level 2, C off, B on: verify only B gate enforced; signals with ❌ components but high points can pass.
4. Level 2, A on/off: verify points >= A threshold gating.
5. All toggles off: Level 2 behaves as Level 1 in terms of filtering.

Integration:
- Small backtest slice with deterministic cache to compare counts across toggle combinations.

## Edge cases
- Missing/None grades: robust `.get()` usage (existing) avoids exceptions; such signals will likely fail points/grade checks and be filtered out when filters are enabled.
- Zero/low points thresholds (misconfiguration) may admit poor-quality signals; documented and visible in diagnostics.
- Conflicting thresholds (e.g., A < B) are allowed; evaluation order still C → B → A.

## Performance considerations
- Filtering is linear over graded signals; negligible runtime impact compared to data loading and grading.

## Rollout plan
- Implement behind config defaults.
- Update references to Level 3+ in documentation to reflect Levels 0/1/2 only.
- Add tests and run full suite via Makefile.

## Affected components
- `backtest.py` (Level 2 filtering path, diagnostics)
- `config.json` (new keys)
- `test_backtest.py` or new `test_grade_filter_toggles.py` (unit tests)
- Documentation references to Levels 3–5

## Future work
- Add structural A-tier checks (e.g., component-specific A requirements) behind `feature_grade_a_filtering_enable`.
- Consider `feature_grade_a_plus_filtering_enable` with a higher points threshold and structural constraints.
- Add visualization/reporting of pass/fail distributions per filter stage.
