"""P11.12 Research Memory System 테스트. **장기 연구 기억 — 기억 시스템 전용.**

기억 생성(CREATED→INDEXED→CONNECTED→RETRIEVABLE→ARCHIVED)·불변 이력·9 기억 유형·맥락 보존·지식 엔트리·실험/실패/
성공 기억·연관 그래프(순환/dangling)·유사도 검색(결정적·설명가능·기록)·계보/관련/역사 비교·스냅샷 결정성·리포트
(is_binding=False)·verify(체인/변조/중복/생애주기/참조/연관순환/스냅샷 일관성)·replay·CLI·보안(금지import·실행/수정/
승인/배포 없음·삭제 API 없음·불변·재작성 없음·MEMORY≠EXECUTION·append-only·모델ID 미노출·rm_ 계층과 격리).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_memory_system import ledger
from jarvis.research_memory_system import models as M
from jarvis.research_memory_system.engine import ResearchMemorySystemEngine
from jarvis.research_memory_system.models import (
    M_ARCHIVED,
    M_CONNECTED,
    M_CREATED,
    M_INDEXED,
    M_RETRIEVABLE,
    MEMORY_TYPES,
    MODE_EXACT,
    MODE_HISTORICAL,
    MODE_LINEAGE,
    MODE_RELATED,
    MODE_SIMILARITY,
    SEARCH_MODES,
    CircularAssociationError,
    DanglingReferenceError,
    IllegalMemoryTransition,
    ImmutableContextError,
    ImmutableExperimentError,
    ImmutableFailureError,
    ImmutableMemoryError,
    ImmutablePatternError,
    InvalidMemoryType,
    InvalidSearchMode,
    MissingSourceError,
    UnknownMemoryError,
)
from jarvis.research_memory_system.verify import (
    association_integrity,
    duplicate_integrity,
    lifecycle_integrity,
    lineage_integrity,
    reference_integrity,
    replay,
    snapshot_consistency,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_memory_system.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchMemorySystemEngine()


def _mem(e, layer="research_agents", sid="A1", mtype="EXPERIMENT_RESULT",
         title="momentum backtest", context="sharpe ratio improved over baseline", now=T[0]):
    return e.register_memory(layer, sid, mtype, title, context, "", now, commit=True).memory_id


def _indexed(e, **kw):
    m = _mem(e, **kw)
    e.store_research_context(m, "setup", "walk forward validation window", T[1], commit=True)
    return m


# ══════════════ Phase 0 / 접두사 / 격리 ══════════════
def test_prefix_all_ledgers_rmem():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rmem_")


def test_twelve_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 12


def test_isolated_from_rm_layer():
    # rmem_ 는 rm_ 계층과 구별 (rm_ 로 시작하지만 rm_ 계층 파일명과 겹치지 않음)
    names = {f for f, _ in ledger.ALL_LEDGERS}
    assert "rm_memories.jsonl" not in names
    assert "rmem_memories.jsonl" in names


def test_source_ledgers_includes_p10_1():
    assert "research_data" in ledger.SOURCE_LEDGERS
    assert len(ledger.SOURCE_LEDGERS) == 19


def test_memory_types_nine():
    assert len(MEMORY_TYPES) == 9


def test_memory_states_five():
    assert len(M.MEMORY_STATES) == 5


def test_search_modes_five():
    assert len(SEARCH_MODES) == 5


# ══════════════ register_memory ══════════════
def test_register_memory_genesis_created(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e)
    assert m.startswith("MSM:")
    assert e.current_state(m) == M_CREATED


def test_register_memory_invalid_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(InvalidMemoryType):
        e.register_memory("research_agents", "A1", "NOPE", "t", "c", "", T[0], commit=True)


def test_register_memory_missing_source_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(MissingSourceError):
        e.register_memory("research_agents", "", "EXPERIMENT_RESULT", "t", "c", "", T[0],
                          commit=True)


def test_register_memory_creates_catalog(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e)
    cat = ledger.catalog_by_memory(m)
    assert cat is not None and cat["memory_id"] == m
    assert cat["registry_id"].startswith("MSR:")


def test_register_memory_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e)
    arts = [a for a in ledger.read_artifacts() if a["artifact_type"] == M.ART_MEMORY]
    assert any(a["ref_id"] == m for a in arts)


def test_register_memory_idempotent_same_context(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_memory("research_agents", "A1", "EXPERIMENT_RESULT", "t", "ctx", "", T[0],
                          commit=True)
    b = e.register_memory("research_agents", "A1", "EXPERIMENT_RESULT", "t", "ctx", "", T[1],
                          commit=True)
    assert a.memory_id == b.memory_id
    assert len(ledger.memory_events(a.memory_id)) == 1


def test_register_memory_immutable_rewrite_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_memory("research_agents", "A1", "EXPERIMENT_RESULT", "t", "ctx1", "", T[0],
                      commit=True)
    with pytest.raises(ImmutableMemoryError):
        e.register_memory("research_agents", "A1", "EXPERIMENT_RESULT", "t", "ctx2", "", T[1],
                          commit=True)


def test_new_info_creates_new_memory(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _mem(e, title="v1")
    b = _mem(e, title="v2", now=T[2])
    assert a != b
    assert len(ledger.memory_ids()) == 2


def test_register_memory_verify_ref_dangling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(DanglingReferenceError):
        e.register_memory("research_agents", "A1", "EXPERIMENT_RESULT", "t", "c", "ghost", T[0],
                          commit=True, verify_ref=True)


def test_memory_preserves_required_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = e.register_memory("research_agents", "A1", "EXPERIMENT_RESULT", "title", "original ctx",
                           "EV1", T[0], commit=True)
    d = ev.to_dict()
    for f in ("source_layer", "source_id", "occurred_at", "original_context", "evidence_ref"):
        assert f in d
    assert ev.source_layer == "research_agents"
    assert ev.evidence_ref == "EV1"


@pytest.mark.parametrize("mtype", list(MEMORY_TYPES))
def test_all_memory_types(tmp_path, monkeypatch, mtype):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = e.register_memory("research_agents", "A1", mtype, "t-" + mtype, "c", "", T[0], commit=True)
    assert ev.memory_type == mtype


# ══════════════ store_research_context ══════════════
def test_store_context_indexes_memory(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e)
    e.store_research_context(m, "setup", "data", T[1], commit=True)
    assert e.current_state(m) == M_INDEXED


def test_store_context_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e)
    e.store_research_context(m, "setup", "data1", T[1], commit=True)
    with pytest.raises(ImmutableContextError):
        e.store_research_context(m, "setup", "data2", T[2], commit=True)


def test_store_context_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e)
    e.store_research_context(m, "setup", "data", T[1], commit=True)
    e.store_research_context(m, "setup", "data", T[2], commit=True)
    assert len(ledger.memory_contexts(m)) == 1


def test_store_context_preserves_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e)
    c = e.store_research_context(m, "setup", "important data", T[1], commit=True)
    assert c.context_hash == M.context_digest("important data")


def test_store_context_unknown_memory(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownMemoryError):
        e.store_research_context("MSM:ghost", "k", "d", T[1], commit=True)


# ══════════════ knowledge entries ══════════════
def test_record_knowledge_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e)
    k = e.record_knowledge_entry(m, "reusable insight", ["momentum", "oos"], True, T[1],
                                 commit=True)
    assert k.knowledge_id.startswith("MSK:")
    assert k.tags == ["momentum", "oos"]


def test_record_knowledge_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e)
    e.record_knowledge_entry(m, "s", ["a"], True, T[1], commit=True)
    e.record_knowledge_entry(m, "s", ["a"], True, T[2], commit=True)
    assert len(ledger.read_knowledge()) == 1


# ══════════════ experiment memory ══════════════
def test_record_experiment_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e)
    x = e.record_experiment_memory(m, "EXP1", "sharpe 1.4", {"sharpe": 1.4}, now=T[1], commit=True)
    assert x.experiment_memory_id.startswith("MSX:")
    assert x.metrics == {"sharpe": 1.4}


def test_record_experiment_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e)
    e.record_experiment_memory(m, "EXP1", "o1", now=T[1], commit=True)
    with pytest.raises(ImmutableExperimentError):
        e.record_experiment_memory(m, "EXP1", "o2", now=T[2], commit=True)


def test_record_experiment_missing_source(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e)
    with pytest.raises(MissingSourceError):
        e.record_experiment_memory(m, "EXP1", "o", source_layer="experiment_manager",
                                   source_ref="", now=T[1], commit=True)


# ══════════════ failure memory ══════════════
def test_record_failure_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e, mtype="FAILED_APPROACH")
    f = e.record_failure_memory(m, "naive grid search", "overfit", 3, now=T[1], commit=True)
    assert f.failure_memory_id.startswith("MSF:")
    assert f.recurrence == 3


def test_record_failure_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e, mtype="FAILED_APPROACH")
    e.record_failure_memory(m, "approach", "r", 1, now=T[1], commit=True)
    with pytest.raises(ImmutableFailureError):
        e.record_failure_memory(m, "approach", "r", 5, now=T[2], commit=True)


def test_failure_recall(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e, mtype="FAILED_APPROACH", title="bad idea")
    e.record_failure_memory(m, "approach", "r", 1, now=T[1], commit=True)
    recalled = e.list_memories("FAILED_APPROACH")
    assert m in recalled
    assert len(ledger.read_failures()) == 1


# ══════════════ success pattern ══════════════
def test_record_success_pattern_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e, mtype="SUCCESS_PATTERN")
    p = e.record_success_pattern(m, "ensemble", "diverse signals", 0.8, T[1], commit=True)
    assert p.success_pattern_id.startswith("MSP:")
    assert p.confidence == 0.8


def test_record_success_pattern_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e, mtype="SUCCESS_PATTERN")
    e.record_success_pattern(m, "p", "c", 0.5, T[1], commit=True)
    with pytest.raises(ImmutablePatternError):
        e.record_success_pattern(m, "p", "c", 0.9, T[2], commit=True)


# ══════════════ link_related_memories ══════════════
def test_link_memories_connects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _indexed(e, title="a")
    b = _indexed(e, title="b")
    e.link_related_memories(a, b, "RELATED", "", T[3], commit=True)
    assert e.current_state(a) == M_CONNECTED
    assert e.current_state(b) == M_CONNECTED


def test_link_records_association(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _indexed(e, title="a")
    b = _indexed(e, title="b")
    assoc = e.link_related_memories(a, b, "SIMILAR", "", T[3], commit=True)
    assert assoc.association_id.startswith("MSA:")
    assert len(ledger.read_associations()) == 1


def test_link_self_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _indexed(e, title="a")
    with pytest.raises(CircularAssociationError):
        e.link_related_memories(a, a, "RELATED", "", T[3], commit=True)


def test_link_circular_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _indexed(e, title="a")
    b = _indexed(e, title="b")
    e.link_related_memories(a, b, "R", "", T[3], commit=True)
    with pytest.raises(CircularAssociationError):
        e.link_related_memories(b, a, "R", "", T[4], commit=True)


def test_link_unknown_memory(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _indexed(e, title="a")
    with pytest.raises(UnknownMemoryError):
        e.link_related_memories(a, "MSM:ghost", "R", "", T[3], commit=True)


def test_related_memories_graph(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _indexed(e, title="a")
    b = _indexed(e, title="b")
    c = _indexed(e, title="c")
    e.link_related_memories(a, b, "R", "", T[3], commit=True)
    e.link_related_memories(a, c, "R", "", T[4], commit=True)
    rel = e.related_memories(a)
    assert b in rel and c in rel


def test_lineage_lookup(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _indexed(e, title="a")
    b = _indexed(e, title="b")
    c = _indexed(e, title="c")
    e.link_related_memories(a, b, "R", "", T[3], commit=True)
    e.link_related_memories(b, c, "R", "", T[4], commit=True)
    # a->b->c 계보에서 a 의 조상은 b, c
    assert set(e.trace_memory_lineage(a)) == {b, c}


# ══════════════ lifecycle: retrievable / archive ══════════════
def test_mark_retrievable_from_indexed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _indexed(e)
    e.mark_retrievable(m, T[3], commit=True)
    assert e.current_state(m) == M_RETRIEVABLE


def test_mark_retrievable_from_connected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _indexed(e, title="a")
    b = _indexed(e, title="b")
    e.link_related_memories(a, b, "R", "", T[3], commit=True)
    e.mark_retrievable(a, T[4], commit=True)
    assert e.current_state(a) == M_RETRIEVABLE


def test_archive_from_retrievable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _indexed(e)
    e.mark_retrievable(m, T[3], commit=True)
    e.archive_memory(m, T[4], commit=True)
    assert e.current_state(m) == M_ARCHIVED


def test_archive_illegal_from_created(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e)
    with pytest.raises(IllegalMemoryTransition):
        e.archive_memory(m, T[4], commit=True)


def test_full_lifecycle_sequence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _mem(e, title="a")
    b = _indexed(e, title="b")
    e.store_research_context(a, "k", "d", T[2], commit=True)
    e.link_related_memories(a, b, "R", "", T[3], commit=True)
    e.mark_retrievable(a, T[4], commit=True)
    e.archive_memory(a, T[5], commit=True)
    states = [r["to_state"] for r in ledger.memory_events(a)]
    assert states == [M_CREATED, M_INDEXED, M_CONNECTED, M_RETRIEVABLE, M_ARCHIVED]


# ══════════════ search_memory (deterministic, explainable, recorded) ══════════════
def test_search_similarity_finds_match(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e, title="momentum sharpe backtest", context="oos validation")
    s = e.search_memory("momentum backtest sharpe", MODE_SIMILARITY, now=T[5], commit=True)
    assert len(s.result_ids) == 1
    assert s.result_ids[0] in s.scores


def test_search_similarity_explainable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e, title="momentum sharpe", context="")
    s = e.search_memory("momentum reversal", MODE_SIMILARITY, now=T[5], commit=True)
    assert "shared:momentum" in s.explanation[m]


def test_search_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e, title="alpha")
    e.search_memory("alpha", MODE_SIMILARITY, now=T[5], commit=True)
    assert len(ledger.read_searches()) == 1


def test_search_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e, title="momentum sharpe")
    a = e.search_memory("momentum", MODE_SIMILARITY, now=T[5], commit=False)
    b = e.search_memory("momentum", MODE_SIMILARITY, now=T[5], commit=False)
    assert a.result_ids == b.result_ids
    assert a.scores == b.scores


def test_search_exact_by_title(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e, title="unique title")
    s = e.search_memory("unique title", MODE_EXACT, now=T[5], commit=True)
    assert s.result_ids == [m]
    assert s.scores[m] == 1.0


def test_search_exact_by_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e, title="t")
    s = e.search_memory(m, MODE_EXACT, now=T[5], commit=True)
    assert s.result_ids == [m]


def test_search_lineage_mode(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _indexed(e, title="a")
    b = _indexed(e, title="b")
    e.link_related_memories(a, b, "R", "", T[3], commit=True)
    s = e.search_memory("", MODE_LINEAGE, target=a, now=T[5], commit=True)
    assert b in s.result_ids


def test_search_related_mode(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _indexed(e, title="a")
    b = _indexed(e, title="b")
    e.link_related_memories(a, b, "R", "", T[3], commit=True)
    s = e.search_memory("", MODE_RELATED, target=a, now=T[5], commit=True)
    assert b in s.result_ids


def test_search_historical_mode(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = _mem(e, mtype="METHODOLOGY", title="m1")
    m2 = _mem(e, mtype="METHODOLOGY", title="m2", now=T[2])
    s = e.search_memory("METHODOLOGY", MODE_HISTORICAL, now=T[5], commit=True)
    assert m1 in s.result_ids and m2 in s.result_ids


def test_search_invalid_mode(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(InvalidSearchMode):
        e.search_memory("q", "FUZZY", now=T[5], commit=True)


def test_search_ranked_by_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e, title="momentum sharpe backtest oos", context="")  # more overlap
    _mem(e, title="momentum only", context="", now=T[2])
    s = e.search_memory("momentum sharpe backtest oos", MODE_SIMILARITY, now=T[5], commit=True)
    # 첫 결과가 최고 점수
    assert s.scores[s.result_ids[0]] >= s.scores[s.result_ids[-1]]


# ══════════════ compare_memories (historical) ══════════════
def test_compare_memories(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _mem(e, title="momentum sharpe", context="")
    b = _mem(e, title="momentum reversal", context="", now=T[2])
    cmp = e.compare_memories(a, b)
    assert "momentum" in cmp["shared_tokens"]
    assert cmp["same_type"] is True


# ══════════════ 유사도 순수 함수 ══════════════
def test_jaccard_identical():
    assert M.jaccard(frozenset({"a", "b"}), frozenset({"a", "b"})) == 1.0


def test_jaccard_disjoint():
    assert M.jaccard(frozenset({"a"}), frozenset({"b"})) == 0.0


def test_jaccard_both_empty():
    assert M.jaccard(frozenset(), frozenset()) == 0.0


def test_token_set_min_length():
    assert "a" not in M.token_set("a bb ccc")
    assert "bb" in M.token_set("a bb ccc")


def test_similarity_explainable_shared():
    score, shared = M.similarity("momentum sharpe", "momentum reversal")
    assert shared == ["momentum"]
    assert 0 < score < 1


# ══════════════ snapshot ══════════════
def test_snapshot_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e, title="a")
    m2 = _indexed(e, title="b")
    snap = e.build_memory_snapshot("ALL", T[6], commit=True)
    assert snap.memory_count == 2
    assert snap.state_distribution.get(M_CREATED) == 1
    assert snap.state_distribution.get(M_INDEXED) == 1


def test_snapshot_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    a = e.build_memory_snapshot("ALL", T[6], commit=False)
    b = e.build_memory_snapshot("ALL", T[6], commit=False)
    assert a.snapshot_id == b.snapshot_id
    assert a.state_distribution == b.state_distribution


def test_snapshot_consistency_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    e.build_memory_snapshot("ALL", T[6], commit=True)
    assert snapshot_consistency()["ok"] is True


# ══════════════ report ══════════════
def test_report_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _indexed(e, title="a")
    e.record_experiment_memory(m, "EXP1", "o", now=T[2], commit=True)
    e.record_failure_memory(m, "app", "r", 1, now=T[3], commit=True)
    e.record_success_pattern(m, "p", "c", 0.5, T[4], commit=True)
    e.mark_retrievable(m, T[5], commit=True)
    rep = e.generate_memory_report("ALL", T[6], commit=True)
    assert rep.memory_count == 1
    assert rep.experiment_count == 1
    assert rep.failure_count == 1
    assert rep.pattern_count == 1
    assert rep.retrievable_count == 1


def test_report_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rep = e.generate_memory_report("ALL", T[1], commit=True)
    assert rep.is_binding is False


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    rep = e.generate_memory_report("ALL", T[1], commit=True)
    assert "MEMORY ≠ EXECUTION" in rep.disclaimer


def test_report_type_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e, mtype="EXPERIMENT_RESULT", title="a")
    _mem(e, mtype="METHODOLOGY", title="b", now=T[2])
    rep = e.generate_memory_report("ALL", T[3], commit=True)
    assert rep.type_distribution.get("EXPERIMENT_RESULT") == 1
    assert rep.type_distribution.get("METHODOLOGY") == 1


# ══════════════ hash chain & tamper ══════════════
def test_chain_intact_full_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _indexed(e, title="a")
    b = _indexed(e, title="b")
    e.link_related_memories(a, b, "R", "", T[3], commit=True)
    e.record_experiment_memory(a, "EXP1", "o", now=T[4], commit=True)
    e.build_memory_snapshot("ALL", T[5], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tampered_memory(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    p = ledger.state_path(ledger.MEMORIES[0])
    recs = ledger.read_memory_events()
    recs[0]["title"] = "TAMPERED"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e, title="a")
    _mem(e, title="b", now=T[2])
    p = ledger.state_path(ledger.MEMORIES[0])
    recs = ledger.read_memory_events()
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.MEMORIES[0]]["ok"] is False


def test_verify_detects_duplicate_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    p = ledger.state_path(ledger.MEMORIES[0])
    recs = ledger.read_memory_events()
    with open(p, "a") as f:
        f.write(json.dumps(recs[0], ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.MEMORIES[0]]["ok"] is False


# ══════════════ verify sub-integrities ══════════════
def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _indexed(e)
    e.mark_retrievable(m, T[3], commit=True)
    assert lifecycle_integrity()["ok"] is True


def test_lifecycle_integrity_bad_initial(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng()
    p = ledger.state_path(ledger.MEMORIES[0])
    bad = {"memory_event_id": "MSV:bad", "memory_id": "MSM:bad", "memory_type": "X",
           "from_state": M.GENESIS, "to_state": M_INDEXED, "previous_hash": M.GENESIS}
    bad["record_hash"] = M.content_hash(bad)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps(bad, ensure_ascii=False) + "\n")
    assert lifecycle_integrity()["ok"] is False


def test_duplicate_integrity_detects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e)
    p = ledger.state_path(ledger.MEMORIES[0])
    g = [r for r in ledger.memory_events(m) if r["from_state"] == M.GENESIS][0]
    with open(p, "a") as f:
        f.write(json.dumps(g, ensure_ascii=False) + "\n")
    assert duplicate_integrity()["ok"] is False


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e)
    e.record_experiment_memory(m, "EXP1", "o", now=T[1], commit=True)
    assert reference_integrity()["ok"] is True


def test_reference_integrity_detects_invalid(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _mem(e)
    e.record_experiment_memory(m, "EXP1", "o", now=T[1], commit=True)
    p = ledger.state_path(ledger.EXPERIMENTS[0])
    recs = ledger.read_experiments()
    recs[0]["memory_id"] = "MSM:ghost"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert reference_integrity()["ok"] is False


def test_association_integrity_detects_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _indexed(e, title="a")
    b = _indexed(e, title="b")
    e.link_related_memories(a, b, "R", "", T[3], commit=True)
    # b->a 위조로 순환 주입
    p = ledger.state_path(ledger.ASSOCIATIONS[0])
    recs = ledger.read_associations()
    forged = dict(recs[0])
    forged["association_id"] = "MSA:forged00000"
    forged["memory_a"] = b
    forged["memory_b"] = a
    forged["previous_hash"] = recs[0]["record_hash"]
    forged["record_hash"] = M.content_hash(forged)
    with open(p, "a") as f:
        f.write(json.dumps(forged, ensure_ascii=False, default=str) + "\n")
    assert association_integrity()["ok"] is False


def test_snapshot_consistency_detects_inconsistent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    e.build_memory_snapshot("ALL", T[6], commit=True)
    p = ledger.state_path(ledger.SNAPSHOTS[0])
    recs = ledger.read_snapshots()
    recs[0]["memory_count"] = 99
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert snapshot_consistency()["ok"] is False


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    assert lineage_integrity()["ok"] is True


# ══════════════ replay / determinism ══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    assert replay(e, T[9])["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _indexed(e)
    e.record_failure_memory(m, "app", "r", 1, now=T[2], commit=True)
    s = e.summary(T[9])
    assert s.registry_count == 1
    assert s.failure_count == 1
    assert s.context_count == 1


def test_replay_reengine_equal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _indexed(e)
    s1 = e.summary(T[9]).to_dict()
    s2 = _eng().summary(T[9]).to_dict()
    assert s1 == s2


def test_verify_integrity_wrapper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    assert e.verify_integrity()["ok"] is True


def test_verify_chain_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = verify_chain()
    assert res["ok"] is True and res["n"] == 0


# ══════════════ can_transition matrix ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (M_CREATED, M_INDEXED, True),
    (M_INDEXED, M_CONNECTED, True),
    (M_INDEXED, M_RETRIEVABLE, True),
    (M_CONNECTED, M_CONNECTED, True),
    (M_CONNECTED, M_RETRIEVABLE, True),
    (M_RETRIEVABLE, M_RETRIEVABLE, True),
    (M_RETRIEVABLE, M_ARCHIVED, True),
    (M_CREATED, M_CONNECTED, False),
    (M_CREATED, M_RETRIEVABLE, False),
    (M_CREATED, M_ARCHIVED, False),
    (M_ARCHIVED, M_RETRIEVABLE, False),
    (M_INDEXED, M_ARCHIVED, False),
])
def test_can_transition_matrix(frm, to, ok):
    assert M.can_transition(frm, to) is ok


# ══════════════ is_forbidden_verb ══════════════
@pytest.mark.parametrize("word", ["EXECUTE", "TRADE", "DEPLOY", "ALLOCATE", "PROMOTE_LIVE",
                                  "APPROVE_STRATEGY", "APPROVE_MODEL", "MODIFY_STRATEGY",
                                  "MODIFY_MODEL", "CHANGE_PERMISSION", "CHANGE_CONFIG", "approve"])
def test_is_forbidden_verb_true(word):
    assert M.is_forbidden_verb(word) is True


@pytest.mark.parametrize("word", ["STORE", "RECALL", "SEARCH", "LINK", "REMEMBER", ""])
def test_is_forbidden_verb_false(word):
    assert M.is_forbidden_verb(word) is False


# ══════════════ ID 결정성 / prefixes ══════════════
def test_ids_deterministic():
    assert M.memory_id("l", "s", "t", "ti") == M.memory_id("l", "s", "t", "ti")
    assert M.association_id("a", "b", "r") == M.association_id("a", "b", "r")


def test_ids_prefixes_ms_scheme():
    assert M.registry_id("m").startswith("MSR:")
    assert M.memory_id("l", "s", "t", "ti").startswith("MSM:")
    assert M.memory_event_id("m", "s", 0).startswith("MSV:")
    assert M.knowledge_id("m", "s").startswith("MSK:")
    assert M.context_id("m", "k").startswith("MSC:")
    assert M.experiment_memory_id("m", "r").startswith("MSX:")
    assert M.failure_memory_id("m", "a").startswith("MSF:")
    assert M.success_pattern_id("m", "p").startswith("MSP:")
    assert M.association_id("a", "b", "r").startswith("MSA:")
    assert M.snapshot_id("s", "t").startswith("MSN:")
    assert M.report_id("s", "t").startswith("MSO:")
    assert M.artifact_id("t", "r").startswith("MST:")
    assert M.search_id("q", "m", 0).startswith("MSS:")


def test_content_hash_excludes_hash_fields():
    a = {"x": 1, "previous_hash": "p", "record_hash": "r"}
    b = {"x": 1, "previous_hash": "q", "record_hash": "s"}
    assert M.content_hash(a) == M.content_hash(b)


def test_detect_cycle_and_ancestors():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) != []
    assert M.detect_cycle([("a", "b")]) == []
    assert M.ancestors([("c", "b"), ("b", "a")], "c") == ["a", "b"]


def test_neighbors_undirected():
    assert M.neighbors([("a", "b"), ("c", "a")], "a") == ["b", "c"]


# ══════════════ 보안: 금지 import AST 스캔 ══════════════
_PKG_DIR = os.path.dirname(os.path.dirname(__file__))
_FORBIDDEN_PREFIXES = (
    "jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
    "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order",
    "jarvis.capital_allocation", "jarvis.live_trading", "jarvis.risk_controller",
    "jarvis.portfolio_execution",
)


def _module_files():
    for fn in os.listdir(_PKG_DIR):
        if fn.endswith(".py"):
            yield os.path.join(_PKG_DIR, fn)


def test_no_forbidden_imports():
    for path in _module_files():
        with open(path) as f:
            tree = ast.parse(f.read(), filename=path)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                for bad in _FORBIDDEN_PREFIXES:
                    assert not name.startswith(bad), f"{path}: {name}"


def test_no_forbidden_method_defs():
    forbidden = ("def execute", "def trade", "def deploy", "def allocate", "def promote_live",
                 "def approve_strategy", "def approve_model", "def modify_strategy",
                 "def modify_model", "def change_permission", "def change_config",
                 "def place_order")
    for path in _module_files():
        with open(path) as f:
            src = f.read().lower()
        for bad in forbidden:
            assert bad not in src, f"{path}: {bad}"


def test_no_model_id_leak():
    for path in _module_files():
        with open(path) as f:
            assert "claude-opus" not in f.read().lower()


def test_ledger_no_delete_update_api():
    import jarvis.research_memory_system.ledger as L
    for name in dir(L):
        assert not name.startswith("delete_")
        assert not name.startswith("update_")
        assert not name.startswith("remove_")


def test_ledger_only_append_mode():
    with open(os.path.join(_PKG_DIR, "ledger.py")) as f:
        src = f.read()
    assert 'open(p, "a")' in src
    assert 'open(p, "w")' not in src


def test_all_written_files_have_rmem_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _indexed(e)
    e.record_experiment_memory(m, "EXP1", "o", now=T[2], commit=True)
    e.search_memory("q", MODE_SIMILARITY, now=T[3], commit=True)
    e.build_memory_snapshot("ALL", T[4], commit=True)
    for fn in os.listdir(tmp_path):
        if fn.endswith(".jsonl"):
            assert fn.startswith("rmem_"), fn


def test_no_rm_underscore_only_files(tmp_path, monkeypatch):
    # 기존 rm_ 계층 파일을 건드리지 않음 — 모든 파일은 rmem_
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    for fn in os.listdir(tmp_path):
        if fn.endswith(".jsonl"):
            assert not (fn.startswith("rm_") and not fn.startswith("rmem_")), fn


# ══════════════ 소스 참조 READ ONLY ══════════════
def test_source_ref_exists_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_ref_exists("research_data", "x") is False


def test_source_ref_read_only_no_write(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = ledger.state_path("datasets.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps({"dataset_hash": "D1"}) + "\n")
    before = os.path.getmtime(p)
    assert ledger.source_ref_exists("research_data", "D1") is True
    assert os.path.getmtime(p) == before


# ══════════════ CLI ══════════════
def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_system.__main__ import main
    assert main(["summary"]) == 0
    assert "memory_event_count" in json.loads(capsys.readouterr().out)


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_system.__main__ import main
    assert main(["verify"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_system.__main__ import main
    main(["memory", "--layer", "research_agents", "--source-id", "A1", "--type",
          "EXPERIMENT_RESULT", "--title", "momentum", "--context", "sharpe oos", "--commit"])
    m = json.loads(capsys.readouterr().out)["memory"]["memory_id"]
    main(["context", "--memory", m, "--key", "setup", "--data", "walk forward", "--commit"])
    capsys.readouterr()
    main(["experiment", "--memory", m, "--ref", "EXP1", "--outcome", "good", "--commit"])
    capsys.readouterr()
    assert main(["retrievable", "--memory", m, "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["event"]["to_state"] == M_RETRIEVABLE


def test_cli_search(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_system.__main__ import main
    main(["memory", "--layer", "research_agents", "--source-id", "A1", "--type",
          "EXPERIMENT_RESULT", "--title", "momentum sharpe", "--commit"])
    capsys.readouterr()
    assert main(["search", "--query", "momentum", "--mode", "SIMILARITY", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["search"]["result_ids"]) == 1


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_system.__main__ import main
    assert main(["replay"]) == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_snapshot_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_system.__main__ import main
    main(["memory", "--layer", "research_agents", "--source-id", "A1", "--type",
          "EXPERIMENT_RESULT", "--title", "t", "--commit"])
    capsys.readouterr()
    assert main(["snapshot", "--commit"]) == 0
    capsys.readouterr()
    assert main(["report", "--commit"]) == 0
    assert json.loads(capsys.readouterr().out)["report"]["is_binding"] is False


def test_cli_link_and_compare(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_system.__main__ import main
    main(["memory", "--layer", "research_agents", "--source-id", "A1", "--type",
          "EXPERIMENT_RESULT", "--title", "momentum a", "--commit"])
    a = json.loads(capsys.readouterr().out)["memory"]["memory_id"]
    main(["context", "--memory", a, "--key", "k", "--data", "d", "--commit"])
    capsys.readouterr()
    main(["memory", "--layer", "research_agents", "--source-id", "A2", "--type",
          "EXPERIMENT_RESULT", "--title", "momentum b", "--commit"])
    b = json.loads(capsys.readouterr().out)["memory"]["memory_id"]
    main(["context", "--memory", b, "--key", "k", "--data", "d", "--commit"])
    capsys.readouterr()
    assert main(["link", "--memory-a", a, "--memory-b", b, "--commit"]) == 0
    capsys.readouterr()
    assert main(["compare", "--a", a, "--b", b]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "momentum" in out["shared_tokens"]


def test_cli_memories_list(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_system.__main__ import main
    main(["memory", "--layer", "research_agents", "--source-id", "A1", "--type",
          "METHODOLOGY", "--title", "t", "--commit"])
    capsys.readouterr()
    assert main(["memories", "--type", "METHODOLOGY"]) == 0
    assert len(json.loads(capsys.readouterr().out)["memories"]) == 1


# ══════════════ no stray writes without commit ══════════════
def test_no_stray_writes_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_memory("research_agents", "A1", "EXPERIMENT_RESULT", "t", "c", "", T[0],
                      commit=False)
    assert ledger.read_memory_events() == []
    assert ledger.read_registry() == []
