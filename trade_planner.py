from dataclasses import dataclass
from math import floor
from typing import Literal, Optional

__all__ = ["TradePlan", "plan_trade"]


@dataclass
class TradePlan:
    side: Literal["long", "short"]
    entry: float
    stop: float
    target: float
    shares: int
    stop_dist: float
    risk_per_trade: float
    max_loss: float
    max_win: float
    position_value: float
    buying_power_used: float
    notes: str


def _round_tick(x: float, tick: float) -> float:
    """Round a price to the nearest valid tick size with stable floating precision."""
    return round(round(x / tick) * tick, 10)


def plan_trade(
    side: Literal["long", "short"],
    entry: float,
    initial_capital: float,
    risk_pct: float,
    rr_ratio: float,
    leverage: float = 1.0,
    stop_price: Optional[float] = None,
    stop_dist: Optional[float] = None,
    tick_size: float = 0.01,
    lot_size: int = 1,
    use_full_buying_power_if_no_stop: bool = True,
) -> TradePlan:
    """Plan a trade using risk-based sizing.

    Behavior:
        - If a stop (price or distance) is provided: size shares from dollar risk
            (initial_capital * risk_pct) and cap by buying power
            (initial_capital * leverage).
        - If no stop is provided and use_full_buying_power_if_no_stop=True: deploy
            full buying power and infer the stop distance that satisfies the dollar
            risk.

    Assumptions:
    - Leverage only increases maximum deployable notional; it does NOT amplify risk_per_trade.
    - All rounding to valid ticks happens after raw distances are computed, then distances/P&L are
      recomputed from rounded prices for consistency.
    """
    assert side in ("long", "short")
    assert entry > 0 and initial_capital > 0 and 0 < risk_pct < 1 and rr_ratio > 0 and leverage > 0

    risk_per_trade = initial_capital * risk_pct
    max_shares_bp = floor((initial_capital * leverage) / entry)
    max_shares_bp = max(0, (max_shares_bp // lot_size) * lot_size)

    # Derive stop_dist if explicit stop_price provided.
    if stop_dist is None and stop_price is not None:
        stop_dist = (entry - stop_price) if side == "long" else (stop_price - entry)

    notes = []
    if stop_dist is not None:
        if stop_dist <= 0:
            raise ValueError("Stop distance must be positive.")
        shares_risk = floor(
            risk_per_trade / stop_dist
        )  # risk-per-share sizing (no leverage multiplier)
        shares = min(shares_risk, max_shares_bp)
        if shares <= 0:
            raise ValueError("Stop too tight or insufficient buying power.")
        if side == "long":
            stop = entry - stop_dist
            target = entry + rr_ratio * stop_dist
        else:
            stop = entry + stop_dist
            target = entry - rr_ratio * stop_dist
        notes.append("Shares sized by risk and capped by buying power.")
    else:
        if not use_full_buying_power_if_no_stop:
            raise ValueError("Provide stop_price/stop_dist or enable full-buying-power inference.")
        shares = max_shares_bp
        if shares <= 0:
            raise ValueError("Insufficient buying power.")
        stop_dist = risk_per_trade / shares
        if side == "long":
            stop = entry - stop_dist
            target = entry + rr_ratio * stop_dist
        else:
            stop = entry + stop_dist
            target = entry - rr_ratio * stop_dist
        notes.append(
            "No stop provided; inferred stop distance from full buying power "
            "to satisfy dollar risk."
        )

    # Round and recompute distances and derived P&L limits.
    stop = _round_tick(stop, tick_size)
    target = _round_tick(target, tick_size)
    stop_dist = abs(entry - stop)
    max_loss = shares * stop_dist
    max_win = shares * rr_ratio * stop_dist
    pos_value = shares * entry

    return TradePlan(
        side=side,
        entry=entry,
        stop=stop,
        target=target,
        shares=shares,
        stop_dist=stop_dist,
        risk_per_trade=risk_per_trade,
        max_loss=max_loss,
        max_win=max_win,
        position_value=pos_value,
        buying_power_used=pos_value / leverage,
        notes=" ".join(notes),
    )
