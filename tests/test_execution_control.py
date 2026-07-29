"""P7.4 Execution Control Plane 테스트.

approved→intent · blocked proposal · risk reject · reconciliation CRITICAL ·
stale data · ARM missing · duplicate intent · deterministic hash · append-only ·
no execution import · no broker call · no permission escalation.
"""
from __future__ import annotations

import os

from jarvis.execution_control.engine import ExecutionControlPlane
from jarvis.execution_control.models import BLOCKED, READY

_NOW = "2026-07-22T00:00:00Z"


def _prop(pid="PP:1", strat="A", alloc=None, created="2026-07-22T00:00:00Z"):
    return {"proposal_id": pid, "source": "demo", "strategy": strat,
            "allocation": alloc if alloc is not None else {"A": 0.4}, "created_at": created}


def _all_pass():
    return dict(approved=True, gate_allow=True, risk_ok=True,
                reconciliation_severity="OK", data_fresh=True, arm_present=True)


# ── 1. approved proposal creates intent ──
def test_build_intent_from_proposal():
    cp = ExecutionControlPlane()
    intent = cp.build_intent(_prop(alloc={"A": 0.4, "B": -0.6}), _NOW)
    assert intent is not None
    assert intent.symbol == "B" and intent.side == "SELL"   # |−0.6| 최대
    assert intent.target_weight == -0.6
    assert intent.quantity == 0.0                            # no capital deployment
    assert intent.source_proposal_id == "PP:1"
    assert intent.intent_id.startswith("EI:")
    assert intent.expiry > intent.created_at


def test_all_checks_pass_ready():
    cp = ExecutionControlPlane()
    intent = cp.build_intent(_prop(), _NOW)
    d = cp.evaluate(intent, _NOW, **_all_pass())
    assert d.status == READY and d.blockers == []


# ── 2. blocked proposal rejected (approval/gate fail) ──
def test_unapproved_proposal_blocks():
    cp = ExecutionControlPlane()
    intent = cp.build_intent(_prop(), _NOW)
    d = cp.evaluate(intent, _NOW, **{**_all_pass(), "approved": False})
    assert d.status == BLOCKED and "approval" in d.blockers


def test_gate_block_blocks():
    cp = ExecutionControlPlane()
    intent = cp.build_intent(_prop(), _NOW)
    d = cp.evaluate(intent, _NOW, **{**_all_pass(), "gate_allow": False})
    assert d.status == BLOCKED and "production_gate" in d.blockers


# ── 3. risk rejection blocks ──
def test_risk_rejection_blocks():
    cp = ExecutionControlPlane()
    intent = cp.build_intent(_prop(), _NOW)
    d = cp.evaluate(intent, _NOW, **{**_all_pass(), "risk_ok": False})
    assert d.status == BLOCKED and "risk" in d.blockers


# ── 4. reconciliation CRITICAL blocks ──
def test_reconciliation_critical_blocks():
    cp = ExecutionControlPlane()
    intent = cp.build_intent(_prop(), _NOW)
    d = cp.evaluate(intent, _NOW, **{**_all_pass(), "reconciliation_severity": "CRITICAL"})
    assert d.status == BLOCKED and "reconciliation" in d.blockers


def test_reconciliation_warning_allowed():
    cp = ExecutionControlPlane()
    intent = cp.build_intent(_prop(), _NOW)
    d = cp.evaluate(intent, _NOW, **{**_all_pass(), "reconciliation_severity": "WARNING"})
    assert d.status == READY   # WARNING은 차단 아님(CRITICAL만)


# ── 5. stale market data blocks ──
def test_stale_data_blocks():
    cp = ExecutionControlPlane()
    intent = cp.build_intent(_prop(), _NOW)
    d = cp.evaluate(intent, _NOW, **{**_all_pass(), "data_fresh": False})
    assert d.status == BLOCKED and "data_freshness" in d.blockers


# ── 6. ARM missing blocks ──
def test_arm_missing_blocks():
    cp = ExecutionControlPlane()
    intent = cp.build_intent(_prop(), _NOW)
    d = cp.evaluate(intent, _NOW, **{**_all_pass(), "arm_present": False})
    assert d.status == BLOCKED and "arm" in d.blockers


def test_expired_intent_blocks():
    cp = ExecutionControlPlane()
    intent = cp.build_intent(_prop(), _NOW, expiry_hours=1.0)
    later = "2026-07-23T00:00:00Z"   # 24h 후 > 1h 만료
    d = cp.evaluate(intent, later, **_all_pass())
    assert d.status == BLOCKED and "not_expired" in d.blockers


