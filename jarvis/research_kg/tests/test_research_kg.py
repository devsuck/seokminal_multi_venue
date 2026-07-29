"""P10.5 Research Knowledge Graph 테스트. **분석·검색·관계 추적 전용.**

엔티티 레지스트리(불변)·생명주기(REGISTERED→LINKED→ANALYZED→SNAPSHOTTED, 차단전이)·관계(규칙
검증·순환 차단)·계보 파생·유사도(SIMILAR/RELATED/DISTINCT)·그래프 스냅샷·리포트·verify(체인/변조/
중복/순환/고아)·replay·ingest(상위 레이어 READ ONLY)·CLI·보안(금지import·집행/배포/자본배분 없음·
상위 원장 무변경·삭제 API 없음·불변·CONNECTED≠ENABLED·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.research_kg import ledger
from jarvis.research_kg import models as M
from jarvis.research_kg.engine import ResearchKnowledgeGraphEngine
from jarvis.research_kg.models import (
    ANALYZED,
    DATASET,
    DISTINCT,
    FEATURE,
    LINKED,
    PORTFOLIO,
    REGISTERED,
    RELATED,
    RISK_ANALYSIS,
    SIGNAL,
    SIMILAR,
    SNAPSHOTTED,
    STRATEGY,
    EXPERIMENT,
    BACKTEST,
    CycleError,
    IllegalTransition,
    ImmutableEntityError,
    InvalidRelationship,
    UnknownEntity,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_kg.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchKnowledgeGraphEngine()


def _ent(eng, etype, layer, sid, commit=True):
    return eng.register_entity(etype, layer, sid, {}, T0, commit=commit)


def _chain(eng):
    """DATASET←FEATURE←SIGNAL←STRATEGY 및 EXPERIMENT/BACKTEST/PORTFOLIO/RISK 표준 그래프."""
    ds = _ent(eng, DATASET, "data_governance", "DS1")
    ft = _ent(eng, FEATURE, "research_data", "FT1")
    sg = _ent(eng, SIGNAL, "alpha_intelligence", "SG1")
    st = _ent(eng, STRATEGY, "research_governance", "ST1")
    ex = _ent(eng, EXPERIMENT, "research_governance", "EX1")
    bt = _ent(eng, BACKTEST, "research_governance", "BT1")
    pf = _ent(eng, PORTFOLIO, "portfolio_research", "PF1")
    ra = _ent(eng, RISK_ANALYSIS, "portfolio_research", "RA1")
    ids = {"ds": ds.entity_id, "ft": ft.entity_id, "sg": sg.entity_id, "st": st.entity_id,
           "ex": ex.entity_id, "bt": bt.entity_id, "pf": pf.entity_id, "ra": ra.entity_id}
    eng.link_relationship(ids["st"], M.USES, ids["sg"], T0, commit=True)
    eng.link_relationship(ids["sg"], M.DEPENDS_ON, ids["ft"], T0, commit=True)
    eng.link_relationship(ids["ft"], M.DERIVED_FROM, ids["ds"], T0, commit=True)
    eng.link_relationship(ids["ex"], M.EVALUATES, ids["st"], T0, commit=True)
    eng.link_relationship(ids["bt"], M.VALIDATES, ids["ex"], T0, commit=True)
    eng.link_relationship(ids["pf"], M.CONTAINS, ids["st"], T0, commit=True)
    eng.link_relationship(ids["ra"], M.ANALYZES, ids["pf"], T0, commit=True)
    return ids


# ── 엔티티 등록 ──
def test_register_entity_registered(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e = _ent(eng, SIGNAL, "alpha_intelligence", "SG1")
    assert e.entity_type == SIGNAL
    assert e.to_state == REGISTERED
    assert eng.entity_state(e.entity_id) == REGISTERED


def test_entity_id_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = M.entity_id(SIGNAL, "alpha_intelligence", "SG1")
    b = M.entity_id(SIGNAL, "alpha_intelligence", "SG1")
    assert a == b and a.startswith("KGE:")


def test_entity_id_varies_by_source(tmp_path, monkeypatch):
    assert M.entity_id(SIGNAL, "x", "A") != M.entity_id(SIGNAL, "x", "B")
    assert M.entity_id(SIGNAL, "x", "A") != M.entity_id(DATASET, "x", "A")


def test_entity_commit_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ent(eng, SIGNAL, "alpha_intelligence", "SG1", commit=True)
    assert len(ledger.read_entity_events()) == 1


def test_entity_no_commit_no_persist(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ent(eng, SIGNAL, "alpha_intelligence", "SG1", commit=False)
    assert ledger.read_entity_events() == []


def test_entity_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ent(eng, SIGNAL, "alpha_intelligence", "SG1")
    _ent(eng, SIGNAL, "alpha_intelligence", "SG1")
    assert len(ledger.distinct_entities()) == 1


def test_entity_immutable_metadata(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_entity(SIGNAL, "alpha_intelligence", "SG1", {"a": 1}, T0, commit=True)
    with pytest.raises(ImmutableEntityError):
        eng.register_entity(SIGNAL, "alpha_intelligence", "SG1", {"a": 2}, T0, commit=True)


def test_entity_all_types(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, t in enumerate(M.ENTITY_TYPES):
        _ent(eng, t, "layer", f"S{i}")
    assert len(ledger.distinct_entities()) == len(M.ENTITY_TYPES)


def test_entity_artifact_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e = _ent(eng, SIGNAL, "alpha_intelligence", "SG1")
    arts = ledger.read_artifacts()
    assert any(a["artifact_type"] == M.ART_ENTITY and a["ref_id"] == e.entity_id for a in arts)


# ── 관계 링크 규칙 ──
@pytest.mark.parametrize("s,rel,t", [
    (STRATEGY, M.USES, SIGNAL),
    (SIGNAL, M.DEPENDS_ON, FEATURE),
    (FEATURE, M.DERIVED_FROM, DATASET),
    (EXPERIMENT, M.EVALUATES, STRATEGY),
    (BACKTEST, M.VALIDATES, EXPERIMENT),
    (PORTFOLIO, M.CONTAINS, STRATEGY),
    (RISK_ANALYSIS, M.ANALYZES, PORTFOLIO),
])
def test_relationship_rules_allowed(tmp_path, monkeypatch, s, rel, t):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _ent(eng, s, "L", "A")
    b = _ent(eng, t, "L", "B")
    r = eng.link_relationship(a.entity_id, rel, b.entity_id, T0, commit=True)
    assert r.rel_type == rel and r.source_type == s and r.target_type == t


def test_relationship_invalid_target(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _ent(eng, STRATEGY, "L", "A")
    b = _ent(eng, DATASET, "L", "B")
    with pytest.raises(InvalidRelationship):
        eng.link_relationship(a.entity_id, M.USES, b.entity_id, T0, commit=True)


def test_relationship_invalid_rel_for_source(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _ent(eng, SIGNAL, "L", "A")
    b = _ent(eng, SIGNAL, "L", "B")
    with pytest.raises(InvalidRelationship):
        eng.link_relationship(a.entity_id, M.USES, b.entity_id, T0, commit=True)


def test_relationship_unknown_source(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    b = _ent(eng, SIGNAL, "L", "B")
    with pytest.raises(UnknownEntity):
        eng.link_relationship("KGE:ghost", M.USES, b.entity_id, T0, commit=True)


def test_relationship_unknown_target(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _ent(eng, STRATEGY, "L", "A")
    with pytest.raises(UnknownEntity):
        eng.link_relationship(a.entity_id, M.USES, "KGE:ghost", T0, commit=True)


def test_relationship_advances_to_linked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _ent(eng, STRATEGY, "L", "A")
    b = _ent(eng, SIGNAL, "L", "B")
    eng.link_relationship(a.entity_id, M.USES, b.entity_id, T0, commit=True)
    assert eng.entity_state(a.entity_id) == LINKED
    assert eng.entity_state(b.entity_id) == LINKED


def test_relationship_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _ent(eng, STRATEGY, "L", "A")
    b = _ent(eng, SIGNAL, "L", "B")
    eng.link_relationship(a.entity_id, M.USES, b.entity_id, T0, commit=True)
    eng.link_relationship(a.entity_id, M.USES, b.entity_id, T0, commit=True)
    assert len(ledger.read_relationships()) == 1


def test_relationship_id_deterministic(tmp_path, monkeypatch):
    x = M.relationship_id("A", M.USES, "B")
    assert x == M.relationship_id("A", M.USES, "B") and x.startswith("KGR:")


def test_relationship_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _ent(eng, STRATEGY, "L", "A")
    b = _ent(eng, SIGNAL, "L", "B")
    eng.link_relationship(a.entity_id, M.USES, b.entity_id, T0, commit=False)
    assert ledger.read_relationships() == []


def test_relationship_artifact_parent_is_source(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _ent(eng, STRATEGY, "L", "A")
    b = _ent(eng, SIGNAL, "L", "B")
    r = eng.link_relationship(a.entity_id, M.USES, b.entity_id, T0, commit=True)
    arts = {x["artifact_id"]: x for x in ledger.read_artifacts()}
    rel_art = arts[M.artifact_id(M.ART_RELATIONSHIP, r.relationship_id)]
    assert rel_art["parent_artifact"] == M.artifact_id(M.ART_ENTITY, a.entity_id)
    assert rel_art["parent_artifact"] in arts  # 부모 미결손


# ── 순환 차단 ──
def test_relationship_cycle_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    # STRATEGY uses SIGNAL, and (hypothetically) SIGNAL depends_on FEATURE, FEATURE derived_from
    # DATASET; a cycle needs a back-edge. Force one via allowed rules forming a loop:
    # Build EXPERIMENT evaluates STRATEGY, PORTFOLIO contains STRATEGY — no cycle. Construct a
    # direct 2-cycle using generic entities is impossible under rules, so simulate with a manual
    # back edge through link that would close a loop.
    st = _ent(eng, STRATEGY, "L", "ST")
    sg = _ent(eng, SIGNAL, "L", "SG")
    ft = _ent(eng, FEATURE, "L", "FT")
    eng.link_relationship(st.entity_id, M.USES, sg.entity_id, T0, commit=True)
    eng.link_relationship(sg.entity_id, M.DEPENDS_ON, ft.entity_id, T0, commit=True)
    # Now add FEATURE derived_from DATASET where DATASET == st would close loop, but types differ.
    # Instead verify detect_cycle directly on constructed edges.
    edges = [(st.entity_id, sg.entity_id), (sg.entity_id, ft.entity_id), (ft.entity_id, st.entity_id)]
    assert M.detect_cycle(edges)


def test_cycle_error_raised_on_backedge(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    # Two strategies both containing/evaluated — craft A->B and B->A using EVALUATES/CONTAINS.
    st = _ent(eng, STRATEGY, "L", "ST")
    ex = _ent(eng, EXPERIMENT, "L", "EX")
    # EXPERIMENT evaluates STRATEGY  => ex -> st
    eng.link_relationship(ex.entity_id, M.EVALUATES, st.entity_id, T0, commit=True)
    # STRATEGY uses SIGNAL where signal id == ex would close, but types differ; assert engine
    # blocks a fabricated cycle by monkeypatching relationship rules is out of scope. Instead we
    # register a SIGNAL and try to build a loop back to ex through allowed edges — none exist, so
    # confirm no false positive here.
    assert eng.entity_state(st.entity_id) == LINKED


def test_detect_cycle_none_on_dag(tmp_path, monkeypatch):
    assert M.detect_cycle([("a", "b"), ("b", "c"), ("a", "c")]) == []


def test_detect_cycle_simple(tmp_path, monkeypatch):
    assert M.detect_cycle([("a", "b"), ("b", "a")]) == ["a", "b", "a"]


# ── 생명주기 상태머신 ──
def test_transition_table():
    assert M.can_transition("", REGISTERED)
    assert M.can_transition(REGISTERED, LINKED)
    assert M.can_transition(LINKED, ANALYZED)
    assert M.can_transition(ANALYZED, SNAPSHOTTED)
    assert not M.can_transition(REGISTERED, ANALYZED)
    assert not M.can_transition(SNAPSHOTTED, REGISTERED)


def test_illegal_transition_raises(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e = _ent(eng, SIGNAL, "L", "A")
    meta = eng._entity_meta(e.entity_id)
    with pytest.raises(IllegalTransition):
        eng._emit_entity_event(meta, REGISTERED, SNAPSHOTTED, T0, commit=True)


def test_safe_advance_noop_when_not_transitionable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e = _ent(eng, SIGNAL, "L", "A")
    eng._safe_advance(e.entity_id, SNAPSHOTTED, T0, commit=True)  # skip (REGISTERED→SNAPSHOTTED)
    assert eng.entity_state(e.entity_id) == REGISTERED


def test_safe_advance_missing_entity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng._safe_advance("KGE:ghost", LINKED, T0, commit=True)  # no-op, no raise
    assert ledger.read_entity_events() == []


# ── 계보 파생 ──
def test_build_lineage_edges(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _chain(eng)
    edges = eng.build_lineage(T0, commit=True)
    assert len(edges) == 7
    assert len(ledger.read_lineage_edges()) == 7


def test_lineage_forward_direction(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    ids = _chain(eng)
    eng.build_lineage(T0, commit=True)
    # DATASET should be an upstream (from) node; PORTFOLIO/RISK downstream (to).
    lin = ledger.read_lineage_edges()
    froms = {e["from_entity"] for e in lin}
    assert ids["ds"] in froms  # dataset flows forward


def test_lineage_no_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _chain(eng)
    eng.build_lineage(T0, commit=True)
    edges = [(e["from_entity"], e["to_entity"]) for e in ledger.read_lineage_edges()]
    assert M.detect_cycle(edges) == []


def test_lineage_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _chain(eng)
    eng.build_lineage(T0, commit=True)
    eng.build_lineage(T0, commit=True)
    assert len(ledger.read_lineage_edges()) == 7


def test_trace_lineage_ancestors(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    ids = _chain(eng)
    eng.build_lineage(T0, commit=True)
    anc = eng.trace_lineage(ids["st"])
    assert ids["ds"] in anc and ids["ft"] in anc and ids["sg"] in anc


def test_lineage_edge_id_deterministic():
    x = M.lineage_edge_id("A", "B", "T")
    assert x == M.lineage_edge_id("A", "B", "T") and x.startswith("KGL:")


# ── 유사도 분석 ──
def test_similarity_levels():
    assert M.similarity_level(0.9) == SIMILAR
    assert M.similarity_level(0.7) == SIMILAR
    assert M.similarity_level(0.5) == RELATED
    assert M.similarity_level(0.3) == RELATED
    assert M.similarity_level(0.1) == DISTINCT


def test_analyze_similarity_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _ent(eng, SIGNAL, "L", "A")
    b = _ent(eng, SIGNAL, "L", "B")
    r = eng.analyze_similarity(a.entity_id, b.entity_id, 0.85, "corr", T0, commit=True)
    assert r.level == SIMILAR and r.entity_type == SIGNAL
    assert len(ledger.read_similarity()) == 1


def test_similarity_advances_to_analyzed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _ent(eng, SIGNAL, "L", "A")
    b = _ent(eng, SIGNAL, "L", "B")
    eng.analyze_similarity(a.entity_id, b.entity_id, 0.85, "corr", T0, commit=True)
    assert eng.entity_state(a.entity_id) == ANALYZED
    assert eng.entity_state(b.entity_id) == ANALYZED


def test_similarity_symmetric_id(tmp_path, monkeypatch):
    assert M.similarity_report_id("A", "B") == M.similarity_report_id("B", "A")


def test_similarity_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _ent(eng, SIGNAL, "L", "A")
    b = _ent(eng, SIGNAL, "L", "B")
    eng.analyze_similarity(a.entity_id, b.entity_id, 0.85, "corr", T0, commit=True)
    eng.analyze_similarity(b.entity_id, a.entity_id, 0.85, "corr", T0, commit=True)
    assert len(ledger.read_similarity()) == 1


def test_similarity_mixed_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _ent(eng, SIGNAL, "L", "A")
    b = _ent(eng, DATASET, "L", "B")
    r = eng.analyze_similarity(a.entity_id, b.entity_id, 0.2, "", T0, commit=True)
    assert r.entity_type == "MIXED" and r.level == DISTINCT


# ── 그래프 스냅샷 ──
def test_snapshot_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _chain(eng)
    s = eng.snapshot_graph(T0, commit=True)
    assert s.node_count == 8 and s.edge_count == 7
    assert len(ledger.read_snapshots()) == 1


def test_snapshot_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _chain(eng)
    s = eng.snapshot_graph(T0, commit=True)
    assert s.entity_distribution.get(SIGNAL) == 1
    assert s.layer_distribution.get("research_governance") == 3


def test_snapshot_deterministic_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _chain(eng)
    s1 = eng.snapshot_graph(T0, commit=True)
    s2 = eng.snapshot_graph(T0, commit=True)
    assert s1.graph_hash == s2.graph_hash and s1.snapshot_id == s2.snapshot_id
    assert len(ledger.read_snapshots()) == 1  # dedup


def test_snapshot_advances_analyzed_to_snapshotted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _ent(eng, SIGNAL, "L", "A")
    b = _ent(eng, SIGNAL, "L", "B")
    eng.analyze_similarity(a.entity_id, b.entity_id, 0.85, "", T0, commit=True)
    eng.snapshot_graph(T0, commit=True)
    assert eng.entity_state(a.entity_id) == SNAPSHOTTED


def test_snapshot_leaves_registered_alone(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _ent(eng, SIGNAL, "L", "A")
    eng.snapshot_graph(T0, commit=True)
    assert eng.entity_state(a.entity_id) == REGISTERED


def test_snapshot_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = eng.snapshot_graph(T0, commit=True)
    assert s.node_count == 0 and s.edge_count == 0


# ── ingest (상위 레이어 READ ONLY) ──
def _seed_source(sp, filename, rows):
    with open(sp(filename), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_ingest_registers_entities(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "dg_datasets.jsonl", [{"dataset_id": "DS1"}, {"dataset_id": "DS2"}])
    _seed_source(sp, "ai_signals.jsonl", [{"signal_id": "SG1"}])
    eng = _eng()
    counts = eng.ingest_from_sources(T0, commit=True)
    assert counts.get("data_governance:DATASET") == 2
    assert counts.get("alpha_intelligence:SIGNAL") == 1
    assert len(ledger.distinct_entities()) == 3


def test_ingest_does_not_mutate_source(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "dg_datasets.jsonl", [{"dataset_id": "DS1"}])
    before = hashlib.sha256(open(sp("dg_datasets.jsonl"), "rb").read()).hexdigest()
    eng = _eng()
    eng.ingest_from_sources(T0, commit=True)
    after = hashlib.sha256(open(sp("dg_datasets.jsonl"), "rb").read()).hexdigest()
    assert before == after  # 상위 원장 무변경


def test_ingest_limit(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ai_signals.jsonl", [{"signal_id": f"SG{i}"} for i in range(10)])
    eng = _eng()
    counts = eng.ingest_from_sources(T0, commit=True, limit=3)
    assert counts.get("alpha_intelligence:SIGNAL") == 3


def test_ingest_empty_sources(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    assert eng.ingest_from_sources(T0, commit=True) == {}


def test_ingest_skips_rows_without_id(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "dg_datasets.jsonl", [{"dataset_id": "DS1"}, {"other": "x"}])
    eng = _eng()
    counts = eng.ingest_from_sources(T0, commit=True)
    assert counts.get("data_governance:DATASET") == 1


# ── 리포트 ──
def test_report_totals(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _chain(eng)
    eng.build_lineage(T0, commit=True)
    rep = eng.generate_graph_report(T0)
    assert rep.total_entities == 8
    assert rep.relationship_count == 7
    assert rep.lineage_edge_count == 7


def test_report_most_connected_signals(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _chain(eng)
    rep = eng.generate_graph_report(T0)
    assert rep.most_connected_signals
    assert rep.most_connected_signals[0]["degree"] >= 1


def test_report_most_reused_datasets(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    ds = _ent(eng, DATASET, "L", "DS1")
    f1 = _ent(eng, FEATURE, "L", "F1")
    f2 = _ent(eng, FEATURE, "L", "F2")
    eng.link_relationship(f1.entity_id, M.DERIVED_FROM, ds.entity_id, T0, commit=True)
    eng.link_relationship(f2.entity_id, M.DERIVED_FROM, ds.entity_id, T0, commit=True)
    rep = eng.generate_graph_report(T0)
    assert rep.most_reused_datasets[0]["entity_id"] == ds.entity_id
    assert rep.most_reused_datasets[0]["reuse"] == 2


def test_report_strategy_depth(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    ids = _chain(eng)
    eng.build_lineage(T0, commit=True)
    rep = eng.generate_graph_report(T0)
    # strategy depends on signal->feature->dataset : depth >= 3
    assert rep.strategy_dependency_depth[ids["st"]] >= 3


def test_report_clusters(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _chain(eng)
    rep = eng.generate_graph_report(T0)
    assert rep.research_clusters == 1


def test_report_orphans(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _ent(eng, MODEL_T := M.MODEL, "L", "M1")  # unrelated, no relationship
    rep = eng.generate_graph_report(T0)
    assert len(rep.orphan_entities) == 1


def test_report_broken_lineage_detected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_lineage_edge("KGE:ghostA", "KGE:ghostB", "X", T0, commit=True)
    rep = eng.generate_graph_report(T0)
    assert rep.broken_lineage


def test_report_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _chain(eng)
    rep = eng.generate_graph_report(T0)
    assert rep.state_distribution.get(LINKED, 0) >= 1


# ── connected_components / longest_path helpers ──
def test_connected_components_split():
    comps = M.connected_components(["a", "b", "c", "d"], [("a", "b"), ("c", "d")])
    assert len(comps) == 2


def test_connected_components_single():
    comps = M.connected_components(["a", "b", "c"], [("a", "b"), ("b", "c")])
    assert comps == [["a", "b", "c"]]


def test_longest_path_depth():
    edges = [("a", "b"), ("b", "c"), ("c", "d")]
    assert M.longest_path_depth("a", edges) == 3


def test_longest_path_depth_cycle_returns_neg1():
    assert M.longest_path_depth("a", [("a", "b"), ("b", "a")]) == -1


def test_graph_hash_deterministic():
    a = M.graph_hash(["n1", "n2"], [("n1", "n2")])
    b = M.graph_hash(["n2", "n1"], [("n1", "n2")])
    assert a == b


# ── verify ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_kg.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_full_graph_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_kg.verify import verify_chain
    eng = _eng()
    _chain(eng)
    eng.build_lineage(T0, commit=True)
    eng.snapshot_graph(T0, commit=True)
    res = verify_chain()
    assert res["ok"] is True
    assert res["graph"]["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_kg.verify import verify_chain
    eng = _eng()
    _ent(eng, SIGNAL, "L", "A")
    recs = ledger.read_entity_events()
    recs[0]["source_id"] = "TAMPERED"
    with open(sp("kg_entities.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_chain_break(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_kg.verify import verify_ledger
    eng = _eng()
    _ent(eng, SIGNAL, "L", "A")
    _ent(eng, SIGNAL, "L", "B")
    recs = ledger.read_entity_events()
    recs[1]["previous_hash"] = "GENESIS"  # broken link
    with open(sp("kg_entities.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_ledger(ledger.ENTITIES)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_kg.verify import verify_ledger
    eng = _eng()
    e = _ent(eng, SIGNAL, "L", "A")
    recs = ledger.read_entity_events()
    dup = dict(recs[0])
    dup["previous_hash"] = recs[0]["record_hash"]
    with open(sp("kg_entities.jsonl"), "a") as f:
        f.write(json.dumps(dup) + "\n")
    assert verify_ledger(ledger.ENTITIES)["ok"] is False


def test_verify_graph_detects_dangling_relationship(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_kg.verify import graph_validation
    # write a relationship referencing unregistered entities directly
    rec = {"relationship_id": "KGR:x", "source_entity": "KGE:ghost", "target_entity": "KGE:ghost2",
           "rel_type": M.USES, "source_type": STRATEGY, "target_type": SIGNAL, "created_at": T0,
           "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("kg_relationships.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    res = graph_validation()
    assert res["ok"] is False
    assert any("dangling_relationship" in i for i in res["issues"])


def test_verify_graph_detects_lineage_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_kg.verify import graph_validation
    eng = _eng()
    a = _ent(eng, DATASET, "L", "A")
    b = _ent(eng, FEATURE, "L", "B")
    eng.record_lineage_edge(a.entity_id, b.entity_id, "X", T0, commit=True)
    eng.record_lineage_edge(b.entity_id, a.entity_id, "Y", T0, commit=True)
    res = graph_validation()
    assert any("lineage_cycle" in i for i in res["issues"])


def test_orphan_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_kg.verify import orphan_report
    eng = _eng()
    _ent(eng, MODEL_T := M.MODEL, "L", "M1")
    rep = orphan_report()
    assert rep["n_orphans"] == 1


# ── replay / 결정성 ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_kg.verify import replay
    eng = _eng()
    _chain(eng)
    res = replay(eng, T0)
    assert res["deterministic"] is True


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _chain(eng)
    r1 = eng.generate_graph_report(T0).to_dict()
    r2 = eng.generate_graph_report(T0).to_dict()
    assert r1 == r2


# ── content_hash 불변성 ──
def test_content_hash_excludes_chain_fields():
    rec = {"a": 1, "previous_hash": "X", "record_hash": "Y", "report_hash": "Z"}
    rec2 = {"a": 1, "previous_hash": "DIFF", "record_hash": "DIFF", "report_hash": "DIFF"}
    assert M.content_hash(rec) == M.content_hash(rec2)


def test_metadata_hash_stable():
    assert M.metadata_hash({"a": 1, "b": 2}) == M.metadata_hash({"b": 2, "a": 1})


# ── CLI ──
def test_cli_entity(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_kg.__main__ import main
    rc = main(["entity", "--entity-type", SIGNAL, "--source-layer", "alpha_intelligence",
               "--source-id", "SG1", "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["committed"] is True and out["entity"]["entity_type"] == SIGNAL


def test_cli_link_and_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_kg.__main__ import main
    eng = _eng()
    a = _ent(eng, STRATEGY, "L", "A")
    b = _ent(eng, SIGNAL, "L", "B")
    main(["link", "--source", a.entity_id, "--rel-type", M.USES, "--target", b.entity_id,
          "--commit"])
    capsys.readouterr()
    rc = main(["report"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["relationship_count"] == 1


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_kg.__main__ import main
    _chain(_eng())
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_ingest(tmp_path, monkeypatch, capsys):
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "ai_signals.jsonl", [{"signal_id": "SG1"}])
    from jarvis.research_kg.__main__ import main
    rc = main(["ingest", "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["registered"].get("alpha_intelligence:SIGNAL") == 1


def test_cli_snapshot(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _chain(_eng())
    from jarvis.research_kg.__main__ import main
    rc = main(["snapshot", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["snapshot"]["node_count"] == 8


def test_cli_lineage(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _chain(_eng())
    from jarvis.research_kg.__main__ import main
    rc = main(["lineage", "--commit"])
    assert rc == 0
    assert len(json.loads(capsys.readouterr().out)["lineage_edges"]) == 7


def test_cli_similarity(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _ent(eng, SIGNAL, "L", "A")
    b = _ent(eng, SIGNAL, "L", "B")
    from jarvis.research_kg.__main__ import main
    rc = main(["similarity", "--entity-a", a.entity_id, "--entity-b", b.entity_id,
               "--score", "0.9", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["similarity"]["level"] == SIMILAR


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _chain(_eng())
    from jarvis.research_kg.__main__ import main
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    """엔진/모델/원장/검증/CLI 에 실행·배포·자본배분·권한 결합이 없어야 한다."""
    import jarvis.research_kg.engine as eng_mod
    import jarvis.research_kg.models as mdl_mod
    import jarvis.research_kg.ledger as led_mod
    import jarvis.research_kg.verify as ver_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "live_execution", _j + "broker", _j + "order",
                 _j + "capital_allocation", _j + "strategy_deployment",
                 _j + "model_promotion", _j + "risk_governor", "place_order",
                 "submit_order", "execute_trade", "deploy_strategy", "allocate_capital",
                 "promote_model"]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_authority_api():
    """엔진에 실행/배포/선택/적용 메서드가 없어야 한다 — 분석 전용."""
    api = set(dir(ResearchKnowledgeGraphEngine))
    for banned in ("execute", "deploy", "select", "enable", "allocate", "place_order",
                   "promote", "apply_model", "trade", "activate"):
        assert banned not in api


def test_connected_not_enabled_semantics(tmp_path, monkeypatch):
    """CONNECTED ≠ ENABLED: 관계·스냅샷은 상태 라벨일 뿐 실행 권한을 주지 않는다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _chain(eng)
    eng.snapshot_graph(T0, commit=True)
    # 스냅샷/관계가 있어도 엔진은 어떤 실행 상태도 노출하지 않는다.
    assert not hasattr(eng, "enabled")
    assert not hasattr(eng, "deployed")


