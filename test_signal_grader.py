"""Legacy signal_grader test removed.

We intentionally keep a sentinel here that asserts the legacy module is
unavailable. If the import succeeds, this test should fail to remind us
to purge lingering dependencies.
"""

import importlib
import pytest


def test_signal_grader_removed():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("signal_grader")