# ── 7. duplicate intent prevented ──
def test_duplicate_intent_prevented(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.execution_control.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))
    cp = ExecutionControlPlane()
    first = cp.build_intent(_prop(), _NOW, commit=True)
    second = cp.build_intent(_prop(), _NOW, commit=True)
    assert first is not None and second is None    # 동일 source_proposal_id → 중복 방지
    from jarvis.execution_control.ledger import read_intents
    assert len(read_intents()) == 1


# ── 8. deterministic hash ──
def test_deterministic_hash():
    cp = ExecutionControlPlane()
    intent = cp.build_intent(_prop(), _NOW)
    d1 = cp.evaluate(intent, _NOW, **_all_pass())
    d2 = cp.evaluate(intent, _NOW, **_all_pass())
    assert d1.hash == d2.hash and d1.to_dict() == d2.to_dict()
    # 상태가 바뀌면 해시도 바뀜
    d3 = cp.evaluate(intent, _NOW, **{**_all_pass(), "risk_ok": False})
    assert d3.hash != d1.hash


def test_intent_id_deterministic():
    from jarvis.execution_control.models import intent_id
    a = intent_id("PP:1", "A", "A", "BUY")
    b = intent_id("PP:1", "A", "A", "BUY")
    c = intent_id("PP:2", "A", "A", "BUY")
    assert a == b and a != c


# ── 9. append-only integrity ──
def test_append_only_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.execution_control.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))
    from jarvis.execution_control.ledger import read_decisions, read_events, read_intents
    cp = ExecutionControlPlane()
    intent = cp.build_intent(_prop(), _NOW, commit=True)
    cp.evaluate(intent, _NOW, commit=True, **_all_pass())
    cp.evaluate(intent, _NOW, commit=True, **{**_all_pass(), "arm_present": False})
    assert len(read_intents()) == 1
    assert len(read_decisions()) == 2     # append-only: 재평가는 새 행
    # 이벤트: intent_created 1 + decision_evaluated 2
    evs = read_events()
    assert sum(1 for e in evs if e["event"] == "intent_created") == 1
    assert sum(1 for e in evs if e["event"] == "decision_evaluated") == 2


# ── 10. no execution gateway import / no broker call ──
def test_no_execution_import():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.execution_control.{m}"))
        # 자기 패키지 참조 제거 후 집행 게이트웨이/ARM 패키지 미import 확인
        stripped = src.replace("jarvis.execution_control", "")
        assert "jarvis.execution" not in stripped   # 집행 게이트웨이/ARM 미import
        assert "gateway" not in src
        assert "place_order" not in src and "order_client" not in src
        assert "create_order" not in src
    # 리스크/레지스트리 변경 없음(엔진은 읽기전용 호출만; dry_run)
    esrc = inspect.getsource(importlib.import_module("jarvis.execution_control.engine"))
    assert "jarvis.registry" not in esrc            # 레지스트리 직접 import 없음
    assert "dry_run=True" in esrc                   # 리스크 호출은 dry-run


def test_no_broker_write_call():
    import importlib
    import inspect
    src = inspect.getsource(importlib.import_module("jarvis.execution_control.engine"))
    # 브로커는 read-only만: positions/health/account 스냅샷은 P7.3 경유. 주문 API 없음.
    for banned in ("submit_order", "cancel_order", "place_order", ".buy(", ".sell("):
        assert banned not in src


# ── 11. no permission escalation ──
def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    assert not any("execution_control" in a for a in ACTION_PERMISSIONS)
    assert not any("execution_intent" in a for a in ACTION_PERMISSIONS)


# ── 12. ExecutionDecision is NOT an order (no order fields) ──
def test_decision_is_not_an_order():
    cp = ExecutionControlPlane()
    intent = cp.build_intent(_prop(), _NOW)
    d = cp.evaluate(intent, _NOW, **_all_pass())
    keys = set(d.to_dict())
    assert keys == {"intent_id", "status", "checks", "blockers", "timestamp", "hash"}
    # 주문 관련 필드 부재
    for order_field in ("order_id", "filled", "broker", "venue", "executed", "price"):
        assert order_field not in keys
    assert d.status in (READY, BLOCKED)


def test_six_mandatory_checks_present():
    cp = ExecutionControlPlane()
    intent = cp.build_intent(_prop(), _NOW)
    d = cp.evaluate(intent, _NOW, **_all_pass())
    names = [c["name"] for c in d.checks]
    for required in ("approval", "production_gate", "risk", "reconciliation",
                     "data_freshness", "arm"):
        assert required in names
