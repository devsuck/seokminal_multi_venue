"""P11 Research OS Orchestration 테스트. **관찰·조직 전용.**

레이어 레지스트리(불변)·생명주기(REGISTERED→ACTIVE→DEPRECATED, 차단전이)·워크플로(CREATED→TRACKING→
COMPLETED→ARCHIVED, 그래프 검증·순환)·교차계층 이벤트·생태계 스냅샷(CREATED→VERIFIED→ARCHIVED)·의존
분석·계보 추적·건강 리포트·verify(체인/변조/중복/계보/의존/워크플로/아티팩트)·replay·상위 READ ONLY
보호·CLI·보안(금지import·실행/거래/배포/선택/config변경/배분 없음·상위 원장 무변경·삭제 API 없음·불변·
ORCHESTRATION≠EXECUTION·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.research_os import ledger
from jarvis.research_os import models as M
from jarvis.research_os.engine import ResearchOSEngine
from jarvis.research_os.models import (
    ACTIVE,
    ARCHIVED,
    COMPLETED,
    CREATED,
    DEGRADED,
    DEPRECATED,
    HEALTHY,
    REGISTERED,
    TRACKING,
    VERIFIED,
    WARNING,
    IllegalTransition,
    ImmutableLayerError,
    ImmutableWorkflowError,
    InvalidWorkflowGraph,
    UnknownLayer,
    UnknownSnapshot,
    UnknownWorkflow,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

_HEALTHY = {"layer_availability": 0.95, "lineage_completeness": 0.85, "data_traceability": 0.8,
            "validation_coverage": 0.8, "research_reproducibility": 0.85}
_DEGRADED = {"layer_availability": 0.2, "lineage_completeness": 0.1, "data_traceability": 0.1,
             "validation_coverage": 0.1, "research_reproducibility": 0.1}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_os.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchOSEngine()


def _layer(eng, name="research_kg", commit=True, activate=False):
    return eng.register_layer(name, "1.0", "kg_", ["graph"], activate, T0, commit=commit)


# ── Layer Registry ──
def test_register_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = _layer(eng)
    assert l.status == REGISTERED and l.prefix == "kg_"
    assert eng.layer_state(l.layer_id) == REGISTERED


def test_layer_id_deterministic():
    a = M.layer_id("n")
    assert a == M.layer_id("n") and a.startswith("ROL:")


def test_layer_commit_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _layer(_eng())
    assert len(ledger.read_layer_events()) == 1


def test_layer_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _layer(_eng(), commit=False)
    assert ledger.read_layer_events() == []


def test_layer_activate_on_register(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = _layer(eng, activate=True)
    assert eng.layer_state(l.layer_id) == ACTIVE


def test_layer_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_layer("l", "1.0", "l_", [], False, T0, commit=True)
    with pytest.raises(ImmutableLayerError):
        eng.register_layer("l", "2.0", "l_", [], False, T0, commit=True)


def test_layer_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _layer(eng)
    _layer(eng)
    assert len(ledger.distinct_layers()) == 1


def test_layer_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = _layer(eng)
    lid = l.layer_id
    eng.transition_layer(lid, ACTIVE, T1, commit=True)
    eng.transition_layer(lid, DEPRECATED, T2, commit=True)
    assert eng.layer_state(lid) == DEPRECATED


def test_layer_register_to_deprecated_direct(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = _layer(eng)
    eng.transition_layer(l.layer_id, DEPRECATED, T1, commit=True)
    assert eng.layer_state(l.layer_id) == DEPRECATED


def test_layer_deprecated_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = _layer(eng)
    eng.transition_layer(l.layer_id, DEPRECATED, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_layer(l.layer_id, ACTIVE, T2, commit=True)


def test_layer_transition_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownLayer):
        _eng().transition_layer("GHOST", ACTIVE, T1, commit=True)


def test_layer_transition_table():
    assert M.can_transition_layer("", REGISTERED)
    assert M.can_transition_layer(REGISTERED, ACTIVE)
    assert M.can_transition_layer(REGISTERED, DEPRECATED)
    assert M.can_transition_layer(ACTIVE, DEPRECATED)
    assert not M.can_transition_layer(DEPRECATED, ACTIVE)


def test_register_known_layers(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    n = eng.register_known_layers(T0, commit=True)
    assert n == len(ledger.SOURCE_LEDGERS)
    assert len(ledger.distinct_layers()) == n
    # 모두 ACTIVE
    for l in ledger.distinct_layers():
        assert eng.layer_state(l.get("layer_id")) == ACTIVE


def test_layer_artifact_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = _layer(eng)
    assert any(a["artifact_type"] == M.ART_LAYER and a["ref_id"] == l.layer_id
               for a in ledger.read_artifacts())


# ── Workflow ──
def _wf(eng, name="research_journey", commit=True):
    nodes = [{"id": "ds", "type": M.NODE_DATASET}, {"id": "ft", "type": M.NODE_FEATURE},
             {"id": "sg", "type": M.NODE_SIGNAL}]
    edges = [["ds", M.PRODUCES, "ft"], ["ft", M.USES, "sg"]]
    return eng.register_workflow(name, nodes, edges, ["kg"], T0, commit=commit)


def test_register_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    assert w.status == CREATED and len(w.nodes) == 3
    assert eng.workflow_state(w.workflow_id) == CREATED


def test_workflow_invalid_node(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    with pytest.raises(InvalidWorkflowGraph):
        eng.register_workflow("w", [{"id": "x", "type": "NONSENSE"}], [], [], T0, commit=True)


def test_workflow_invalid_edge(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    with pytest.raises(InvalidWorkflowGraph):
        eng.register_workflow("w", [], [["a", "NONSENSE", "b"]], [], T0, commit=True)


def test_workflow_cycle_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    edges = [["a", M.PRODUCES, "b"], ["b", M.USES, "c"], ["c", M.IMPROVES, "a"]]
    with pytest.raises(InvalidWorkflowGraph):
        eng.register_workflow("w", [], edges, [], T0, commit=True)


def test_workflow_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    wid = w.workflow_id
    eng.transition_workflow(wid, TRACKING, T1, commit=True)
    eng.transition_workflow(wid, COMPLETED, T1, commit=True)
    eng.transition_workflow(wid, ARCHIVED, T2, commit=True)
    assert eng.workflow_state(wid) == ARCHIVED


def test_workflow_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    with pytest.raises(IllegalTransition):
        eng.transition_workflow(w.workflow_id, COMPLETED, T1, commit=True)


def test_workflow_transition_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownWorkflow):
        _eng().transition_workflow("GHOST", TRACKING, T1, commit=True)


def test_workflow_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_workflow("w", [{"id": "a", "type": M.NODE_DATASET}], [], [], T0, commit=True)
    with pytest.raises(ImmutableWorkflowError):
        eng.register_workflow("w", [{"id": "b", "type": M.NODE_FEATURE}], [], [], T0, commit=True)


def test_workflow_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _wf(eng)
    _wf(eng)
    assert len(ledger.distinct_workflows()) == 1


def test_workflow_transition_table():
    assert M.can_transition_workflow("", CREATED)
    assert M.can_transition_workflow(CREATED, TRACKING)
    assert M.can_transition_workflow(TRACKING, COMPLETED)
    assert not M.can_transition_workflow(CREATED, COMPLETED)


def test_workflow_acyclic_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = _wf(eng)
    assert w.edges  # DAG 통과


# ── Cross layer event ──
def test_record_event(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e = eng.record_event("research_data", M.DATASET_REGISTERED, "DS1", T0, T0, commit=True)
    assert e.event_type == M.DATASET_REGISTERED and e.reference_id == "DS1"
    assert len(ledger.read_events()) == 1


@pytest.mark.parametrize("et", list(M.EVENT_TYPES))
def test_event_types(tmp_path, monkeypatch, et):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e = eng.record_event("layer", et, "ref", T0, T0, commit=True)
    assert e.event_type == et


def test_event_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_event("l", M.INSIGHT_GENERATED, "I1", T0, T0, commit=True)
    eng.record_event("l", M.INSIGHT_GENERATED, "I1", T0, T0, commit=True)
    assert len(ledger.read_events()) == 1


def test_event_links_to_layer_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_layer("research_kg", "1.0", "kg_", [], True, T0, commit=True)
    eng.record_event("research_kg", M.INSIGHT_GENERATED, "I1", T0, T0, commit=True)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    ea = arts[M.artifact_id(M.ART_EVENT, M.event_id("research_kg", M.INSIGHT_GENERATED, "I1"))]
    assert ea["parent_artifact"] == M.artifact_id(M.ART_LAYER, M.layer_id("research_kg"))


# ── Lineage ──
def test_add_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    ln = eng.add_lineage("DS1", M.NODE_DATASET, M.PRODUCES, "FT1", M.NODE_FEATURE, T0,
                         commit=True)
    assert ln.edge_type == M.PRODUCES


@pytest.mark.parametrize("edge", list(M.EDGE_TYPES))
def test_lineage_edge_types(tmp_path, monkeypatch, edge):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    ln = eng.add_lineage("A", M.NODE_DATASET, edge, "B", M.NODE_INSIGHT, T0, commit=True)
    assert ln.edge_type == edge


def test_lineage_invalid_node(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    with pytest.raises(InvalidWorkflowGraph):
        eng.add_lineage("A", "NONSENSE", M.PRODUCES, "B", M.NODE_FEATURE, T0, commit=True)


def test_lineage_cycle_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.add_lineage("A", M.NODE_DATASET, M.PRODUCES, "B", M.NODE_FEATURE, T0, commit=True)
    eng.add_lineage("B", M.NODE_FEATURE, M.USES, "C", M.NODE_SIGNAL, T0, commit=True)
    with pytest.raises(InvalidWorkflowGraph):
        eng.add_lineage("C", M.NODE_SIGNAL, M.IMPROVES, "A", M.NODE_DATASET, T0, commit=True)


def test_trace_research_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.add_lineage("DS1", M.NODE_DATASET, M.PRODUCES, "FT1", M.NODE_FEATURE, T0, commit=True)
    eng.add_lineage("FT1", M.NODE_FEATURE, M.USES, "SG1", M.NODE_SIGNAL, T0, commit=True)
    eng.add_lineage("SG1", M.NODE_SIGNAL, M.USES, "ST1", M.NODE_STRATEGY, T0, commit=True)
    anc = eng.trace_research_lineage("ST1")
    assert "DS1" in anc and "FT1" in anc and "SG1" in anc


def test_lineage_cycle_free(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.add_lineage("A", M.NODE_DATASET, M.PRODUCES, "B", M.NODE_FEATURE, T0, commit=True)
    assert eng.lineage_cycle() == []


def test_lineage_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.add_lineage("A", M.NODE_DATASET, M.PRODUCES, "B", M.NODE_FEATURE, T0, commit=True)
    eng.add_lineage("A", M.NODE_DATASET, M.PRODUCES, "B", M.NODE_FEATURE, T0, commit=True)
    assert len(ledger.read_lineage()) == 1


# ── Dependency analysis ──
def test_analyze_dependencies(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    deps = eng.analyze_dependencies([("research_planning", "research_memory", "DEPENDS_ON"),
                                     ("research_memory", "causal_intelligence", "DEPENDS_ON")],
                                    T0, commit=True)
    assert len(deps) == 2 and len(ledger.read_dependencies()) == 2


def test_dependency_cycle_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.analyze_dependencies([("A", "B"), ("B", "A")], T0, commit=True)
    assert eng.dependency_cycle() != []


def test_dependency_acyclic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.analyze_dependencies([("A", "B"), ("B", "C")], T0, commit=True)
    assert eng.dependency_cycle() == []


def test_dependency_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.analyze_dependencies([("A", "B")], T0, commit=True)
    eng.analyze_dependencies([("A", "B")], T0, commit=True)
    assert len(ledger.read_dependencies()) == 1


# ── Snapshot ──
def test_build_ecosystem_snapshot(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_known_layers(T0, commit=True)
    _wf(eng)
    eng.record_event("l", M.DATASET_REGISTERED, "DS1", T0, T0, commit=True)
    s = eng.build_ecosystem_snapshot("snap1", "2026Q3", _HEALTHY, T1, commit=True)
    assert s.workflow_count == 1 and s.event_count == 1 and s.status == CREATED
    assert s.health_score > 0 and s.ecosystem_hash.startswith("sha256:")


def test_snapshot_verify(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = eng.build_ecosystem_snapshot("s", "e", _HEALTHY, T0, commit=True)
    eng.verify_snapshot(s.snapshot_id, T1, commit=True)
    assert eng.snapshot_state(s.snapshot_id) == VERIFIED


def test_snapshot_verify_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownSnapshot):
        _eng().verify_snapshot("GHOST", T1, commit=True)


def test_snapshot_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.build_ecosystem_snapshot("s", "e", _HEALTHY, T0, commit=True)
    eng.build_ecosystem_snapshot("s", "e", _HEALTHY, T0, commit=True)
    assert len(ledger.distinct_snapshots()) == 1


def test_snapshot_deterministic_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_layer("l1", "1.0", "l_", [], True, T0, commit=True)
    s1 = eng.build_ecosystem_snapshot("a", "1", _HEALTHY, T0, commit=True)
    s2 = eng.build_ecosystem_snapshot("b", "2", _HEALTHY, T0, commit=True)
    assert s1.ecosystem_hash == s2.ecosystem_hash  # 동일 생태계 상태


def test_snapshot_transition_table():
    assert M.can_transition_snapshot("", CREATED)
    assert M.can_transition_snapshot(CREATED, VERIFIED)
    assert M.can_transition_snapshot(VERIFIED, ARCHIVED)
    assert not M.can_transition_snapshot(CREATED, ARCHIVED)


def test_compare_snapshots(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s1 = eng.build_ecosystem_snapshot("a", "1", _HEALTHY, T0, commit=True)
    eng.register_layer("newlayer", "1.0", "n_", [], True, T0, commit=True)
    _wf(eng)
    s2 = eng.build_ecosystem_snapshot("b", "2", _HEALTHY, T1, commit=True)
    cmp = eng.compare_snapshots(s2.snapshot_id, s1.snapshot_id)
    assert cmp["workflow_delta"] == 1 and cmp["hash_changed"] is True


def test_compare_snapshots_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = eng.build_ecosystem_snapshot("a", "1", _HEALTHY, T0, commit=True)
    with pytest.raises(UnknownSnapshot):
        eng.compare_snapshots(s.snapshot_id, "GHOST")


def test_ecosystem_hash_helper():
    a = M.ecosystem_hash(["l1", "l2"], 3, 5)
    b = M.ecosystem_hash(["l2", "l1"], 3, 5)
    assert a == b


# ── Health framework ──
def test_health_score_full():
    m = {k: 1.0 for k in M.HEALTH_WEIGHTS}
    assert abs(M.health_score(m) - 1.0) < 1e-9


def test_health_weights_sum_one():
    assert abs(sum(M.HEALTH_WEIGHTS.values()) - 1.0) < 1e-9


def test_system_health_healthy():
    assert M.system_health(_HEALTHY) == HEALTHY


def test_system_health_degraded():
    assert M.system_health(_DEGRADED) == DEGRADED


def test_system_health_warning():
    m = {k: 0.5 for k in M.HEALTH_WEIGHTS}
    assert M.system_health(m) == WARNING


def test_generate_health_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_known_layers(T0, commit=True)
    h = eng.generate_health_report("GLOBAL", _HEALTHY, T1, commit=True)
    assert h.system_health == HEALTHY and h.active_layer_count == h.layer_count
    assert "STATUS ≠ APPROVAL" in h.disclaimer
    assert len(ledger.read_health_reports()) == 1


def test_health_report_auto_layer_availability(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_layer("l1", "1.0", "l_", [], True, T0, commit=True)
    eng.register_layer("l2", "1.0", "m_", [], False, T0, commit=True)  # not active
    h = eng.generate_health_report("GLOBAL", {"lineage_completeness": 0.5}, T1, commit=True)
    assert abs(h.metrics["layer_availability"] - 0.5) < 1e-6  # 1/2 active


def test_health_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_health_report("GLOBAL", _HEALTHY, T1, commit=True)
    eng.generate_health_report("GLOBAL", _HEALTHY, T1, commit=True)
    assert len(ledger.read_health_reports()) == 1


def test_health_informational_no_remediation(tmp_path, monkeypatch):
    """건강 리포트에 remediation/fix/action 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    h = eng.generate_health_report("GLOBAL", _HEALTHY, T1, commit=True)
    for banned in ("remediation", "fix", "action", "deploy"):
        assert banned not in h.to_dict()


