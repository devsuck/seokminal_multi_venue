"""P10.23 Research Governance Orchestration 테스트. **전 거버넌스 계층 관찰·집계 전용.**

레이어 레지스트리(불변·생명주기 REGISTERED→CONNECTED→MONITORED→ARCHIVED)·계층 상태 수집(불변)·의존 지도
(자기참조·순환)·시스템 스냅샷(이벤트 소싱 CREATED→GENERATED→VERIFIED·결정적)·교차계층 충돌(범주·불변)·건강
요약·오케스트레이션 리포트(결정적)·verify(체인/변조/중복/전이/의존/계보)·replay·상위 READ ONLY 보호·CLI·
보안(금지import·실행/거래/배포/승인 없음·상위 원장 무변경·삭제 API 없음·불변·ORCHESTRATION≠EXECUTION·
append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.governance_orchestration import ledger
from jarvis.governance_orchestration import models as M
from jarvis.governance_orchestration.engine import GovernanceOrchestrationEngine
from jarvis.governance_orchestration.models import (
    ARCHIVED,
    CONNECTED,
    CREATED,
    GENERATED,
    MONITORED,
    REGISTERED,
    VERIFIED,
    IllegalTransition,
    ImmutableLayerError,
    ImmutableStatusError,
    InvalidConflictCategory,
    InvalidDependencyGraph,
    UnknownLayer,
    UnknownSnapshot,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

_HI = {"layer_availability": 0.9, "monitoring_coverage": 0.85, "dependency_integrity": 0.9,
       "conflict_freedom": 0.9, "status_freshness": 0.8}
_LO = {"layer_availability": 0.1, "monitoring_coverage": 0.2, "dependency_integrity": 0.1,
       "conflict_freedom": 0.2, "status_freshness": 0.1}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.governance_orchestration.ledger.state_path", sp)
    return sp


def _eng():
    return GovernanceOrchestrationEngine()


def _layer(eng, name="research_compliance", ltype="governance", prefix="rc_", commit=True):
    return eng.register_layer(name, ltype, prefix, T0, commit=commit)


def _full(eng):
    """layer(x2)→status→dependency→snapshot→conflict→health→report end-to-end."""
    la = _layer(eng, name="research_compliance", prefix="rc_")
    lb = _layer(eng, name="governance_memory", prefix="gm_")
    eng.ingest_layer_status("research_compliance", "HEALTHY", {"x": 1}, "E1", T0, commit=True)
    eng.build_dependency_map([("governance_memory", "research_compliance", "DEPENDS_ON")], T0,
                             commit=True)
    eng.create_system_snapshot("sys1", "E1", _HI, T0, commit=True)
    eng.detect_conflicts([("research_compliance", "governance_memory", M.CF_VERSION_MISMATCH,
                           "MEDIUM", "v1 vs v2", [])], T0, commit=True)
    eng.generate_health_report("GLOBAL", _HI, "E1", T1, commit=True)
    return la, lb


# ── Layer Registry ──
def test_layer_register(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    l = _layer(_eng())
    assert l.layer_id.startswith("GOL:")
    assert l.to_state == REGISTERED
    assert l.source_prefix == "rc_"


def test_layer_persisted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _layer(_eng())
    assert len(ledger.distinct_layers()) == 1


def test_layer_not_committed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _layer(_eng(), commit=False)
    assert ledger.read_layer_events() == []


def test_layer_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    l = _layer(_eng())
    assert l.layer_id == M.layer_id("research_compliance")


def test_layer_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _layer(eng)
    b = _layer(eng)
    assert a.layer_id == b.layer_id
    assert len(ledger.distinct_layers()) == 1


def test_layer_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _layer(eng, prefix="rc_")
    with pytest.raises(ImmutableLayerError):
        _layer(eng, prefix="xx_")


def test_layer_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = _layer(eng)
    eng.transition_layer(l.layer_id, CONNECTED, T1, commit=True)
    eng.transition_layer(l.layer_id, MONITORED, T2, commit=True)
    assert eng.layer_state(l.layer_id) == MONITORED


def test_layer_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = _layer(eng)
    with pytest.raises(IllegalTransition):
        eng.transition_layer(l.layer_id, MONITORED, T1, commit=True)  # skips CONNECTED


def test_layer_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownLayer):
        _eng().transition_layer("GOL:nope", CONNECTED, T1, commit=True)


def test_layer_archived_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = _layer(eng)
    eng.transition_layer(l.layer_id, ARCHIVED, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_layer(l.layer_id, CONNECTED, T2, commit=True)


def test_layer_can_transition_table():
    assert M.can_transition_layer("", REGISTERED)
    assert M.can_transition_layer(REGISTERED, CONNECTED)
    assert M.can_transition_layer(CONNECTED, MONITORED)
    assert not M.can_transition_layer(REGISTERED, MONITORED)
    assert not M.can_transition_layer(MONITORED, REGISTERED)


def test_register_known_layers(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    n = eng.register_known_layers(T0, commit=True)
    assert n == len(ledger.SOURCE_LEDGERS)
    assert len(ledger.distinct_layers()) == n


def test_layer_artifact_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    l = _layer(_eng())
    assert ledger.artifact_exists(M.artifact_id(M.ART_LAYER, l.layer_id))


# ── Layer Status ──
def test_status_ingest(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().ingest_layer_status("rc", "HEALTHY", {"m": 1}, "E1", T0, commit=True)
    assert s.status_id.startswith("GOT:")
    assert s.status == "HEALTHY"


def test_status_promotes_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = _layer(eng, name="research_compliance")
    eng.ingest_layer_status("research_compliance", "HEALTHY", {}, "E1", T0, commit=True)
    assert eng.layer_state(l.layer_id) == MONITORED


def test_status_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.ingest_layer_status("rc", "HEALTHY", {"m": 1}, "E1", T0, commit=True)
    with pytest.raises(ImmutableStatusError):
        eng.ingest_layer_status("rc", "DEGRADED", {"m": 2}, "E1", T0, commit=True)


def test_status_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.ingest_layer_status("rc", "HEALTHY", {"m": 1}, "E1", T0, commit=True)
    b = eng.ingest_layer_status("rc", "HEALTHY", {"m": 1}, "E1", T0, commit=True)
    assert a.status_id == b.status_id
    assert len(ledger.read_status()) == 1


def test_status_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().ingest_layer_status("rc", "HEALTHY", {}, "E1", T0, commit=True)
    assert s.status_id == M.status_id("rc", "E1")


def test_status_different_epochs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.ingest_layer_status("rc", "HEALTHY", {}, "E1", T0, commit=True)
    b = eng.ingest_layer_status("rc", "HEALTHY", {}, "E2", T1, commit=True)
    assert a.status_id != b.status_id


# ── Dependency Map ──
def test_dependency_build(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    d = _eng().build_dependency_map([("A", "B", "DEPENDS_ON")], T0, commit=True)
    assert d[0].dependency_id.startswith("GOD:")
    assert d[0].from_layer == "A"


def test_dependency_self_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidDependencyGraph):
        _eng().build_dependency_map([("A", "A", "DEPENDS_ON")], T0, commit=True)


def test_dependency_cycle_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.build_dependency_map([("A", "B")], T0, commit=True)
    with pytest.raises(InvalidDependencyGraph):
        eng.build_dependency_map([("B", "A")], T0, commit=True)


def test_dependency_chain_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.build_dependency_map([("A", "B"), ("B", "C")], T0, commit=True)
    assert eng.dependency_cycle() == []
    assert len(ledger.read_dependencies()) == 2


def test_dependency_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    d = _eng().build_dependency_map([("A", "B")], T0, commit=True)
    assert d[0].dependency_id == M.dependency_id("A", "B")


def test_dependency_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.build_dependency_map([("A", "B")], T0, commit=True)
    eng.build_dependency_map([("A", "B")], T0, commit=True)
    assert len(ledger.read_dependencies()) == 1


def test_dependency_graph_correctness(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.build_dependency_map([("A", "B"), ("A", "C"), ("B", "D")], T0, commit=True)
    assert len(ledger.read_dependencies()) == 3
    assert eng.dependency_cycle() == []


# ── System Snapshot ──
def test_snapshot_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _layer(eng)
    s = eng.create_system_snapshot("sys1", "E1", _HI, T0, commit=True)
    assert s.snapshot_id.startswith("GOS:")
    assert s.to_state == CREATED
    assert s.layer_count == 1


def test_snapshot_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = eng.create_system_snapshot("sys1", "E1", _HI, T0, commit=True)
    eng.advance_snapshot(s.snapshot_id, T1, commit=True)
    assert eng.snapshot_state(s.snapshot_id) == GENERATED
    eng.advance_snapshot(s.snapshot_id, T2, commit=True)
    assert eng.snapshot_state(s.snapshot_id) == VERIFIED


def test_snapshot_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = eng.create_system_snapshot("sys1", "E1", _HI, T0, commit=True)
    from jarvis.governance_orchestration.models import GENERATED as G
    with pytest.raises(IllegalTransition):
        eng._emit_snapshot_event(eng._snapshot_meta(s.snapshot_id), CREATED, VERIFIED, T1,
                                 commit=True)  # skips GENERATED


def test_snapshot_unknown_advance(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownSnapshot):
        _eng().advance_snapshot("GOS:nope", T1, commit=True)


def test_snapshot_deterministic_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _layer(eng)
    a = eng.create_system_snapshot("sysX", "E9", _HI, T0, commit=False)
    b = eng.create_system_snapshot("sysX", "E9", _HI, T0, commit=False)
    assert a.system_hash == b.system_hash


def test_snapshot_duplicate_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_system_snapshot("sys1", "E1", _HI, T0, commit=True)
    eng.create_system_snapshot("sys1", "E1", _HI, T0, commit=True)
    assert len(ledger.distinct_snapshots()) == 1


def test_snapshot_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().create_system_snapshot("sys1", "E1", {}, T0, commit=True)
    assert s.snapshot_id == M.snapshot_id("sys1", "E1")


# ── Conflicts ──
def test_conflict_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    c = _eng().detect_conflicts([("A", "B", M.CF_VERSION_MISMATCH, "HIGH", "d", [])], T0,
                                commit=True)
    assert c[0].conflict_id.startswith("GOC:")
    assert c[0].category == M.CF_VERSION_MISMATCH


def test_conflict_invalid_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidConflictCategory):
        _eng().detect_conflicts([("A", "B", "not_a_cat")], T0, commit=True)


def test_conflict_all_categories(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, cat in enumerate(M.CONFLICT_CATEGORIES):
        eng.detect_conflicts([(f"A{i}", f"B{i}", cat, "LOW", "", [])], T0, commit=True)
    assert len(ledger.read_conflicts()) == len(M.CONFLICT_CATEGORIES)


def test_conflict_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.detect_conflicts([("A", "B", M.CF_STATE_INCONSISTENCY, "LOW", "", [])], T0, commit=True)
    eng.detect_conflicts([("A", "B", M.CF_STATE_INCONSISTENCY, "LOW", "", [])], T0, commit=True)
    assert len(ledger.read_conflicts()) == 1


def test_conflict_auto_dependency_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    # build a cycle via direct ledger injection (bypass guard), then detect
    from jarvis.governance_orchestration.models import content_hash, dependency_id
    for (fr, to) in (("A", "B"), ("B", "A")):
        did = dependency_id(fr, to)
        head = ledger.dependencies_head()
        rec = {"dependency_id": did, "from_layer": fr, "to_layer": to, "relation": "DEPENDS_ON",
               "created_at": T0, "input_hash": "", "record_hash": "",
               "previous_hash": head["record_hash"] if head else "GENESIS"}
        rec["record_hash"] = content_hash(rec)
        ledger.append_dependency(rec)
    c = eng.detect_conflicts([], T0, commit=True)
    assert any(x.category == M.CF_DEPENDENCY_CYCLE for x in c)


def test_conflict_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    c = _eng().detect_conflicts([("A", "B", M.CF_VERSION_MISMATCH, "LOW", "", [])], T0,
                                commit=True)
    assert c[0].conflict_id == M.conflict_id("A", "B", M.CF_VERSION_MISMATCH)


# ── Health / score ──
def test_health_score_high():
    assert M.health_score(_HI) > 0.7


def test_health_score_low():
    assert M.health_score(_LO) < 0.4


def test_health_weights_sum_one():
    assert abs(sum(M.HEALTH_WEIGHTS.values()) - 1.0) < 1e-9


def test_system_health_labels():
    assert M.system_health(_HI) == "HEALTHY"
    assert M.system_health(_LO) == "DEGRADED"
    assert M.system_health({"layer_availability": 1.0, "monitoring_coverage": 1.0}) == "WARNING"


def test_analyze(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().analyze(_HI)
    assert res["system_health"] == "HEALTHY"
    assert res["health_score"] > 0.7


def test_severity_weight():
    assert M.severity_weight("CRITICAL") == 1.0
    assert M.severity_weight("???") == 0.0


def test_generate_health_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    h = eng.generate_health_report("GLOBAL", _HI, "E2", T2, commit=True)
    assert h.health_id.startswith("GOH:")
    assert h.layer_count >= 2
    assert h.system_health == "HEALTHY"
    # also writes an orchestration report
    assert len(ledger.read_reports()) >= 1


def test_health_monitored_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _layer(eng, name="research_compliance")
    eng.ingest_layer_status("research_compliance", "HEALTHY", {}, "E1", T0, commit=True)
    h = eng.generate_health_report("GLOBAL", {}, "E1", T1, commit=True)
    assert h.monitored_layer_count == 1


def test_health_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    h = _eng().generate_health_report("GLOBAL", _HI, "E1", T0, commit=True)
    assert "ORCHESTRATION ≠ EXECUTION" in h.disclaimer


def test_health_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_health_report("GLOBAL", _HI, "E1", T0, commit=True)
    eng.generate_health_report("GLOBAL", _HI, "E1", T0, commit=True)
    assert len(ledger.read_health()) == 1


# ── Report ──
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert r.report_id.startswith("GOR:")
    assert r.layer_count >= 2
    assert r.conflict_count >= 1


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    a = eng.generate_report("GLOBAL", _HI, T2, commit=False)
    b = eng.generate_report("GLOBAL", _HI, T2, commit=False)
    assert a.to_dict() == b.to_dict()


def test_report_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert REGISTERED in r.layer_state_distribution or MONITORED in r.layer_state_distribution
    assert M.CF_VERSION_MISMATCH in r.conflict_category_distribution


def test_report_no_trading_verbs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    d = r.to_dict()
    d.pop("disclaimer")
    blob = json.dumps(d, ensure_ascii=False).lower()
    for verb in ("buy", "sell", "place_order", "deploy", "allocate_capital"):
        assert verb not in blob


# ── verify / integrity ──
def test_verify_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.verify_integrity()["ok"] is True


def test_trace_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = _layer(eng, name="research_compliance")
    eng.ingest_layer_status("research_compliance", "HEALTHY", {}, "E1", T0, commit=True)
    sid = M.status_id("research_compliance", "E1")
    anc = eng.trace_lineage(M.artifact_id(M.ART_STATUS, sid))
    assert M.artifact_id(M.ART_LAYER, l.layer_id) in anc


def test_verify_chain_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.governance_orchestration.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] >= 1


def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_orchestration.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _layer(eng)
    p = sp("go_layers.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["source_prefix"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.governance_orchestration.verify import verify_ledger
    assert verify_ledger(ledger.LAYERS)["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.ingest_layer_status("a", "HEALTHY", {}, "E1", T0, commit=True)
    eng.ingest_layer_status("b", "HEALTHY", {}, "E1", T0, commit=True)
    p = sp("go_status.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.governance_orchestration.verify import verify_ledger
    assert verify_ledger(ledger.STATUS)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _layer(eng)
    p = sp("go_layers.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows.append(dict(rows[0]))
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.governance_orchestration.verify import verify_ledger
    assert verify_ledger(ledger.LAYERS)["ok"] is False


def test_verify_layer_transitions_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = _layer(eng, name="research_compliance")
    eng.ingest_layer_status("research_compliance", "HEALTHY", {}, "E1", T0, commit=True)
    from jarvis.governance_orchestration.verify import layer_transition_validation
    assert layer_transition_validation()["ok"] is True


def test_verify_detects_bad_layer_transition(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _layer(eng)
    p = sp("go_layers.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["to_state"] = "MONITORED"  # illegal from GENESIS
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.governance_orchestration.verify import layer_transition_validation
    assert layer_transition_validation()["ok"] is False


def test_verify_snapshot_transitions_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = eng.create_system_snapshot("sys1", "E1", _HI, T0, commit=True)
    eng.advance_snapshot(s.snapshot_id, T1, commit=True)
    from jarvis.governance_orchestration.verify import snapshot_transition_validation
    assert snapshot_transition_validation()["ok"] is True


def test_verify_dependency_validation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.build_dependency_map([("A", "B"), ("B", "C")], T0, commit=True)
    from jarvis.governance_orchestration.verify import dependency_validation
    assert dependency_validation()["ok"] is True


def test_verify_full_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.governance_orchestration.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["layer_transitions"]["ok"] is True
    assert res["snapshot_transitions"]["ok"] is True
    assert res["dependency"]["ok"] is True
    assert res["lineage"]["ok"] is True


def test_verify_lineage_cycle_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _layer(eng)
    from jarvis.governance_orchestration.models import content_hash
    h = ledger.artifacts_head()["record_hash"]
    a1 = {"artifact_id": "GOA:c1", "artifact_type": "LAYER", "ref_id": "x1",
          "parent_artifact": "GOA:c2", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": h}
    a1["record_hash"] = content_hash(a1)
    ledger.append_artifact(a1)
    a2 = {"artifact_id": "GOA:c2", "artifact_type": "LAYER", "ref_id": "x2",
          "parent_artifact": "GOA:c1", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": a1["record_hash"]}
    a2["record_hash"] = content_hash(a2)
    ledger.append_artifact(a2)
    res = eng.verify_integrity()
    assert res["ok"] is False
    assert any("cycle" in i for i in res["issues"])


# ── replay / summary (Research OS Status) ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.governance_orchestration.verify import replay
    assert replay(eng, T0)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert s.layer_count >= 2
    assert s.status_count >= 1
    assert s.dependency_count >= 1
    assert s.snapshot_count >= 1
    assert s.conflict_count >= 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.summary(T0).to_dict() == eng.summary(T0).to_dict()


def test_summary_layer_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert sum(s.layer_state_distribution.values()) == s.layer_count


# ── 상위 READ ONLY ──
def test_list_source_objects_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_objects("research_governance") == []


def test_list_source_objects_reads(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("rg_strategies.jsonl"), "w") as f:
        f.write(json.dumps({"strategy_id": "ST1"}) + "\n")
        f.write(json.dumps({"strategy_id": "ST2"}) + "\n")
    out = _eng().list_source_objects("research_governance")
    assert out == ["research_governance:ST1", "research_governance:ST2"]


def test_source_read_only_no_write(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    src = sp("rg_strategies.jsonl")
    with open(src, "w") as f:
        f.write(json.dumps({"strategy_id": "ST1"}) + "\n")
    before = open(src).read()
    eng = _eng()
    _full(eng)
    eng.list_source_objects("research_governance")
    assert open(src).read() == before


def test_unknown_source_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_objects("nonexistent") == []


def test_source_count(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("rg_strategies.jsonl"), "w") as f:
        f.write(json.dumps({"strategy_id": "ST1"}) + "\n")
    assert ledger.source_count("research_governance") == 1
    assert ledger.source_count("nope") == 0


def test_all_upstream_layers_covered():
    for layer in ("data_governance", "research_compliance", "governance_evolution",
                  "research_orchestration", "governance_memory"):
        assert layer in ledger.SOURCE_LEDGERS


# ── CLI ──
def test_cli_layer(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_orchestration.__main__ import main
    rc = main(["layer", "--name", "rc", "--source-prefix", "rc_", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["layer"]["layer_id"].startswith("GOL:")


def test_cli_status(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_orchestration.__main__ import main
    rc = main(["status", "--layer-reference", "rc", "--status", "HEALTHY", "--epoch", "E1",
               "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["status"]["status_id"].startswith("GOT:")


def test_cli_dependency(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_orchestration.__main__ import main
    rc = main(["dependency", "--from-layer", "A", "--to-layer", "B", "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dependency"]["dependency_id"].startswith("GOD:")
    assert out["cycle"] == []


def test_cli_snapshot(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_orchestration.__main__ import main
    rc = main(["snapshot", "--name", "sys1", "--epoch", "E1", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["snapshot"]["snapshot_id"].startswith("GOS:")


def test_cli_conflict(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_orchestration.__main__ import main
    rc = main(["conflict", "--layer-a", "A", "--layer-b", "B", "--category", "version_mismatch",
               "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["conflicts"][0]["conflict_id"].startswith("GOC:")


def test_cli_health(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_orchestration.__main__ import main
    rc = main(["health", "--metrics-json", json.dumps(_HI), "--epoch", "E1", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["health"]["health_id"].startswith("GOH:")


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_orchestration.__main__ import main
    rc = main(["report", "--metrics-json", json.dumps(_HI), "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["report"]["report_id"].startswith("GOR:")


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_orchestration.__main__ import main
    main(["layer", "--name", "rc", "--commit"])
    capsys.readouterr()
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_orchestration.__main__ import main
    main(["layer", "--name", "rc", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_orchestration.__main__ import main
    rc = main(["summary"])
    assert rc == 0
    assert "layer_count" in json.loads(capsys.readouterr().out)


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.governance_orchestration.engine as eng_mod
    import jarvis.governance_orchestration.models as mdl_mod
    import jarvis.governance_orchestration.ledger as led_mod
    import jarvis.governance_orchestration.verify as ver_mod
    import jarvis.governance_orchestration.__main__ as cli_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod, cli_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "execution", _j + "broker", _j + "order",
                 _j + "portfolio_execution", _j + "capital_allocation", _j + "live_trading",
                 _j + "permission", _j + "risk_controller",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "promote_strategy(", "activate_live("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_keyword_methods():
    import jarvis.governance_orchestration.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def execute", "def trade", "def deploy", "def allocate", "def place_order",
               "def promote", "def activate_live"):
        assert kw not in src


def test_no_execution_authority_api():
    api = set(dir(GovernanceOrchestrationEngine))
    for banned in ("execute", "trade", "deploy", "allocate", "place_order", "promote",
                   "activate_live", "allocate_capital"):
        assert banned not in api


def test_orchestration_not_execution(tmp_path, monkeypatch):
    """레이어 이벤트에 execute/deploy/order/capital 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    l = _layer(_eng())
    d = l.to_dict()
    for banned in ("execute", "deploy", "order", "capital", "position"):
        assert banned not in d


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
        m = importlib.import_module(f"jarvis.governance_orchestration.{mod_name}")
        for name in dir(m):
            low = name.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledger_prefix_go(tmp_path, monkeypatch):
    for fn, _idf in ledger.ALL_LEDGERS:
        assert fn.startswith("go_")


