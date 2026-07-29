"""P10.14 Research Memory Intelligence 테스트. **연구 기억 보존·검색 전용.**

기억(불변)·생명주기(STORED→CONNECTED→RETRIEVED→ARCHIVED, 차단전이)·교훈(불변)·패턴·연결(관계 검증·
순환 차단)·검색(결정적 유사도)·클러스터·리포트·verify(체인/변조/중복/그래프/계보/검색결정성)·replay·
상위 READ ONLY 보호·CLI·보안(금지import·실행/거래/배포/선택/모델수정 없음·상위 원장 무변경·삭제 API
없음·불변·MEMORY≠DECISION·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.research_memory import ledger
from jarvis.research_memory import models as M
from jarvis.research_memory.engine import ResearchMemoryEngine
from jarvis.research_memory.models import (
    ARCHIVED,
    CONNECTED,
    FAILURE,
    HIGH,
    INSIGHT,
    LESSON,
    LOW,
    MEDIUM,
    METHOD,
    PATTERN,
    RETRIEVED,
    STORED,
    IllegalTransition,
    ImmutableLessonError,
    ImmutableMemoryError,
    ImmutablePatternError,
    InvalidConnection,
    UnknownMemory,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

_HI = {"historical_relevance": 0.9, "evidence_strength": 0.85, "recurrence_frequency": 0.8,
       "confidence": 0.85, "contradiction_level": 0.0}
_LO = {"historical_relevance": 0.2, "evidence_strength": 0.1, "recurrence_frequency": 0.1,
       "confidence": 0.2, "contradiction_level": 0.5}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_memory.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchMemoryEngine()


def _mem(eng, mtype=LESSON, ref="rg:ST1", content="high parameter count caused instability",
         commit=True):
    return eng.store_memory(mtype, ref, content, "", 0.7, 0.6, 8, "tag", T0, commit=commit)


# ── Memory ──
def test_store_memory(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    m = _mem(eng)
    assert m.mem_type == LESSON and m.status == STORED
    assert eng.memory_state(m.memory_id) == STORED


def test_memory_id_deterministic():
    a = M.memory_id("t", "s", "sha256:x")
    assert a == M.memory_id("t", "s", "sha256:x") and a.startswith("RMM:")


def test_memory_commit_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _mem(_eng())
    assert len(ledger.read_memory_events()) == 1


def test_memory_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _mem(_eng(), commit=False)
    assert ledger.read_memory_events() == []


@pytest.mark.parametrize("mtype", list(M.MEMORY_TYPES))
def test_memory_types(tmp_path, monkeypatch, mtype):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    m = eng.store_memory(mtype, f"ref_{mtype}", "content", "", 0.5, 0.5, 0, "", T0, commit=True)
    assert m.mem_type == mtype


def test_memory_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _mem(eng)
    _mem(eng)
    assert len(ledger.distinct_memories()) == 1


def test_memory_immutable_different_content(tmp_path, monkeypatch):
    """동일 type+source 라도 content 다르면 다른 memory_id (content_hash 반영)."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    m1 = eng.store_memory(LESSON, "ref", "content A", "", 0.5, 0.5, 0, "", T0, commit=True)
    m2 = eng.store_memory(LESSON, "ref", "content B", "", 0.5, 0.5, 0, "", T0, commit=True)
    assert m1.memory_id != m2.memory_id


def test_memory_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    m = _mem(eng)
    mid = m.memory_id
    eng.transition_memory(mid, CONNECTED, T1, commit=True)
    eng.transition_memory(mid, RETRIEVED, T1, commit=True)
    eng.transition_memory(mid, ARCHIVED, T2, commit=True)
    assert eng.memory_state(mid) == ARCHIVED


def test_memory_invalid_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    m = _mem(eng)
    eng.transition_memory(m.memory_id, ARCHIVED, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.transition_memory(m.memory_id, STORED, T2, commit=True)


def test_memory_transition_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownMemory):
        _eng().transition_memory("GHOST", CONNECTED, T1, commit=True)


def test_memory_transition_table():
    assert M.can_transition_memory("", STORED)
    assert M.can_transition_memory(STORED, CONNECTED)
    assert M.can_transition_memory(STORED, RETRIEVED)
    assert M.can_transition_memory(CONNECTED, RETRIEVED)
    assert not M.can_transition_memory(ARCHIVED, STORED)


