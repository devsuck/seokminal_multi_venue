"""P6.1 Production Readiness 테스트.

approval determinism · duplicate rejection · expired rejection · safety gate blocking ·
risk governor integration · missing data · audit integrity · no source mutation.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.agents import HUMAN_ADMIN, LIVE_PROPOSAL_AGENT
from jarvis.permissions import PermissionDenied
from jarvis.production.approval import ApprovalGate, proposal_status, submit
from jarvis.production.gate import ProductionGate
from jarvis.production.models import ProductionProposal, is_expired, make_proposal_id


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import jarvis.audit.log as al
    import jarvis.production.approval as ap
    import jarvis.production.gate as gt
    import jarvis.registry.lifecycle as rl
    monkeypatch.setattr(al, "state_path", sp)
    monkeypatch.setattr(ap, "state_path", sp)
    monkeypatch.setattr(gt, "state_path", sp)
    monkeypatch.setattr(rl, "state_path", sp)
    return sp


def _prop(strategy="S1", created="2026-07-22T00:00:00Z", source="test"):
    return ProductionProposal(proposal_id=make_proposal_id(source, strategy, created),
                              source=source, strategy=strategy, created_at=created)


# ─────────────── Approval ───────────────
def test_submit_requires_permission_and_pending():
    p = _prop()
    res = submit(p, principal=LIVE_PROPOSAL_AGENT)
    assert res["status"] == "PENDING_APPROVAL"


def test_submit_denied_for_low_principal():
    from jarvis.agents import RESEARCH_AGENT
    with pytest.raises(PermissionDenied):
        submit(_prop(), principal=RESEARCH_AGENT)   # RESEARCH_ONLY < LIVE_PROPOSAL


def test_approval_determinism():
    p = _prop()
    submit(p)
    now = "2026-07-22T01:00:00Z"
    r1 = ApprovalGate().approve(p.proposal_id, now, ts=now, approver=HUMAN_ADMIN)
    # 재승인 시도는 중복으로 거부(결정적)
    r2 = ApprovalGate().approve(p.proposal_id, now, ts=now, approver=HUMAN_ADMIN)
    assert r1["approved"] is True
    assert r2["approved"] is False and r2["reason"] == "duplicate_approval"


def test_duplicate_approval_rejected():
    p = _prop()
    submit(p)
    g = ApprovalGate()
    g.approve(p.proposal_id, "2026-07-22T01:00:00Z", ts="t", approver=HUMAN_ADMIN)
    r = g.approve(p.proposal_id, "2026-07-22T02:00:00Z", ts="t", approver=HUMAN_ADMIN)
    assert r["reason"] == "duplicate_approval"


def test_expired_proposal_rejected():
    p = _prop(created="2026-07-01T00:00:00Z")   # 3주 전
    submit(p)
    r = ApprovalGate().approve(p.proposal_id, "2026-07-22T00:00:00Z", ts="t", approver=HUMAN_ADMIN)
    assert r["approved"] is False and r["reason"] == "expired"


def test_ai_cannot_approve():
    p = _prop()
    submit(p)
    with pytest.raises(PermissionDenied):
        ApprovalGate().approve(p.proposal_id, "2026-07-22T01:00:00Z",
                               approver=LIVE_PROPOSAL_AGENT)   # 사람 아님 → 거부


def test_immutable_history_append_only():
    p = _prop()
    submit(p)
    g = ApprovalGate()
    g.approve(p.proposal_id, "2026-07-22T01:00:00Z", ts="t", approver=HUMAN_ADMIN)
    from jarvis.production.approval import read_approvals
    assert len(read_approvals()) == 1
    g.approve(p.proposal_id, "2026-07-22T02:00:00Z", ts="t", approver=HUMAN_ADMIN)  # 중복
    assert len(read_approvals()) == 1                # 중복은 이력 추가 안 함(APPROVED 유지)


# ─────────────── Safety Gate ───────────────
def _register(sp, strategy, status):
    """registry에 전략을 특정 상태로 시드(테스트용)."""
    from jarvis.registry import Status, StrategyRegistry
    reg = StrategyRegistry()
    reg.register(strategy, name=strategy, config={"s": strategy})
    chain = {"paper_active": [Status.DATA_AUDIT_PASSED, Status.BACKTESTED, Status.WATCHLIST,
                              Status.PAPER_CANDIDATE, Status.PAPER_ACTIVE]}
    for s in chain.get(status, []):
        reg.transition(strategy, s, "test")


def test_safety_gate_blocks_unready_strategy():
    now = "2026-07-22T00:00:00Z"
    dec = ProductionGate().check(_prop(strategy="ghost", created=now), now, ts=now)
    assert dec.decision == "BLOCK"
    # 미등록 전략 + autonomy<6 → 여러 실패
    assert any("strategy_status" in f for f in dec.failed_checks)
    assert any("permission_level" in f for f in dec.failed_checks)


def test_risk_governor_integration_blocks(_isolate):
    _register(_isolate, "paper_strat", "paper_active")
    now = "2026-07-22T00:00:00Z"
    dec = ProductionGate().check(_prop(strategy="paper_strat", created=now), now, ts=now)
    # paper_active는 live 상태 아님 → risk governor REJECT → BLOCK
    assert dec.decision == "BLOCK"
    assert any("risk_governor" in f for f in dec.failed_checks)
    assert dec.checks["risk_governor"] == "REJECTED"


def test_gate_missing_timestamp_handled():
    dec = ProductionGate().check(_prop(created=""), "2026-07-22T00:00:00Z", ts="t")
    assert dec.decision == "BLOCK"
    assert any("data_freshness" in f for f in dec.failed_checks)


def test_gate_stale_data_flagged():
    dec = ProductionGate().check(_prop(created="2026-07-01T00:00:00Z"),
                                 "2026-07-22T00:00:00Z", ts="t")
    assert any("data_stale" in f for f in dec.failed_checks)


def test_gate_deterministic():
    now = "2026-07-22T00:00:00Z"
    p = _prop(created=now)
    a = ProductionGate().check(p, now, ts=now)
    b = ProductionGate().check(p, now, ts=now)
    assert a.decision == b.decision and a.failed_checks == b.failed_checks


# ─────────────── Monitor ───────────────
def test_monitor_snapshot_counts_and_health():
    submit(_prop(strategy="A"))
    submit(_prop(strategy="B", created="2026-07-01T00:00:00Z"))  # stale
    from jarvis.production.monitor import ProductionMonitor
    snap = ProductionMonitor().snapshot("2026-07-22T00:00:00Z")
    assert snap["proposal_count"] == 2
    assert snap["stale_data"] == 1
    assert snap["system_health"]["production_boundary"] == "CLOSED"   # autonomy<6


# ─────────────── Audit / integrity ───────────────
def test_audit_integrity():
    p = _prop()
    submit(p)
    ApprovalGate().approve(p.proposal_id, "2026-07-22T01:00:00Z", ts="t", approver=HUMAN_ADMIN)
    from jarvis.production.audit import read_production_events
    events = read_production_events()
    actions = {e["action"] for e in events}
    assert "submit_production_proposal" in actions
    assert "approve_production_proposal" in actions


def test_verify_deterministic():
    from jarvis.production.verify import verify
    res = verify("2026-07-22T00:00:00Z")
    assert res["deterministic"] is True and res["boundary_closed"] is True


# ─────────────── No source mutation ───────────────
def test_no_existing_source_mutation(tmp_path, _isolate):
    # 기존 소스(registry) 파일을 시드한 뒤, production 동작이 이를 변경하지 않는지
    _register(_isolate, "seed_strat", "paper_active")
    reg_path = _isolate("registry.jsonl")
    before = hashlib.sha256(open(reg_path, "rb").read()).hexdigest()
    p = _prop(strategy="seed_strat")
    submit(p)
    ProductionGate().check(p, "2026-07-22T00:00:00Z", ts="t")
    assert hashlib.sha256(open(reg_path, "rb").read()).hexdigest() == before  # registry 불변