def test_no_or_prefix_ownership():
    """P10.23 은 or_ 원장(P10.17 소유)을 소유하지 않는다."""
    for fn, _idf in ledger.ALL_LEDGERS:
        assert not fn.startswith("or_")


def test_all_ledgers_distinct():
    names = [fn for fn, _ in ledger.ALL_LEDGERS]
    assert len(names) == len(set(names)) == 8


def test_engine_no_upstream_layer_import():
    import jarvis.governance_orchestration.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for up in ("import jarvis.research_orchestration", "import jarvis.governance_evolution",
               "import jarvis.governance_memory", "import jarvis.research_os"):
        assert up not in src


# ── 추가 커버리지 ──
def test_id_prefixes_distinct():
    prefixes = {
        M.layer_id("a")[:4],
        M.layer_event_id("a", "", REGISTERED)[:4],
        M.status_id("a", "b")[:4],
        M.snapshot_id("a", "b")[:4],
        M.snapshot_event_id("a", "", CREATED)[:4],
        M.health_id("a", "b")[:4],
        M.dependency_id("a", "b")[:4],
        M.conflict_id("a", "b", "c")[:4],
        M.report_id("a")[:4],
        M.artifact_id("a", "b")[:4],
    }
    assert len(prefixes) == 10


def test_content_hash_excludes_chain_fields():
    r1 = {"a": 1, "previous_hash": "x", "record_hash": "y"}
    r2 = {"a": 1, "previous_hash": "z", "record_hash": "w"}
    assert M.content_hash(r1) == M.content_hash(r2)


