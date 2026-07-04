"""Agent registry + structured cycle store."""
import pytest

import api_server.agent_store as _store


@pytest.fixture
def store(tmp_path, monkeypatch):
    # _db_path() reads AGENT_DB_PATH per call, so env redirection isolates each
    # test against a fresh DB without reloading the module.
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "agents.db"))
    return _store


def test_create_agent_returns_profile(store):
    a = store.create_agent("Swing Bot", "swing", 50000.0)
    assert a["name"] == "Swing Bot"
    assert a["type"] == "swing"
    assert a["status"] == "stopped"
    assert a["account_alloc"] == 50000.0
    assert a["profile"]["cadence_seconds"] == 8 * 3600
    assert len(a["id"]) == 8


def test_create_rejects_unknown_type(store):
    with pytest.raises(ValueError, match="unknown agent type"):
        store.create_agent("X", "scalper", 1000.0)


def test_list_and_get(store):
    a = store.create_agent("A", "swing", 10000.0)
    b = store.create_agent("B", "daytrade", 20000.0)
    ids = {x["id"] for x in store.list_agents()}
    assert ids == {a["id"], b["id"]}
    assert store.get_agent(a["id"])["name"] == "A"
    assert store.get_agent("nope") is None


def test_set_status(store):
    a = store.create_agent("A", "swing", 10000.0)
    updated = store.set_status(a["id"], "running")
    assert updated["status"] == "running"
    assert store.get_agent(a["id"])["status"] == "running"


def test_set_status_invalid(store):
    a = store.create_agent("A", "swing", 10000.0)
    with pytest.raises(ValueError, match="invalid status"):
        store.set_status(a["id"], "paused")


def test_set_status_missing_agent_returns_none(store):
    assert store.set_status("ghost", "running") is None


def test_delete_agent_removes_cycles(store):
    a = store.create_agent("A", "daytrade", 10000.0)
    store.record_cycle(a["id"], {"cycle": 1, "decision": "WATCH", "symbol": "AAPL"})
    assert store.delete_agent(a["id"]) is True
    assert store.get_agent(a["id"]) is None
    assert store.read_cycles(a["id"]) == []


def test_record_and_read_cycles_newest_last(store):
    a = store.create_agent("A", "swing", 10000.0)
    for i in range(1, 4):
        store.record_cycle(a["id"], {
            "cycle": i, "decision": "WATCH", "symbol": "AAPL",
            "score": 18, "max_score": 40, "cash_pct": 100,
        })
    cycles = store.read_cycles(a["id"])
    assert [c["cycle"] for c in cycles] == [1, 2, 3]
    assert cycles[-1]["score"] == 18


def test_record_cycle_rejects_bad_decision(store):
    a = store.create_agent("A", "swing", 10000.0)
    with pytest.raises(ValueError, match="invalid decision"):
        store.record_cycle(a["id"], {"cycle": 1, "decision": "MOON", "symbol": "AAPL"})


def test_record_cycle_defaults_ts(store):
    a = store.create_agent("A", "swing", 10000.0)
    entry = store.record_cycle(a["id"], {"cycle": 1, "decision": "BUY", "symbol": "AAPL"})
    assert "ts" in entry and entry["ts"]


def test_read_cycles_limit(store):
    a = store.create_agent("A", "daytrade", 10000.0)
    for i in range(1, 11):
        store.record_cycle(a["id"], {"cycle": i, "decision": "HOLD", "symbol": "SPY"})
    cycles = store.read_cycles(a["id"], limit=3)
    assert [c["cycle"] for c in cycles] == [8, 9, 10]


def test_paper_flag_defaults_true(store):
    a = store.create_agent("A", "hl_daytrade", 10.0)
    assert a["paper"] is True
    assert store.get_agent(a["id"])["paper"] is True


def test_live_flag_persists(store):
    a = store.create_agent("Live", "hl_daytrade", 100.0, paper=False)
    assert a["paper"] is False
    assert store.get_agent(a["id"])["paper"] is False


def test_autonomy_defaults_and_persists(store):
    a = store.create_agent("A", "swing", 100.0, autonomy=3)
    assert a["autonomy"] == 3
    assert store.get_agent(a["id"])["autonomy"] == 3
    b = store.create_agent("B", "swing", 100.0)
    assert b["autonomy"] == 2  # default = AI strategist


def test_autonomy_invalid_rejected(store):
    import pytest
    with pytest.raises(ValueError, match="autonomy"):
        store.create_agent("X", "swing", 100.0, autonomy=6)  # 6 범위 초과


def test_market_scope_defaults_and_persists(store):
    a = store.create_agent("A", "swing", 100.0, market="MIXED")
    assert a["market"] == "MIXED"
    assert store.get_agent(a["id"])["market"] == "MIXED"
    assert store.create_agent("B", "swing", 100.0)["market"] == "US"  # default


def test_market_invalid_rejected(store):
    import pytest
    with pytest.raises(ValueError, match="market"):
        store.create_agent("X", "swing", 100.0, market="JP")
