"""daytrade-tick smoke: budget/wiring regression (no live network)."""
import pytest
from fastapi.testclient import TestClient

from api_server.routers import alpaca_shared as shared
from api_server.main import app


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """jarvis state 파일들을 tmp로 격리(실 상태 오염 방지).
    지금은 모든 테스트 에이전트가 paper=True라 enforce_paper가 상태 파일을
    건드리기 전에 단락되지만, paper=False 에이전트가 추가되는 순간을 대비."""
    monkeypatch.setattr("jarvis.config.STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "agents.db"))
    # Avoid network: US scores come back empty → AVOID, no orders.
    monkeypatch.setattr(shared, "_fetch_intraday_bars", lambda s, days=2: [])
    # Alpaca client stub (account + positions)
    class _Acct:  equity = 100000.0
    class _Cli:
        def get_account(self): return _Acct()
        def get_all_positions(self): return []
        def close_position(self, s): pass
        def submit_order(self, r): pass
    monkeypatch.setattr(shared, "_trading_client", lambda *a, **k: _Cli())
    return TestClient(app, client=("127.0.0.1", 1))


def test_daytrade_tick_us_no_crash(client):
    aid = client.post("/agents", json={"name": "D", "type": "daytrade", "account_alloc": 50000}).json()["id"]
    r = client.post(f"/agents/{aid}/daytrade-tick?cycle=1")
    assert r.status_code == 200
    assert r.json()["decision"] == "SKIP"  # empty scores → no entry
    # cycle recorded
    assert len(client.get(f"/agents/{aid}/cycles").json()["cycles"]) == 1


def test_lv5_agentic_overlay_skipped_for_live_god_mode_agent(client, monkeypatch):
    """Lv3 agent promoted to live(paper=False) must NOT run the Claude-driven
    agentic overlay (unvalidated universe/dsl changes on real money would
    violate CONSTITUTION.md's "no autonomous trading") — only the
    deterministic compute_lv5_params() may still adjust threshold/position_pct."""
    import api_server.lv5_agent as lv5_agent
    from jarvis.execution import agent_gate

    monkeypatch.setattr(agent_gate, "enforce_paper", lambda agent: (False, ""))
    calls = []
    monkeypatch.setattr(lv5_agent, "apply_cached_strategy", lambda *a, **k: calls.append("apply") or (0, 0, [], False, ""))
    monkeypatch.setattr(lv5_agent, "trigger_review_if_needed", lambda *a, **k: calls.append("trigger"))

    aid = client.post("/agents", json={
        "name": "LiveLv3", "type": "daytrade", "account_alloc": 50000,
        "paper": False, "autonomy": 3,
    }).json()["id"]
    r = client.post(f"/agents/{aid}/daytrade-tick?cycle=1")
    assert r.status_code == 200
    assert calls == []


def test_lv5_agentic_overlay_runs_for_paper_agent(client, monkeypatch):
    """Unchanged behavior for paper agents: the agentic overlay still applies."""
    import api_server.lv5_agent as lv5_agent
    import api_server.lv5_context as lv5_context
    from jarvis.execution import agent_gate

    monkeypatch.setattr(agent_gate, "enforce_paper", lambda agent: (True, ""))
    calls = []
    monkeypatch.setattr(lv5_agent, "apply_cached_strategy",
                         lambda agent_id, threshold, position_pct, universe: (calls.append("apply") or (threshold, position_pct, universe, False, "")))
    monkeypatch.setattr(lv5_agent, "trigger_review_if_needed", lambda *a, **k: calls.append("trigger"))
    monkeypatch.setattr(lv5_context, "get_cached_context", lambda *a, **k: {})

    aid = client.post("/agents", json={
        "name": "PaperLv3", "type": "daytrade", "account_alloc": 50000,
        "paper": True, "autonomy": 3,
    }).json()["id"]
    r = client.post(f"/agents/{aid}/daytrade-tick?cycle=1")
    assert r.status_code == 200
    assert calls == ["apply", "trigger"]


def test_swing_kr_routes_to_kr_not_us(client, monkeypatch):
    """스윙(장투) 봇 + market=KR → KR 실행(KIS), US(Alpaca) 아님. 통화 오라우팅 회귀."""
    monkeypatch.setattr(shared, "_fetch_kr_intraday_bars", lambda s: [])

    class _KIS:
        def __init__(self, *a, **k): pass
        def get_balance(self): return {"net_asset": 1000000.0}
        def get_holdings(self): return []
        def place_order(self, *a, **k): return {"order_id": "1"}
    monkeypatch.setattr("backends.kis.order_client.KISOrderClient", _KIS)

    aid = client.post("/agents", json={
        "name": "KRswing", "type": "swing", "market": "KR", "account_alloc": 1000000,
    }).json()["id"]
    r = client.post(f"/agents/{aid}/daytrade-tick?cycle=1")
    assert r.status_code == 200
    assert r.json()["venue"] == "KR"  # not US → no Alpaca/USD order
