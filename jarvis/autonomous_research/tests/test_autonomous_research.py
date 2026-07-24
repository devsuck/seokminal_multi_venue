"""P25 autonomous_research 테스트 — 사이클/제안 생애주기·기회 탐지(자동선택 금지)·제안 워크플로(사람 검토)·
실험 계획(실행 금지)·피드백·학습 계보·verify·replay·CLI·보안·금지능력·READ ONLY 상위. KNOWLEDGE ≠ TRADING."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.autonomous_research import ledger
from jarvis.autonomous_research import models as M
from jarvis.autonomous_research.engine import AutonomousResearchEngine
from jarvis.autonomous_research.models import (
    CYCLE_STATES,
    FORBIDDEN_VERBS,
    GENESIS,
    LEARNING_KINDS,
    OPPORTUNITY_PATTERNS,
    PROPOSAL_STATES,
    RISK_LEVELS,
    C_ANALYZING,
    C_ARCHIVED,
    C_COMPLETED,
    C_CREATED,
    C_EVALUATING,
    C_PLANNED,
    P_ACCEPTED,
    P_DRAFT,
    P_REJECTED,
    P_REVIEWED,
    P_SUBMITTED,
    IllegalCycleTransition,
    IllegalProposalTransition,
    ReviewerRequired,
    UnknownEntityError,
    can_cycle_transition,
    can_proposal_transition,
    classify_priority,
    content_hash,
    priority_score,
)
from jarvis.autonomous_research.verify import (
    cycle_lifecycle_integrity,
    duplicate_integrity,
    learning_integrity,
    lineage_integrity,
    opportunity_integrity,
    plan_integrity,
    proposal_lifecycle_integrity,
    replay,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.autonomous_research.ledger.state_path", sp)
    return sp


def _eng():
    return AutonomousResearchEngine()


def _cyc(e, objective="improve alpha decay", now=T[0]):
    return e.create_cycle(objective, ["src1"], now, commit=True).cycle_id


def _prop(e, cyc, hypothesis="regime filter improves sharpe", now=T[1]):
    return e.create_hypothesis(cyc, hypothesis, "higher sharpe", "MEDIUM", ["oos"], "", now,
                               commit=True).proposal_id


# ═══════════════ cycle lifecycle ═══════════════
def test_create_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().create_cycle("obj", ["s"], T[0], commit=True)
    assert ev.to_state == C_CREATED
    assert ev.cycle_id.startswith("ARC:")
    assert ev.cycle_event_id.startswith("ARY:")


def test_cycle_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    e.start_analyzing(cyc, now=T[1], commit=True)
    e.mark_planned(cyc, now=T[2], commit=True)
    e.start_evaluating(cyc, now=T[3], commit=True)
    e.complete_cycle(cyc, now=T[4], commit=True)
    e.archive_cycle(cyc, now=T[5], commit=True)
    assert e.cycle_state(cyc) == C_ARCHIVED


def test_cycle_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    with pytest.raises(IllegalCycleTransition):
        e.complete_cycle(cyc, now=T[1], commit=True)  # CREATED→COMPLETED skip


def test_cycle_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.create_cycle("o", ["s"], T[0], commit=True).cycle_id
    b = e.create_cycle("o", ["s"], T[1], commit=True).cycle_id
    assert a == b
    assert len(ledger.cycle_events(a)) == 1


def test_cycle_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().start_analyzing("ARC:nope", now=T[1], commit=True)


def test_cycle_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _cyc(e)
    assert any(a["artifact_type"] == "CYCLE" for a in ledger.read_artifacts())


def test_cycle_reanalyze_from_completed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    e.start_analyzing(cyc, now=T[1], commit=True)
    e.mark_planned(cyc, now=T[2], commit=True)
    e.start_evaluating(cyc, now=T[3], commit=True)
    e.complete_cycle(cyc, now=T[4], commit=True)
    e.start_analyzing(cyc, now=T[5], commit=True)  # COMPLETED→ANALYZING 다음 사이클
    assert e.cycle_state(cyc) == C_ANALYZING


def test_cycles_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    e.start_analyzing(cyc, now=T[1], commit=True)
    assert cyc in e.cycles_in_state(C_ANALYZING)


@pytest.mark.parametrize("frm,to,ok", [
    (C_CREATED, C_ANALYZING, True), (C_CREATED, C_PLANNED, False),
    (C_ANALYZING, C_PLANNED, True), (C_PLANNED, C_EVALUATING, True),
    (C_EVALUATING, C_COMPLETED, True), (C_EVALUATING, C_PLANNED, True),
    (C_COMPLETED, C_ARCHIVED, True), (C_COMPLETED, C_ANALYZING, True),
    (C_ARCHIVED, C_ANALYZING, False), (C_CREATED, C_ARCHIVED, False),
])
def test_cycle_transition_matrix(frm, to, ok):
    assert can_cycle_transition(frm, to) is ok


@pytest.mark.parametrize("s", CYCLE_STATES)
def test_cycle_states(s):
    assert s in CYCLE_STATES


# ═══════════════ analyze_history (READ ONLY) ═══════════════
def test_analyze_history_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().analyze_history(T[0])
    assert res["read_only"] is True
    assert res["total"] == 0


def test_analyze_history_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("rel_incidents.jsonl")
    with open(p, "w") as f:
        for i in range(4):
            f.write(json.dumps({"incident_event_id": f"e{i}"}) + "\n")
    before = open(p).read()
    res = _eng().analyze_history(T[0])
    assert res["signals"]["REPEATED_FAILURES"]["count"] == 4
    assert open(p).read() == before  # 상위 원장 불변


# ═══════════════ opportunity detection ═══════════════
def test_discover_opportunity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    o = e.discover_opportunity(cyc, "REPEATED_FAILURES", "3 repeated incidents",
                               {"evidence_count": 3}, 1.0, T[1], commit=True)
    assert o.opportunity_id.startswith("ARO:")
    assert o.is_auto_selected is False
    assert 0.0 <= o.priority_score <= 1.0


def test_opportunity_bad_pattern(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    with pytest.raises(ValueError):
        e.discover_opportunity(cyc, "NOPE", "d", now=T[1], commit=True)


def test_opportunity_unknown_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().discover_opportunity("ARC:nope", "REPEATED_FAILURES", "d", now=T[0], commit=True)


def test_detect_opportunities_from_history(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    for fn, idf in [("rel_incidents.jsonl", "incident_event_id"),
                    ("rmon_anomalies.jsonl", "anomaly_id")]:
        with open(sp(fn), "w") as f:
            f.write(json.dumps({idf: "x0"}) + "\n")
    e = _eng()
    cyc = _cyc(e)
    opps = e.detect_opportunities_from_history(cyc, T[1], commit=True)
    patterns = {o.source_pattern for o in opps}
    assert "REPEATED_FAILURES" in patterns  # rel_incidents 존재
    assert "VALIDATION_WARNINGS" in patterns  # rmon_anomalies 존재
    assert all(o.is_auto_selected is False for o in opps)


def test_opportunity_lineage_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    o = e.discover_opportunity(cyc, "ROBUSTNESS_ISSUES", "d", {"evidence_count": 1}, 1.0, T[1],
                               commit=True)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    opp_art = next(a for a in arts.values() if a["ref_id"] == o.opportunity_id)
    assert opp_art["parent_artifact"] == M.artifact_id(M.ART_CYCLE, cyc)


@pytest.mark.parametrize("pat", OPPORTUNITY_PATTERNS)
def test_opportunity_patterns(pat):
    assert pat in OPPORTUNITY_PATTERNS


def test_priority_score_monotonic():
    assert priority_score(0) < priority_score(2) < priority_score(10)


def test_priority_score_bounds():
    assert priority_score(0) == 0.0
    assert 0.0 <= priority_score(1000) <= 1.0


def test_priority_score_bad():
    assert priority_score("x") == 0.0


@pytest.mark.parametrize("score,level", [
    (0.9, "HIGH"), (0.7, "HIGH"), (0.5, "MEDIUM"), (0.4, "MEDIUM"), (0.1, "LOW"), (0.0, "LOW"),
])
def test_classify_priority(score, level):
    assert classify_priority(score) == level


# ═══════════════ proposal workflow (human review) ═══════════════
def test_create_hypothesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    p = e.create_hypothesis(cyc, "H1", "value", "LOW", ["oos"], "", T[1], commit=True)
    assert p.to_state == P_DRAFT
    assert p.proposal_id.startswith("ARP:")
    assert p.proposal_event_id.startswith("ARM:")


def test_proposal_bad_risk(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    with pytest.raises(ValueError):
        e.create_hypothesis(cyc, "H", "v", "EXTREME", now=T[1], commit=True)


def test_proposal_full_accept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    prop = _prop(e, cyc)
    e.submit_proposal(prop, now=T[2], commit=True)
    e.review_proposal(prop, "reviewer-1", now=T[3], commit=True)
    e.accept_proposal(prop, "lead-1", now=T[4], commit=True)
    assert e.proposal_state(prop) == P_ACCEPTED


def test_proposal_reject(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    prop = _prop(e, cyc)
    e.submit_proposal(prop, now=T[2], commit=True)
    e.review_proposal(prop, "rev", now=T[3], commit=True)
    e.reject_proposal(prop, "lead", now=T[4], commit=True)
    assert e.proposal_state(prop) == P_REJECTED


def test_proposal_accept_requires_reviewer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    prop = _prop(e, cyc)
    e.submit_proposal(prop, now=T[2], commit=True)
    e.review_proposal(prop, "rev", now=T[3], commit=True)
    with pytest.raises(ReviewerRequired):
        e.accept_proposal(prop, "", now=T[4], commit=True)


def test_proposal_review_requires_reviewer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    prop = _prop(e, cyc)
    e.submit_proposal(prop, now=T[2], commit=True)
    with pytest.raises(ReviewerRequired):
        e.review_proposal(prop, "", now=T[3], commit=True)


def test_proposal_no_skip_to_accept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    prop = _prop(e, cyc)
    with pytest.raises(IllegalProposalTransition):
        e.accept_proposal(prop, "rev", now=T[2], commit=True)  # DRAFT→ACCEPTED skip


def test_proposal_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    a = e.create_hypothesis(cyc, "H", "v", "LOW", now=T[1], commit=True).proposal_id
    b = e.create_hypothesis(cyc, "H", "v2", "HIGH", now=T[2], commit=True).proposal_id
    assert a == b
    assert len(ledger.proposal_events(a)) == 1


def test_proposal_unknown_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().create_hypothesis("ARC:nope", "H", now=T[0], commit=True)


@pytest.mark.parametrize("frm,to,ok", [
    (P_DRAFT, P_SUBMITTED, True), (P_DRAFT, P_ACCEPTED, False),
    (P_SUBMITTED, P_REVIEWED, True), (P_REVIEWED, P_ACCEPTED, True),
    (P_REVIEWED, P_REJECTED, True), (P_ACCEPTED, P_REJECTED, False),
    (P_REJECTED, P_REVIEWED, False),
])
def test_proposal_transition_matrix(frm, to, ok):
    assert can_proposal_transition(frm, to) is ok


@pytest.mark.parametrize("s", PROPOSAL_STATES)
def test_proposal_states(s):
    assert s in PROPOSAL_STATES


@pytest.mark.parametrize("r", RISK_LEVELS)
def test_risk_levels(r):
    assert r in RISK_LEVELS


# ═══════════════ experiment plan (no execution) ═══════════════
def test_generate_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    prop = _prop(e, cyc)
    pl = e.generate_plan(prop, ["ds1"], ["f1", "f2"], ["oos", "walk_forward"], ["sharpe"], T[2],
                         commit=True)
    assert pl.plan_id.startswith("ARX:")
    assert pl.is_executable is False
    assert pl.features == ["f1", "f2"]


def test_plan_unknown_proposal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().generate_plan("ARP:nope", ["d"], now=T[0], commit=True)


def test_plan_lineage_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    prop = _prop(e, cyc)
    pl = e.generate_plan(prop, ["d"], now=T[2], commit=True)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    plan_art = next(a for a in arts.values() if a["ref_id"] == pl.plan_id)
    assert plan_art["parent_artifact"] == M.artifact_id(M.ART_PROPOSAL, prop)


def test_multiple_plans(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    prop = _prop(e, cyc)
    e.generate_plan(prop, ["a"], now=T[2], commit=True)
    e.generate_plan(prop, ["b"], now=T[3], commit=True)
    assert len(ledger.plans_for(prop)) == 2


# ═══════════════ feedback ═══════════════
def test_record_feedback(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    fb = e.record_feedback(cyc, "sharpe up 0.2", ["regime filter helps"], "extend to other assets",
                           T[2], commit=True)
    assert fb.feedback_id.startswith("ARF:")
    assert fb.lessons == ["regime filter helps"]


def test_feedback_unknown_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().record_feedback("ARC:nope", "s", now=T[0], commit=True)


def test_feedback_for(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    e.record_feedback(cyc, "s1", now=T[2], commit=True)
    e.record_feedback(cyc, "s2", now=T[3], commit=True)
    assert len(ledger.feedback_for(cyc)) == 2


# ═══════════════ learning ═══════════════
def test_update_learning_history(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    le = e.update_learning_history(cyc, "SUCCESSFUL_PATTERN", "regime-aware sizing",
                                   {"sharpe": 1.4}, T[2], commit=True)
    assert le.learning_event_id.startswith("ARL:")
    assert le.kind == "SUCCESSFUL_PATTERN"


def test_learning_bad_kind(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    with pytest.raises(ValueError):
        e.update_learning_history(cyc, "NOPE", "p", now=T[2], commit=True)


def test_learning_unknown_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().update_learning_history("ARC:nope", "FAILED_PATTERN", "p", now=T[0], commit=True)


@pytest.mark.parametrize("k", LEARNING_KINDS)
def test_learning_kinds(k):
    assert k in LEARNING_KINDS


def test_learning_for(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    e.update_learning_history(cyc, "SUCCESSFUL_PATTERN", "a", now=T[2], commit=True)
    e.update_learning_history(cyc, "FAILED_PATTERN", "b", now=T[3], commit=True)
    assert len(ledger.learning_for(cyc)) == 2


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    e.discover_opportunity(cyc, "MISSING_EXPERIMENTS", "gap", {"evidence_count": 2}, 1.0, T[1],
                           commit=True)
    e.update_learning_history(cyc, "RESEARCH_LESSON", "document more", now=T[2], commit=True)
    r = e.generate_report("SYSTEM", T[3], commit=True)
    assert r.report_id.startswith("ARR:")
    assert r.is_binding is False
    assert r.cycle_count == 1
    assert r.opportunity_count == 1
    assert r.pattern_distribution.get("MISSING_EXPERIMENTS") == 1
    assert r.learning_distribution.get("RESEARCH_LESSON") == 1


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "TRADING" in r.disclaimer


def test_report_accepted_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    prop = _prop(e, cyc)
    e.submit_proposal(prop, now=T[2], commit=True)
    e.review_proposal(prop, "rev", now=T[3], commit=True)
    e.accept_proposal(prop, "lead", now=T[4], commit=True)
    r = e.generate_report("SYSTEM", T[5], commit=True)
    assert r.accepted_proposal_count == 1


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers_present():
    for k in ("strategy_research_governance", "alpha_intelligence", "portfolio_research",
              "knowledge_graph", "agent_governance", "decision_intelligence", "simulation",
              "production_readiness", "automation", "monitoring", "reliability"):
        assert k in ledger.SOURCE_LAYERS


def test_source_count_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("ai_experiments.jsonl")
    with open(p, "w") as f:
        for i in range(5):
            f.write(json.dumps({"experiment_id": f"e{i}"}) + "\n")
    before = open(p).read()
    assert ledger.source_count("alpha_intelligence") == 5
    assert open(p).read() == before


def test_all_source_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    counts = ledger.all_source_counts()
    assert set(counts) == set(ledger.SOURCE_LAYERS)
    assert all(v == 0 for v in counts.values())


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    e.start_analyzing(cyc, now=T[1], commit=True)
    o = e.discover_opportunity(cyc, "REPEATED_FAILURES", "d", {"evidence_count": 2}, 1.0, T[2],
                               commit=True)
    prop = e.create_hypothesis(cyc, "H", "v", "LOW", ["oos"], o.opportunity_id, T[3],
                               commit=True).proposal_id
    e.generate_plan(prop, ["d"], now=T[4], commit=True)
    e.record_feedback(cyc, "s", ["l"], now=T[5], commit=True)
    e.update_learning_history(cyc, "SUCCESSFUL_PATTERN", "p", now=T[6], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _cyc(e)
    p = sp("ar_cycles.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["objective"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    e.start_analyzing(cyc, now=T[1], commit=True)
    p = sp("ar_cycles.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _cyc(e)
    p = sp("ar_cycles.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_cycle_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    e.start_analyzing(cyc, now=T[1], commit=True)
    assert cycle_lifecycle_integrity()["ok"] is True


def test_proposal_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    prop = _prop(e, cyc)
    e.submit_proposal(prop, now=T[2], commit=True)
    assert proposal_lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _cyc(e, "a")
    _cyc(e, "b")
    assert duplicate_integrity()["ok"] is True


def test_opportunity_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    e.discover_opportunity(cyc, "REPEATED_FAILURES", "d", {"evidence_count": 1}, 1.0, T[1],
                           commit=True)
    assert opportunity_integrity()["ok"] is True


def test_opportunity_integrity_detects_auto_selected(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    e.discover_opportunity(cyc, "REPEATED_FAILURES", "d", {"evidence_count": 1}, 1.0, T[1],
                           commit=True)
    p = sp("ar_opportunities.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_auto_selected"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert opportunity_integrity()["ok"] is False


def test_plan_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    prop = _prop(e, cyc)
    e.generate_plan(prop, ["d"], now=T[2], commit=True)
    assert plan_integrity()["ok"] is True


def test_plan_integrity_detects_executable(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    prop = _prop(e, cyc)
    e.generate_plan(prop, ["d"], now=T[2], commit=True)
    p = sp("ar_experiment_plans.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_executable"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert plan_integrity()["ok"] is False


def test_learning_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    e.update_learning_history(cyc, "FAILED_PATTERN", "p", now=T[2], commit=True)
    assert learning_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    o = e.discover_opportunity(cyc, "REPEATED_FAILURES", "d", {"evidence_count": 1}, 1.0, T[1],
                               commit=True)
    prop = e.create_hypothesis(cyc, "H", "v", "LOW", [], o.opportunity_id, T[2],
                               commit=True).proposal_id
    e.generate_plan(prop, ["d"], now=T[3], commit=True)
    e.record_feedback(cyc, "s", now=T[4], commit=True)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    e.discover_opportunity(cyc, "REPEATED_FAILURES", "d", {"evidence_count": 1}, 1.0, T[1],
                           commit=True)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["ANALYZE", "DISCOVER", "PROPOSE", "PLAN", "LEARN", "RECORD"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


@pytest.mark.parametrize("v", ["EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL",
                                "DEPLOY_STRATEGY", "ACTIVATE_LIVE", "APPROVE_FOR_TRADING",
                                "MODIFY_MODEL", "SELECT_STRATEGY", "APPROVE_LIVE"])
def test_forbidden_membership(v):
    assert v in FORBIDDEN_VERBS


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.cycle_id, ("o",), "ARC:"),
    (M.cycle_event_id, ("c", "CREATED", 0), "ARY:"),
    (M.opportunity_id, ("REPEATED_FAILURES", "d"), "ARO:"),
    (M.proposal_id, ("c", "h"), "ARP:"),
    (M.proposal_event_id, ("p", "DRAFT", 0), "ARM:"),
    (M.experiment_plan_id, ("p", 0), "ARX:"),
    (M.feedback_id, ("c", 0), "ARF:"),
    (M.learning_event_id, ("c", "SUCCESSFUL_PATTERN", 0), "ARL:"),
    (M.report_id, ("s", "t"), "ARR:"),
    (M.artifact_id, ("CYCLE", "r"), "ARA:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_ids_deterministic():
    assert M.cycle_id("obj") == M.cycle_id("obj")


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


# ═══════════════ 조회 / summary ═══════════════
def test_list_cycles(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _cyc(e, "a")
    _cyc(e, "b")
    assert len(e.list_cycles()) == 2


def test_list_proposals(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    _prop(e, cyc)
    assert len(e.list_proposals()) == 1


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    cyc = _cyc(e)
    e.discover_opportunity(cyc, "REPEATED_FAILURES", "d", {"evidence_count": 1}, 1.0, T[1],
                           commit=True)
    e.record_feedback(cyc, "s", now=T[2], commit=True)
    s = e.summary(T[9])
    assert s.cycle_count == 1
    assert s.opportunity_count == 1
    assert s.feedback_count == 1


# ═══════════════ CLI ═══════════════
def test_cli_cycle(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research.__main__ import main
    assert main(["cycle", "--objective", "improve", "--refs", "a|b", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["cycle"]["to_state"] == "CREATED"


def test_cli_opportunity(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research.__main__ import main
    main(["cycle", "--objective", "o", "--commit"])
    cyc = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    assert main(["opportunity", "--cycle", cyc, "--pattern", "REPEATED_FAILURES", "--desc", "d",
                 "--evidence-count", "3", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["opportunity"]["is_auto_selected"] is False


def test_cli_proposal_and_plan(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research.__main__ import main
    main(["cycle", "--objective", "o", "--commit"])
    cyc = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    main(["proposal", "--cycle", cyc, "--hypothesis", "H", "--risk", "LOW", "--commit"])
    prop = json.loads(capsys.readouterr().out)["proposal"]["proposal_id"]
    assert main(["plan", "--proposal", prop, "--datasets", "d1|d2", "--metrics", "sharpe",
                 "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["plan"]["is_executable"] is False


def test_cli_feedback(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research.__main__ import main
    main(["cycle", "--objective", "o", "--commit"])
    cyc = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    assert main(["feedback", "--cycle", cyc, "--summary", "s", "--lessons", "l1|l2",
                 "--commit"]) == 0


def test_cli_learning(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research.__main__ import main
    main(["cycle", "--objective", "o", "--commit"])
    cyc = json.loads(capsys.readouterr().out)["cycle"]["cycle_id"]
    assert main(["learning", "--cycle", cyc, "--kind", "SUCCESSFUL_PATTERN", "--pattern", "p",
                 "--commit"]) == 0


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.autonomous_research.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_no_write_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().create_cycle("o", ["s"], T[0], commit=False)
    assert not os.path.exists(os.path.join(tmp_path, "ar_cycles.jsonl"))


def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().create_cycle("o", ["s"], T[0], commit=True)
    with pytest.raises(Exception):
        ev.objective = "x"


def test_eight_ledgers():
    assert len(ledger.ALL_LEDGERS) == 8


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("ar_")


def test_required_ledgers_present():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    for req in ("ar_cycles.jsonl", "ar_opportunities.jsonl", "ar_proposals.jsonl",
                "ar_experiment_plans.jsonl", "ar_feedback.jsonl", "ar_learning_events.jsonl",
                "ar_reports.jsonl", "ar_artifacts.jsonl"):
        assert req in names


# ═══════════════ 보안 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.live_trading", "jarvis.portfolio_execution",
    "jarvis.live_portfolio", "jarvis.portfolio", "jarvis.order", "jarvis.deployment", "jarvis.live",
)


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN_IMPORTS), node.module
        if isinstance(node, ast.Import):
            for n in node.names:
                assert not any(n.name.startswith(f) for f in _FORBIDDEN_IMPORTS), n.name


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_method_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute", "deploy", "trade", "allocate", "approve_live", "select_strategy",
           "execute_trade", "place_order", "allocate_capital", "deploy_strategy", "activate_live",
           "approve_for_trading", "modify_model", "promote")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_destructive_ledger_api(path):
    src = open(path).read()
    # 진짜 파괴적 연산만 — update_learning_history 는 append-only 학습 기록(파괴 아님)
    for bad in ("def delete_", "def overwrite_", "def drop_", "def truncate", "def purge_"):
        assert bad not in src


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src


def test_engine_no_forbidden_methods():
    e = _eng()
    for attr in ("execute", "deploy", "trade", "allocate", "approve_live", "select_strategy"):
        assert not hasattr(e, attr)


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 상위 소스 시드(READ ONLY 대상): 신뢰성 장애 + 모니터링 이상
    with open(sp("rel_incidents.jsonl"), "w") as f:
        for i in range(3):
            f.write(json.dumps({"incident_event_id": f"e{i}"}) + "\n")
    with open(sp("rmon_anomalies.jsonl"), "w") as f:
        for i in range(2):
            f.write(json.dumps({"anomaly_id": f"a{i}"}) + "\n")
    e = _eng()
    # 이력 분석(READ ONLY)
    hist = e.analyze_history(T[0])
    assert hist["read_only"] is True
    assert hist["total"] == 5
    # 사이클 생성 → 분석
    cyc = e.create_cycle("reduce repeated pipeline failures", ["rel", "rmon"], T[1],
                         commit=True).cycle_id
    e.start_analyzing(cyc, now=T[2], commit=True)
    # 기회 탐지(점수만, 자동 선택 없음)
    opps = e.detect_opportunities_from_history(cyc, T[3], commit=True)
    assert any(o.source_pattern == "REPEATED_FAILURES" for o in opps)
    assert all(o.is_auto_selected is False for o in opps)
    opp = opps[0]
    # 가설 제안(초안) → 제출 → 검토 → 수락(사람 검토 필수)
    prop = e.create_hypothesis(cyc, "earlier anomaly gate reduces failures", "fewer incidents",
                               "MEDIUM", ["oos", "walk_forward"], opp.opportunity_id, T[4],
                               commit=True).proposal_id
    e.mark_planned(cyc, now=T[5], commit=True)
    e.submit_proposal(prop, now=T[6], commit=True)
    e.review_proposal(prop, "reviewer-1", now=T[7], commit=True)
    e.accept_proposal(prop, "lead-1", now=T[8], commit=True)
    assert e.proposal_state(prop) == P_ACCEPTED  # ACCEPTED ≠ 배포/거래
    # 실험 계획(계획만, 실행 없음)
    plan = e.generate_plan(prop, ["incidents_ds"], ["anomaly_rate"], ["oos"], ["failure_reduction"],
                           T[9], commit=True)
    assert plan.is_executable is False
    # 평가 → 피드백 → 학습
    e.start_evaluating(cyc, now=T[10], commit=True)
    e.record_feedback(cyc, "failure rate down 40%", ["earlier gating works"], "apply to more layers",
                      T[11], commit=True)
    e.update_learning_history(cyc, "SUCCESSFUL_PATTERN", "early-anomaly-gate", {"reduction": 0.4},
                              T[12], commit=True)
    e.complete_cycle(cyc, now=T[13], commit=True)
    # 리포트
    r = e.generate_report("SYSTEM", T[14], commit=True)
    assert r.cycle_count == 1
    assert r.accepted_proposal_count == 1
    assert r.is_binding is False  # KNOWLEDGE ≠ TRADING
    e.archive_cycle(cyc, now=T[15], commit=True)
    assert e.cycle_state(cyc) == C_ARCHIVED
    assert open(sp("rel_incidents.jsonl")).read()  # 상위 원장 여전히 존재·불변
    assert verify_chain()["ok"] is True
    assert replay(e, T[16])["deterministic"] is True
