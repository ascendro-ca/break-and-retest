"""
Deprecated compatibility shim for detection functions.

Note: The project now uses multi-timeframe-only detection implemented in
`break_and_retest_detection_mt.py`. This module re-exports the public API so
older imports continue to work until the file can be fully removed.
"""

from break_and_retest_detection_mt import (  # re-export for backward compatibility
    detect_breakout_5m,
    detect_retest_and_ignition_1m,
    is_strong_body,
    scan_for_setups,
)

__all__ = [
    "detect_breakout_5m",
    "detect_retest_and_ignition_1m",
    "is_strong_body",
    "scan_for_setups",
]
