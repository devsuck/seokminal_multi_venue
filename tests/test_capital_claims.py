"""자본 청구 모델 테스트 — 엔벨로프 내 자율승인, 초과 시 대기열, LIVE는 arm capital_limit 재사용.

설계: docs/superpowers/specs/2026-09-11-capital-claim-model-design.md
"""
from __future__ import annotations

import importlib
import os

import pytest

import api_server.ai_portfolio as ap
from jarvis.agents import HUMAN_ADMIN, LIVE_PROPOSAL_AGENT, PAPER_AGENT
from jarvis.execution import capital_claims as cc
from jarvis.execution import capital_envelope as ce
from jarvis.execution.arm import arm
from jarvis.permissions import PermissionDenied
from jarvis.registry import Status, StrategyRegistry


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    for mod in ("jarvis.audit.log", "jarvis.registry.lifecycle", "jarvis.execution.arm",
                "jarvis.execution.capital_envelope", "jarvis.execution.capital_claims"):
        monkeypatch.setattr(importlib.import_module(mod), "state_path", sp)
    monkeypatch.setattr(ap, "_STATE_PATH", str(tmp_path / "ai_portfolio_recs.jsonl"))
    return tmp_path


def _paper_active(sid="S"):
    reg = StrategyRegistry()
    reg.register(sid, name=sid, config={"x": 1})
    for s in (Status.DATA_AUDIT_PASSED, Status.BACKTESTED, Status.WATCHLIST,
              Status.PAPER_CANDIDATE, Status.PAPER_ACTIVE):
        reg.transition(sid, s, "t")
    return reg


def _live_candidate(sid="S"):
    reg = _paper_active(sid)
    reg.transition(sid, Status.LIVE_CANDIDATE, "approved", approver="human_admin")
    return reg


def test_envelope_default_zero_when_unset():
    env = ce.get_envelope()
    assert env["pool_limit"] == 0.0
    assert env["per_strategy_paper_limit"] == {}


def test_set_envelope_requires_human_admin():
    with pytest.raises(PermissionDenied):
        ce.set_envelope(LIVE_PROPOSAL_AGENT, pool_limit=1000)


def test_set_envelope_overwrites():
    ce.set_envelope(HUMAN_ADMIN, pool_limit=1000, default_paper_limit=200)
    ce.set_envelope(HUMAN_ADMIN, pool_limit=500, default_paper_limit=100)
    env = ce.get_envelope()
    assert env["pool_limit"] == 500
    assert env["default_paper_limit"] == 100


def test_submit_claim_not_registered():
    row = cc.submit_claim("NOPE", LIVE_PROPOSAL_AGENT, requested_amount=100)
    assert row["status"] == "rejected"
    assert row["reason"] == "not_registered"


def test_ai_without_permission_denied():
    _paper_active("S1")
    with pytest.raises(PermissionDenied):
        cc.submit_claim("S1", PAPER_AGENT, requested_amount=100)


def test_submit_claim_within_envelope_auto_approved():
    _paper_active("S1")
    ce.set_envelope(HUMAN_ADMIN, pool_limit=1000, default_paper_limit=500)
    row = cc.submit_claim("S1", LIVE_PROPOSAL_AGENT, requested_amount=300)
    assert row["status"] == "approved"
    assert row["allocated_capital"] == 300
    assert row["fulfillment_mode"] == "paper"
    assert row["decided_by"] == "AI"
    assert cc.allocated_capital("S1") == 300


def test_submit_claim_exceeds_strategy_limit_queued():
    _paper_active("S1")
    ce.set_envelope(HUMAN_ADMIN, pool_limit=1000, default_paper_limit=200)
    row = cc.submit_claim("S1", LIVE_PROPOSAL_AGENT, requested_amount=300)
    assert row["status"] == "queued"
    assert cc.allocated_capital("S1") == 0.0
    assert row in cc.pending_queue()


