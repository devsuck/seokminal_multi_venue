"""Per-agent performance endpoint (FIFO ledger from cycle fills)."""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api_server.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "agents.db"))
    return TestClient(app)


def _post_fill(client, aid, cycle, symbol, side, qty, price, note=""):
    return client.post(f"/agents/{aid}/cycles", json={
        "cycle": cycle, "decision": side.upper(), "symbol": symbol,
        "note": note, "fill": {"side": side, "qty": qty, "price": price},
    })


def test_performance_missing_agent_404(client):
    assert client.get("/agents/ghost/performance").status_code == 404


def test_performance_no_trades(client):
    aid = client.post("/agents", json={"name": "A", "type": "swing", "account_alloc": 100000}).json()["id"]
    body = client.get(f"/agents/{aid}/performance").json()
    assert body["realized_pnl"] == 0.0
    assert body["trades"] == []
    assert body["open_positions"] == []
    assert body["cash"] == 100000.0


def test_performance_realized_pnl_and_trade_reason(client):
    aid = client.post("/agents", json={"name": "A", "type": "swing", "account_alloc": 100000}).json()["id"]
    _post_fill(client, aid, 1, "AAPL", "buy", 10, 100.0, "저평가 진입")
    _post_fill(client, aid, 2, "AAPL", "sell", 10, 110.0, "목표가 익절")
    body = client.get(f"/agents/{aid}/performance").json()
    assert body["realized_pnl"] == 100.0
    assert body["open_positions"] == []
    # newest-first trade log carries the reason
    assert body["trades"][0]["reason"] == "목표가 익절"
    assert body["trades"][0]["side"] == "sell"


def test_performance_open_position_uses_ib_price_for_live_us_agent(client, monkeypatch):
    """Live (non-paper) US-venue agents fill via IB, not Alpaca — /performance must
    price open positions off IB, or unrealized_pnl silently stays 0 (2026-08-02 bug)."""
    import api_server.routers.agents as agents_router_module

    monkeypatch.setattr("jarvis.execution.agent_gate.enforce_paper", lambda agent: (False, None))
    monkeypatch.setattr(agents_router_module, "_ib_latest_prices", lambda symbols: dict.fromkeys(symbols, 120.0))
    monkeypatch.setattr(agents_router_module, "_latest_price", lambda symbol: (_ for _ in ()).throw(
        AssertionError("Alpaca path must not be used for a live IB agent")))

    aid = client.post("/agents", json={"name": "A", "type": "swing", "account_alloc": 100000}).json()["id"]
    _post_fill(client, aid, 1, "NVDA", "buy", 10, 100.0)
    body = client.get(f"/agents/{aid}/performance").json()
    assert body["open_positions"][0]["current_price"] == 120.0
    assert body["unrealized_pnl"] == 200.0


def test_performance_open_position_prices_via_barset_data_not_contains(client, monkeypatch):
    """Alpaca's BarSet has no working `__contains__` (`sym in resp` is always False
    even when `resp.data[sym]` has bars) — pricing must read `resp.data` directly,
    or unrealized_pnl silently stays 0 for every paper-US agent (found 2026-08-04
    while investigating a user report that swing/autonomous agents showed no
    unrealized PnL)."""
    import api_server.routers.agents as agents_router_module

    fake_bar = MagicMock(close=120.0)
    fake_resp = MagicMock(data={"NVDA": [fake_bar]})
    fake_resp.__contains__ = MagicMock(return_value=False)  # BarSet's real (broken) behavior
    fake_client = MagicMock()
    fake_client.get_stock_bars.return_value = fake_resp
    monkeypatch.setattr(agents_router_module.shared, "_data_client", lambda: fake_client)

    aid = client.post("/agents", json={"name": "A", "type": "swing", "account_alloc": 100000}).json()["id"]
    _post_fill(client, aid, 1, "NVDA", "buy", 10, 100.0)
    body = client.get(f"/agents/{aid}/performance").json()
    assert body["open_positions"][0]["current_price"] == 120.0
    assert body["unrealized_pnl"] == 200.0
