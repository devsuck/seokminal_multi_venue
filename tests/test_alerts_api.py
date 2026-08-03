import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from api_server.main import app, _alert_rules, _triggered_alerts

client = TestClient(app)


def setup_function():
    _alert_rules.clear()
    _triggered_alerts.clear()


@pytest.fixture(autouse=True)
def _stub_convergence_compute():
    """get_triggered_alerts()가 매 폴링마다 _check_insider_convergence()를 통해
    실제 _convergence_compute()(DART/Congress/options-UOA 라이브 네트워크 호출)를
    부른다. 개별 테스트가 자체 patch로 재정의하지 않는 한 기본값 []로 스텁해서
    기존(컨버전스 무관) 테스트들이 실제 네트워크 I/O로 멎지 않게 한다."""
    with patch("api_server.main._convergence_compute", return_value=[]):
        yield


# ── POST /alerts/rules ────────────────────────────────────────

def test_create_rule_price_above_returns_201():
    r = client.post("/alerts/rules", json={
        "label": "AAPL high", "condition_type": "price_above",
        "bot_id": "bot1", "threshold": 200.0,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["label"] == "AAPL high"
    assert body["condition_type"] == "price_above"
    assert body["threshold"] == 200.0
    assert "id" in body
    assert "created_at" in body


def test_create_rule_bot_stopped_no_threshold_ok():
    r = client.post("/alerts/rules", json={
        "label": "bot down", "condition_type": "bot_stopped", "bot_id": "bot1",
    })
    assert r.status_code == 201
    assert r.json()["threshold"] is None


def test_create_rule_unknown_condition_type_returns_400():
    r = client.post("/alerts/rules", json={
        "label": "bad", "condition_type": "unknown_type", "bot_id": "bot1",
    })
    assert r.status_code == 400


def test_create_rule_price_above_missing_threshold_returns_400():
    r = client.post("/alerts/rules", json={
        "label": "no threshold", "condition_type": "price_above", "bot_id": "bot1",
    })
    assert r.status_code == 400


def test_create_rule_pnl_below_missing_threshold_returns_400():
    r = client.post("/alerts/rules", json={
        "label": "pnl check", "condition_type": "pnl_below", "bot_id": "bot1",
    })
    assert r.status_code == 400


# ── GET /alerts/rules ─────────────────────────────────────────

def test_list_rules_empty():
    r = client.get("/alerts/rules")
    assert r.status_code == 200
    assert r.json()["rules"] == []


def test_list_rules_returns_created_rules():
    client.post("/alerts/rules", json={
        "label": "rule A", "condition_type": "bot_error", "bot_id": "bot1",
    })
    client.post("/alerts/rules", json={
        "label": "rule B", "condition_type": "bot_stopped", "bot_id": "bot2",
    })
    r = client.get("/alerts/rules")
    assert r.status_code == 200
    assert len(r.json()["rules"]) == 2


# ── DELETE /alerts/rules/{id} ─────────────────────────────────

def test_delete_rule_returns_204():
    create_r = client.post("/alerts/rules", json={
        "label": "to delete", "condition_type": "bot_stopped", "bot_id": "bot1",
    })
    rule_id = create_r.json()["id"]
    r = client.delete(f"/alerts/rules/{rule_id}")
    assert r.status_code == 204


def test_delete_rule_removes_from_list():
    create_r = client.post("/alerts/rules", json={
        "label": "to delete", "condition_type": "bot_stopped", "bot_id": "bot1",
    })
    rule_id = create_r.json()["id"]
    client.delete(f"/alerts/rules/{rule_id}")
    r = client.get("/alerts/rules")
    assert all(rule["id"] != rule_id for rule in r.json()["rules"])


def test_delete_nonexistent_rule_returns_404():
    r = client.delete("/alerts/rules/does-not-exist")
    assert r.status_code == 404


# ── GET /alerts/triggered ─────────────────────────────────────

def test_triggered_empty_when_no_rules():
    r = client.get("/alerts/triggered")
    assert r.status_code == 200
    assert r.json()["triggered"] == []


def test_triggered_bot_stopped_when_bot_not_in_engine():
    client.post("/alerts/rules", json={
        "label": "bot down", "condition_type": "bot_stopped", "bot_id": "ghost_bot",
    })
    with patch("api_server.main.live_engine") as mock_engine:
        mock_engine.get_all_statuses.return_value = {}
        r = client.get("/alerts/triggered")
    assert r.status_code == 200
    triggered = r.json()["triggered"]
    assert len(triggered) == 1
    assert triggered[0]["condition_type"] == "bot_stopped"
    assert triggered[0]["bot_id"] == "ghost_bot"


def test_triggered_price_above_when_condition_met():
    client.post("/alerts/rules", json={
        "label": "high price", "condition_type": "price_above",
        "bot_id": "bot1", "threshold": 100.0,
    })
    mock_status = MagicMock()
    mock_status.last_price = 150.0
    mock_status.position = "FLAT"
    mock_status.qty = 0.0
    mock_status.entry_price = None
    mock_status.error = None
    with patch("api_server.main.live_engine") as mock_engine:
        mock_engine.get_all_statuses.return_value = {"bot1": mock_status}
        r = client.get("/alerts/triggered")
    assert r.status_code == 200
    triggered = r.json()["triggered"]
    assert len(triggered) == 1
    assert "150" in triggered[0]["detail"]


def test_triggered_no_duplicate_within_dedup_window():
    client.post("/alerts/rules", json={
        "label": "bot down", "condition_type": "bot_stopped", "bot_id": "ghost_bot",
    })
    with patch("api_server.main.live_engine") as mock_engine:
        mock_engine.get_all_statuses.return_value = {}
        client.get("/alerts/triggered")
        r = client.get("/alerts/triggered")
    assert len(r.json()["triggered"]) == 1


def test_triggered_condition_not_met_no_entry():
    client.post("/alerts/rules", json={
        "label": "low price", "condition_type": "price_below",
        "bot_id": "bot1", "threshold": 50.0,
    })
    mock_status = MagicMock()
    mock_status.last_price = 100.0
    mock_status.error = None
    with patch("api_server.main.live_engine") as mock_engine:
        mock_engine.get_all_statuses.return_value = {"bot1": mock_status}
        r = client.get("/alerts/triggered")
    assert r.json()["triggered"] == []


# ── insider convergence merge ─────────────────────────────────

def test_triggered_includes_insider_convergence_signal():
    mock_signals_kr = [{
        "ticker": "005930", "market": "kr", "direction": "BULLISH", "score": 2,
        "legs": [
            {"source": "dart_exec", "trade_date": "2026-08-01", "detail": "d1", "url": None},
            {"source": "dart_corp_action", "trade_date": "2026-08-01", "detail": "d2", "url": None},
        ],
    }]
    with patch("api_server.main.live_engine") as mock_engine, \
         patch("api_server.main._convergence_compute", side_effect=lambda market, days=30: mock_signals_kr if market == "kr" else []):
        mock_engine.get_all_statuses.return_value = {}
        r = client.get("/alerts/triggered")
    assert r.status_code == 200
    triggered = r.json()["triggered"]
    conv = [t for t in triggered if t["bot_id"] == "insider-convergence"]
    assert len(conv) == 1
    assert conv[0]["rule_id"] == "insider-convergence:kr:005930:BULLISH"
    assert "005930" in conv[0]["detail"]


def test_triggered_convergence_dedup_within_window():
    mock_signals_kr = [{
        "ticker": "005930", "market": "kr", "direction": "BULLISH", "score": 2,
        "legs": [{"source": "dart_exec", "trade_date": "2026-08-01", "detail": "d1", "url": None}],
    }]
    with patch("api_server.main.live_engine") as mock_engine, \
         patch("api_server.main._convergence_compute", side_effect=lambda market, days=30: mock_signals_kr if market == "kr" else []):
        mock_engine.get_all_statuses.return_value = {}
        client.get("/alerts/triggered")
        r2 = client.get("/alerts/triggered")
    conv = [t for t in r2.json()["triggered"] if t["bot_id"] == "insider-convergence"]
    assert len(conv) == 1  # 두번째 폴링에서 중복 추가 안됨 (300s dedup window)
