#!/usr/bin/env python3
"""
Deprecated shim retained for backward compatibility.

This module has been renamed to stockdata_retriever.py.
Please use stockdata_retriever.py going forward.
"""

import sys

from stockdata_retriever import main as _main  # type: ignore


def main():  # pragma: no cover - shim
    print("WARNING: stockdata_test.py is deprecated. Use stockdata_retriever.py instead.")
    return _main()


if __name__ == "__main__":  # pragma: no cover - shim
    sys.exit(main())
