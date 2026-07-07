"""God Mode 승급 3조건 심사 (api_server/god_mode.py)."""
import datetime as dt

import pytest

import api_server.agent_store as _store
import api_server.god_mode as god_mode


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "agents.db"))
    return _store


def _iso(days_ago: float) -> str:
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)).isoformat()


def _record(store, agent_id, n, symbol, side, qty, price, days_ago):
    store.record_cycle(agent_id, {
        "cycle": n, "ts": _iso(days_ago), "symbol": symbol, "decision": side.upper(),
        "fill": {"side": side, "qty": qty, "price": price},
    })


def test_unknown_agent_raises_value_error(store):
    with pytest.raises(ValueError):
        god_mode.evaluate("nope")


def test_no_cycles_in_window_fails_all_conditions(store, monkeypatch):
    agent = store.create_agent("A", "swing", 10000.0, autonomy=3)
    report = god_mode.evaluate(agent["id"])
    assert report["eligible"] is False
    assert all(not c["passed"] for c in report["conditions"])


def test_eligible_when_all_three_conditions_pass(store, monkeypatch):
    monkeypatch.setattr(god_mode, "_benchmark_return_pct", lambda market, start, end: 1.0)
    agent = store.create_agent("A", "swing", 10000.0, autonomy=3, market="US")
    # 순수익 20% (벤치마크 1% 초과), MDD 0%, 후반(150) >= 전반(50)
    _record(store, agent["id"], 1, "AAPL", "buy", 10, 100.0, days_ago=10)
    _record(store, agent["id"], 2, "AAPL", "sell", 10, 105.0, days_ago=8)   # +50
    _record(store, agent["id"], 3, "AAPL", "buy", 10, 100.0, days_ago=6)
    _record(store, agent["id"], 4, "AAPL", "sell", 10, 115.0, days_ago=4)   # +150

    report = god_mode.evaluate(agent["id"])
    assert report["eligible"] is True
    assert all(c["passed"] for c in report["conditions"])
    assert report["agent_id"] == agent["id"]
    assert report["window_days"] == 30


def test_fails_when_below_benchmark(store, monkeypatch):
    monkeypatch.setattr(god_mode, "_benchmark_return_pct", lambda market, start, end: 50.0)
    agent = store.create_agent("A", "swing", 10000.0, autonomy=3, market="US")
    _record(store, agent["id"], 1, "AAPL", "buy", 10, 100.0, days_ago=5)
    _record(store, agent["id"], 2, "AAPL", "sell", 10, 105.0, days_ago=3)  # +50 = +0.5%, well under 50%

    report = god_mode.evaluate(agent["id"])
    assert report["eligible"] is False
    beats = next(c for c in report["conditions"] if c["key"] == "beats_benchmark")
    assert beats["passed"] is False


def test_fails_when_mdd_exceeds_limit(store, monkeypatch):
    monkeypatch.setattr(god_mode, "_benchmark_return_pct", lambda market, start, end: -100.0)
    agent = store.create_agent("A", "swing", 1000.0, autonomy=3, market="US")
    _record(store, agent["id"], 1, "AAPL", "buy", 10, 100.0, days_ago=6)
    _record(store, agent["id"], 2, "AAPL", "sell", 10, 50.0, days_ago=4)  # -500 realized, -50% of alloc

    report = god_mode.evaluate(agent["id"])
    assert report["eligible"] is False
    mdd = next(c for c in report["conditions"] if c["key"] == "mdd_within_limit")
    assert mdd["passed"] is False


def test_fails_walk_forward_when_second_half_worse(store, monkeypatch):
    monkeypatch.setattr(god_mode, "_benchmark_return_pct", lambda market, start, end: -100.0)
    agent = store.create_agent("A", "swing", 10000.0, autonomy=3, market="US")
    _record(store, agent["id"], 1, "AAPL", "buy", 10, 100.0, days_ago=10)
    _record(store, agent["id"], 2, "AAPL", "sell", 10, 120.0, days_ago=8)   # +200 (전반)
    _record(store, agent["id"], 3, "AAPL", "buy", 10, 100.0, days_ago=6)
    _record(store, agent["id"], 4, "AAPL", "sell", 10, 90.0, days_ago=4)    # -100 (후반, 전반보다 나쁨)

    report = god_mode.evaluate(agent["id"])
    assert report["eligible"] is False
    wf = next(c for c in report["conditions"] if c["key"] == "walk_forward_stable")
    assert wf["passed"] is False
