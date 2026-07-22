"""P7.3 Portfolio Reconciliation & Control 테스트.

identical→PASS · quantity drift · missing position · NAV mismatch · stale broker ·
missing market price · deterministic report · append-only · no execution · no mutation.
"""
from __future__ import annotations

import os

import pytest

from jarvis.broker_readonly.adapters import IBReadOnlyProvider, MockBrokerProvider
from jarvis.live_market_data.adapters import MockStreamingProvider
from jarvis.reconciliation.engine import ReconciliationEngine
from jarvis.reconciliation.models import (
    BROKER_UNAVAILABLE,
    CRITICAL,
    NAV_DRIFT,
    OK,
    POSITION_DRIFT,
    PRICE_DRIFT,
    STALE_DATA,
    WARNING,
)


def _paper(sym="A", qty=10, avg=100, mv=1000):
    return [{"strategy_id": sym, "quantity": qty, "average_price": avg, "market_value": mv}]


def _broker(sym="A", qty=10, avg=100, mv=1000, **h):
    return MockBrokerProvider(
        account={"cash": 5000, "equity": 11000, "buying_power": 10000},
        positions=[{"symbol": sym, "quantity": qty, "avg_price": avg, "market_value": mv}],
        timestamp="2026-07-22T00:00:00Z", **h)


def _types(report):
    return {e["type"] for e in report.control_events}


# ── 1. identical → PASS ──
def test_identical_portfolio_pass():
    eng = ReconciliationEngine()
    r = eng.reconcile(_paper(), _broker().positions(), paper_nav=11000, broker_equity=11000,
                      broker_health=_broker().health_check(), now="t")
    assert r.severity == OK
    assert r.matched_positions == ["A"]
    assert r.quantity_difference == {} and r.nav_difference == 0.0
    assert r.control_events == []


# ── 2. quantity drift ──
def test_quantity_drift_detection():
    eng = ReconciliationEngine()
    r = eng.reconcile(_paper(qty=10), _broker(qty=7).positions(),
                      broker_health=_broker().health_check(), now="t")
    assert r.quantity_difference["A"] == 3.0
    assert POSITION_DRIFT in _types(r) and r.severity == WARNING


# ── 3. missing position ──
def test_missing_position_detection():
    eng = ReconciliationEngine()
    paper = _paper("A") + [{"strategy_id": "PONLY", "quantity": 5, "average_price": 10, "market_value": 50}]
    r = eng.reconcile(paper, _broker("A").positions() +
                      [__import__("jarvis.broker_readonly.models", fromlist=["BrokerPosition"]).BrokerPosition("BONLY", 1, 1, 1)],
                      broker_health=_broker().health_check(), now="t")
    assert "PONLY" in r.missing_in_broker and "BONLY" in r.missing_in_paper


# ── 4. NAV mismatch ──
def test_nav_mismatch():
    eng = ReconciliationEngine()
    # paper NAV 12000 vs broker equity 10000 → 20% > critical 5%
    r = eng.reconcile(_paper(), _broker().positions(), paper_nav=12000, broker_equity=10000,
                      broker_health=_broker().health_check(), now="t")
    assert NAV_DRIFT in _types(r) and r.severity == CRITICAL
    assert r.nav_difference == 2000.0


# ── 5. stale broker data ──
def test_stale_broker_data():
    eng = ReconciliationEngine()
    stale = _broker(stale=True)
    r = eng.reconcile(_paper(), stale.positions(), broker_health=stale.health_check(), now="t")
    assert STALE_DATA in _types(r)


def test_broker_unavailable():
    eng = ReconciliationEngine()
    ib = IBReadOnlyProvider("t")   # 미구성 → disconnected
    r = eng.reconcile(_paper(), ib.positions(), broker_health=ib.health_check(), now="t")
    assert BROKER_UNAVAILABLE in _types(r) and r.severity == CRITICAL


