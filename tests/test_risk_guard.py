"""Tests for the pre-trade risk guard shared by every order path."""
import pytest

from live_engine.risk_guard import (
    DailyPnLTracker,
    RiskConfig,
    RiskViolation,
    validate_order,
)


def _cfg(**over):
    base = dict(
        max_order_qty=1000,
        max_order_notional=100_000.0,
        max_position_qty=5000,
        daily_loss_limit=10_000.0,
        kill_switch=False,
    )
    base.update(over)
    return RiskConfig(**base)


def test_accepts_valid_order():
    # within all limits -> no raise
    validate_order(
        side="BUY", quantity=10, price_estimate=150.0,
        current_position_qty=0, day_realized_pnl=0.0, config=_cfg(),
    )


def test_rejects_zero_quantity():
    with pytest.raises(RiskViolation, match="quantity"):
        validate_order(
            side="BUY", quantity=0, price_estimate=150.0,
            current_position_qty=0, day_realized_pnl=0.0, config=_cfg(),
        )


def test_rejects_negative_quantity():
    with pytest.raises(RiskViolation, match="quantity"):
        validate_order(
            side="SELL", quantity=-5, price_estimate=150.0,
            current_position_qty=0, day_realized_pnl=0.0, config=_cfg(),
        )


def test_rejects_quantity_over_max():
    with pytest.raises(RiskViolation, match="max order qty"):
        validate_order(
            side="BUY", quantity=2000, price_estimate=10.0,
            current_position_qty=0, day_realized_pnl=0.0, config=_cfg(),
        )


def test_rejects_notional_over_max():
    # 100 * 2000 = 200k > 100k notional cap (qty under qty cap)
    with pytest.raises(RiskViolation, match="notional"):
        validate_order(
            side="BUY", quantity=900, price_estimate=2000.0,
            current_position_qty=0, day_realized_pnl=0.0, config=_cfg(),
        )


def test_rejects_position_over_max_on_same_side_add():
    # already long 4900, buying 200 more -> 5100 > 5000 cap
    with pytest.raises(RiskViolation, match="position"):
        validate_order(
            side="BUY", quantity=200, price_estimate=10.0,
            current_position_qty=4900, day_realized_pnl=0.0, config=_cfg(),
        )


def test_reducing_position_is_allowed_even_near_cap():
    # long 5000 (at cap), SELL reduces -> allowed
    validate_order(
        side="SELL", quantity=200, price_estimate=10.0,
        current_position_qty=5000, day_realized_pnl=0.0, config=_cfg(),
    )


def test_rejects_when_daily_loss_limit_breached():
    with pytest.raises(RiskViolation, match="daily loss"):
        validate_order(
            side="BUY", quantity=10, price_estimate=10.0,
            current_position_qty=0, day_realized_pnl=-10_500.0, config=_cfg(),
        )


def test_rejects_when_kill_switch_on():
    with pytest.raises(RiskViolation, match="kill switch"):
        validate_order(
            side="BUY", quantity=10, price_estimate=10.0,
            current_position_qty=0, day_realized_pnl=0.0, config=_cfg(kill_switch=True),
        )


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("MAX_ORDER_QTY", "50")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "5000")
    monkeypatch.setenv("MAX_POSITION_QTY", "200")
    monkeypatch.setenv("DAILY_LOSS_LIMIT", "1000")
    monkeypatch.setenv("TRADING_KILL_SWITCH", "true")
    cfg = RiskConfig.from_env()
    assert cfg.max_order_qty == 50
    assert cfg.max_order_notional == 5000.0
    assert cfg.max_position_qty == 200
    assert cfg.daily_loss_limit == 1000.0
    assert cfg.kill_switch is True


def test_daily_pnl_tracker_accumulates_per_day():
    t = DailyPnLTracker()
    t.add(-100.0, day="2026-07-01")
    t.add(-50.0, day="2026-07-01")
    assert t.realized("2026-07-01") == -150.0
    # different day is independent
    assert t.realized("2026-07-02") == 0.0


def test_daily_pnl_tracker_defaults_to_today():
    t = DailyPnLTracker()
    t.add(25.0)
    assert t.realized() == 25.0