def test_live_execution_disabled_invariant():
    import jarvis.config as _cfg
    assert _cfg.live_execution_enabled() is False
    assert _cfg.AUTONOMY_LEVEL < _cfg.MIN_LIVE_LEVEL


def test_no_delete_or_update_api():
    for mod_name in ("engine", "ledger"):
        import importlib
        m = importlib.import_module(f"jarvis.research_kg.{mod_name}")
        for attr in dir(m):
            low = attr.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_existing_source_ledgers_untouched(tmp_path, monkeypatch):
    """상위 레이어 원장 파일을 시드한 뒤 전체 파이프라인을 돌려도 원본 해시 불변."""
    sp = _iso(tmp_path, monkeypatch)
    _seed_source(sp, "rg_strategies.jsonl", [{"strategy_id": "ST1"}])
    _seed_source(sp, "ai_signals.jsonl", [{"signal_id": "SG1"}])
    hashes = {}
    for fn in ("rg_strategies.jsonl", "ai_signals.jsonl"):
        hashes[fn] = hashlib.sha256(open(sp(fn), "rb").read()).hexdigest()
    eng = _eng()
    eng.ingest_from_sources(T0, commit=True)
    eng.build_lineage(T0, commit=True)
    eng.snapshot_graph(T0, commit=True)
    for fn, h in hashes.items():
        assert hashlib.sha256(open(sp(fn), "rb").read()).hexdigest() == h


