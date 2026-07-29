"""P7.1 Broker Read-Only Integration 테스트.

deterministic mock · no write capability · reconciliation · missing position ·
stale account · audit integrity · no execution path · no permission escalation.
"""
from __future__ import annotations

import os

import pytest

from jarvis.broker_readonly.adapters import (
    IBReadOnlyProvider,
    KISReadOnlyProvider,
    MockBrokerProvider,
)
from jarvis.broker_readonly.provider import BrokerReadOnlyProvider
from jarvis.broker_readonly.reconcile import reconcile


def _mock():
    return MockBrokerProvider(
        account={"cash": 5000.0, "equity": 11000.0, "buying_power": 10000.0},
        positions=[{"symbol": "AAA", "quantity": 50, "avg_price": 100, "market_value": 6000},
                   {"symbol": "BBB", "quantity": 10, "avg_price": 20, "market_value": 200}],
        orders=[{"order_id": "O1", "symbol": "AAA", "side": "BUY", "status": "FILLED"}],
        timestamp="2026-07-22T00:00:00Z")


# ── 1. deterministic mock provider ──
def test_deterministic_mock_provider():
    a, b = _mock(), _mock()
    assert a.account_snapshot().to_dict() == b.account_snapshot().to_dict()
    assert [p.to_dict() for p in a.positions()] == [p.to_dict() for p in b.positions()]
    assert a.health_check().connected is True
    acct = a.account_snapshot()
    assert acct.cash == 5000.0 and acct.equity == 11000.0 and acct.timestamp


# ── 2. no write capability ──
def test_no_write_capability():
    for prov in (_mock(), IBReadOnlyProvider(), KISReadOnlyProvider()):
        for attr in ("execute", "place_order", "submit_order", "buy", "sell",
                     "cancel_order", "modify_order", "close_position"):
            assert not hasattr(prov, attr), f"{attr} 존재하면 안 됨"
    # 인터페이스는 읽기 메서드만
    methods = {m for m in dir(BrokerReadOnlyProvider) if not m.startswith("_")}
    assert methods == {"account_snapshot", "positions", "balances",
                       "orders_history", "health_check", "source_name"}


# ── 3. reconciliation correctness ──
def test_reconciliation_correctness():
    paper = [{"strategy_id": "AAA", "quantity": 50, "market_value": 6000},
             {"strategy_id": "BBB", "quantity": 12, "market_value": 250}]   # BBB qty/val 불일치
    rep = reconcile(paper, _mock().positions(), "2026-07-22T00:00:00Z")
    assert rep.matched == ["AAA", "BBB"]
    assert "BBB" in rep.quantity_difference and rep.quantity_difference["BBB"] == 2.0
    assert "BBB" in rep.value_difference
    assert "AAA" not in rep.quantity_difference          # 완전 일치


# ── 4. missing position handling ──
def test_missing_position_handling():
    paper = [{"strategy_id": "AAA", "quantity": 50, "market_value": 6000},
             {"strategy_id": "PAPER_ONLY", "quantity": 5, "market_value": 500}]
    rep = reconcile(paper, _mock().positions(), "t")
    assert "PAPER_ONLY" in rep.missing_in_broker          # paper엔 있으나 broker엔 없음
    assert "BBB" in rep.missing_in_paper                  # broker엔 있으나 paper엔 없음


def test_empty_broker_all_missing():
    paper = [{"strategy_id": "X", "quantity": 1, "market_value": 10}]
    rep = reconcile(paper, IBReadOnlyProvider().positions(), "t")   # broker 빈값
    assert rep.missing_in_broker == ["X"] and rep.matched == []


# ── 5. stale account handling ──
def test_stale_account_handling():
    stale = MockBrokerProvider(account={"cash": 1, "equity": 1, "buying_power": 1},
                               connected=True, stale=True, timestamp="2026-06-01T00:00:00Z")
    h = stale.health_check()
    assert h.stale is True and h.connected is True
    # 미구성 플레이스홀더 = disconnected + stale + error
    ib = IBReadOnlyProvider("t").health_check()
    assert ib.connected is False and ib.stale is True and "not_configured" in ib.error


# ── 6. audit integrity ──
def test_audit_integrity(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.broker_readonly.audit.state_path",
                        lambda name: os.path.join(tmp_path, name))
    from jarvis.broker_readonly.audit import read_events, record_query, result_hash
    r1 = record_query("mock", "status", "2026-07-22T00:00:00Z", {"a": 1})
    r2 = record_query("mock", "positions", "2026-07-22T00:00:00Z", {"b": 2})
    ev = read_events()
    assert len(ev) == 2 and ev[0]["provider"] == "mock"
    assert set(ev[0]) == {"provider", "query", "timestamp", "result_hash"}
    # 결정적 해시
    assert result_hash({"a": 1}) == result_hash({"a": 1})
    assert r1["result_hash"] != r2["result_hash"]


# ── 7. no execution path ──
def test_no_execution_import():
    # broker_readonly 모듈들이 jarvis.execution / jarvis.risk / jarvis.registry를 import하지 않음
    import importlib
    import inspect
    for modname in ("models", "provider", "adapters", "reconcile", "audit"):
        mod = importlib.import_module(f"jarvis.broker_readonly.{modname}")
        src = inspect.getsource(mod)
        assert "jarvis.execution" not in src, f"{modname} imports execution"
        assert "jarvis.risk" not in src, f"{modname} imports risk"
        assert "jarvis.registry" not in src, f"{modname} imports registry"
        assert "place_order" not in src and "backends.ib" not in src and "backends.kis" not in src


# ── 8. no permission escalation ──
def test_no_permission_escalation():
    # P7.1은 신규 권한을 추가하지 않음(읽기전용). FORBIDDEN 불변.
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    assert not any("broker" in a for a in ACTION_PERMISSIONS)   # broker 관련 권한 없음


# ── balances / orders_history 읽기 ──
def test_balances_and_orders():
    m = _mock()
    assert m.balances()["equity"] == 11000.0
    assert m.orders_history()[0]["status"] == "FILLED"      # 과거 이력(읽기)
    assert IBReadOnlyProvider().orders_history() == []       # 미구성 → 빈값
