from __future__ import annotations

from typing import Any, Dict, Protocol, Tuple


class Grader(Protocol):
    """Interface for grading systems.

    All methods return (grade_symbol, description).
    Grade symbols use the existing conventions:
    - Breakout/Retest/RR/Market: "✅" (A), "⚠️" (B), "C", "❌"
    - Continuation: "✅"/"⚠️"/"❌" in report mode; or emoji variants in alt ignition grading.
    """

    def grade_breakout_candle(
        self,
        candle: Dict[str, float],
        vol_ratio: float,
        body_pct: float,
        level: float | None = None,
        direction: str | None = None,
        *,
        a_upper_wick_max: float = 0.15,
        b_body_max: float = 0.65,
        or_range: float | None = None,
    ) -> Tuple[str, str]: ...

    def grade_retest(
        self,
        retest_candle: Dict[str, float],
        retest_vol_ratio: float,
        level: float,
        direction: str,
        *,
        retest_volume_a_max_ratio: float = 0.30,
        retest_volume_b_max_ratio: float = 0.60,
        b_level_epsilon_pct: float = 0.10,
        b_structure_soft: bool = True,
    ) -> Tuple[str, str]: ...

    def grade_continuation(
        self,
        ignition_candle: Dict[str, float],
        ignition_vol_ratio: float,
        distance_to_target: float,
        body_pct: float,
    ) -> Tuple[str, str]: ...

    def grade_risk_reward(self, rr_ratio: float) -> Tuple[str, str]: ...

    def grade_market_context(self, nq_sentiment: str = "neutral") -> Tuple[str, str]: ...

    def calculate_overall_grade(self, grades: Dict[str, str]) -> str: ...

    def generate_signal_report(self, signal: Dict[str, Any], **kwargs: Any) -> str: ...
