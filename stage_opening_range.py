"""
Stage 1: Opening Range Detection
==================================

Establishes the opening range (OR) from the first 5-minute candle of the
regular trading session. This becomes the reference level for breakout detection.

Base Criteria:
- Use the High and Low of the first 5m candle

Future Extensions:
- Could support multi-bar OR (e.g., first 15 minutes)
- Could support dynamic OR based on pre-market action
"""

from typing import Dict

import pandas as pd


def detect_opening_range(session_df_5m: pd.DataFrame) -> Dict[str, float]:
    """
    Detect the opening range from session data.

    Args:
        session_df_5m: 5-minute session DataFrame, sorted ascending by Datetime

    Returns:
        Dict with keys: 'high', 'low', 'open_time'
    """
    if session_df_5m is None or session_df_5m.empty:
        return {"high": 0.0, "low": 0.0, "open_time": None}

    first_candle = session_df_5m.iloc[0]
    return {
        "high": float(first_candle["High"]),
        "low": float(first_candle["Low"]),
        "open_time": first_candle["Datetime"],
    }