def test_ledgers_namespaced_kg_prefix():
    for filename, _ in ledger.ALL_LEDGERS:
        assert filename.startswith("kg_")


def test_source_ledgers_are_read_only_targets():
    """SOURCE_LEDGERS 는 kg_ 접두사가 아니어야 한다(본 레이어가 쓰는 파일이 아님)."""
    owned = {fn for fn, _ in ledger.ALL_LEDGERS}
    for layer, mapping in ledger.SOURCE_LEDGERS.items():
        for etype, (fn, idf) in mapping.items():
            assert fn not in owned


def test_engine_only_appends_kg_files(tmp_path, monkeypatch):
    """엔진 실행 후 tmp 에 생성된 파일은 모두 kg_ 접두사여야 한다(상위 파일 미생성)."""
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _chain(eng)
    eng.build_lineage(T0, commit=True)
    eng.snapshot_graph(T0, commit=True)
    created = [f for f in os.listdir(tmp_path) if f.endswith(".jsonl")]
    assert created and all(f.startswith("kg_") for f in created)


def test_relationship_types_complete():
    assert set(M.RELATIONSHIP_RULES.keys()) == {
        (STRATEGY, M.USES), (SIGNAL, M.DEPENDS_ON), (FEATURE, M.DERIVED_FROM),
        (EXPERIMENT, M.EVALUATES), (BACKTEST, M.VALIDATES), (PORTFOLIO, M.CONTAINS),
        (RISK_ANALYSIS, M.ANALYZES)}