def test_submit_claim_exceeds_pool_limit_queued():
    _paper_active("S1")
    _paper_active("S2")
    ce.set_envelope(HUMAN_ADMIN, pool_limit=400, default_paper_limit=1000)
    r1 = cc.submit_claim("S1", LIVE_PROPOSAL_AGENT, requested_amount=300)
    r2 = cc.submit_claim("S2", LIVE_PROPOSAL_AGENT, requested_amount=300)
    assert r1["status"] == "approved"
    assert r2["status"] == "queued"


def test_duplicate_open_claim_rejected():
    _paper_active("S1")
    ce.set_envelope(HUMAN_ADMIN, pool_limit=100, default_paper_limit=100)
    cc.submit_claim("S1", LIVE_PROPOSAL_AGENT, requested_amount=500)  # queued (초과)
    dup = cc.submit_claim("S1", LIVE_PROPOSAL_AGENT, requested_amount=10)
    assert dup["status"] == "rejected"
    assert dup["reason"] == "duplicate_open_claim"


def test_live_armed_uses_arm_capital_limit():
    reg = _live_candidate("S1")
    reg.transition("S1", Status.MICRO_LIVE, "promoted", approver="human_admin")
    arm("S1", HUMAN_ADMIN, capital_limit=1000, paper_months=12)
    ce.set_envelope(HUMAN_ADMIN, pool_limit=5000, default_paper_limit=50)  # paper한도는 무관해야함
    row = cc.submit_claim("S1", LIVE_PROPOSAL_AGENT, requested_amount=800)
    assert row["fulfillment_mode"] == "live"
    assert row["envelope_check"]["strategy_limit"] == 1000
    assert row["status"] == "approved"


def test_live_not_armed_degrades_to_paper():
    _live_candidate("S1")  # arm() 호출 안 함
    ce.set_envelope(HUMAN_ADMIN, pool_limit=5000, default_paper_limit=50)
    row = cc.submit_claim("S1", LIVE_PROPOSAL_AGENT, requested_amount=30)
    assert row["fulfillment_mode"] == "paper"
    assert row["envelope_check"]["strategy_limit"] == 50


def test_approve_queued_by_human():
    _paper_active("S1")
    ce.set_envelope(HUMAN_ADMIN, pool_limit=100, default_paper_limit=100)
    q = cc.submit_claim("S1", LIVE_PROPOSAL_AGENT, requested_amount=500)
    assert q["status"] == "queued"
    decided = cc.approve_queued(q["claim_id"], HUMAN_ADMIN, approve=True, note="ok")
    assert decided["status"] == "approved"
    assert decided["allocated_capital"] == 500
    assert cc.allocated_capital("S1") == 500
    assert cc.pending_queue() == []


def test_approve_queued_denied_for_non_human():
    _paper_active("S1")
    ce.set_envelope(HUMAN_ADMIN, pool_limit=100, default_paper_limit=100)
    q = cc.submit_claim("S1", LIVE_PROPOSAL_AGENT, requested_amount=500)
    with pytest.raises(PermissionDenied):
        cc.approve_queued(q["claim_id"], LIVE_PROPOSAL_AGENT, approve=True)


def test_second_claim_replaces_not_adds():
    _paper_active("S1")
    ce.set_envelope(HUMAN_ADMIN, pool_limit=1000, default_paper_limit=1000)
    cc.submit_claim("S1", LIVE_PROPOSAL_AGENT, requested_amount=300)
    row2 = cc.submit_claim("S1", LIVE_PROPOSAL_AGENT, requested_amount=400)
    assert row2["status"] == "approved"
    assert cc.allocated_capital("S1") == 400  # 300+400 아님 — 절대값 교체


def test_ceiling_ref_stale_when_no_recommendation():
    _paper_active("S1")
    proposal = cc.propose_claim("S1", requested_amount=None, total_capital_basis=10000)
    assert proposal["ceiling_ref"]["stale"] is True
