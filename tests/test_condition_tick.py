"""condition-tick smoke: Lv1 조건식 게이트 + EMA 크로스 wiring (no live network)."""
import pytest
from fastapi.testclient import TestClient

from api_server.main import app

INSTRUMENT = "005930.XKRX"


def _rule(rsi_threshold: float) -> dict:
    return {
        "condition": {
            "combinator": "AND",
            "conditions": [
                {
                    "left": {
                        "indicator": "RSI",
                        "bar_type": f"{INSTRUMENT}-1-DAY-LAST-EXTERNAL",
                        "params": {"period": 14},
                    },
                    "op": "<",
                    "right": {"value": rsi_threshold},
                },
            ],
        },
        "strategy": {"params": {"fast_ema_period": 5, "slow_ema_period": 15}},
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "agents.db"))
    return TestClient(app)


def test_condition_tick_rejects_non_lv1_agent(client):
    aid = client.post("/agents", json={
        "name": "S", "type": "swing", "account_alloc": 50000,
    }).json()["id"]

    r = client.post(f"/agents/{aid}/condition-tick?cycle=1")
    assert r.status_code == 400


def test_condition_tick_watch_when_gate_false(client):
    aid = client.post("/agents", json={
        "name": "L1", "type": "condition_lv1", "account_alloc": 1000000, "autonomy": 1,
        "condition": _rule(0.001), "instrument_id": INSTRUMENT,
    }).json()["id"]

    r = client.post(f"/agents/{aid}/condition-tick?cycle=1")
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "WATCH"
    assert body["spawned"] is False


def test_condition_tick_buys_when_gate_true(client, monkeypatch):
    class _KIS:
        def __init__(self, *args, **kwargs):
            pass

        def get_balance(self):
            return {"net_asset": 1000000.0}

        def get_holdings(self):
            return []

        def place_order(self, *args, **kwargs):
            return {"order_id": "1"}

    monkeypatch.setattr("backends.kis.order_client.KISOrderClient", _KIS)

    aid = client.post("/agents", json={
        "name": "L1", "type": "condition_lv1", "account_alloc": 50000000, "autonomy": 1,
        "condition": _rule(99), "instrument_id": INSTRUMENT,
    }).json()["id"]

    r = client.post(f"/agents/{aid}/condition-tick?cycle=1")
    assert r.status_code == 200
    body = r.json()
    assert body["spawned"] is True
    assert body["decision"] in ("BUY", "HOLD")

    assert len(client.get(f"/agents/{aid}/cycles").json()["cycles"]) == 1


def test_condition_tick_dd_pause_blocks_new_buy_after_big_realized_loss(client, monkeypatch):
    # 실현손실이 배정자본의 50%를 넘으면 신규진입(BUY) 정지 — 청산은 막지 않는다.
    from api_server import agent_store

    class _KIS:
        def __init__(self, *args, **kwargs):
            pass

        def get_balance(self):
            return {"net_asset": 1000000.0}

        def get_holdings(self):
            return []

        def place_order(self, *args, **kwargs):
            raise AssertionError("dd_pause should have blocked this order")

    monkeypatch.setattr("backends.kis.order_client.KISOrderClient", _KIS)

    aid = client.post("/agents", json={
        "name": "L1", "type": "condition_lv1", "account_alloc": 100000, "autonomy": 1,
        "condition": _rule(99), "instrument_id": INSTRUMENT,
    }).json()["id"]

    agent_store.record_cycle(aid, {
        "cycle": 1, "decision": "BUY", "symbol": INSTRUMENT,
        "fill": {"side": "buy", "qty": 1000, "price": 100.0},
    })
    agent_store.record_cycle(aid, {
        "cycle": 2, "decision": "SELL", "symbol": INSTRUMENT,
        "fill": {"side": "sell", "qty": 1000, "price": 50.0},  # realized -50000 == -alloc*0.5
    })

    r = client.post(f"/agents/{aid}/condition-tick?cycle=3")
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "SKIP"
    cycles = client.get(f"/agents/{aid}/cycles").json()["cycles"]
    assert "서킷브레이커" in cycles[-1]["note"]
