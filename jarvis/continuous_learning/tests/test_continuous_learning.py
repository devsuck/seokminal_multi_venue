"""P20 continuous_learning 테스트 — 기억/교훈 생애주기·실험/실패/패턴 기억·검색·유사도·
학습지표·계보·verify·replay·CLI·보안·금지능력·READ ONLY 상위."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.continuous_learning import ledger
from jarvis.continuous_learning import models as M
from jarvis.continuous_learning.engine import ContinuousLearningEngine
from jarvis.continuous_learning.models import (
    FAILURE_TYPES,
    FORBIDDEN_VERBS,
    GENESIS,
    LESSON_STATES,
    L_DRAFT,
    L_RECORDED,
    L_REVIEWED,
    MEMORY_STATES,
    MEMORY_TYPES,
    M_ARCHIVED,
    M_CREATED,
    M_INDEXED,
    M_REFERENCED,
    M_RETRIEVABLE,
    IllegalTransition,
    ImmutableRecordError,
    ReviewerRequired,
    UnknownEntityError,
    can_lesson_transition,
    can_memory_transition,
    content_hash,
    jaccard,
    metadata_similarity,
)
from jarvis.continuous_learning.verify import (
    duplicate_integrity,
    lesson_review_integrity,
    lifecycle_integrity,
    lineage_integrity,
    reference_integrity,
    replay,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.continuous_learning.ledger.state_path", sp)
    return sp


def _eng():
    return ContinuousLearningEngine()


def _mem(e, layer="research_operations", ref="exp1", mtype="EXPERIMENT", summary="s", now=T[0]):
    return e.register_memory(mtype, layer, ref, summary, {"a": 1}, ["momentum"], now,
                             commit=True).memory_id


# ═══════════════ memory lifecycle ═══════════════
def test_register_memory(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().register_memory("EXPERIMENT", "research_operations", "e1", "sum", {}, [], T[0],
                                commit=True)
    assert ev.to_state == M_CREATED
    assert ev.memory_id.startswith("CLM:")
    assert ev.memory_event_id.startswith("CLL:")


def test_register_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().register_memory("NOPE", "l", "r", now=T[0], commit=True)


def test_memory_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    e.index_memory(mem, T[1], commit=True)
    e.mark_retrievable(mem, T[2], commit=True)
    e.reference_memory(mem, T[3], commit=True)
    e.archive_memory(mem, T[4], commit=True)
    assert e.memory_state(mem) == M_ARCHIVED


def test_memory_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    with pytest.raises(IllegalTransition):
        e.mark_retrievable(mem, T[1], commit=True)  # CREATED→RETRIEVABLE skip


def test_memory_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_memory("EXPERIMENT", "l", "r", "s", now=T[0], commit=True).memory_id
    b = e.register_memory("EXPERIMENT", "l", "r", "s", now=T[1], commit=True).memory_id
    assert a == b
    assert len(ledger.memory_events(a)) == 1


def test_memory_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_memory("EXPERIMENT", "l", "r", "s1", now=T[0], commit=True)
    with pytest.raises(ImmutableRecordError):
        e.register_memory("EXPERIMENT", "l", "r", "s2", now=T[1], commit=True)


def test_memory_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    assert any(a["artifact_type"] == "MEMORY" for a in ledger.read_artifacts())


def test_memory_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_memory("EXPERIMENT", "l", "r", now=T[0], commit=False)
    assert ledger.read_memory_events() == []


def test_memory_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().index_memory("CLM:nope", T[1], commit=True)


@pytest.mark.parametrize("frm,to,ok", [
    (M_CREATED, M_INDEXED, True), (M_CREATED, M_RETRIEVABLE, False),
    (M_INDEXED, M_RETRIEVABLE, True), (M_RETRIEVABLE, M_REFERENCED, True),
    (M_RETRIEVABLE, M_ARCHIVED, True), (M_REFERENCED, M_RETRIEVABLE, True),
    (M_ARCHIVED, M_INDEXED, False),
])
def test_memory_transition_matrix(frm, to, ok):
    assert can_memory_transition(frm, to) is ok


@pytest.mark.parametrize("s", MEMORY_STATES)
def test_memory_states(s):
    assert s in MEMORY_STATES


@pytest.mark.parametrize("mt", MEMORY_TYPES)
def test_memory_types(mt):
    assert mt in MEMORY_TYPES


def test_ten_memory_types():
    assert len(MEMORY_TYPES) == 10


# ═══════════════ publish KG reference (read-only upstream) ═══════════════
def test_publish_kg_reference(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    e.index_memory(mem, T[1], commit=True)
    e.mark_retrievable(mem, T[2], commit=True)
    a = e.publish_kg_reference(mem, "kg:entity1", T[3], commit=True)
    assert a.artifact_type == "REFERENCE"
    assert e.memory_state(mem) == M_REFERENCED


def test_publish_does_not_write_kg(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    e.index_memory(mem, T[1], commit=True)
    e.mark_retrievable(mem, T[2], commit=True)
    e.publish_kg_reference(mem, "kg:x", T[3], commit=True)
    assert not os.path.exists(sp("kg_entities.jsonl"))  # 상위 원장 미생성/미변경


# ═══════════════ experiment memory ═══════════════
def test_record_experiment(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r = e.record_experiment_memory("exp1", "h", "ds", {"lr": 0.1}, "won", "VALIDATED", "", now=T[0],
                                   commit=True)
    assert r.experiment_memory_id.startswith("CLE:")
    assert r.validation_status == "VALIDATED"


def test_experiment_failure_reason(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r = e.record_experiment_memory("exp2", failure_reason="overfit", validation_status="FAILED",
                                   now=T[0], commit=True)
    assert r.failure_reason == "overfit"


def test_experiment_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.record_experiment_memory("exp1", now=T[0], commit=True).experiment_memory_id
    b = e.record_experiment_memory("exp1", now=T[1], commit=True).experiment_memory_id
    assert a == b
    assert len(ledger.read_experiments()) == 1


# ═══════════════ failure memory ═══════════════
def test_record_failure(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r = e.record_failure("OVERFITTING", "too many params", ["e1"], "exp1", now=T[0], commit=True)
    assert r.failure_id.startswith("CLF:")
    assert r.failure_type == "OVERFITTING"


def test_failure_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().record_failure("NOPE", "c", now=T[0], commit=True)


def test_failure_preserves_negative_knowledge(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_failure("DATA_ISSUE", "bad data", now=T[0], commit=True)
    e.record_failure("DATA_ISSUE", "bad data2", now=T[1], commit=True)
    assert len(ledger.read_failures()) == 2


@pytest.mark.parametrize("ft", FAILURE_TYPES)
def test_failure_types(ft):
    assert ft in FAILURE_TYPES


def test_repeated_failure_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_failure("OVERFITTING", "c1", affected_research="a", now=T[0], commit=True)
    e.record_failure("OVERFITTING", "c2", affected_research="b", now=T[1], commit=True)
    assert e.repeated_failure_count("OVERFITTING") == 2


# ═══════════════ success pattern ═══════════════
def test_record_pattern(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r = e.record_success_pattern("VALIDATION", "walk-forward", ["e1", "e2"], 0.8, now=T[0],
                                 commit=True)
    assert r.pattern_id.startswith("CLP:")
    assert r.confidence == 0.8


def test_pattern_confidence_is_metadata(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r = e.record_success_pattern("DATA", "reliable source", confidence=0.95, now=T[0], commit=True)
    # confidence 는 메타데이터일 뿐 — 승인 표식 없음
    d = r.to_dict()
    assert "approval" not in d
    assert d["confidence"] == 0.95


# ═══════════════ lessons (human review) ═══════════════
def test_draft_lesson(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r = e.draft_lesson("avoid overfitting", "momentum", ["e1"], ["exp1"], "agentA", now=T[0],
                       commit=True)
    assert r.lesson_id.startswith("CLS:")
    assert r.to_state == L_DRAFT


def test_lesson_full_workflow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    les = e.draft_lesson("l1", "ctx", now=T[0], commit=True).lesson_id
    e.review_lesson(les, "dr.human", T[1], commit=True)
    e.record_lesson(les, T[2], commit=True)
    assert e.lesson_state(les) == L_RECORDED


def test_lesson_review_requires_reviewer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    les = e.draft_lesson("l1", "ctx", now=T[0], commit=True).lesson_id
    with pytest.raises(ReviewerRequired):
        e.review_lesson(les, "", T[1], commit=True)


def test_lesson_record_requires_review(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    les = e.draft_lesson("l1", "ctx", now=T[0], commit=True).lesson_id
    # DRAFT→RECORDED 직접 불가(검토 필요)
    with pytest.raises(IllegalTransition):
        e.record_lesson(les, T[1], commit=True)


def test_lesson_reviewer_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    les = e.draft_lesson("l1", "ctx", now=T[0], commit=True).lesson_id
    e.review_lesson(les, "dr.jane", T[1], commit=True)
    ev = e.record_lesson(les, T[2], commit=True)
    assert ev.reviewer == "dr.jane"


@pytest.mark.parametrize("frm,to,ok", [
    (L_DRAFT, L_REVIEWED, True), (L_DRAFT, L_RECORDED, False),
    (L_REVIEWED, L_RECORDED, True), (L_REVIEWED, L_DRAFT, True), (L_RECORDED, L_DRAFT, False),
])
def test_lesson_transition_matrix(frm, to, ok):
    assert can_lesson_transition(frm, to) is ok


@pytest.mark.parametrize("s", LESSON_STATES)
def test_lesson_states(s):
    assert s in LESSON_STATES


# ═══════════════ retrieval (deterministic) ═══════════════
def test_search_memory_by_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_memory("EXPERIMENT", "l", "r1", "s", {}, ["a"], T[0], commit=True)
    e.register_memory("FAILURE", "l", "r2", "s", {}, ["a"], T[1], commit=True)
    res = e.search_memory(memory_type="EXPERIMENT", now=T[2], commit=True)
    assert len(res) == 1


def test_search_memory_by_tags(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_memory("EXPERIMENT", "l", "r1", "s", {}, ["momentum", "daily"], T[0], commit=True)
    e.register_memory("EXPERIMENT", "l", "r2", "s", {}, ["value"], T[1], commit=True)
    res = e.search_memory(tags=["momentum"], now=T[2], commit=True)
    assert len(res) == 1


def test_search_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e, ref="a")
    _mem(e, ref="b")
    assert e.search_memory(now=T[3]) == e.search_memory(now=T[3])


def test_search_records_retrieval(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    e.search_memory(now=T[3], commit=True)
    assert len(ledger.read_retrievals()) == 1


def test_find_similar_experiments(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_experiment_memory("e1", parameters={"lr": 0.1, "n": 10}, now=T[0], commit=True)
    e.record_experiment_memory("e2", parameters={"lr": 0.1, "n": 10}, now=T[1], commit=True)
    e.record_experiment_memory("e3", parameters={"lr": 0.9, "n": 99}, now=T[2], commit=True)
    res = e.find_similar_experiments(parameters={"lr": 0.1, "n": 10}, now=T[3], commit=True)
    # 최고 유사(동일 파라미터) 먼저
    assert res[0][1] == 1.0


def test_find_related_failures(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_failure("OVERFITTING", "c", affected_research="expA", now=T[0], commit=True)
    e.record_failure("DATA_ISSUE", "c", affected_research="expA", now=T[1], commit=True)
    res = e.find_related_failures(failure_type="OVERFITTING", now=T[2], commit=True)
    assert len(res) == 1


def test_retrieve_lessons(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    les = e.draft_lesson("l1", "c", now=T[0], commit=True).lesson_id
    e.review_lesson(les, "r", T[1], commit=True)
    e.record_lesson(les, T[2], commit=True)
    e.draft_lesson("l2", "c", now=T[3], commit=True)
    recorded = e.retrieve_lessons(state="RECORDED", now=T[4], commit=True)
    assert len(recorded) == 1


# ═══════════════ similarity (score only) ═══════════════
def test_jaccard():
    assert jaccard(["a", "b"], ["a", "b"]) == 1.0
    assert jaccard(["a"], ["b"]) == 0.0
    assert jaccard([], []) == 1.0


def test_metadata_similarity():
    assert metadata_similarity({"a": 1}, {"a": 1}) == 1.0
    assert metadata_similarity({"a": 1}, {"a": 2}) == 0.0


def test_memory_similarity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = e.register_memory("EXPERIMENT", "l", "r1", "s", {"a": 1}, ["x"], T[0], commit=True).memory_id
    m2 = e.register_memory("EXPERIMENT", "l", "r2", "s", {"a": 1}, ["x"], T[1], commit=True).memory_id
    sim = e.memory_similarity(m1, m2)
    assert sim == 1.0  # 동일 유형·태그·metadata_hash


def test_experiment_similarity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.record_experiment_memory("e1", parameters={"lr": 0.1}, now=T[0], commit=True).experiment_memory_id
    b = e.record_experiment_memory("e2", parameters={"lr": 0.1}, now=T[1], commit=True).experiment_memory_id
    assert e.experiment_similarity(a, b) == 1.0


def test_failure_similarity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.record_failure("OVERFITTING", "c", ["e1"], "x", now=T[0], commit=True).failure_id
    b = e.record_failure("OVERFITTING", "c", ["e1"], "y", now=T[1], commit=True).failure_id
    assert e.failure_similarity(a, b) == 1.0


# ═══════════════ learning metrics ═══════════════
def test_record_metric(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r = e.record_metric("experiment_reduction_ratio", 0.3, now=T[0], commit=True)
    assert r.metric_id.startswith("CLG:")
    assert r.is_observation is True


def test_learning_stats(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    e.record_failure("OVERFITTING", "c", now=T[1], commit=True)
    e.record_experiment_memory("e1", now=T[2], commit=True)
    stats = e.learning_stats()
    assert stats["total_memories"] == 1
    assert stats["total_failures"] == 1
    assert stats["total_experiments"] == 1


def test_reused_knowledge_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    e.index_memory(mem, T[1], commit=True)
    e.mark_retrievable(mem, T[2], commit=True)
    e.publish_kg_reference(mem, "kg:1", T[3], commit=True)
    assert e.reused_knowledge_count() == 1


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers(tmp_path, monkeypatch):
    for k in ("knowledge_graph", "research_operations", "research_collaboration",
              "decision_intelligence", "simulation", "agent_governance"):
        assert k in ledger.SOURCE_LAYERS


def test_source_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("kg_entities.jsonl")
    with open(p, "w") as f:
        for i in range(2):
            f.write(json.dumps({"event_id": f"e{i}"}) + "\n")
    before = open(p).read()
    assert ledger.source_count("knowledge_graph") == 2
    assert open(p).read() == before


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    e.index_memory(mem, T[1], commit=True)
    e.record_failure("OVERFITTING", "c", now=T[2], commit=True)
    e.record_experiment_memory("e1", now=T[3], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    p = sp("cl_memories.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["summary"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_failure("OVERFITTING", "c1", now=T[0], commit=True)
    e.record_failure("DATA_ISSUE", "c2", now=T[1], commit=True)
    p = sp("cl_failure_records.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    p = sp("cl_memories.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    e.index_memory(mem, T[1], commit=True)
    assert lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e, ref="a")
    _mem(e, ref="b")
    assert duplicate_integrity()["ok"] is True


def test_lesson_review_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    les = e.draft_lesson("l", "c", now=T[0], commit=True).lesson_id
    e.review_lesson(les, "r", T[1], commit=True)
    e.record_lesson(les, T[2], commit=True)
    assert lesson_review_integrity()["ok"] is True


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_experiment_memory("e1", now=T[0], commit=True)
    e.record_failure("OVERFITTING", "c", now=T[1], commit=True)
    assert reference_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    e.record_failure("OVERFITTING", "c", now=T[1], commit=True)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["REMEMBER", "RETRIEVE", "STORE", "ANALYZE", "SEARCH", "RECORD"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


@pytest.mark.parametrize("v", ["EXECUTE_TRADE", "PLACE_ORDER", "DEPLOY_STRATEGY",
                                "ALLOCATE_CAPITAL", "MODIFY_MODEL", "AUTO_LEARN_MODEL",
                                "AUTO_SELECT_STRATEGY", "TRAIN_MODEL", "OPTIMIZE_LIVE"])
def test_forbidden_membership(v):
    assert v in FORBIDDEN_VERBS


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.memory_id, ("l", "r"), "CLM:"),
    (M.memory_event_id, ("m", "S", 0), "CLL:"),
    (M.experiment_memory_id, ("e",), "CLE:"),
    (M.failure_id, ("t", "a", 0), "CLF:"),
    (M.pattern_id, ("t", "d"), "CLP:"),
    (M.lesson_id, ("l", "c"), "CLS:"),
    (M.lesson_event_id, ("l", "S", 0), "CLN:"),
    (M.retrieval_id, ("k", "h", 0), "CLR:"),
    (M.metric_id, ("n", 0), "CLG:"),
    (M.artifact_id, ("MEMORY", "r"), "CLA:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


# ═══════════════ 조회 ═══════════════
def test_list_memories(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e, ref="a")
    _mem(e, ref="b")
    assert len(e.list_memories()) == 2


def test_memories_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    e.index_memory(mem, T[1], commit=True)
    assert mem in e.memories_in_state(M_INDEXED)


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    e.record_failure("OVERFITTING", "c", now=T[1], commit=True)
    s = e.summary(T[9])
    assert s.failure_count == 1
    assert s.memory_event_count == 1


# ═══════════════ CLI ═══════════════
def test_cli_memory(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.continuous_learning.__main__ import main
    assert main(["memory", "--type", "EXPERIMENT", "--layer", "l", "--ref", "r", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["memory"]["to_state"] == "CREATED"


def test_cli_failure(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.continuous_learning.__main__ import main
    assert main(["failure", "--type", "OVERFITTING", "--cause", "x", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["failure"]["failure_type"] == "OVERFITTING"


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.continuous_learning.__main__ import main
    assert main(["verify"]) == 0


def test_cli_stats(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.continuous_learning.__main__ import main
    assert main(["stats"]) == 0


def test_cli_search(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.continuous_learning.__main__ import main
    main(["memory", "--type", "EXPERIMENT", "--layer", "l", "--ref", "r", "--commit"])
    capsys.readouterr()
    assert main(["search", "--type", "EXPERIMENT"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["results"]) == 1


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.continuous_learning.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.continuous_learning.__main__ import main
    assert main(["summary"]) == 0


# ═══════════════ 격리 / 불변 ═══════════════
def test_no_write_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_memory("EXPERIMENT", "l", "r", now=T[0], commit=False)
    assert not os.path.exists(os.path.join(tmp_path, "cl_memories.jsonl"))


def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().register_memory("EXPERIMENT", "l", "r", now=T[0], commit=True)
    with pytest.raises(Exception):
        ev.summary = "x"


def test_eight_ledgers():
    assert len(ledger.ALL_LEDGERS) == 8


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("cl_")


# ═══════════════ 보안 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.portfolio", "jarvis.risk",
    "jarvis.permission", "jarvis.deployment", "jarvis.live", "jarvis.order",
    "jarvis.live_execution", "jarvis.live_trading",
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
    bad = ("execute", "trade", "deploy", "allocate", "promote", "train_model", "optimize_live",
           "execute_trade", "place_order", "deploy_strategy", "allocate_capital", "modify_model",
           "auto_learn_model", "auto_select_strategy")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_destructive_ledger_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def overwrite_", "def drop_", "def truncate"):
        assert bad not in src


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    # 실험 기억(성공/실패)
    e.record_experiment_memory("exp-A", "momentum", "kospi", {"lookback": 20}, "sharpe 1.2",
                               "VALIDATED", "", now=T[0], commit=True)
    e.record_experiment_memory("exp-B", "meanrev", "kospi", {"lookback": 5}, "overfit",
                               "FAILED", "overfitting on small sample", now=T[1], commit=True)
    # 실패 기억(음성 지식)
    e.record_failure("OVERFITTING", "too few samples", ["exp-B"], "exp-B", now=T[2], commit=True)
    # 성공 패턴
    e.record_success_pattern("VALIDATION", "walk-forward validation", ["exp-A"], 0.85, now=T[3],
                             commit=True)
    # 기억 등록 + 생애주기
    mem = e.register_memory("EXPERIMENT", "research_operations", "exp-A", "validated momentum",
                            {"lookback": 20}, ["momentum", "kospi"], T[4], commit=True).memory_id
    e.index_memory(mem, T[5], commit=True)
    e.mark_retrievable(mem, T[6], commit=True)
    # 검색·유사도
    similar = e.find_similar_experiments(parameters={"lookback": 20}, now=T[7], commit=True)
    assert similar[0][1] == 1.0
    fails = e.find_related_failures(failure_type="OVERFITTING", now=T[8], commit=True)
    assert len(fails) == 1
    # 교훈(사람 검토)
    les = e.draft_lesson("small samples overfit", "meanrev", ["e1"], ["exp-B"], "agentA",
                         now=T[9], commit=True).lesson_id
    e.review_lesson(les, "dr.oversight", T[10], commit=True)
    e.record_lesson(les, T[11], commit=True)
    # KG 참조 발행(상위 미변경)
    e.publish_kg_reference(mem, "kg:momentum", T[12], commit=True)
    # 학습 지표
    e.record_metric("experiment_reduction_ratio", 0.4, now=T[13], commit=True)
    stats = e.learning_stats()
    assert stats["recorded_lessons"] == 1
    assert stats["reused_knowledge"] == 1
    assert stats["total_failures"] == 1
    assert verify_chain()["ok"] is True
    assert replay(e, T[14])["deterministic"] is True