def test_input_digest_order_matters():
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_system_hash_sorts_layers():
    assert M.system_hash(["b", "a"], 0.5, 0) == M.system_hash(["a", "b"], 0.5, 0)


def test_detect_cycle_finds():
    assert M.detect_cycle([("a", "b"), ("b", "a")])


def test_detect_cycle_none():
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []


def test_layer_states_count():
    assert len(M.LAYER_STATES) == 4


def test_snapshot_states_count():
    assert len(M.SNAPSHOT_STATES) == 3


def test_conflict_categories_count():
    assert len(M.CONFLICT_CATEGORIES) == 5


def test_node_types_count():
    assert len(M.NODE_TYPES) == 6


def test_no_commit_no_files(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _layer(eng, commit=False)
    for fn, _ in ledger.ALL_LEDGERS:
        assert ledger.read_jsonl(fn) == []


def test_layer_to_dict_roundtrip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    l = _layer(_eng())
    d = l.to_dict()
    assert d["layer_id"] == l.layer_id
    assert set(("name", "layer_type", "source_prefix")).issubset(d)


def test_report_metrics_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    assert r.metrics == _HI


def test_multiple_scopes_distinct_reports(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_report("A", _HI, T0, commit=True)
    eng.generate_report("B", _HI, T0, commit=True)
    assert len(ledger.read_reports()) == 2


def test_layer_input_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    l = _layer(_eng())
    assert l.input_hash == M.input_digest(l.layer_id, "", REGISTERED)


def test_status_metrics_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().ingest_layer_status("rc", "HEALTHY", {"a": 1}, "E1", T0, commit=True)
    assert s.metrics == {"a": 1}


def test_snapshot_system_hash_field(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _layer(eng)
    s = eng.create_system_snapshot("sys1", "E1", _HI, T0, commit=True)
    assert s.system_hash.startswith("sha256:")


def test_source_ledgers_not_go_prefixed():
    for layer, (fn, idf) in ledger.SOURCE_LEDGERS.items():
        assert not fn.startswith("go_")
        assert isinstance(idf, str)


def test_source_ledgers_include_or_read_only():
    """P10.17 research_orchestration(or_)는 READ ONLY 소스로만 참조."""
    spec = ledger.SOURCE_LEDGERS.get("research_orchestration")
    assert spec is not None and spec[0].startswith("or_")


def test_engine_reused(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _layer(eng, name="l1", prefix="a_")
    b = _layer(eng, name="l2", prefix="b_")
    assert a.layer_id != b.layer_id
    assert len(ledger.distinct_layers()) == 2


def test_disclaimer_full_phrases(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    h = _eng().generate_health_report("GLOBAL", _HI, "E1", T0, commit=True)
    for phrase in ("ORCHESTRATION ≠ EXECUTION", "MONITORING ≠ CONTROL", "STATUS ≠ APPROVAL",
                   "AGGREGATION ≠ ACTION"):
        assert phrase in h.disclaimer


def test_health_score_partial_metrics():
    s = M.health_score({"layer_availability": 1.0, "monitoring_coverage": 1.0})
    assert abs(s - (0.25 + 0.20)) < 1e-9


def test_snapshot_reflects_conflicts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.detect_conflicts([("A", "B", M.CF_VERSION_MISMATCH, "LOW", "", [])], T0, commit=True)
    s = eng.create_system_snapshot("sys1", "E1", {}, T0, commit=True)
    assert s.conflict_count == 1
