"""DEPRECATED MODULE

The legacy monolithic scarface signal_grader has been removed in favor of
discrete, profile-based stage graders under the `grading` package.

Do not import this module. Use:
  from grading import load_profile, grade_breakout, grade_retest, grade_ignition
"""

raise ModuleNotFoundError(
    "signal_grader has been removed. Use profile-based stage graders in `grading`."
)