# ── 6. missing market price + price drift ──
def test_missing_market_price():
    eng = ReconciliationEngine()
    live = MockStreamingProvider({}, clock="t")   # 라이브 데이터 없음
    r = eng.reconcile(_paper(), _broker().positions(), live_provider=live,
                      broker_health=_broker().health_check(), now="t")
    assert STALE_DATA in _types(r)   # missing live price


def test_price_drift_detection():
    eng = ReconciliationEngine()
    # 페이퍼 마크 = mv/qty = 1000/10 = 100. 라이브 130 → 23% drift > critical
    live = MockStreamingProvider(
        {"A": [{"price": 130.0, "timestamp": "2026-07-22T00:00:00Z"}]}, clock="2026-07-22T00:00:01Z",
        stale_seconds=1e9)
    r = eng.reconcile(_paper(qty=10, mv=1000), _broker(qty=10, mv=1000).positions(),
                      live_provider=live, broker_health=_broker().health_check(), now="2026-07-22T00:00:01Z")
    assert PRICE_DRIFT in _types(r) and r.severity == CRITICAL


# ── 7. deterministic report ──
def test_deterministic_report():
    eng = ReconciliationEngine()
    kw = dict(paper_nav=12000, broker_equity=10000, broker_health=_broker().health_check(), now="t")
    r1 = eng.reconcile(_paper(qty=10), _broker(qty=7).positions(), **kw)
    r2 = eng.reconcile(_paper(qty=10), _broker(qty=7).positions(), **kw)
    from jarvis.reconciliation.ledger import report_hash
    assert r1.to_dict() == r2.to_dict() and report_hash(r1) == report_hash(r2)


# ── 8. append-only integrity ──
def test_append_only_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.reconciliation.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))
    from jarvis.reconciliation.ledger import read_events, record_report
    eng = ReconciliationEngine()
    r = eng.reconcile(_paper(qty=10), _broker(qty=7).positions(),
                      broker_health=_broker().health_check(), now="t")
    record_report(r)
    record_report(r)
    rows = read_events()
    assert len(rows) == 2
    assert set(rows[0]) == {"report_hash", "timestamp", "severity", "detected_issues"}
    assert rows[0]["report_hash"] == rows[1]["report_hash"]   # 동일 리포트 → 동일 해시


# ── 9. no execution capability ──
def test_no_execution_import():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger"):
        src = inspect.getsource(importlib.import_module(f"jarvis.reconciliation.{m}"))
        assert "jarvis.execution" not in src
        assert "gateway" not in src
        assert "place_order" not in src and "order_client" not in src
    # 리스크/레지스트리 미변경(engine은 읽기만; import 없음)
    src = inspect.getsource(importlib.import_module("jarvis.reconciliation.engine"))
    assert "jarvis.risk" not in src and "jarvis.registry" not in src


def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    assert not any("reconcil" in a for a in ACTION_PERMISSIONS)


# ── 10. no mutation of source ledgers ──
def test_no_source_ledger_mutation(tmp_path, monkeypatch):
    import hashlib

    def sp(name):
        return os.path.join(tmp_path, name)
    import jarvis.paper_execution.ledger as pel
    monkeypatch.setattr(pel, "state_path", sp)
    # 페이퍼 포지션 원장 시드
    from jarvis.paper_execution.engine import PaperExecutionEngine
    PaperExecutionEngine(capital=10000).execute_proposal(
        {"proposal_id": "PP:1", "strategy": "A", "allocation": {"A": 0.5}, "created_at": "t"},
        True, {"decision": "ALLOW"}, lambda s, ts: 100.0, "t", commit=True)
    pos_path = sp("paper_positions.jsonl")
    before = hashlib.sha256(open(pos_path, "rb").read()).hexdigest()
    # reconcile_runtime 실행(읽기전용)
    monkeypatch.setattr("jarvis.reconciliation.ledger.state_path", sp)
    from jarvis.reconciliation.engine import reconcile_runtime
    reconcile_runtime(_broker("A"), MockStreamingProvider({}), "t", capital=10000, commit=False)
    assert hashlib.sha256(open(pos_path, "rb").read()).hexdigest() == before   # 페이퍼 원장 불변
