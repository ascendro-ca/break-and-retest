import pytest

from trade_planner import plan_trade, TradePlan


def test_plan_with_explicit_stop_price_long():
    tp = plan_trade(
        side="long",
        entry=50.0,
        initial_capital=10_000.0,
        risk_pct=0.01,
        rr_ratio=2.5,
        leverage=2.0,
        stop_price=48.0,
        tick_size=0.01,
    )
    assert tp.shares == 50  # risk_per_trade=100; stop_dist=2 => floor(100/2)=50
    assert tp.stop == 48.0
    assert tp.target == 55.0  # 50 + 2.5*2
    assert pytest.approx(tp.max_loss, rel=1e-6) == 100.0
    assert pytest.approx(tp.max_win, rel=1e-6) == 250.0
    assert "risk" in tp.notes.lower()


def test_plan_short_with_stop_dist():
    tp = plan_trade(
        side="short",
        entry=30.0,
        initial_capital=5_000.0,
        risk_pct=0.02,
        rr_ratio=2.0,
        leverage=1.0,
        stop_dist=1.5,
        tick_size=0.01,
    )
    assert tp.stop == 31.5
    assert tp.target == 27.0
    assert tp.shares == 66  # risk_per_trade=100; floor(100/1.5)=66
    assert pytest.approx(tp.max_loss, rel=1e-6) == 99.0  # 66*1.5
    assert pytest.approx(tp.max_win, rel=1e-6) == 198.0  # 66*2*1.5


def test_plan_infer_stop_distance_full_bp():
    tp = plan_trade(
        side="long",
        entry=25.0,
        initial_capital=10_000.0,
        risk_pct=0.01,
        rr_ratio=3.0,
        leverage=1.0,
        tick_size=0.01,
        stop_price=None,
        stop_dist=None,
        use_full_buying_power_if_no_stop=True,
    )
    # max_shares_bp = floor(10000/25)=400; stop_dist=risk_per_trade/shares=100/400=0.25
    assert tp.shares == 400
    assert pytest.approx(tp.stop, rel=1e-6) == 24.75
    assert pytest.approx(tp.target, rel=1e-6) == 25.75  # 25 + 0.25*3
    assert pytest.approx(tp.stop_dist, rel=1e-6) == 0.25


def test_invalid_stop_distance_raises():
    with pytest.raises(ValueError):
        plan_trade(
            side="long",
            entry=10.0,
            initial_capital=1_000.0,
            risk_pct=0.01,
            rr_ratio=2.0,
            leverage=1.0,
            stop_dist=0.0,
        )


def test_missing_stop_without_flag_raises():
    with pytest.raises(ValueError):
        plan_trade(
            side="short",
            entry=15.0,
            initial_capital=2_000.0,
            risk_pct=0.02,
            rr_ratio=2.0,
            leverage=1.0,
            stop_price=None,
            stop_dist=None,
            use_full_buying_power_if_no_stop=False,
        )
