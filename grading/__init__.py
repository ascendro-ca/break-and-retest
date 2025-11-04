from __future__ import annotations

from typing import Dict

from .base import Grader
from .grading_points import PointsGrader

_GRADERS: Dict[str, Grader] = {
    "points": PointsGrader(),
}


def get_grader(name: str = "points") -> Grader:
    """Factory to retrieve a grader by name (case-insensitive)."""
    key = (name or "points").strip().lower()
    return _GRADERS.get(key, _GRADERS["points"])  # default fallback
