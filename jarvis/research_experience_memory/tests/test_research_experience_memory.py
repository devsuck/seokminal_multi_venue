"""P12.7 Research Memory & Experience 테스트. **기억·기록·검색 전용.**

기억 등록(CREATED→RECORDED→INDEXED→RETRIEVABLE→REFERENCED→ARCHIVED)·7 유형·경험/실패/성공패턴·에피소드·검색(결정적·
기록)·메타데이터 유사도(추천 아님)·요약·계보·verify(체인/변조/중복/생애주기/유형/참조/계보)·replay·CLI·보안(금지import·
실행 없음·삭제 API 없음·불변·MEMORY≠EXECUTION·rm_/rmem_ 계층과 격리·모델ID 미노출).

패키지 내부 tests/ — 상위 conftest 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_experience_memory import ledger
from jarvis.research_experience_memory import models as M
from jarvis.research_experience_memory.engine import ResearchExperienceMemoryEngine
from jarvis.research_experience_memory.models import (
    M_ARCHIVED,
    M_CREATED,
    M_INDEXED,
    M_RECORDED,
    M_REFERENCED,
    M_RETRIEVABLE,
    MEMORY_STATES,
    MEMORY_TYPES,
    SIM_KEYS,
    DanglingReferenceError,
    IllegalMemoryTransition,
    ImmutableExperienceError,
    ImmutableFailureError,
    ImmutableMemoryError,
    ImmutablePatternError,
    InvalidMemoryType,
    UnknownEpisodeError,
    UnknownMemoryError,
)
from jarvis.research_experience_memory.verify import (
    duplicate_integrity,
    lifecycle_integrity,
    lineage_integrity,
    reference_integrity,
    replay,
    type_integrity,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_experience_memory.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchExperienceMemoryEngine()


def _memory(e, layer="autonomous_research_pipeline", ref="CYC1", mtype="SUCCESS_PATTERN",
            title="momentum works", context="oos robust", meta=None, now=T[0]):
    return e.register_memory(layer, ref, mtype, title, context, meta or {}, now,
                             commit=True).memory_id


def _retrievable(e, **kw):
    m = _memory(e, **kw)
    e.record_experience(m, "backtest", "positive", "always oos", "agent1", T[1], commit=True)
    e.make_retrievable(m, T[2], commit=True)
    return m


# ══════════════ Phase 0 / 접두사 / 격리 ══════════════
def test_prefix_all_ledgers_rxm():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rxm_")


def test_eight_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 8


def test_isolated_from_rm_and_rmem():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    for n in names:
        assert not (n.startswith("rm_") and not n.startswith("rxm_"))
        assert not n.startswith("rmem_")


def test_seven_memory_types():
    assert len(MEMORY_TYPES) == 7


def test_six_lifecycle_states():
    assert len(MEMORY_STATES) == 6


def test_six_sim_keys():
    assert len(SIM_KEYS) == 6


def test_source_ledgers_read_only(tmp_path, monkeypatch):
    assert "decision_intelligence" in ledger.SOURCE_LEDGERS
    assert "research_optimization_engine" in ledger.SOURCE_LEDGERS


# ══════════════ register_memory ══════════════
def test_register_memory_genesis(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    assert m.startswith("RXM:")
    assert e.current_state(m) == M_RECORDED


def test_register_memory_records_created_then_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    states = [x["to_state"] for x in ledger.memory_events(m)]
    assert states == [M_CREATED, M_RECORDED]


def test_register_memory_invalid_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(InvalidMemoryType):
        e.register_memory("l", "r", "BOGUS", "t", "c", {}, T[0], commit=True)


def test_register_memory_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_memory("l", "r", "SUCCESS_PATTERN", "t", "c", {}, T[0], commit=True)
    e.register_memory("l", "r", "SUCCESS_PATTERN", "t", "c", {}, T[1], commit=True)
    assert len(ledger.memory_events(a.memory_id)) == 2


def test_register_memory_immutable_rewrite(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_memory("l", "r", "SUCCESS_PATTERN", "t", "c1", {}, T[0], commit=True)
    with pytest.raises(ImmutableMemoryError):
        e.register_memory("l", "r", "SUCCESS_PATTERN", "t", "c2", {}, T[1], commit=True)


def test_register_memory_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    arts = [a for a in ledger.read_artifacts() if a["artifact_type"] == M.ART_MEMORY]
    assert any(a["ref_id"] == m for a in arts)


@pytest.mark.parametrize("mtype", list(MEMORY_TYPES))
def test_all_memory_types(tmp_path, monkeypatch, mtype):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = e.register_memory("l", "r-" + mtype, mtype, "t", "c", {}, T[0], commit=True)
    assert ev.memory_type == mtype


def test_register_memory_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_memory("l", "r", "SUCCESS_PATTERN", "t", "c", {}, T[0], commit=False)
    assert ledger.read_memory_events() == []


# ══════════════ record_experience ══════════════
def test_record_experience_indexes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    e.record_experience(m, "backtest", "good", "lesson", "agent", T[1], commit=True)
    assert e.current_state(m) == M_INDEXED


def test_record_experience_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    ex = e.record_experience(m, "subj", "out", "less", "ag", T[1], commit=True)
    assert ex.experience_id.startswith("RXE:")


def test_record_experience_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    e.record_experience(m, "s", "out1", "", "", T[1], commit=True)
    with pytest.raises(ImmutableExperienceError):
        e.record_experience(m, "s", "out2", "", "", T[2], commit=True)


def test_record_experience_unknown_memory(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownMemoryError):
        e.record_experience("RXM:ghost", "s", "", "", "", T[1], commit=True)


# ══════════════ record_failure ══════════════
def test_record_failure_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e, mtype="FAILED_EXPERIMENT")
    f = e.record_failure(m, "naive grid", "overfit", 3, T[1], commit=True)
    assert f.failure_id.startswith("RXF:")
    assert f.recurrence == 3


def test_record_failure_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e, mtype="FAILED_EXPERIMENT")
    e.record_failure(m, "app", "r", 1, T[1], commit=True)
    with pytest.raises(ImmutableFailureError):
        e.record_failure(m, "app", "r", 9, T[2], commit=True)


# ══════════════ record_success_pattern ══════════════
def test_record_pattern_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    p = e.record_success_pattern(m, "ensemble", "diverse", 0.8, T[1], commit=True)
    assert p.pattern_id.startswith("RXP:")
    assert p.confidence == 0.8


def test_record_pattern_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    e.record_success_pattern(m, "p", "c", 0.5, T[1], commit=True)
    with pytest.raises(ImmutablePatternError):
        e.record_success_pattern(m, "p", "c", 0.9, T[2], commit=True)


# ══════════════ create_episode ══════════════
def test_create_episode_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = _memory(e, ref="A", title="a")
    m2 = _memory(e, ref="B", title="b", now=T[1])
    ep = e.create_episode("episode1", "desc", [m1, m2], T[2], commit=True)
    assert ep.episode_id.startswith("RXS:")
    assert sorted(ep.memory_refs) == sorted([m1, m2])


def test_create_episode_dangling(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(DanglingReferenceError):
        e.create_episode("ep", "d", ["RXM:ghost"], T[2], commit=True)


def test_create_episode_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = _memory(e)
    ep = e.create_episode("ep", "d", [m1], T[2], commit=True)
    arts = [a for a in ledger.read_artifacts() if a["artifact_type"] == M.ART_EPISODE]
    assert any(a["ref_id"] == ep.episode_id for a in arts)


def test_episode_memories(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = _memory(e, ref="A")
    ep = e.create_episode("ep", "d", [m1], T[2], commit=True).episode_id
    assert e.episode_memories(ep) == [m1]


# ══════════════ lifecycle: retrievable / referenced / archive ══════════════
def test_make_retrievable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _retrievable(e)
    assert e.current_state(m) == M_RETRIEVABLE


def test_archive_from_retrievable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _retrievable(e)
    e.archive_memory(m, T[5], commit=True)
    assert e.current_state(m) == M_ARCHIVED


def test_archive_illegal_from_created(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    with pytest.raises(IllegalMemoryTransition):
        e.archive_memory(m, T[5], commit=True)


def test_full_lifecycle_sequence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    e.record_experience(m, "s", "o", "l", "a", T[1], commit=True)
    e.make_retrievable(m, T[2], commit=True)
    e.retrieve_memory("", "SUCCESS_PATTERN", T[3], commit=True)  # REFERENCED
    e.archive_memory(m, T[4], commit=True)
    states = [x["to_state"] for x in ledger.memory_events(m)]
    assert states == [M_CREATED, M_RECORDED, M_INDEXED, M_RETRIEVABLE, M_REFERENCED, M_ARCHIVED]


# ══════════════ retrieve_memory ══════════════
def test_retrieve_finds_retrievable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _retrievable(e, title="momentum")
    r = e.retrieve_memory("momentum", "", T[3], commit=True)
    assert m in r.result_ids


def test_retrieve_marks_referenced(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _retrievable(e, title="momentum")
    e.retrieve_memory("momentum", "", T[3], commit=True)
    assert e.current_state(m) == M_REFERENCED


def test_retrieve_type_filter(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _retrievable(e, ref="A", mtype="SUCCESS_PATTERN", title="a")
    _retrievable(e, ref="B", mtype="FAILED_EXPERIMENT", title="b", now=T[5])
    r = e.retrieve_memory("", "SUCCESS_PATTERN", T[10], commit=True)
    assert len(r.result_ids) == 1


def test_retrieve_excludes_non_retrievable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)  # only RECORDED, not retrievable
    r = e.retrieve_memory("", "", T[3], commit=True)
    assert m not in r.result_ids


def test_retrieve_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _retrievable(e)
    e.retrieve_memory("", "", T[3], commit=True)
    assert len(ledger.read_retrievals()) == 1


def test_retrieve_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _retrievable(e, title="momentum")
    a = e.retrieve_memory("momentum", "", T[3], commit=False)
    b = e.retrieve_memory("momentum", "", T[3], commit=False)
    assert a.result_ids == b.result_ids and a.retrieval_id == b.retrieval_id


# ══════════════ find_similar_experience (metadata similarity) ══════════════
def test_find_similar_metadata(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = _memory(e, ref="A", title="a", meta={"strategy": "momentum", "regime": "bull"})
    m2 = _memory(e, ref="B", title="b", meta={"strategy": "momentum", "regime": "bear"}, now=T[1])
    r = e.find_similar_experience(m1, 0.0, T[3], commit=True)
    assert m2 in r.result_ids
    assert "strategy" in r.explanation[m2]


def test_find_similar_no_match(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = _memory(e, ref="A", title="a", meta={"strategy": "momentum"})
    _memory(e, ref="B", title="b", meta={"strategy": "reversal"}, now=T[1])
    r = e.find_similar_experience(m1, 0.0, T[3], commit=True)
    assert r.result_ids == []


def test_find_similar_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = _memory(e, ref="A", title="a", meta={"strategy": "m", "dataset": "d"})
    _memory(e, ref="B", title="b", meta={"strategy": "m", "dataset": "d"}, now=T[1])
    a = e.find_similar_experience(m1, 0.0, T[3], commit=False)
    b = e.find_similar_experience(m1, 0.0, T[3], commit=False)
    assert a.scores == b.scores


def test_metadata_similarity_pure():
    score, matched = M.metadata_similarity({"strategy": "m", "regime": "bull"},
                                           {"strategy": "m", "regime": "bear"})
    assert matched == ["strategy"]
    assert score == 0.5


def test_metadata_similarity_empty():
    score, matched = M.metadata_similarity({}, {})
    assert score == 0.0 and matched == []


# ══════════════ generate_summary ══════════════
def test_generate_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    e.record_experience(m, "s", "o", "l", "a", T[1], commit=True)
    e.record_failure(m, "app", "r", 1, T[2], commit=True)
    s = e.generate_summary("ALL", "ALL", T[3], commit=True)
    assert s.memory_count == 1
    assert s.experience_count == 1
    assert s.failure_count == 1


def test_generate_summary_type_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _memory(e, ref="A", mtype="SUCCESS_PATTERN")
    _memory(e, ref="B", mtype="FAILED_EXPERIMENT", now=T[1])
    s = e.generate_summary("ALL", "ALL", T[2], commit=True)
    assert s.type_distribution.get("SUCCESS_PATTERN") == 1
    assert s.type_distribution.get("FAILED_EXPERIMENT") == 1


def test_generate_summary_creates_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s = e.generate_summary("ALL", "ALL", T[1], commit=True)
    arts = [a for a in ledger.read_artifacts() if a["artifact_type"] == M.ART_SUMMARY]
    assert any(a["ref_id"] == s.summary_id for a in arts)


# ══════════════ build_lineage ══════════════
def test_build_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = _memory(e, ref="A")
    m2 = _memory(e, ref="B", now=T[1])
    ep = e.create_episode("ep", "d", [m1, m2], T[2], commit=True).episode_id
    arts = e.build_lineage(ep, T[3], commit=True)
    assert len(arts) == 2


def test_build_lineage_unknown_episode(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    with pytest.raises(UnknownEpisodeError):
        e.build_lineage("RXS:ghost", T[3], commit=True)


def test_lineage_ancestors(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = _memory(e, ref="A")
    ep = e.create_episode("ep", "d", [m1], T[2], commit=True).episode_id
    e.build_lineage(ep, T[3], commit=True)
    anc = e.lineage_ancestors(m1)
    assert M.artifact_id(M.ART_EPISODE, ep) in anc


# ══════════════ hash chain & tamper ══════════════
def test_chain_intact_full_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _retrievable(e)
    e.record_failure(m, "app", "r", 1, T[3], commit=True)
    e.retrieve_memory("", "", T[4], commit=True)
    e.generate_summary("ALL", "ALL", T[5], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tampered(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _memory(e)
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
    _memory(e)
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
    _memory(e)
    p = ledger.state_path(ledger.MEMORIES[0])
    recs = ledger.read_memory_events()
    with open(p, "a") as f:
        f.write(json.dumps(recs[0], ensure_ascii=False, default=str) + "\n")
    assert verify_chain()["ledgers"][ledger.MEMORIES[0]]["ok"] is False


# ══════════════ verify sub-integrities ══════════════
def test_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _retrievable(e)
    assert lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_detects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    p = ledger.state_path(ledger.MEMORIES[0])
    g = [r for r in ledger.memory_events(m) if r["from_state"] == M.GENESIS][0]
    with open(p, "a") as f:
        f.write(json.dumps(g, ensure_ascii=False) + "\n")
    assert duplicate_integrity()["ok"] is False


def test_type_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _memory(e)
    assert type_integrity()["ok"] is True


def test_type_integrity_detects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _memory(e)
    p = ledger.state_path(ledger.MEMORIES[0])
    recs = ledger.read_memory_events()
    for r in recs:
        if r["from_state"] == M.GENESIS:
            r["memory_type"] = "BOGUS"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert type_integrity()["ok"] is False


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    e.record_experience(m, "s", "o", "l", "a", T[1], commit=True)
    assert reference_integrity()["ok"] is True


def test_reference_integrity_orphan(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    e.record_experience(m, "s", "o", "l", "a", T[1], commit=True)
    p = ledger.state_path(ledger.EXPERIENCES[0])
    recs = ledger.read_experiences()
    recs[0]["memory_id"] = "RXM:ghost"
    with open(p, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    assert reference_integrity()["ok"] is False


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _memory(e)
    assert lineage_integrity()["ok"] is True


# ══════════════ replay / determinism ══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _memory(e)
    assert replay(e, T[9])["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    e.record_experience(m, "s", "o", "l", "a", T[1], commit=True)
    s = e.summary(T[9])
    assert s.experience_count == 1


def test_replay_reengine_equal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _memory(e)
    s1 = e.summary(T[9]).to_dict()
    s2 = _eng().summary(T[9]).to_dict()
    assert s1 == s2


def test_verify_integrity_wrapper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _memory(e)
    assert e.verify_integrity()["ok"] is True


def test_verify_chain_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_memories_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    assert m in e.memories_in_state(M_RECORDED)


def test_list_memories_by_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _memory(e, mtype="AGENT_EXPERIENCE")
    assert len(e.list_memories("AGENT_EXPERIENCE")) == 1


# ══════════════ can_transition matrix ══════════════
@pytest.mark.parametrize("frm,to,ok", [
    (M_CREATED, M_RECORDED, True),
    (M_RECORDED, M_INDEXED, True),
    (M_INDEXED, M_RETRIEVABLE, True),
    (M_RETRIEVABLE, M_REFERENCED, True),
    (M_RETRIEVABLE, M_ARCHIVED, True),
    (M_REFERENCED, M_RETRIEVABLE, True),
    (M_REFERENCED, M_ARCHIVED, True),
    (M_CREATED, M_INDEXED, False),
    (M_RECORDED, M_RETRIEVABLE, False),
    (M_ARCHIVED, M_RETRIEVABLE, False),
    (M_CREATED, M_ARCHIVED, False),
])
def test_can_transition_matrix(frm, to, ok):
    assert M.can_transition(frm, to) is ok


# ══════════════ is_forbidden_verb ══════════════
@pytest.mark.parametrize("word", ["TRADE", "ORDER", "EXECUTE", "DEPLOY", "ALLOCATE",
                                  "PROMOTE_MODEL", "PLACE_ORDER", "ALLOCATE_CAPITAL",
                                  "CHANGE_PERMISSION", "RECOMMEND"])
def test_is_forbidden_verb_true(word):
    assert M.is_forbidden_verb(word) is True


@pytest.mark.parametrize("word", ["REMEMBER", "RECORD", "RETRIEVE", "STORE", "RECALL", ""])
def test_is_forbidden_verb_false(word):
    assert M.is_forbidden_verb(word) is False


# ══════════════ ID 결정성 / prefixes ══════════════
def test_ids_deterministic():
    assert M.memory_id("l", "r", "t", "ti") == M.memory_id("l", "r", "t", "ti")


def test_ids_prefixes_rx_scheme():
    assert M.memory_id("l", "r", "t", "ti").startswith("RXM:")
    assert M.memory_event_id("m", "s", 0).startswith("RXV:")
    assert M.experience_id("m", "s").startswith("RXE:")
    assert M.failure_id("m", "a").startswith("RXF:")
    assert M.pattern_id("m", "p").startswith("RXP:")
    assert M.episode_id("n").startswith("RXS:")
    assert M.retrieval_id("q", "m", 0).startswith("RXR:")
    assert M.summary_id("s", "i", "t").startswith("RXG:")
    assert M.artifact_id("t", "r").startswith("RXA:")


def test_content_hash_excludes_hash_fields():
    a = {"x": 1, "previous_hash": "p", "record_hash": "r"}
    b = {"x": 1, "previous_hash": "q", "record_hash": "s"}
    assert M.content_hash(a) == M.content_hash(b)


def test_detect_cycle_pure():
    assert M.detect_cycle([("a", "b"), ("b", "a")]) != []
    assert M.detect_cycle([("a", "b")]) == []


# ══════════════ 보안 스캔 ══════════════
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
    forbidden = ("def trade", "def place_order", "def execute", "def deploy", "def allocate",
                 "def promote_model", "def allocate_capital", "def change_permission")
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
    import jarvis.research_experience_memory.ledger as L
    for name in dir(L):
        assert not name.startswith("delete_")
        assert not name.startswith("update_")
        assert not name.startswith("remove_")


def test_ledger_only_append_mode():
    with open(os.path.join(_PKG_DIR, "ledger.py")) as f:
        src = f.read()
    assert 'open(p, "a")' in src
    assert 'open(p, "w")' not in src


def test_all_written_files_have_rxm_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _retrievable(e)
    e.record_failure(m, "a", "r", 1, T[3], commit=True)
    e.record_success_pattern(m, "p", "c", 0.5, T[4], commit=True)
    ep = e.create_episode("ep", "d", [m], T[5], commit=True).episode_id
    e.build_lineage(ep, T[6], commit=True)
    e.retrieve_memory("", "", T[7], commit=True)
    e.generate_summary("ALL", "ALL", T[8], commit=True)
    for fn in os.listdir(tmp_path):
        if fn.endswith(".jsonl"):
            assert fn.startswith("rxm_"), fn


def test_no_rm_or_rmem_files(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _memory(e)
    for fn in os.listdir(tmp_path):
        assert not fn.startswith("rmem_"), fn
        assert not (fn.startswith("rm_") and not fn.startswith("rxm_")), fn


# ══════════════ 소스 참조 READ ONLY ══════════════
def test_source_ref_exists_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.source_ref_exists("decision_intelligence", "x") is False


def test_source_ref_read_only_no_write(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = ledger.state_path("di_frameworks.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps({"framework_id": "F1"}) + "\n")
    before = os.path.getmtime(p)
    assert ledger.source_ref_exists("decision_intelligence", "F1") is True
    assert os.path.getmtime(p) == before


# ══════════════ CLI ══════════════
def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_experience_memory.__main__ import main
    assert main(["summary"]) == 0
    assert "memory_event_count" in json.loads(capsys.readouterr().out)


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_experience_memory.__main__ import main
    assert main(["verify"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_full_flow(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_experience_memory.__main__ import main
    main(["memory", "--layer", "l", "--ref", "R1", "--type", "SUCCESS_PATTERN", "--title", "t",
          "--commit"])
    m = json.loads(capsys.readouterr().out)["memory"]["memory_id"]
    main(["experience", "--memory", m, "--subject", "s", "--commit"])
    capsys.readouterr()
    assert main(["retrievable", "--memory", m, "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["event"]["to_state"] == M_RETRIEVABLE


def test_cli_retrieve(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_experience_memory.__main__ import main
    main(["memory", "--layer", "l", "--ref", "R1", "--type", "SUCCESS_PATTERN", "--title",
          "momentum", "--commit"])
    m = json.loads(capsys.readouterr().out)["memory"]["memory_id"]
    main(["experience", "--memory", m, "--subject", "s", "--commit"])
    capsys.readouterr()
    main(["retrievable", "--memory", m, "--commit"])
    capsys.readouterr()
    assert main(["retrieve", "--query", "momentum", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert m in out["retrieval"]["result_ids"]


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_experience_memory.__main__ import main
    assert main(["replay"]) == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_summary_gen(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_experience_memory.__main__ import main
    assert main(["summary-gen", "--commit"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["summary_id"].startswith("RXG:")


# ══════════════ 추가 커버리지 ══════════════
@pytest.mark.parametrize("mtype", list(MEMORY_TYPES))
def test_summary_per_type(tmp_path, monkeypatch, mtype):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _memory(e, ref="R-" + mtype, mtype=mtype)
    s = e.generate_summary("TYPE", mtype, T[5], commit=True)
    assert s.memory_count == 1


@pytest.mark.parametrize("ref", ["A", "B", "C", "D", "E"])
def test_multiple_memories(tmp_path, monkeypatch, ref):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = e.register_memory("l", ref, "SUCCESS_PATTERN", "t", "c", {}, T[0], commit=True)
    assert ev.source_ref == ref


def test_no_stray_writes_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_memory("l", "r", "SUCCESS_PATTERN", "t", "c", {}, T[0], commit=False)
    assert ledger.read_memory_events() == []


def test_memory_meta_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e, meta={"strategy": "momentum"})
    meta = e.memory_meta(m)
    assert meta["metadata"]["strategy"] == "momentum"


def test_metadata_preserved(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = e.register_memory("l", "r", "SUCCESS_PATTERN", "t", "c",
                           {"strategy": "s", "regime": "bull"}, T[0], commit=True)
    assert ev.metadata == {"regime": "bull", "strategy": "s"}


def test_input_digest_order():
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_verify_all_ledgers_present(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _memory(e)
    res = verify_chain()
    for fn, _ in ledger.ALL_LEDGERS:
        assert fn in res["ledgers"]


@pytest.mark.parametrize("st", list(MEMORY_STATES))
def test_state_membership(st):
    assert st in MEMORY_STATES


@pytest.mark.parametrize("k", list(SIM_KEYS))
def test_sim_key_similarity(tmp_path, monkeypatch, k):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = e.register_memory("l", "A", "SUCCESS_PATTERN", "a", "c", {k: "same"}, T[0],
                           commit=True).memory_id
    e.register_memory("l", "B", "SUCCESS_PATTERN", "b", "c", {k: "same"}, T[1], commit=True)
    sim = e.find_similar_experience(m1, 0.0, T[2], commit=True)
    assert len(sim.result_ids) == 1


@pytest.mark.parametrize("conf", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_pattern_confidences(tmp_path, monkeypatch, conf):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e, ref=f"R{conf}")
    p = e.record_success_pattern(m, "pat", "cond", conf, T[1], commit=True)
    assert p.confidence == conf


def test_episode_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = _memory(e, ref="A")
    m2 = _memory(e, ref="B", now=T[1])
    e.create_episode("ep", "d", [m1], T[2], commit=True)
    with pytest.raises(M.ImmutableEpisodeError):
        e.create_episode("ep", "d", [m1, m2], T[3], commit=True)


def test_memory_episodes_helper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = _memory(e, ref="A")
    ep = e.create_episode("ep", "d", [m1], T[2], commit=True).episode_id
    assert ep in e.memory_episodes(m1)


def test_experience_carries_agent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e)
    ex = e.record_experience(m, "s", "o", "l", "analyst_x", T[1], commit=True)
    assert ex.agent == "analyst_x"


def test_failure_recurrence_field(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _memory(e, mtype="FAILED_EXPERIMENT")
    f = e.record_failure(m, "app", "reason", 7, T[1], commit=True)
    assert f.recurrence == 7 and f.reason == "reason"


def test_similar_higher_score_ranked_first(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    base = e.register_memory("l", "BASE", "SUCCESS_PATTERN", "base", "c",
                             {"strategy": "m", "dataset": "d", "regime": "bull"}, T[0],
                             commit=True).memory_id
    e.register_memory("l", "HIGH", "SUCCESS_PATTERN", "high", "c",
                      {"strategy": "m", "dataset": "d", "regime": "bull"}, T[1], commit=True)
    e.register_memory("l", "LOW", "SUCCESS_PATTERN", "low", "c",
                      {"strategy": "m", "dataset": "x", "regime": "y"}, T[2], commit=True)
    sim = e.find_similar_experience(base, 0.0, T[3], commit=True)
    assert sim.scores[sim.result_ids[0]] >= sim.scores[sim.result_ids[-1]]


def test_retrieve_empty_when_none_retrievable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _memory(e)
    r = e.retrieve_memory("", "", T[3], commit=True)
    assert r.result_ids == []


def test_jaccard_pure():
    assert M.jaccard(frozenset({"a", "b"}), frozenset({"a", "b"})) == 1.0
    assert M.jaccard(frozenset({"a"}), frozenset({"b"})) == 0.0


def test_token_set_pure():
    assert "momentum" in M.token_set("Momentum Strategy")
    assert "a" not in M.token_set("a bb")


def test_summary_state_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _memory(e)
    s = e.generate_summary("ALL", "ALL", T[3], commit=True)
    assert s.state_distribution.get(M_RECORDED) == 1


def test_context_hash_preserved(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ev = e.register_memory("l", "r", "SUCCESS_PATTERN", "t", "special context", {}, T[0],
                           commit=True)
    assert ev.context_hash == M.context_digest("special context")


def test_end_to_end_memory(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = e.register_memory("autonomous_research_pipeline", "CYC1", "SUCCESS_PATTERN",
                           "walk-forward wins", "oos robust",
                           {"strategy": "momentum", "regime": "bull"}, T[0], commit=True).memory_id
    e.record_experience(m1, "backtest", "positive", "always validate oos", "analyst", T[1],
                        commit=True)
    e.record_success_pattern(m1, "walk-forward", "multi-window", 0.85, T[2], commit=True)
    e.make_retrievable(m1, T[3], commit=True)
    m2 = e.register_memory("autonomous_research_evaluation", "EV9", "FAILED_EXPERIMENT",
                           "in-sample overfit", "collapsed oos",
                           {"strategy": "momentum", "regime": "bear"}, T[4], commit=True).memory_id
    e.record_failure(m2, "in-sample-only", "no oos", 4, T[5], commit=True)
    ep = e.create_episode("momentum_study", "success vs failure", [m1, m2], T[6],
                          commit=True).episode_id
    e.build_lineage(ep, T[7], commit=True)
    sim = e.find_similar_experience(m1, 0.0, T[8], commit=True)
    assert m2 in sim.result_ids  # same strategy metadata
    r = e.retrieve_memory("walk-forward", "", T[9], commit=True)
    assert m1 in r.result_ids
    s = e.generate_summary("ALL", "ALL", T[10], commit=True)
    assert s.memory_count == 2 and s.failure_count == 1
    assert verify_chain()["ok"] is True
