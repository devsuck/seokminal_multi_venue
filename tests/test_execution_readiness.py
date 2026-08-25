"""P7.7 Execution Readiness Certification 테스트.

all pass→READY · missing ARM · risk fail · broker unavailable · stale market ·
simulation fail · reconciliation fail · deterministic hash · replay · append-only ·
no gateway import · no broker write · no position mutation · no permission escalation.
"""
from __future__ import annotations

import os

from jarvis.execution_control.models import ExecutionIntent
from jarvis.execution_readiness.engine import ExecutionReadinessEngine
from jarvis.execution_readiness.models import BLOCKED, READY

_NOW = "2026-07-22T00:00:00Z"


def _intent(iid="EI:1"):
    return ExecutionIntent(intent_id=iid, strategy="A", symbol="A", side="BUY",
                           quantity=0.0, target_weight=0.4, source_proposal_id="PP:1",
                           created_at=_NOW, expiry="")


def _all_pass():
    return dict(approval=True, control_ready=True, risk_ok=True, arm_present=True,
                broker_ok=True, market_ok=True, simulation_pass=True, reconciliation_ok=True)


# ── 1. all checks pass → READY ──
def test_all_checks_pass_ready():
    eng = ExecutionReadinessEngine()
    cert = eng.certify(_intent(), _NOW, **_all_pass())
    assert cert.status == READY and cert.blockers == []
    assert len(cert.checks) == 8
    assert all(c["status"] == "PASS" for c in cert.checks)
    assert cert.certificate_id.startswith("CERT:")


def test_eight_mandatory_checks_present():
    eng = ExecutionReadinessEngine()
    cert = eng.certify(_intent(), _NOW, **_all_pass())
    names = [c["name"] for c in cert.checks]
    for req in ("approval", "control", "risk", "arm", "broker", "market",
                "simulation", "reconciliation"):
        assert req in names


# ── 2. missing ARM → BLOCKED ──
def test_missing_arm_blocked():
    eng = ExecutionReadinessEngine()
    cert = eng.certify(_intent(), _NOW, **{**_all_pass(), "arm_present": False})
    assert cert.status == BLOCKED and "arm" in cert.blockers


# ── 3. risk failure → BLOCKED ──
def test_risk_failure_blocked():
    eng = ExecutionReadinessEngine()
    cert = eng.certify(_intent(), _NOW, **{**_all_pass(), "risk_ok": False})
    assert cert.status == BLOCKED and "risk" in cert.blockers


# ── 4. broker unavailable → BLOCKED ──
def test_broker_unavailable_blocked():
    eng = ExecutionReadinessEngine()
    cert = eng.certify(_intent(), _NOW, **{**_all_pass(), "broker_ok": False})
    assert cert.status == BLOCKED and "broker" in cert.blockers


# ── 5. stale market data → BLOCKED ──
def test_stale_market_blocked():
    eng = ExecutionReadinessEngine()
    cert = eng.certify(_intent(), _NOW, **{**_all_pass(), "market_ok": False})
    assert cert.status == BLOCKED and "market" in cert.blockers


# ── 6. simulation failure → BLOCKED ──
def test_simulation_failure_blocked():
    eng = ExecutionReadinessEngine()
    cert = eng.certify(_intent(), _NOW, **{**_all_pass(), "simulation_pass": False})
    assert cert.status == BLOCKED and "simulation" in cert.blockers


# ── 7. reconciliation failure → BLOCKED ──
def test_reconciliation_failure_blocked():
    eng = ExecutionReadinessEngine()
    cert = eng.certify(_intent(), _NOW, **{**_all_pass(), "reconciliation_ok": False})
    assert cert.status == BLOCKED and "reconciliation" in cert.blockers


def test_approval_control_failure_blocked():
    eng = ExecutionReadinessEngine()
    c1 = eng.certify(_intent(), _NOW, **{**_all_pass(), "approval": False})
    assert c1.status == BLOCKED and "approval" in c1.blockers
    c2 = eng.certify(_intent(), _NOW, **{**_all_pass(), "control_ready": False})
    assert c2.status == BLOCKED and "control" in c2.blockers


# ── 8. deterministic certificate hash ──
def test_deterministic_hash():
    eng = ExecutionReadinessEngine()
    c1 = eng.certify(_intent(), _NOW, **_all_pass())
    c2 = eng.certify(_intent(), _NOW, **_all_pass())
    assert c1.hash == c2.hash and c1.to_dict() == c2.to_dict()
    c3 = eng.certify(_intent(), _NOW, **{**_all_pass(), "arm_present": False})
    assert c3.hash != c1.hash


def test_input_hash_present():
    eng = ExecutionReadinessEngine()
    cert = eng.certify(_intent(), _NOW, **_all_pass())
    assert cert.input_hash.startswith("sha256:") and cert.input_hash != cert.hash


