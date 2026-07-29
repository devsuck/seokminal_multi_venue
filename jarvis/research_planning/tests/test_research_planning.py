"""P10.15 Research Planning Intelligence 테스트. **연구 계획 전용.**

기회 생명주기(IDENTIFIED→ANALYZED→PLANNED→ARCHIVED, 차단전이)·가설·청사진(불변, 실행 없음)·계획
(불변, priority 정보용)·의존 그래프(노드/엣지 검증·순환)·우선순위(정보용)·리포트·verify(체인/변조/중복/
의존/청사진/계보)·replay·상위 READ ONLY 보호·CLI·보안(금지import·실행/거래/배포/선택/배분 없음·상위
원장 무변경·삭제 API 없음·불변·PLAN≠EXECUTION·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.research_planning import ledger
from jarvis.research_planning import models as M
from jarvis.research_planning.engine import ResearchPlanningEngine
from jarvis.research_planning.models import (
    ANALYZED,
    ARCHIVED,
    COMPLEXITY_HIGH,
    COMPLEXITY_LOW,
    COMPLEXITY_MEDIUM,
    HIGH,
    IDENTIFIED,
    LOW,
    MEDIUM,
    PLANNED,
    IllegalTransition,
    ImmutableBlueprintError,
    ImmutableHypothesisError,
    ImmutableOpportunityError,
    ImmutablePlanError,
    InvalidDependency,
    UnknownOpportunity,
    UnknownPlan,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

_HI = {"expected_learning_value": 0.9, "evidence_availability": 0.85, "validation_feasibility": 0.8,
       "historical_success": 0.85, "complexity": 0.2}
_LO = {"expected_learning_value": 0.2, "evidence_availability": 0.1, "validation_feasibility": 0.1,
       "historical_success": 0.2, "complexity": 0.9}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_planning.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchPlanningEngine()


def _opp(eng, desc="explore liquidity-drawdown causal link", commit=True):
    return eng.register_opportunity(desc, ["rm:M1"], "learn causal strength", 0.7, T0,
                                    commit=commit)


# ── Opportunity lifecycle ──
def test_register_opportunity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = _opp(eng)
    assert o.status == IDENTIFIED and o.confidence == 0.7
    assert eng.opportunity_state(o.opportunity_id) == IDENTIFIED


def test_opportunity_id_deterministic():
    a = M.opportunity_id("d")
    assert a == M.opportunity_id("d") and a.startswith("RPO:")


def test_opportunity_commit_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _opp(_eng())
    assert len(ledger.read_opportunity_events()) == 1


def test_opportunity_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _opp(_eng(), commit=False)
    assert ledger.read_opportunity_events() == []


def test_opportunity_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_opportunity("d", [], "learn A", 0.5, T0, commit=True)
    with pytest.raises(ImmutableOpportunityError):
        eng.register_opportunity("d", [], "learn B", 0.5, T0, commit=True)


def test_opportunity_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _opp(eng)
    _opp(eng)
    assert len(ledger.distinct_opportunities()) == 1


def test_opportunity_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = _opp(eng)
    oid = o.opportunity_id
    eng.transition_opportunity(oid, ANALYZED, T1, commit=True)
    eng.transition_opportunity(oid, PLANNED, T1, commit=True)
    eng.transition_opportunity(oid, ARCHIVED, T2, commit=True)
    assert eng.opportunity_state(oid) == ARCHIVED


def test_opportunity_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = _opp(eng)
    with pytest.raises(IllegalTransition):
        eng.transition_opportunity(o.opportunity_id, PLANNED, T1, commit=True)


def test_opportunity_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = _opp(eng)
    for to in (ANALYZED, PLANNED, ARCHIVED):
        eng.transition_opportunity(o.opportunity_id, to, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_opportunity(o.opportunity_id, IDENTIFIED, T2, commit=True)


def test_opportunity_transition_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownOpportunity):
        _eng().transition_opportunity("GHOST", ANALYZED, T1, commit=True)


def test_opportunity_transition_table():
    assert M.can_transition_opportunity("", IDENTIFIED)
    assert M.can_transition_opportunity(IDENTIFIED, ANALYZED)
    assert M.can_transition_opportunity(ANALYZED, PLANNED)
    assert not M.can_transition_opportunity(IDENTIFIED, PLANNED)


def test_opportunity_artifact_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = _opp(eng)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    oa = arts[M.artifact_id(M.ART_OPPORTUNITY, o.opportunity_id)]
    assert oa["parent_artifact"] in arts


# ── Hypothesis ──
def test_create_hypothesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    h = eng.create_hypothesis("liquidity drives drawdown", "causal evidence", ["ci:E1"], 0.7, T0,
                              commit=True)
    assert h.statement.startswith("liquidity") and len(ledger.read_hypotheses()) == 1


def test_hypothesis_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_hypothesis("s", "r1", [], 0.5, T0, commit=True)
    with pytest.raises(ImmutableHypothesisError):
        eng.create_hypothesis("s", "r2", [], 0.5, T0, commit=True)


def test_hypothesis_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_hypothesis("s", "r", [], 0.5, T0, commit=True)
    eng.create_hypothesis("s", "r", [], 0.5, T0, commit=True)
    assert len(ledger.read_hypotheses()) == 1


# ── Blueprint ──
def test_create_blueprint(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    b = eng.create_blueprint("test liquidity effect", ["dataset:prices"], "regime_comparison",
                             ["walk_forward"], ["dataset:prices"], T0, commit=True)
    assert b.objective.startswith("test") and b.method == "regime_comparison"
    assert len(ledger.read_blueprints()) == 1


def test_blueprint_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_blueprint("obj", ["a"], "m", [], [], T0, commit=True)
    with pytest.raises(ImmutableBlueprintError):
        eng.create_blueprint("obj", ["a", "b"], "m", [], [], T0, commit=True)


def test_blueprint_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_blueprint("obj", ["a"], "m", [], [], T0, commit=True)
    eng.create_blueprint("obj", ["a"], "m", [], [], T0, commit=True)
    assert len(ledger.read_blueprints()) == 1


def test_blueprint_no_execution(tmp_path, monkeypatch):
    """청사진에 실행/시작 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    b = eng.create_blueprint("obj", ["a"], "m", [], [], T0, commit=True)
    for banned in ("execute", "start", "run", "deploy"):
        assert banned not in b.to_dict()


