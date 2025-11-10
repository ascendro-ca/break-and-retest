# Deprecated: Grade-specific Filter Toggling

Last updated: 2025-11-10
Status: Removed
Owner: Backtest/Signals

This document described per-grade filtering toggles controlled via `config.json` keys such as:

- `feature_grade_c_filtering_enable`
- `feature_grade_b_filtering_enable`
- `feature_grade_a_filtering_enable`

These feature flags and the associated points thresholds have been removed as part of the
grading simplification and Level 2 parity work. Profiles are now name-only shells (`C`, `B`, `A`, `A+`)
used for analytics and reporting only. No grade-based gating is applied at Level 2; behavior matches
Level 1 entry semantics across all profiles.

What remains:
- Retest A+ evaluation is retained for analytics (`retest_aplus`, `retest_aplus_reason`) and does not gate.
- Minimum risk/reward remains enforced via `min_rr_ratio` (default 2.0).
- You can still select a profile via `--grade` to annotate results, but it does not filter trades.

If you need to experiment with stricter filtering again in the future, consider reintroducing it behind
new, clearly documented feature flags and dedicated tests. For now, this doc is kept to explain the
historical context and the rationale for removal.
