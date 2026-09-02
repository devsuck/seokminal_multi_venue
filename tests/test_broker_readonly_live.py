"""jarvis/broker_readonly/live_providers.py 단위 테스트 — 실 네트워크 없음.
HL/KIS SDK 호출 지점을 monkeypatch로 가짜 응답으로 대체."""
from __future__ import annotations

from jarvis.broker_readonly.live_providers import HLReadOnlyProvider, KISReadOnlyProvider


def _fake_hl_positions(paper=False):
    return {
        "margin_summary": {"accountValue": "1000.5", "spotUsdcBalance": "50.0"},
        "asset_positions": [
            {"position": {"coin": "BTC", "szi": "0.1", "entryPx": "60000", "positionValue": "6500"}},
            {"position": {"coin": "ETH", "szi": "0", "entryPx": "0", "positionValue": "0"}},
        ],
        "open_orders": [],
    }


def test_hl_account_snapshot(monkeypatch):
    monkeypatch.setattr("hyperliquid.trader.get_positions", _fake_hl_positions)
    snap = HLReadOnlyProvider(paper=False).account_snapshot()
    assert snap.equity == 1000.5 and snap.cash == 50.0


def test_hl_positions_skips_zero_size(monkeypatch):
    monkeypatch.setattr("hyperliquid.trader.get_positions", _fake_hl_positions)
    positions = HLReadOnlyProvider(paper=False).positions()
    assert len(positions) == 1 and positions[0].symbol == "BTC"


def test_hl_health_check_reports_disconnected_on_error(monkeypatch):
    def _raise(paper=False):
        raise ValueError("HL_PRIVATE_KEY env var not set")
    monkeypatch.setattr("hyperliquid.trader.get_positions", _raise)
    h = HLReadOnlyProvider(paper=False).health_check()
    assert h.connected is False and "HL_PRIVATE_KEY" in h.error


def test_hl_orders_history_filters_by_venue_and_paper(monkeypatch):
    entries = [
        {"ts": "t1", "venue": "HL", "status": "submitted",
         "request": {"coin": "BTC", "is_buy": True, "size": 0.1, "paper": False}},
        {"ts": "t2", "venue": "HL", "status": "submitted",
         "request": {"coin": "ETH", "is_buy": False, "size": 1.0, "paper": True}},
        {"ts": "t3", "venue": "KR", "status": "submitted",
         "request": {"code": "005930", "side": "BUY", "quantity": 10, "paper": False}},
    ]
    monkeypatch.setattr("api_server.order_audit.read_recent", lambda limit=2000: entries)
    trades = HLReadOnlyProvider(paper=False).orders_history()
    assert len(trades) == 1 and trades[0]["symbol"] == "BTC" and trades[0]["side"] == "BUY"


def test_kis_missing_creds_raises_in_health_check(monkeypatch):
    for k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_CANO", "KIS_ACNT_PRDT_CD"):
        monkeypatch.delenv(k, raising=False)
    h = KISReadOnlyProvider(paper=False).health_check()
    assert h.connected is False and "미설정" in h.error


def test_kis_account_snapshot(monkeypatch):
    monkeypatch.setenv("KIS_APP_KEY", "k")
    monkeypatch.setenv("KIS_APP_SECRET", "s")
    monkeypatch.setenv("KIS_CANO", "12345678")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def get_balance(self):
            return {"deposit": 1000.0, "total_eval": 5000.0, "net_asset": 4900.0}

        def get_holdings(self):
            return [{"code": "005930", "qty": 10.0, "avg_price": 70000.0, "current": 72000.0}]

    monkeypatch.setattr("backends.kis.order_client.KISOrderClient", _FakeClient)
    p = KISReadOnlyProvider(paper=False)
    snap = p.account_snapshot()
    assert snap.cash == 1000.0 and snap.equity == 4900.0
    positions = p.positions()
    assert positions[0].symbol == "005930" and positions[0].market_value == 720000.0


def test_kis_mock_prefix_used_for_paper(monkeypatch):
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "mk")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "ms")
    monkeypatch.setenv("KIS_MOCK_CANO", "87654321")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")
    captured = {}

    class _FakeClient:
        def __init__(self, app_key, app_secret, cano, acnt_prdt_cd, mock=True):
            captured["mock"] = mock
            captured["cano"] = cano

        def get_balance(self):
            return {"deposit": 0.0, "total_eval": 0.0, "net_asset": 0.0}

    monkeypatch.setattr("backends.kis.order_client.KISOrderClient", _FakeClient)
    KISReadOnlyProvider(paper=True).account_snapshot()
    assert captured == {"mock": True, "cano": "87654321"}
