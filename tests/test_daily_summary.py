"""daily_summary.run(): only agents with fills *today* get notified, win_rate/pnl computed
from today's slice only."""
import pytest

from api_server import agent_store, daily_summary


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "agents.db"))


def test_agent_with_todays_fill_gets_notified(monkeypatch):
    calls = []
    monkeypatch.setattr("api_server.daily_summary.notify_daily_summary", lambda **kw: calls.append(kw))

    agent = agent_store.create_agent("D", "swing", 1000)
    agent_store.record_cycle(agent["id"], {
        "cycle": 1, "decision": "BUY", "symbol": "X",
        "fill": {"side": "buy", "qty": 10, "price": 100}, "ts": "2026-08-25T09:00:00+00:00",
    })
    agent_store.record_cycle(agent["id"], {
        "cycle": 2, "decision": "SELL", "symbol": "X",
        "fill": {"side": "sell", "qty": 10, "price": 110}, "ts": "2026-08-25T10:00:00+00:00",
    })

    n = daily_summary.run(today="2026-08-25")

    assert n == 1
    assert len(calls) == 1
    assert calls[0]["agent_id"] == agent["id"]
    assert calls[0]["n_trades"] == 2
    assert calls[0]["win_rate"] == 1.0
    assert calls[0]["pnl_usd"] == 100.0


def test_agent_without_todays_fill_skipped(monkeypatch):
    calls = []
    monkeypatch.setattr("api_server.daily_summary.notify_daily_summary", lambda **kw: calls.append(kw))

    agent = agent_store.create_agent("D", "swing", 1000)
    agent_store.record_cycle(agent["id"], {
        "cycle": 1, "decision": "BUY", "symbol": "X",
        "fill": {"side": "buy", "qty": 10, "price": 100}, "ts": "2026-08-24T09:00:00+00:00",
    })

    n = daily_summary.run(today="2026-08-25")

    assert n == 0
    assert calls == []