# ── Dependency graph ──
def test_add_dependency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    d = eng.add_dependency("D1", M.NODE_DATASET, M.REQUIRES, "F1", M.NODE_FEATURE, T0,
                           commit=True)
    assert d.edge_type == M.REQUIRES and d.from_type == M.NODE_DATASET


@pytest.mark.parametrize("edge", list(M.EDGE_TYPES))
def test_dependency_edge_types(tmp_path, monkeypatch, edge):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    d = eng.add_dependency("A", M.NODE_DATASET, edge, "B", M.NODE_FEATURE, T0, commit=True)
    assert d.edge_type == edge


@pytest.mark.parametrize("node", list(M.NODE_TYPES))
def test_dependency_node_types(tmp_path, monkeypatch, node):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    d = eng.add_dependency("A", node, M.DEPENDS_ON, "B", M.NODE_VALIDATION, T0, commit=True)
    assert d.from_type == node


def test_dependency_invalid_node(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    with pytest.raises(InvalidDependency):
        eng.add_dependency("A", "NONSENSE", M.REQUIRES, "B", M.NODE_FEATURE, T0, commit=True)


def test_dependency_invalid_edge(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    with pytest.raises(InvalidDependency):
        eng.add_dependency("A", M.NODE_DATASET, "NONSENSE", "B", M.NODE_FEATURE, T0, commit=True)


def test_dependency_cycle_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.add_dependency("A", M.NODE_DATASET, M.REQUIRES, "B", M.NODE_FEATURE, T0, commit=True)
    eng.add_dependency("B", M.NODE_FEATURE, M.REQUIRES, "C", M.NODE_SIGNAL, T0, commit=True)
    with pytest.raises(InvalidDependency):
        eng.add_dependency("C", M.NODE_SIGNAL, M.REQUIRES, "A", M.NODE_DATASET, T0, commit=True)


def test_dependency_cycle_free(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.add_dependency("A", M.NODE_DATASET, M.REQUIRES, "B", M.NODE_FEATURE, T0, commit=True)
    assert eng.dependency_cycle() == []


def test_dependency_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.add_dependency("A", M.NODE_DATASET, M.REQUIRES, "B", M.NODE_FEATURE, T0, commit=True)
    eng.add_dependency("A", M.NODE_DATASET, M.REQUIRES, "B", M.NODE_FEATURE, T0, commit=True)
    assert len(ledger.read_dependencies()) == 1


def test_detect_cycle_helper():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) == ["a", "b", "a"]
    assert M.detect_cycle([("a", "b")]) == []


# ── Plan ──
def test_create_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = _opp(eng)
    p = eng.create_plan("Q4_causal_research", [o.opportunity_id], [], _HI, COMPLEXITY_LOW,
                        "high learning", T0, commit=True)
    assert p.name == "Q4_causal_research" and o.opportunity_id in p.opportunities
    assert 0.0 <= p.priority_score <= 1.0


def test_plan_advances_opportunity_to_planned(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o = _opp(eng)
    eng.create_plan("plan1", [o.opportunity_id], [], _HI, COMPLEXITY_LOW, "", T0, commit=True)
    assert eng.opportunity_state(o.opportunity_id) == PLANNED


def test_plan_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_plan("p", ["o1"], [], {}, COMPLEXITY_LOW, "v1", T0, commit=True)
    with pytest.raises(ImmutablePlanError):
        eng.create_plan("p", ["o1"], [], {}, COMPLEXITY_HIGH, "v2", T0, commit=True)


def test_plan_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_plan("p", ["o1"], [], {}, COMPLEXITY_LOW, "v", T0, commit=True)
    eng.create_plan("p", ["o1"], [], {}, COMPLEXITY_LOW, "v", T0, commit=True)
    assert len(ledger.read_plans()) == 1


def test_plan_priority_informational(tmp_path, monkeypatch):
    """계획에 approval/execute/deploy 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = eng.create_plan("p", [], [], _HI, COMPLEXITY_LOW, "", T0, commit=True)
    for banned in ("approved", "execute", "deploy", "selected"):
        assert banned not in p.to_dict()


def test_plan_complexity_affects_priority(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    base = {"expected_learning_value": 0.8, "evidence_availability": 0.8,
            "validation_feasibility": 0.8, "historical_success": 0.8}
    p_low = eng.create_plan("low", [], [], base, COMPLEXITY_LOW, "", T0, commit=True)
    p_high = eng.create_plan("high", [], [], base, COMPLEXITY_HIGH, "", T0, commit=True)
    assert p_low.priority_score > p_high.priority_score


# ── Priority analysis ──
def test_prioritize(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = eng.create_plan("p", [], [], {}, COMPLEXITY_LOW, "", T0, commit=True)
    pr = eng.prioritize(p.plan_id, _HI, T1, commit=True)
    assert pr.rank in ("P1", "P2", "P3") and 0.0 <= pr.priority_score <= 1.0
    assert len(ledger.read_priorities()) == 1


def test_prioritize_unknown_plan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownPlan):
        _eng().prioritize("GHOST", _HI, T1, commit=True)


def test_prioritize_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = eng.create_plan("p", [], [], {}, COMPLEXITY_LOW, "", T0, commit=True)
    eng.prioritize(p.plan_id, _HI, T1, commit=True)
    eng.prioritize(p.plan_id, _HI, T1, commit=True)
    assert len(ledger.read_priorities()) == 1


def test_priority_rank_helper():
    assert M.priority_rank(0.8) == "P1"
    assert M.priority_rank(0.5) == "P2"
    assert M.priority_rank(0.2) == "P3"


# ── Planning analysis ──
def test_planning_score_full():
    m = {k: 1.0 for k in M.PLANNING_WEIGHTS}
    m["complexity"] = 0.0
    assert abs(M.planning_score(m) - 1.0) < 1e-9


def test_planning_weights_sum_one():
    assert abs(sum(M.PLANNING_WEIGHTS.values()) - 1.0) < 1e-9


def test_planning_confidence_high():
    assert M.planning_confidence(_HI) == HIGH


def test_planning_confidence_low():
    assert M.planning_confidence(_LO) == LOW


def test_planning_confidence_medium():
    m = {k: 0.5 for k in M.PLANNING_WEIGHTS}
    m["complexity"] = 0.2
    assert M.planning_confidence(m) == MEDIUM


def test_analyze(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().analyze(_HI)["planning_confidence"] == HIGH


def test_complexity_value_helper():
    assert M.complexity_value(COMPLEXITY_LOW) < M.complexity_value(COMPLEXITY_HIGH)


# ── Report / summary ──
def _full(eng):
    o = _opp(eng)
    eng.create_hypothesis("liquidity drives drawdown", "causal", ["ci:E1"], 0.7, T0, commit=True)
    eng.create_blueprint("test liquidity", ["dataset:prices"], "regime_comparison",
                         ["walk_forward"], ["dataset:prices"], T0, commit=True)
    p = eng.create_plan("Q4_plan", [o.opportunity_id], [], _HI, COMPLEXITY_LOW, "high", T0,
                        commit=True)
    eng.add_dependency("dataset:prices", M.NODE_DATASET, M.REQUIRES, "feat:mom", M.NODE_FEATURE,
                       T0, commit=True)
    eng.prioritize(p.plan_id, _HI, T1, commit=True)
    return o, p


def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert rep.opportunity_count == 1 and rep.plan_count == 1 and rep.blueprint_count == 1
    assert rep.hypothesis_count == 1 and rep.dependency_count == 1 and rep.priority_count == 1
    assert rep.planning_confidence == HIGH and "PLAN ≠ EXECUTION" in rep.disclaimer


def test_report_opportunity_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert rep.opportunity_state_distribution.get(PLANNED) == 1


def test_report_no_trading_verbs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    d = rep.to_dict()
    d.pop("disclaimer")
    blob = json.dumps(d).upper()
    for verb in ("BUY", "SELL", "DEPLOY", "ALLOCATE", "EXECUTE"):
        assert verb not in blob


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    eng.generate_report("GLOBAL", _HI, T2, commit=True)
    eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert len(ledger.read_reports()) == 1


def test_summary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.summary(T2)
    assert rep.opportunity_count == 1 and rep.plan_count == 1 and rep.dependency_count == 1
    assert rep.priority_count == 1 and rep.blueprint_count == 1 and rep.hypothesis_count == 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.summary(T2).to_dict() == eng.summary(T2).to_dict()


def test_summary_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rep = _eng().summary(T0)
    assert rep.opportunity_count == 0 and rep.report_count == 0


# ── verify ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_planning.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_full_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_planning.verify import verify_chain
    eng = _eng()
    _full(eng)
    res = verify_chain()
    assert res["ok"] is True
    assert res["dependency"]["ok"] and res["blueprint"]["ok"] and res["lineage"]["ok"]


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_planning.verify import verify_chain
    eng = _eng()
    _opp(eng)
    recs = ledger.read_opportunity_events()
    recs[0]["description"] = "TAMPERED"
    with open(sp("rp_opportunities.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_chain_break(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_planning.verify import verify_ledger
    eng = _eng()
    eng.register_opportunity("a", [], "la", 0.5, T0, commit=True)
    eng.register_opportunity("b", [], "lb", 0.5, T0, commit=True)
    recs = ledger.read_opportunity_events()
    recs[1]["previous_hash"] = "GENESIS"
    with open(sp("rp_opportunities.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_ledger(ledger.OPPORTUNITIES)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_planning.verify import verify_ledger
    eng = _eng()
    _opp(eng)
    recs = ledger.read_opportunity_events()
    dup = dict(recs[0])
    dup["previous_hash"] = recs[0]["record_hash"]
    with open(sp("rp_opportunities.jsonl"), "a") as f:
        f.write(json.dumps(dup) + "\n")
    assert verify_ledger(ledger.OPPORTUNITIES)["ok"] is False


def test_verify_dependency_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_planning.verify import dependency_validation
    for frm, to in (("A", "B"), ("B", "A")):
        rec = {"dependency_id": M.dependency_id(frm, M.REQUIRES, to), "from_node": frm,
               "from_type": M.NODE_DATASET, "edge_type": M.REQUIRES, "to_node": to,
               "to_type": M.NODE_FEATURE, "created_at": T0, "previous_hash": "GENESIS"}
        rec["record_hash"] = M.content_hash(rec)
        ledger.append_dependency(rec)
    assert any("dependency_cycle" in i for i in dependency_validation()["issues"])


def test_verify_dependency_invalid_node(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_planning.verify import dependency_validation
    rec = {"dependency_id": "RPD:x", "from_node": "A", "from_type": "BADTYPE",
           "edge_type": M.REQUIRES, "to_node": "B", "to_type": M.NODE_FEATURE, "created_at": T0,
           "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("rp_dependencies.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    assert any("invalid_node" in i for i in dependency_validation()["issues"])


def test_verify_blueprint_missing_objective(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_planning.verify import blueprint_validation
    rec = {"blueprint_id": "RPB:x", "objective": "", "inputs": [], "method": "m",
           "validation_requirements": [], "dependencies": [], "metadata_hash": "h",
           "created_at": T0, "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("rp_blueprints.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    assert blueprint_validation()["ok"] is False


def test_verify_artifact_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_planning.verify import lineage_validation
    a1 = {"artifact_id": "A1", "artifact_type": "X", "ref_id": "r", "parent_artifact": "A2",
          "created_at": T0, "previous_hash": "GENESIS"}
    a1["record_hash"] = M.content_hash(a1)
    a2 = {"artifact_id": "A2", "artifact_type": "X", "ref_id": "r", "parent_artifact": "A1",
          "created_at": T0, "previous_hash": a1["record_hash"]}
    a2["record_hash"] = M.content_hash(a2)
    with open(sp("rp_artifacts.jsonl"), "w") as f:
        f.write(json.dumps(a1) + "\n")
        f.write(json.dumps(a2) + "\n")
    assert any("artifact_cycle" in i for i in lineage_validation()["issues"])


# ── replay ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_planning.verify import replay
    eng = _eng()
    _full(eng)
    assert replay(eng, T2)["deterministic"] is True


def test_content_hash_excludes_chain_fields():
    a = {"x": 1, "previous_hash": "A", "record_hash": "B", "report_hash": "C"}
    b = {"x": 1, "previous_hash": "Z", "record_hash": "Z", "report_hash": "Z"}
    assert M.content_hash(a) == M.content_hash(b)


# ── CLI ──
def test_cli_opportunity_and_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_planning.__main__ import main
    rc = main(["opportunity", "--description", "explore X", "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["opportunity"]["status"] == IDENTIFIED
    main(["summary"])
    assert json.loads(capsys.readouterr().out)["opportunity_count"] == 1


def test_cli_full_workflow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_planning.__main__ import main
    main(["opportunity", "--description", "explore liquidity", "--commit"])
    oid = json.loads(capsys.readouterr().out)["opportunity"]["opportunity_id"]
    main(["plan", "--name", "plan1", "--opportunities", oid, "--complexity", "LOW", "--commit"])
    pid = json.loads(capsys.readouterr().out)["plan"]["plan_id"]
    main(["blueprint", "--objective", "test liq", "--method", "regime_comparison", "--commit"])
    capsys.readouterr()
    main(["dependency", "--from-node", "D1", "--from-type", "DATASET", "--edge-type", "REQUIRES",
          "--to-node", "F1", "--to-type", "FEATURE", "--commit"])
    dep = json.loads(capsys.readouterr().out)
    assert dep["cycle"] == []
    main(["priority", "--plan-ref", pid, "--metrics-json", json.dumps({"expected_learning_value":
          0.9, "evidence_availability": 0.9, "validation_feasibility": 0.9,
          "historical_success": 0.9, "complexity": 0.1}), "--commit"])
    pr = json.loads(capsys.readouterr().out)["priority"]
    assert pr["rank"] == "P1"
    main(["report", "--commit"])
    capsys.readouterr()
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_blueprint(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_planning.__main__ import main
    rc = main(["blueprint", "--objective", "o", "--method", "m", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["blueprint"]["method"] == "m"


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_planning.__main__ import main
    main(["opportunity", "--description", "d", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.research_planning.engine as eng_mod
    import jarvis.research_planning.models as mdl_mod
    import jarvis.research_planning.ledger as led_mod
    import jarvis.research_planning.verify as ver_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "live_execution", _j + "broker", _j + "order",
                 _j + "portfolio.", _j + "risk_governor", _j + "permission",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "select_strategy(", "activate_live("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_keyword_methods():
    import jarvis.research_planning.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def execute", "def trade", "def allocate", "def deploy", "def approve",
               "def select_strategy", "def activate_live"):
        assert kw not in src


def test_no_execution_authority_api():
    api = set(dir(ResearchPlanningEngine))
    for banned in ("execute", "trade", "allocate", "deploy", "approve", "select_strategy",
                   "activate_live", "start_experiment", "assign_agent", "place_order"):
        assert banned not in api


def test_no_automatic_experiment_creation():
    """실험 자동 생성/agent 배정/model 변경 메서드가 없어야 한다."""
    eng = ResearchPlanningEngine()
    for banned in ("start_experiment", "create_experiment", "assign_agent", "modify_model",
                   "run_plan"):
        assert not hasattr(eng, banned)


def test_plan_not_execution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = eng.create_plan("p", [], [], _HI, COMPLEXITY_LOW, "", T0, commit=True)
    for banned in ("approved", "executed", "deployed", "started"):
        assert banned not in p.to_dict()


def test_live_execution_disabled_invariant():
    import jarvis.config as _cfg
    assert _cfg.live_execution_enabled() is False
    assert _cfg.AUTONOMY_LEVEL < _cfg.MIN_LIVE_LEVEL


def test_autonomy_unchanged(tmp_path, monkeypatch):
    import jarvis.config as _cfg
    before = _cfg.AUTONOMY_LEVEL
    _iso(tmp_path, monkeypatch)
    _full(_eng())
    assert _cfg.AUTONOMY_LEVEL == before
    assert _cfg.live_execution_enabled() is False


def test_no_delete_or_update_api():
    import importlib
    for mod_name in ("engine", "ledger"):
        m = importlib.import_module(f"jarvis.research_planning.{mod_name}")
        for attr in dir(m):
            low = attr.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledgers_namespaced_rp_prefix():
    for filename, _ in ledger.ALL_LEDGERS:
        assert filename.startswith("rp_")


def test_no_collision_with_existing_prefixes():
    ours = {fn for fn, _ in ledger.ALL_LEDGERS}
    known = {"rm_memories.jsonl", "rv_validations.jsonl", "rg_strategies.jsonl",
             "kg_entities.jsonl", "di_candidates.jsonl", "sim_scenarios.jsonl",
             "ci_variables.jsonl", "mi_patterns.jsonl", "si_workflows.jsonl"}
    assert ours.isdisjoint(known)
    assert all(fn.startswith("rp_") for fn in ours)


def test_source_ledgers_read_only_not_owned():
    owned = {fn for fn, _ in ledger.ALL_LEDGERS}
    for layer, spec in ledger.SOURCE_LEDGERS.items():
        assert spec[0] not in owned


def test_existing_source_ledgers_untouched(tmp_path, monkeypatch):
    """상위 P10.5/7/8/11/12/13/14 원장을 시드한 뒤 전체 워크플로를 돌려도 원본 SHA256 불변."""
    sp = _iso(tmp_path, monkeypatch)
    seeds = {"kg_entities.jsonl": [{"entity_id": "KGE:1"}],
             "sim_results.jsonl": [{"result_id": "SRS:1"}],
             "ci_hypotheses.jsonl": [{"event_id": "E1"}],
             "rm_memories.jsonl": [{"event_id": "RME:1"}]}
    hashes = {}
    for fn, rows in seeds.items():
        with open(sp(fn), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        hashes[fn] = hashlib.sha256(open(sp(fn), "rb").read()).hexdigest()
    eng = _eng()
    refs = eng.list_source_objects("research_kg")
    assert refs == ["research_kg:KGE:1"]
    _full(eng)
    for fn, h in hashes.items():
        assert hashlib.sha256(open(sp(fn), "rb").read()).hexdigest() == h


def test_engine_only_appends_rp_files(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    created = [f for f in os.listdir(tmp_path) if f.endswith(".jsonl")]
    assert created and all(f.startswith("rp_") for f in created)


def test_node_and_edge_types_defined():
    assert set(M.NODE_TYPES) == {"DATASET", "FEATURE", "SIGNAL", "STRATEGY", "MODEL",
                                 "EXPERIMENT", "VALIDATION"}
    assert set(M.EDGE_TYPES) == {"REQUIRES", "BUILDS_ON", "DEPENDS_ON"}


def test_list_source_objects_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_objects("NOPE") == []


# ── 추가 ID prefix ──
def test_plan_id_prefix():
    assert M.plan_id("n").startswith("RPP:")


def test_blueprint_id_prefix():
    assert M.blueprint_id("o", "m").startswith("RPB:")


def test_hypothesis_id_prefix():
    assert M.hypothesis_id("s").startswith("RPH:")


def test_dependency_id_prefix():
    assert M.dependency_id("a", M.REQUIRES, "b").startswith("RPD:")


def test_priority_id_prefix():
    assert M.priority_id("p").startswith("RPR:")


def test_report_id_prefix():
    assert M.report_id("s").startswith("RPT:")


def test_artifact_id_prefix():
    assert M.artifact_id(M.ART_PLAN, "x").startswith("RPA:")


def test_opportunity_event_id_prefix():
    assert M.opportunity_event_id("o", "", M.IDENTIFIED).startswith("ROE:")


def test_priority_score_equals_planning_score():
    assert M.priority_score(_HI) == M.planning_score(_HI)


def test_plan_priority_artifact_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = eng.create_plan("p", [], [], {}, COMPLEXITY_LOW, "", T0, commit=True)
    pr = eng.prioritize(p.plan_id, _HI, T1, commit=True)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    pa = arts[M.artifact_id(M.ART_PRIORITY, pr.priority_id)]
    assert pa["parent_artifact"] == M.artifact_id(M.ART_PLAN, p.plan_id)


def test_blueprint_dependencies_stored(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    b = eng.create_blueprint("obj", ["dataset:x"], "m", ["wf"], ["dataset:x", "feat:y"], T0,
                             commit=True)
    assert b.dependencies == ["dataset:x", "feat:y"]


def test_plan_multiple_opportunities(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    o1 = eng.register_opportunity("opp one", [], "l1", 0.5, T0, commit=True)
    o2 = eng.register_opportunity("opp two", [], "l2", 0.5, T0, commit=True)
    p = eng.create_plan("multi", [o1.opportunity_id, o2.opportunity_id], [], _HI,
                        COMPLEXITY_LOW, "", T0, commit=True)
    assert len(p.opportunities) == 2
    assert eng.opportunity_state(o1.opportunity_id) == PLANNED
    assert eng.opportunity_state(o2.opportunity_id) == PLANNED


def test_full_lineage_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_planning.verify import lineage_validation
    eng = _eng()
    _full(eng)
    res = lineage_validation()
    assert res["ok"] is True and not res["issues"]