def test_analyze(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().analyze(_HEALTHY)["system_health"] == HEALTHY


# ── Summary ──
def _full(eng):
    eng.register_known_layers(T0, commit=True)
    _wf(eng)
    eng.record_event("research_data", M.DATASET_REGISTERED, "DS1", T0, T0, commit=True)
    eng.record_event("research_governance", M.EXPERIMENT_COMPLETED, "EX1", T0, T0, commit=True)
    eng.add_lineage("DS1", M.NODE_DATASET, M.PRODUCES, "FT1", M.NODE_FEATURE, T0, commit=True)
    eng.analyze_dependencies([("research_planning", "research_memory")], T0, commit=True)
    s = eng.build_ecosystem_snapshot("snap", "2026Q3", _HEALTHY, T1, commit=True)
    eng.verify_snapshot(s.snapshot_id, T1, commit=True)
    eng.generate_health_report("GLOBAL", _HEALTHY, T1, commit=True)
    return s


def test_summary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.summary(T2)
    assert rep.layer_count == len(ledger.SOURCE_LEDGERS) and rep.workflow_count == 1
    assert rep.event_count == 2 and rep.snapshot_count == 1 and rep.dependency_count == 1
    assert rep.lineage_count == 1 and rep.health_report_count == 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.summary(T2).to_dict() == eng.summary(T2).to_dict()


def test_summary_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rep = _eng().summary(T0)
    assert rep.layer_count == 0 and rep.snapshot_count == 0


def test_summary_event_type_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.summary(T2)
    assert rep.event_type_distribution.get(M.DATASET_REGISTERED) == 1


# ── verify ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_os.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_full_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_os.verify import verify_chain
    eng = _eng()
    _full(eng)
    res = verify_chain()
    assert res["ok"] is True
    assert res["lineage"]["ok"] and res["dependency"]["ok"] and res["workflow"]["ok"] \
        and res["artifact"]["ok"]


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_os.verify import verify_chain
    eng = _eng()
    _layer(eng)
    recs = ledger.read_layer_events()
    recs[0]["name"] = "TAMPERED"
    with open(sp("ros_layers.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_chain_break(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_os.verify import verify_ledger
    eng = _eng()
    eng.register_layer("a", "1.0", "a_", [], False, T0, commit=True)
    eng.register_layer("b", "1.0", "b_", [], False, T0, commit=True)
    recs = ledger.read_layer_events()
    recs[1]["previous_hash"] = "GENESIS"
    with open(sp("ros_layers.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_ledger(ledger.LAYERS)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_os.verify import verify_ledger
    eng = _eng()
    _layer(eng)
    recs = ledger.read_layer_events()
    dup = dict(recs[0])
    dup["previous_hash"] = recs[0]["record_hash"]
    with open(sp("ros_layers.jsonl"), "a") as f:
        f.write(json.dumps(dup) + "\n")
    assert verify_ledger(ledger.LAYERS)["ok"] is False


def test_verify_lineage_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_os.verify import lineage_validation
    for frm, to in (("A", "B"), ("B", "A")):
        rec = {"lineage_id": M.lineage_id(frm, M.PRODUCES, to), "from_node": frm,
               "from_type": M.NODE_DATASET, "edge_type": M.PRODUCES, "to_node": to,
               "to_type": M.NODE_FEATURE, "created_at": T0, "previous_hash": "GENESIS"}
        rec["record_hash"] = M.content_hash(rec)
        ledger.append_lineage(rec)
    assert any("lineage_cycle" in i for i in lineage_validation()["issues"])


def test_verify_lineage_invalid_node(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_os.verify import lineage_validation
    rec = {"lineage_id": "RLN:x", "from_node": "A", "from_type": "BADTYPE",
           "edge_type": M.PRODUCES, "to_node": "B", "to_type": M.NODE_FEATURE, "created_at": T0,
           "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("ros_lineage.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    assert any("invalid_node" in i for i in lineage_validation()["issues"])


def test_verify_dependency_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_os.verify import dependency_validation
    eng = _eng()
    eng.analyze_dependencies([("A", "B"), ("B", "A")], T0, commit=True)
    assert any("dependency_cycle" in i for i in dependency_validation()["issues"])


def test_verify_artifact_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_os.verify import artifact_validation
    a1 = {"artifact_id": "A1", "artifact_type": "X", "ref_id": "r", "parent_artifact": "A2",
          "created_at": T0, "previous_hash": "GENESIS"}
    a1["record_hash"] = M.content_hash(a1)
    a2 = {"artifact_id": "A2", "artifact_type": "X", "ref_id": "r", "parent_artifact": "A1",
          "created_at": T0, "previous_hash": a1["record_hash"]}
    a2["record_hash"] = M.content_hash(a2)
    with open(sp("ros_artifacts.jsonl"), "w") as f:
        f.write(json.dumps(a1) + "\n")
        f.write(json.dumps(a2) + "\n")
    assert any("artifact_cycle" in i for i in artifact_validation()["issues"])


def test_detect_cycle_helper():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) == ["a", "b", "a"]
    assert M.detect_cycle([("a", "b")]) == []


# ── replay ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_os.verify import replay
    eng = _eng()
    _full(eng)
    assert replay(eng, T2)["deterministic"] is True


def test_content_hash_excludes_chain_fields():
    a = {"x": 1, "previous_hash": "A", "record_hash": "B", "report_hash": "C"}
    b = {"x": 1, "previous_hash": "Z", "record_hash": "Z", "report_hash": "Z"}
    assert M.content_hash(a) == M.content_hash(b)


# ── CLI ──
def test_cli_layer_and_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_os.__main__ import main
    rc = main(["layer", "--name", "research_kg", "--prefix", "kg_", "--activate", "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["layer"]["name"] == "research_kg"
    main(["summary"])
    assert json.loads(capsys.readouterr().out)["layer_count"] == 1


def test_cli_full_workflow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_os.__main__ import main
    main(["layer", "--name", "research_data", "--prefix", "d_", "--activate", "--commit"])
    capsys.readouterr()
    main(["workflow", "--name", "journey", "--commit"])
    capsys.readouterr()
    main(["event", "--layer", "research_data", "--event-type", "DATASET_REGISTERED",
          "--reference-id", "DS1", "--commit"])
    capsys.readouterr()
    main(["lineage", "--from-node", "DS1", "--from-type", "DATASET", "--edge-type", "PRODUCES",
          "--to-node", "FT1", "--to-type", "FEATURE", "--commit"])
    lin = json.loads(capsys.readouterr().out)
    assert lin["cycle"] == []
    main(["snapshot", "--name", "snap", "--metrics-json", json.dumps({"layer_availability": 0.9,
          "lineage_completeness": 0.9, "data_traceability": 0.9, "validation_coverage": 0.9,
          "research_reproducibility": 0.9}), "--commit"])
    capsys.readouterr()
    main(["health", "--metrics-json", json.dumps({"layer_availability": 0.9,
          "lineage_completeness": 0.9, "data_traceability": 0.9, "validation_coverage": 0.9,
          "research_reproducibility": 0.9}), "--commit"])
    h = json.loads(capsys.readouterr().out)["health"]
    assert h["system_health"] == HEALTHY
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_os.__main__ import main
    main(["layer", "--name", "l", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.research_os.engine as eng_mod
    import jarvis.research_os.models as mdl_mod
    import jarvis.research_os.ledger as led_mod
    import jarvis.research_os.verify as ver_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "live_execution", _j + "broker", _j + "order",
                 _j + "portfolio.", _j + "risk_governor", _j + "permission",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "approve_strategy(", "modify_model(", "activate_live("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_keyword_methods():
    import jarvis.research_os.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def execute", "def trade", "def allocate", "def deploy", "def approve_strategy",
               "def modify_model", "def activate_live"):
        assert kw not in src


def test_no_execution_authority_api():
    api = set(dir(ResearchOSEngine))
    for banned in ("execute", "trade", "allocate", "deploy", "approve_strategy", "modify_model",
                   "activate_live", "select_strategy", "assign_agent", "place_order"):
        assert banned not in api


def test_no_automatic_workflow_creation():
    """자동 워크플로 생성/실험 트리거/전략 선택/agent 배정 메서드가 없어야 한다."""
    eng = ResearchOSEngine()
    for banned in ("auto_create_workflow", "trigger_experiment", "select_strategy",
                   "assign_agent", "start_experiment"):
        assert not hasattr(eng, banned)


def test_orchestration_not_execution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = _layer(eng, activate=True)
    assert eng.layer_state(l.layer_id) == ACTIVE
    assert not hasattr(eng, "run_layer")
    assert not hasattr(eng, "execute_workflow")


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
        m = importlib.import_module(f"jarvis.research_os.{mod_name}")
        for attr in dir(m):
            low = attr.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledgers_namespaced_ros_prefix():
    for filename, _ in ledger.ALL_LEDGERS:
        assert filename.startswith("ros_")


def test_no_collision_with_existing_prefixes():
    ours = {fn for fn, _ in ledger.ALL_LEDGERS}
    known = {"rp_opportunities.jsonl", "rm_memories.jsonl", "rv_validations.jsonl",
             "rg_strategies.jsonl", "kg_entities.jsonl", "sim_scenarios.jsonl",
             "ci_variables.jsonl", "mi_patterns.jsonl", "si_workflows.jsonl",
             "ob_snapshots.jsonl"}
    assert ours.isdisjoint(known)
    assert all(fn.startswith("ros_") for fn in ours)


def test_source_ledgers_read_only_not_owned():
    owned = {fn for fn, _ in ledger.ALL_LEDGERS}
    for layer, spec in ledger.SOURCE_LEDGERS.items():
        assert spec[0] not in owned


def test_source_ledgers_cover_all_prior_layers():
    """SOURCE_LEDGERS 가 주요 상위 레이어를 포함해야 한다(관찰 범위)."""
    layers = set(ledger.SOURCE_LEDGERS)
    for expected in ("research_kg", "decision_intelligence", "simulation_environment",
                     "causal_intelligence", "meta_intelligence",
                     "self_improvement_intelligence", "research_memory", "research_planning"):
        assert expected in layers


def test_existing_source_ledgers_untouched(tmp_path, monkeypatch):
    """상위 원장을 시드한 뒤 전체 오케스트레이션을 돌려도 원본 SHA256 불변."""
    sp = _iso(tmp_path, monkeypatch)
    seeds = {"kg_entities.jsonl": [{"entity_id": "KGE:1"}],
             "rg_strategies.jsonl": [{"strategy_id": "ST1"}],
             "sim_scenarios.jsonl": [{"event_id": "E1", "scenario_id": "SSC:1"}],
             "rp_opportunities.jsonl": [{"event_id": "E1", "opportunity_id": "RPO:1"}]}
    hashes = {}
    for fn, rows in seeds.items():
        with open(sp(fn), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        hashes[fn] = hashlib.sha256(open(sp(fn), "rb").read()).hexdigest()
    eng = _eng()
    assert ledger.source_count("research_kg") == 1
    _full(eng)
    for fn, h in hashes.items():
        assert hashlib.sha256(open(sp(fn), "rb").read()).hexdigest() == h


def test_engine_only_appends_ros_files(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    created = [f for f in os.listdir(tmp_path) if f.endswith(".jsonl")]
    assert created and all(f.startswith("ros_") for f in created)


def test_node_and_edge_types_defined():
    assert "DATASET" in M.NODE_TYPES and "INSIGHT" in M.NODE_TYPES and "PLAN" in M.NODE_TYPES
    assert set(M.EDGE_TYPES) == {"PRODUCES", "USES", "VALIDATES", "EXPLAINS", "IMPROVES",
                                 "PLANS"}


# ── 추가 ID prefix / 세부 ──
def test_workflow_id_prefix():
    assert M.workflow_id("n").startswith("ROW:")


def test_event_id_prefix():
    assert M.event_id("l", "e", "r").startswith("REV:")


def test_snapshot_id_prefix():
    assert M.snapshot_id("n", "e").startswith("RSN:")


def test_dependency_id_prefix():
    assert M.dependency_id("a", "b").startswith("ROD:")


def test_health_report_id_prefix():
    assert M.health_report_id("s").startswith("RHR:")


def test_lineage_id_prefix():
    assert M.lineage_id("a", M.PRODUCES, "b").startswith("RLN:")


def test_artifact_id_prefix():
    assert M.artifact_id(M.ART_LAYER, "x").startswith("ROA:")


def test_snapshot_captures_layers(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_layer("l1", "1.0", "a_", [], True, T0, commit=True)
    eng.register_layer("l2", "1.0", "b_", [], True, T0, commit=True)
    s = eng.build_ecosystem_snapshot("s", "e", _HEALTHY, T0, commit=True)
    assert len(s.layers) == 2


def test_source_count_helper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("kg_entities.jsonl"), "w") as f:
        f.write(json.dumps({"entity_id": "K1"}) + "\n")
        f.write(json.dumps({"entity_id": "K2"}) + "\n")
    assert ledger.source_count("research_kg") == 2
    assert ledger.source_count("NOPE") == 0


# ── 추가 세부 커버리지 ──
def test_layer_event_id_prefix():
    assert M.layer_event_id("l", "", M.REGISTERED).startswith("RLE:")


def test_workflow_event_id_prefix():
    assert M.workflow_event_id("w", "", M.CREATED).startswith("RWE:")


def test_snapshot_event_id_prefix():
    assert M.snapshot_event_id("s", "", M.CREATED).startswith("RSE:")


def test_layer_capabilities_stored(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = eng.register_layer("l", "1.0", "l_", ["read", "trace"], False, T0, commit=True)
    assert l.capabilities == ["read", "trace"]


def test_workflow_created_from_stored(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    w = eng.register_workflow("w", [{"id": "a", "type": M.NODE_DATASET}], [],
                              ["research_memory"], T0, commit=True)
    assert w.created_from == ["research_memory"]


def test_event_timestamp_preserved(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e = eng.record_event("l", M.DATASET_REGISTERED, "R", "2026-01-01T00:00:00Z", T0, commit=True)
    assert e.timestamp == "2026-01-01T00:00:00Z"


def test_snapshot_layers_sorted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_layer("zeta", "1.0", "z_", [], True, T0, commit=True)
    eng.register_layer("alpha", "1.0", "a_", [], True, T0, commit=True)
    s = eng.build_ecosystem_snapshot("s", "e", _HEALTHY, T0, commit=True)
    assert s.layers == sorted(s.layers)


def test_health_layer_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_layer("l1", "1.0", "a_", [], True, T0, commit=True)
    eng.register_layer("l2", "1.0", "b_", [], False, T0, commit=True)
    h = eng.generate_health_report("GLOBAL", _HEALTHY, T1, commit=True)
    assert h.layer_count == 2 and h.active_layer_count == 1


def test_compare_snapshots_health_delta(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s1 = eng.build_ecosystem_snapshot("a", "1", _DEGRADED, T0, commit=True)
    eng.register_layer("x", "1.0", "x_", [], True, T0, commit=True)
    s2 = eng.build_ecosystem_snapshot("b", "2", _HEALTHY, T1, commit=True)
    cmp = eng.compare_snapshots(s2.snapshot_id, s1.snapshot_id)
    assert cmp["health_delta"] > 0 and cmp["layer_delta"] == 1


def test_snapshot_artifact_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = eng.build_ecosystem_snapshot("s", "e", _HEALTHY, T0, commit=True)
    assert any(a["artifact_type"] == M.ART_SNAPSHOT and a["ref_id"] == s.snapshot_id
               for a in ledger.read_artifacts())


def test_dependency_relation_stored(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    deps = eng.analyze_dependencies([("A", "B", "BUILDS_ON")], T0, commit=True)
    assert deps[0].relation == "BUILDS_ON"


def test_full_workflow_artifact_lineage_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_os.verify import artifact_validation
    eng = _eng()
    _full(eng)
    res = artifact_validation()
    assert res["ok"] is True and not res["issues"]


def test_workflow_validation_clean(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_os.verify import workflow_validation
    eng = _eng()
    _wf(eng)
    assert workflow_validation()["ok"] is True


def test_register_known_layers_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_known_layers(T0, commit=True)
    eng.register_known_layers(T0, commit=True)
    assert len(ledger.distinct_layers()) == len(ledger.SOURCE_LEDGERS)