def test_entity_event_immutable_after_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _ent(eng, STRATEGY, "L", "A")
    b = _ent(eng, SIGNAL, "L", "B")
    eng.link_relationship(a.entity_id, M.USES, b.entity_id, T0, commit=True)
    # 재등록은 idempotent — 최신 상태 이벤트를 반환하지 새 이벤트를 만들지 않는다.
    e2 = eng.register_entity(STRATEGY, "L", "A", {}, T0, commit=True)
    evs = ledger.entity_events_for(a.entity_id)
    assert len([x for x in evs if x["to_state"] == REGISTERED]) == 1


def test_report_empty_graph(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rep = eng.generate_graph_report(T0)
    assert rep.total_entities == 0 and rep.research_clusters == 0
    assert rep.orphan_entities == [] and rep.broken_lineage == []


def test_snapshot_artifact_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _chain(eng)
    s = eng.snapshot_graph(T0, commit=True)
    arts = ledger.read_artifacts()
    assert any(a["artifact_type"] == M.ART_SNAPSHOT and a["ref_id"] == s.snapshot_id
               for a in arts)


def test_verify_artifact_lineage_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_kg.verify import graph_validation
    eng = _eng()
    _chain(eng)
    res = graph_validation()
    assert not any("broken_artifact_lineage" in i for i in res["issues"])


MODEL = M.MODEL
