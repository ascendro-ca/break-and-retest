"""Deprecated test file: detection_mt module removed.

This file intentionally contains a trivial test to keep test discovery stable
without depending on the removed multi-threaded detection module.
"""


def test_detection_timing_removed_replaced_by_pipeline():
    # Legacy detection_mt timing test removed; covered by pipeline-based tests.
    assert True
