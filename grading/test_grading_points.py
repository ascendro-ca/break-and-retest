"""Legacy points grading tests removed.

This suite previously validated grading/grading_points.py. The points system
is deprecated in favor of profile-based stage graders. Keep a sentinel test
to ensure the legacy module stays gone.
"""

import pytest


def test_points_grader_module_absent():
    with pytest.raises(ModuleNotFoundError):
        __import__("grading.grading_points")