def test_memory_embedding_metadata(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    m = eng.store_memory(INSIGHT, "ref", "content", "", 0.5, 0.5, 128, "minilm", T0, commit=True)
    assert m.embedding_dim == 128 and m.embedding_tag == "minilm"


def test_memory_artifact_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    m = _mem(eng)
    arts = {a["artifact_id"]: a for a in ledger.read_artifacts()}
    ma = arts[M.artifact_id(M.ART_MEMORY, m.memory_id)]
    assert ma["parent_artifact"] in arts


# ── Lesson ──
def test_record_lesson(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = eng.record_lesson("High parameter count caused instability", "too many params",
                          "unstable", ["ST1"], 0.7, T0, commit=True)
    assert l.observation.startswith("High parameter")
    assert len(ledger.read_lessons()) == 1


def test_lesson_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_lesson("obs", "cause", "impact1", [], 0.5, T0, commit=True)
    with pytest.raises(ImmutableLessonError):
        eng.record_lesson("obs", "cause", "impact2", [], 0.5, T0, commit=True)


def test_lesson_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_lesson("obs", "cause", "impact", [], 0.5, T0, commit=True)
    eng.record_lesson("obs", "cause", "impact", [], 0.5, T0, commit=True)
    assert len(ledger.read_lessons()) == 1


def test_compare_lessons(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.record_lesson("overfitting from short lookback", "short lookback", "unstable", [],
                          0.6, T0, commit=True)
    b = eng.record_lesson("overfitting from many params", "many params", "unstable", [], 0.6, T0,
                          commit=True)
    cmp = eng.compare_lessons(a.lesson_id, b.lesson_id)
    assert 0.0 <= cmp["similarity"] <= 1.0 and "VALIDATION" in cmp["note"]


def test_compare_lessons_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.record_lesson("o", "c", "i", [], 0.5, T0, commit=True)
    with pytest.raises(ImmutableLessonError):
        eng.compare_lessons(a.lesson_id, "GHOST")


# ── Pattern ──
def test_record_pattern(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = eng.record_pattern("walk_forward_pattern", "reusable wf methodology", ["ST1"], 0.8, T0,
                           commit=True)
    assert p.name == "walk_forward_pattern"
    assert len(ledger.read_patterns()) == 1


def test_pattern_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_pattern("p", "desc1", [], 0.5, T0, commit=True)
    with pytest.raises(ImmutablePatternError):
        eng.record_pattern("p", "desc2", [], 0.5, T0, commit=True)


def test_pattern_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_pattern("p", "desc", [], 0.5, T0, commit=True)
    eng.record_pattern("p", "desc", [], 0.5, T0, commit=True)
    assert len(ledger.read_patterns()) == 1


# ── Connection ──
def _two_mem(eng):
    a = eng.store_memory(LESSON, "rg:A", "lesson about overfit", "", 0.6, 0.6, 0, "", T0,
                         commit=True)
    b = eng.store_memory(FAILURE, "rg:B", "failure from overfit", "", 0.6, 0.6, 0, "", T0,
                         commit=True)
    return a, b


@pytest.mark.parametrize("rel", list(M.RELATIONS))
def test_connect_relations(tmp_path, monkeypatch, rel):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_mem(eng)
    c = eng.connect_memory(a.memory_id, rel, b.memory_id, 0.5, T0, commit=True)
    assert c.relation == rel


def test_connect_unknown_memory(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_mem(eng)
    with pytest.raises(UnknownMemory):
        eng.connect_memory(a.memory_id, M.SIMILAR_TO, "GHOST", 0.5, T0, commit=True)


def test_connect_invalid_relation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_mem(eng)
    with pytest.raises(InvalidConnection):
        eng.connect_memory(a.memory_id, "NONSENSE", b.memory_id, 0.5, T0, commit=True)


def test_connect_advances_memory_to_connected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_mem(eng)
    eng.connect_memory(a.memory_id, M.SIMILAR_TO, b.memory_id, 0.5, T0, commit=True)
    assert eng.memory_state(a.memory_id) == CONNECTED
    assert eng.memory_state(b.memory_id) == CONNECTED


def test_connect_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_mem(eng)
    eng.connect_memory(a.memory_id, M.SIMILAR_TO, b.memory_id, 0.5, T0, commit=True)
    eng.connect_memory(a.memory_id, M.SIMILAR_TO, b.memory_id, 0.5, T0, commit=True)
    assert len(ledger.read_connections()) == 1


def test_connect_derived_cycle_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.store_memory(LESSON, "A", "a", "", 0.5, 0.5, 0, "", T0, commit=True)
    b = eng.store_memory(LESSON, "B", "b", "", 0.5, 0.5, 0, "", T0, commit=True)
    c = eng.store_memory(LESSON, "C", "c", "", 0.5, 0.5, 0, "", T0, commit=True)
    eng.connect_memory(a.memory_id, M.DERIVED_FROM, b.memory_id, 0.5, T0, commit=True)
    eng.connect_memory(b.memory_id, M.DERIVED_FROM, c.memory_id, 0.5, T0, commit=True)
    with pytest.raises(InvalidConnection):
        eng.connect_memory(c.memory_id, M.DERIVED_FROM, a.memory_id, 0.5, T0, commit=True)


def test_connect_similar_symmetric_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_mem(eng)
    eng.connect_memory(a.memory_id, M.SIMILAR_TO, b.memory_id, 0.5, T0, commit=True)
    c = eng.connect_memory(b.memory_id, M.SIMILAR_TO, a.memory_id, 0.5, T0, commit=True)
    assert c.relation == M.SIMILAR_TO  # 대칭 관계는 순환 검사 없음


def test_connection_cycle_helper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_mem(eng)
    eng.connect_memory(a.memory_id, M.DERIVED_FROM, b.memory_id, 0.5, T0, commit=True)
    assert eng.connection_cycle() == []


# ── Search / retrieval ──
def test_similarity_helper():
    assert M.similarity("overfit lookback", "overfit lookback") == 1.0
    assert M.similarity("a b", "c d") == 0.0
    assert 0.0 < M.similarity("overfit lookback", "overfit params") < 1.0


def test_search_memory(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.store_memory(LESSON, "rg:A", "overfitting from short lookback window", "", 0.6, 0.6, 0,
                     "", T0, commit=True)
    eng.store_memory(INSIGHT, "rg:B", "liquidity affects drawdown", "", 0.6, 0.6, 0, "", T0,
                     commit=True)
    r = eng.search_memory("overfitting lookback", 0.1, 5, T1, commit=True)
    assert len(r.matched_memories) >= 1 and r.top_similarity > 0
    assert len(ledger.read_retrievals()) == 1


def test_search_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.store_memory(LESSON, "rg:A", "overfitting lookback", "", 0.6, 0.6, 0, "", T0, commit=True)
    r1 = eng.search_memory("overfitting", 0.1, 5, T1, commit=True)
    r2 = eng.search_memory("overfitting", 0.1, 5, T1, commit=True)
    assert r1.retrieval_id == r2.retrieval_id and r1.matched_memories == r2.matched_memories
    assert len(ledger.read_retrievals()) == 1  # dedup


def test_search_advances_matched_to_retrieved(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    m = eng.store_memory(LESSON, "rg:A", "overfitting lookback", "", 0.6, 0.6, 0, "", T0,
                         commit=True)
    eng.search_memory("overfitting lookback", 0.1, 5, T1, commit=True)
    assert eng.memory_state(m.memory_id) == RETRIEVED


def test_search_threshold_filters(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.store_memory(LESSON, "rg:A", "totally unrelated content xyz", "", 0.6, 0.6, 0, "", T0,
                     commit=True)
    r = eng.search_memory("overfitting lookback", 0.5, 5, T1, commit=True)
    assert r.matched_memories == []


def test_search_top_k(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i in range(5):
        eng.store_memory(LESSON, f"rg:{i}", "overfitting lookback param tuning", "", 0.6, 0.6, 0,
                         "", T0, commit=True)
    r = eng.search_memory("overfitting lookback", 0.1, 2, T1, commit=True)
    assert len(r.matched_memories) == 2


def test_search_sorted_desc(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.store_memory(LESSON, "rg:A", "overfitting lookback exact", "", 0.6, 0.6, 0, "", T0,
                     commit=True)
    eng.store_memory(LESSON, "rg:B", "overfitting only", "", 0.6, 0.6, 0, "", T0, commit=True)
    r = eng.search_memory("overfitting lookback exact", 0.05, 5, T1, commit=True)
    vals = [r.similarity_scores[mid] for mid in r.matched_memories]
    assert vals == sorted(vals, reverse=True)


# ── Clustering ──
def test_cluster_memories(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_mem(eng)
    c = eng.store_memory(INSIGHT, "rg:C", "c content", "", 0.6, 0.6, 0, "", T0, commit=True)
    eng.connect_memory(a.memory_id, M.SIMILAR_TO, b.memory_id, 0.5, T0, commit=True)
    eng.connect_memory(b.memory_id, M.SUPPORTS, c.memory_id, 0.5, T0, commit=True)
    clusters = eng.cluster_memories(T1, commit=True)
    assert len(clusters) == 1 and clusters[0].size == 3


def test_cluster_singletons_excluded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _two_mem(eng)  # 연결 없음 → 모두 singleton
    clusters = eng.cluster_memories(T1, commit=True)
    assert clusters == []


def test_cluster_cohesion(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_mem(eng)
    eng.connect_memory(a.memory_id, M.SIMILAR_TO, b.memory_id, 0.5, T0, commit=True)
    clusters = eng.cluster_memories(T1, commit=True)
    assert clusters[0].cohesion == 1.0  # 2 노드 1 엣지 → 완전


def test_connected_components_helper():
    comps = M.connected_components(["a", "b", "c"], [("a", "b")])
    assert ["a", "b"] in comps and ["c"] in comps


# ── Memory analysis ──
def test_memory_confidence_high():
    assert M.memory_confidence(_HI) == HIGH


def test_memory_confidence_low():
    assert M.memory_confidence(_LO) == LOW


def test_memory_confidence_medium():
    m = {"historical_relevance": 0.6, "evidence_strength": 0.5, "recurrence_frequency": 0.5,
         "confidence": 0.5, "contradiction_level": 0.1}
    assert M.memory_confidence(m) == MEDIUM


def test_memory_score_contradiction_penalty():
    base = {"historical_relevance": 0.8, "evidence_strength": 0.8, "recurrence_frequency": 0.8,
            "confidence": 0.8}
    hi = M.memory_score({**base, "contradiction_level": 0.0})
    lo = M.memory_score({**base, "contradiction_level": 1.0})
    assert hi > lo


def test_memory_weights_sum_one():
    assert abs(sum(M.MEMORY_WEIGHTS.values()) - 1.0) < 1e-9


def test_analyze(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().analyze(_HI)["memory_confidence"] == HIGH


# ── Report / summary ──
def _full(eng):
    a = eng.store_memory(LESSON, "rg:A", "overfitting from short lookback", "", 0.7, 0.7, 8, "t",
                         T0, commit=True)
    b = eng.store_memory(FAILURE, "rg:B", "failed experiment overfit", "", 0.6, 0.6, 8, "t", T0,
                         commit=True)
    eng.record_lesson("short lookback overfits", "short lookback", "instability", ["rg:A"], 0.7,
                      T0, commit=True)
    eng.record_pattern("walk_forward", "reusable wf", ["rg:A"], 0.8, T0, commit=True)
    eng.connect_memory(a.memory_id, M.SIMILAR_TO, b.memory_id, 0.6, T0, commit=True)
    eng.search_memory("overfitting", 0.1, 5, T1, commit=True)
    eng.cluster_memories(T1, commit=True)
    return a, b


def test_generate_memory_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_memory_report("GLOBAL", _HI, T2, commit=True)
    assert rep.memory_count == 2 and rep.lesson_count == 1 and rep.pattern_count == 1
    assert rep.connection_count == 1 and rep.retrieval_count == 1 and rep.cluster_count == 1
    assert rep.memory_confidence == HIGH and "MEMORY ≠ DECISION" in rep.disclaimer


def test_report_type_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_memory_report("GLOBAL", _HI, T2, commit=True)
    assert rep.memory_type_distribution.get(LESSON) == 1
    assert rep.memory_type_distribution.get(FAILURE) == 1


def test_report_no_trading_verbs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_memory_report("GLOBAL", _HI, T2, commit=True)
    d = rep.to_dict()
    d.pop("disclaimer")
    blob = json.dumps(d).upper()
    for verb in ("BUY", "SELL", "DEPLOY", "ALLOCATE", "EXECUTE"):
        assert verb not in blob


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    eng.generate_memory_report("GLOBAL", _HI, T2, commit=True)
    eng.generate_memory_report("GLOBAL", _HI, T2, commit=True)
    assert len(ledger.read_reports()) == 1


def test_summary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.summary(T2)
    assert rep.memory_count == 2 and rep.lesson_count == 1 and rep.connection_count == 1
    assert rep.retrieval_count == 1 and rep.cluster_count == 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.summary(T2).to_dict() == eng.summary(T2).to_dict()


def test_summary_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rep = _eng().summary(T0)
    assert rep.memory_count == 0 and rep.report_count == 0


# ── verify ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_full_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory.verify import verify_chain
    eng = _eng()
    _full(eng)
    res = verify_chain()
    assert res["ok"] is True
    assert res["graph"]["ok"] and res["lineage"]["ok"] and res["retrieval"]["ok"]


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_memory.verify import verify_chain
    eng = _eng()
    _mem(eng)
    recs = ledger.read_memory_events()
    recs[0]["source_reference"] = "TAMPERED"
    with open(sp("rm_memories.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_chain_break(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_memory.verify import verify_ledger
    eng = _eng()
    eng.store_memory(LESSON, "A", "a", "", 0.5, 0.5, 0, "", T0, commit=True)
    eng.store_memory(LESSON, "B", "b", "", 0.5, 0.5, 0, "", T0, commit=True)
    recs = ledger.read_memory_events()
    recs[1]["previous_hash"] = "GENESIS"
    with open(sp("rm_memories.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_ledger(ledger.MEMORIES)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_memory.verify import verify_ledger
    eng = _eng()
    _mem(eng)
    recs = ledger.read_memory_events()
    dup = dict(recs[0])
    dup["previous_hash"] = recs[0]["record_hash"]
    with open(sp("rm_memories.jsonl"), "a") as f:
        f.write(json.dumps(dup) + "\n")
    assert verify_ledger(ledger.MEMORIES)["ok"] is False


def test_verify_graph_unknown_memory(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_memory.verify import graph_validation
    ResearchMemoryEngine().store_memory(LESSON, "A", "a", "", 0.5, 0.5, 0, "", T0, commit=True)
    rec = {"connection_id": "RMC:x", "from_memory": "GHOST", "to_memory": "GHOST2",
           "relation": M.SIMILAR_TO, "weight": 0.0, "created_at": T0, "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("rm_connections.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    res = graph_validation()
    assert any("unknown_memory" in i for i in res["issues"])


def test_verify_retrieval_determinism_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_memory.verify import retrieval_determinism
    rec = {"retrieval_id": "RMR:wrong", "query": "q", "matched_memories": ["m1"],
           "similarity_scores": {}, "top_similarity": 0.0, "created_at": T0,
           "previous_hash": "GENESIS"}
    rec["record_hash"] = M.content_hash(rec)
    with open(sp("rm_retrievals.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")
    res = retrieval_determinism()
    assert res["ok"] is False


def test_verify_artifact_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.research_memory.verify import lineage_validation
    a1 = {"artifact_id": "A1", "artifact_type": "X", "ref_id": "r", "parent_artifact": "A2",
          "created_at": T0, "previous_hash": "GENESIS"}
    a1["record_hash"] = M.content_hash(a1)
    a2 = {"artifact_id": "A2", "artifact_type": "X", "ref_id": "r", "parent_artifact": "A1",
          "created_at": T0, "previous_hash": a1["record_hash"]}
    a2["record_hash"] = M.content_hash(a2)
    with open(sp("rm_artifacts.jsonl"), "w") as f:
        f.write(json.dumps(a1) + "\n")
        f.write(json.dumps(a2) + "\n")
    assert any("artifact_cycle" in i for i in lineage_validation()["issues"])


def test_detect_cycle_helper():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) == ["a", "b", "a"]
    assert M.detect_cycle([("a", "b")]) == []


# ── replay ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory.verify import replay
    eng = _eng()
    _full(eng)
    assert replay(eng, T2)["deterministic"] is True


def test_content_hash_excludes_chain_fields():
    a = {"x": 1, "previous_hash": "A", "record_hash": "B", "report_hash": "C"}
    b = {"x": 1, "previous_hash": "Z", "record_hash": "Z", "report_hash": "Z"}
    assert M.content_hash(a) == M.content_hash(b)


# ── CLI ──
def test_cli_memory_and_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory.__main__ import main
    rc = main(["memory", "--type", "LESSON", "--source-ref", "rg:ST1", "--content",
               "overfit lesson", "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["memory"]["mem_type"] == "LESSON"
    main(["summary"])
    assert json.loads(capsys.readouterr().out)["memory_count"] == 1


def test_cli_full_workflow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory.__main__ import main
    main(["memory", "--type", "LESSON", "--source-ref", "rg:A", "--content",
          "overfitting lookback", "--commit"])
    ma = json.loads(capsys.readouterr().out)["memory"]["memory_id"]
    main(["memory", "--type", "FAILURE", "--source-ref", "rg:B", "--content",
          "overfitting failure", "--commit"])
    mb = json.loads(capsys.readouterr().out)["memory"]["memory_id"]
    main(["connect", "--from-memory", ma, "--relation", "SIMILAR_TO", "--to-memory", mb,
          "--commit"])
    capsys.readouterr()
    main(["search", "--query", "overfitting", "--commit"])
    r = json.loads(capsys.readouterr().out)["retrieval"]
    assert len(r["matched_memories"]) >= 1
    main(["cluster", "--commit"])
    capsys.readouterr()
    main(["report", "--metrics-json", json.dumps({"historical_relevance": 0.9,
          "evidence_strength": 0.9, "recurrence_frequency": 0.9, "confidence": 0.9,
          "contradiction_level": 0.0}), "--commit"])
    rep = json.loads(capsys.readouterr().out)["report"]
    assert rep["memory_confidence"] == HIGH
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_lesson(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory.__main__ import main
    rc = main(["lesson", "--observation", "high params unstable", "--cause", "many params",
               "--commit"])
    assert rc == 0
    assert "lesson_id" in json.loads(capsys.readouterr().out)["lesson"]


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory.__main__ import main
    main(["memory", "--type", "LESSON", "--source-ref", "r", "--content", "c", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.research_memory.engine as eng_mod
    import jarvis.research_memory.models as mdl_mod
    import jarvis.research_memory.ledger as led_mod
    import jarvis.research_memory.verify as ver_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "live_execution", _j + "broker", _j + "order",
                 _j + "portfolio.", _j + "risk_governor", _j + "permission",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "select_strategy(", "modify_model(", "activate_live("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_keyword_methods():
    import jarvis.research_memory.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def execute", "def trade", "def allocate", "def deploy", "def select_strategy",
               "def modify_model", "def activate_live"):
        assert kw not in src


def test_no_execution_authority_api():
    api = set(dir(ResearchMemoryEngine))
    for banned in ("execute", "trade", "allocate", "deploy", "select_strategy", "modify_model",
                   "activate_live", "approve", "place_order"):
        assert banned not in api


def test_no_automatic_learning_update():
    """자동 학습 갱신 메서드가 없어야 한다 — 기억은 불변 append-only."""
    eng = ResearchMemoryEngine()
    for banned in ("update_memory", "train", "learn", "retrain", "fine_tune"):
        assert not hasattr(eng, banned)


def test_memory_not_decision(tmp_path, monkeypatch):
    """기억/리포트에 decision/approval/action 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    m = _mem(eng)
    for banned in ("decision", "approval", "action", "deploy"):
        assert banned not in m.to_dict()


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
        m = importlib.import_module(f"jarvis.research_memory.{mod_name}")
        for attr in dir(m):
            low = attr.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledgers_namespaced_rm_prefix():
    for filename, _ in ledger.ALL_LEDGERS:
        assert filename.startswith("rm_")


def test_no_collision_with_existing_prefixes():
    ours = {fn for fn, _ in ledger.ALL_LEDGERS}
    known = {"rv_validations.jsonl", "rg_strategies.jsonl", "kg_entities.jsonl",
             "di_candidates.jsonl", "sim_scenarios.jsonl", "ci_variables.jsonl",
             "mi_patterns.jsonl", "si_workflows.jsonl"}
    assert ours.isdisjoint(known)
    assert all(fn.startswith("rm_") for fn in ours)


def test_source_ledgers_read_only_not_owned():
    owned = {fn for fn, _ in ledger.ALL_LEDGERS}
    for layer, spec in ledger.SOURCE_LEDGERS.items():
        assert spec[0] not in owned


def test_existing_source_ledgers_untouched(tmp_path, monkeypatch):
    """상위 P10.5/7/8/11/12/13 원장을 시드한 뒤 전체 워크플로를 돌려도 원본 SHA256 불변."""
    sp = _iso(tmp_path, monkeypatch)
    seeds = {"kg_entities.jsonl": [{"entity_id": "KGE:1"}],
             "sim_results.jsonl": [{"result_id": "SRS:1"}],
             "ci_evidences.jsonl": [{"evidence_id": "CIE:1"}],
             "si_recommendations.jsonl": [{"event_id": "E1", "recommendation_id": "SIR:1"}]}
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


def test_engine_only_appends_rm_files(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    created = [f for f in os.listdir(tmp_path) if f.endswith(".jsonl")]
    assert created and all(f.startswith("rm_") for f in created)


def test_relations_and_types_defined():
    assert set(M.MEMORY_TYPES) == {"LESSON", "FAILURE", "PATTERN", "METHOD", "INSIGHT"}
    assert set(M.RELATIONS) == {"SIMILAR_TO", "DERIVED_FROM", "CONTRADICTS", "SUPPORTS",
                                "REPEATS"}


def test_list_source_objects_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_objects("NOPE") == []


# ── 추가: ID prefix / 세부 ──
def test_lesson_id_prefix():
    assert M.lesson_id("o", "c").startswith("RML:")


def test_pattern_id_prefix():
    assert M.pattern_id("n").startswith("RPT:")


def test_connection_id_prefix():
    assert M.connection_id("a", M.SIMILAR_TO, "b").startswith("RMC:")


def test_retrieval_id_prefix():
    assert M.retrieval_id("q", ["m"]).startswith("RMR:")


def test_cluster_id_prefix():
    assert M.cluster_id("sig").startswith("RMK:")


def test_report_id_prefix():
    assert M.report_id("s").startswith("RMO:")


def test_artifact_id_prefix():
    assert M.artifact_id(M.ART_MEMORY, "x").startswith("RMA:")


def test_directed_relations_subset():
    assert set(M.DIRECTED_RELATIONS).issubset(set(M.RELATIONS))
    assert M.SIMILAR_TO not in M.DIRECTED_RELATIONS


def test_similarity_symmetric():
    assert M.similarity("a b c", "b c d") == M.similarity("b c d", "a b c")


def test_similarity_empty():
    assert M.similarity("", "") == 0.0


def test_tokenize_helper():
    assert M.tokenize("Overfit, Lookback!") == {"overfit", "lookback"}


def test_store_memory_importance_confidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    m = eng.store_memory(LESSON, "r", "c", "", 0.9, 0.8, 0, "", T0, commit=True)
    assert m.importance == 0.9 and m.confidence == 0.8


def test_connection_weight(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_mem(eng)
    c = eng.connect_memory(a.memory_id, M.SUPPORTS, b.memory_id, 0.42, T0, commit=True)
    assert c.weight == 0.42


def test_cluster_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a, b = _two_mem(eng)
    eng.connect_memory(a.memory_id, M.SIMILAR_TO, b.memory_id, 0.5, T0, commit=True)
    eng.cluster_memories(T1, commit=True)
    eng.cluster_memories(T1, commit=True)
    assert len(ledger.read_clusters()) == 1


def test_report_metrics_carried(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    rep = eng.generate_memory_report("GLOBAL", _HI, T2, commit=True)
    assert rep.metrics == _HI and 0.0 <= rep.memory_score <= 1.0


def test_search_empty_no_match(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = eng.search_memory("anything", 0.1, 5, T1, commit=True)
    assert r.matched_memories == [] and r.top_similarity == 0.0
