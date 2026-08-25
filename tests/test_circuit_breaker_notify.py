"""_check_risk → notify_circuit_breaker wiring: fires once per breach-day, not per retry."""
import pytest
from fastapi import HTTPException

from api_server import main as api_main


@pytest.fixture(autouse=True)
def _isolate_tracker(monkeypatch):
    # Fresh tracker + reset debounce state so tests don't leak into each other.
    monkeypatch.setattr(api_main, "daily_pnl_tracker", api_main.DailyPnLTracker())
    monkeypatch.setattr(api_main, "_circuit_breaker_notified_day", None)
    monkeypatch.setenv("DAILY_LOSS_LIMIT", "1000")
    monkeypatch.delenv("TRADING_KILL_SWITCH", raising=False)


def test_daily_loss_breach_notifies_once(monkeypatch):
    calls = []
    monkeypatch.setattr("api_server.lv6_notify.notify_circuit_breaker", lambda **kw: calls.append(kw))
    api_main.daily_pnl_tracker.add(-2000)

    for _ in range(3):
        with pytest.raises(HTTPException):
            api_main._check_risk(side="BUY", quantity=1, price_estimate=10)

    assert len(calls) == 1
    assert calls[0]["agent_id"] == "FIRM"
    assert calls[0]["daily_loss_usd"] == 2000
    assert calls[0]["limit_usd"] == 1000


def test_non_daily_loss_violation_does_not_notify(monkeypatch):
    calls = []
    monkeypatch.setattr("api_server.lv6_notify.notify_circuit_breaker", lambda **kw: calls.append(kw))

    with pytest.raises(HTTPException):
        api_main._check_risk(side="BUY", quantity=-1, price_estimate=10)

    assert calls == []