# ── 9. replay consistency ──
def test_replay_consistency(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.execution_readiness.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))
    eng = ExecutionReadinessEngine()
    committed = eng.certify(_intent(), _NOW, commit=True, **_all_pass())
    replay = eng.certify(_intent(), _NOW, commit=False, **_all_pass())
    assert replay.hash == committed.hash and replay.to_dict() == committed.to_dict()


# ── 10. append-only integrity ──
def test_append_only_integrity(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.execution_readiness.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))
    from jarvis.execution_readiness.ledger import read_certificates, read_events
    eng = ExecutionReadinessEngine()
    eng.certify(_intent("EI:a"), _NOW, commit=True, **_all_pass())
    eng.certify(_intent("EI:b"), _NOW, commit=True, **{**_all_pass(), "arm_present": False})
    # 동일 certificate_id 재커밋은 중복 방지(append-only)
    eng.certify(_intent("EI:a"), _NOW, commit=True, **_all_pass())
    assert len(read_certificates()) == 2
    assert len(read_events()) == 2


# ── 11. no gateway import / no broker write ──
def test_no_execution_import():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.execution_readiness.{m}"))
        stripped = (src.replace("jarvis.execution_readiness", "")
                       .replace("jarvis.execution_control", "")
                       .replace("jarvis.execution_simulation", "")
                       .replace("jarvis.execution_reconciliation", ""))
        assert "jarvis.execution" not in stripped   # 집행 게이트웨이/ARM 미import
        assert "gateway" not in src
        assert "place_order" not in src and "submit_order" not in src
        assert "create_order" not in src


def test_no_broker_write():
    import importlib
    import inspect
    src = inspect.getsource(importlib.import_module("jarvis.execution_readiness.engine"))
    for banned in (".buy(", ".sell(", "cancel_order", "order_client", "submit_order"):
        assert banned not in src
    # 브로커는 health_check 읽기만; 레지스트리 직접 import 없음
    assert "jarvis.registry" not in src


# ── 12. no position mutation (paper + sim + reconciliation ledgers immutable) ──
def test_no_position_mutation(tmp_path, monkeypatch):
    import hashlib

    def sp(name):
        return os.path.join(tmp_path, name)
    import jarvis.paper_execution.ledger as pel
    monkeypatch.setattr(pel, "state_path", sp)
    from jarvis.paper_execution.engine import PaperExecutionEngine
    PaperExecutionEngine(capital=10000).execute_proposal(
        {"proposal_id": "PP:1", "strategy": "A", "allocation": {"A": 0.5}, "created_at": "t"},
        True, {"decision": "ALLOW"}, lambda s, ts: 100.0, "t", commit=True)
    pos_path = sp("paper_positions.jsonl")
    before = hashlib.sha256(open(pos_path, "rb").read()).hexdigest()
    # 인증 실행(격리 원장)
    monkeypatch.setattr("jarvis.execution_readiness.ledger.state_path", sp)
    eng = ExecutionReadinessEngine()
    eng.certify(_intent(), _NOW, commit=True, **_all_pass())
    assert hashlib.sha256(open(pos_path, "rb").read()).hexdigest() == before   # 페이퍼 불변


# ── 13. no permission escalation ──
def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    assert not any("readiness" in a for a in ACTION_PERMISSIONS)
    assert not any("certificate" in a for a in ACTION_PERMISSIONS)
    assert not any("certification" in a for a in ACTION_PERMISSIONS)


# ── 14. certificate is NOT trade permission (states pre-flight only) ──
def test_certificate_is_not_trade_permission():
    eng = ExecutionReadinessEngine()
    cert = eng.certify(_intent(), _NOW, **_all_pass())
    keys = set(cert.to_dict())
    assert keys == {"certificate_id", "status", "checks", "blockers", "warnings",
                    "intent_id", "created_at", "input_hash", "hash"}
    # 집행/주문/자본 관련 필드 부재
    for f in ("order_id", "broker", "venue", "gateway", "executed", "capital", "authorized"):
        assert f not in keys
    assert cert.status in (READY, BLOCKED)   # 상태는 인증 여부일 뿐, 거래 허가 아님


# ── 15. honest CLOSED boundary via real sources (offline → BLOCKED) ──
def test_real_sources_default_blocked(tmp_path, monkeypatch):
    # 모든 하위 원장 격리(비어있음) → 실소스 산출 시 정직한 BLOCKED
    for mod in ("jarvis.execution_control.ledger", "jarvis.execution_reconciliation.ledger",
                "jarvis.production.approval"):
        pass
    monkeypatch.setattr("jarvis.execution_control.ledger.state_path",
                        lambda n: os.path.join(tmp_path, n))
    monkeypatch.setattr("jarvis.execution_reconciliation.ledger.state_path",
                        lambda n: os.path.join(tmp_path, n))
    eng = ExecutionReadinessEngine()
    # broker/live provider 미주입(None) → broker/market FAIL. approval도 원장 비어있어 FAIL.
    cert = eng.certify(_intent(), _NOW)
    assert cert.status == BLOCKED
    assert {"approval", "arm", "broker", "market", "simulation", "reconciliation"} <= set(cert.blockers)
