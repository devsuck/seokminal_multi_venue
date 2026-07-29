"""P27 research_memory_intelligence 테스트 — 메모리 등록/불변/생애주기·교훈·패턴·성공/실패·진화(추가전용)·
검색 결정성·계보·verify·replay·CLI·보안·READ ONLY 상위. MEMORY DOES NOT DECIDE."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_memory_intelligence import ledger
from jarvis.research_memory_intelligence import models as M
from jarvis.research_memory_intelligence.engine import ResearchMemoryIntelligenceEngine
from jarvis.research_memory_intelligence.models import (
    CHANGE_TYPES,
    FORBIDDEN_VERBS,
    GENESIS,
    MEMORY_CATEGORIES,
    MEMORY_STATES,
    PATTERN_TYPES,
    M_ARCHIVED,
    M_CONNECTED,
    M_CREATED,
    M_EVOLVED,
    M_REINFORCED,
    IllegalMemoryTransition,
    UnknownEntityError,
    can_memory_transition,
    content_hash,
    evolve_confidence,
    jaccard,
)
from jarvis.research_memory_intelligence.verify import (
    duplicate_integrity,
    evolution_integrity,
    lineage_integrity,
    memory_lifecycle_integrity,
    pattern_integrity,
    retrieval_integrity,
    replay,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_memory_intelligence.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchMemoryIntelligenceEngine()


def _mem(e, source="kg:regime", category="DISCOVERY", content="regime filter improves sharpe",
         imp=0.6, now=T[0]):
    return e.register_memory(source, category, content, imp, now, commit=True).memory_id


# ═══════════════ memory registration ═══════════════
def test_register_memory(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().register_memory("kg:1", "DISCOVERY", "content", 0.7, T[0], commit=True)
    assert ev.to_state == M_CREATED
    assert ev.memory_id.startswith("KMM:")
    assert ev.memory_event_id.startswith("KME:")
    assert ev.content_hash.startswith("sha256:")


def test_memory_bad_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().register_memory("s", "NOPE", "c", now=T[0], commit=True)


def test_memory_immutable_content(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_memory("s", "DISCOVERY", "same", 0.5, T[0], commit=True)
    b = e.register_memory("s", "DISCOVERY", "same", 0.9, T[1], commit=True)
    assert a.memory_id == b.memory_id
    assert a.content_hash == b.content_hash
    assert len(ledger.memory_events(a.memory_id)) == 1  # genesis 유일


def test_memory_importance_clamped(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().register_memory("s", "DISCOVERY", "c", 5.0, T[0], commit=True)
    assert ev.importance_score == 1.0


def test_memory_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    assert any(a["artifact_type"] == "MEMORY" for a in ledger.read_artifacts())


def test_memory_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_memory("s", "DISCOVERY", "c", now=T[0], commit=False)
    assert ledger.read_memory_events() == []


@pytest.mark.parametrize("cat", MEMORY_CATEGORIES)
def test_memory_categories(tmp_path, monkeypatch, cat):
    _iso(tmp_path, monkeypatch)
    ev = _eng().register_memory("s", cat, "c", 0.5, T[0], commit=True)
    assert ev.category == cat


# ═══════════════ memory lifecycle ═══════════════
def test_memory_lifecycle_via_evolution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    e.evolve_memory(mem, "CONNECTED", "linked", now=T[1], commit=True)
    assert e.memory_state(mem) == M_CONNECTED
    e.evolve_memory(mem, "REINFORCED", "validated again", now=T[2], commit=True)
    assert e.memory_state(mem) == M_REINFORCED


def test_memory_archive(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    e.evolve_memory(mem, "CONNECTED", now=T[1], commit=True)
    e.evolve_memory(mem, "REINFORCED", now=T[2], commit=True)
    e.archive_memory(mem, now=T[3], commit=True)
    assert e.memory_state(mem) == M_ARCHIVED


def test_memory_deprecated_archives(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    e.evolve_memory(mem, "CONNECTED", now=T[1], commit=True)
    e.evolve_memory(mem, "DEPRECATED", "outdated", now=T[2], commit=True)
    assert e.memory_state(mem) == M_ARCHIVED


def test_memory_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    with pytest.raises(IllegalMemoryTransition):
        e.archive_memory(mem, now=T[1], commit=True)  # CREATED→ARCHIVED skip


def test_memory_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().archive_memory("KMM:nope", now=T[1], commit=True)


def test_memories_in_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    e.evolve_memory(mem, "CONNECTED", now=T[1], commit=True)
    assert mem in e.memories_in_state(M_CONNECTED)


@pytest.mark.parametrize("frm,to,ok", [
    (M_CREATED, M_CONNECTED, True), (M_CREATED, M_REINFORCED, False),
    (M_CONNECTED, M_REINFORCED, True), (M_CONNECTED, M_EVOLVED, True),
    (M_REINFORCED, M_EVOLVED, True), (M_REINFORCED, M_ARCHIVED, True),
    (M_EVOLVED, M_ARCHIVED, True), (M_ARCHIVED, M_CONNECTED, False),
])
def test_memory_transition_matrix(frm, to, ok):
    assert can_memory_transition(frm, to) is ok


@pytest.mark.parametrize("s", MEMORY_STATES)
def test_memory_states(s):
    assert s in MEMORY_STATES


# ═══════════════ lessons ═══════════════
def test_record_lesson(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    l = _eng().record_lesson("exp:1", "regime filter helps", {"sharpe": 0.2}, "HIGH", T[0],
                             commit=True)
    assert l.lesson_id.startswith("KML:")
    assert l.impact == "HIGH"


def test_lesson_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.record_lesson("o", "L", now=T[0], commit=True).lesson_id
    b = e.record_lesson("o", "L", now=T[1], commit=True).lesson_id
    assert a == b
    assert len(ledger.read_lessons()) == 1


# ═══════════════ patterns ═══════════════
def test_store_pattern(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _eng().store_pattern("SUCCESS_PATTERN", "regime-aware-sizing", 3, 0.8, T[0], commit=True)
    assert p.pattern_id.startswith("KMP:")
    assert p.occurrences == 3


def test_pattern_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().store_pattern("NOPE", "sig", now=T[0], commit=True)


def test_pattern_confidence_clamped(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _eng().store_pattern("DATA_PATTERN", "sig", 1, 9.0, T[0], commit=True)
    assert p.confidence == 1.0


@pytest.mark.parametrize("pt", PATTERN_TYPES)
def test_pattern_types(pt):
    assert pt in PATTERN_TYPES


# ═══════════════ success / failure memories ═══════════════
def test_record_success(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().record_success("exp:1", "beat benchmark OOS", {"sharpe": 1.5}, T[0], commit=True)
    assert s.success_id.startswith("KMS:")


def test_record_failure(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    f = _eng().record_failure("exp:2", "overfit in-sample", {"decay": 0.9}, T[0], commit=True)
    assert f.failure_id.startswith("KMF:")


def test_success_failure_distinct(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_success("o", "s", now=T[0], commit=True)
    e.record_failure("o", "f", now=T[1], commit=True)
    assert len(ledger.read_successes()) == 1
    assert len(ledger.read_failures()) == 1


# ═══════════════ knowledge evolution (append-only, confidence derived) ═══════════════
def test_evolve_memory(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    ev = e.evolve_memory(mem, "CONNECTED", "linked to exp2", now=T[1], commit=True)
    assert ev.event_id.startswith("KMV:")
    assert ev.change_type == "CONNECTED"


def test_evolve_bad_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    with pytest.raises(ValueError):
        e.evolve_memory(mem, "NOPE", now=T[1], commit=True)


def test_evolve_unknown_memory(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().evolve_memory("KMM:nope", "CONNECTED", now=T[0], commit=True)


def test_reinforcement_increases_confidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e, imp=0.5)
    base = e.memory_confidence(mem)
    e.evolve_memory(mem, "CONNECTED", now=T[1], commit=True)
    e.evolve_memory(mem, "REINFORCED", now=T[2], commit=True)
    assert e.memory_confidence(mem) > base


def test_weakening_decreases_confidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e, imp=0.6)
    e.evolve_memory(mem, "CONNECTED", now=T[1], commit=True)
    before = e.memory_confidence(mem)
    e.evolve_memory(mem, "WEAKENED", "contradictory evidence", now=T[2], commit=True)
    assert e.memory_confidence(mem) < before


def test_deprecation_zeroes_confidence(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e, imp=0.9)
    e.evolve_memory(mem, "CONNECTED", now=T[1], commit=True)
    e.evolve_memory(mem, "DEPRECATED", now=T[2], commit=True)
    assert e.memory_confidence(mem) == 0.0


def test_evolution_never_mutates_genesis(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    genesis_before = ledger.memory_events(mem)[0]
    e.evolve_memory(mem, "CONNECTED", now=T[1], commit=True)
    e.evolve_memory(mem, "REINFORCED", now=T[2], commit=True)
    genesis_after = ledger.memory_events(mem)[0]
    assert genesis_before == genesis_after  # 과거 메모리 절대 변경 없음


def test_evolve_confidence_helper():
    assert evolve_confidence(0.5, ["REINFORCED", "REINFORCED"]) == 0.7
    assert evolve_confidence(0.5, ["WEAKENED"]) == 0.4
    assert evolve_confidence(0.9, ["DEPRECATED"]) == 0.0


@pytest.mark.parametrize("ct", CHANGE_TYPES)
def test_change_types(ct):
    assert ct in CHANGE_TYPES


def test_connect_knowledge(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = _mem(e, content="a")
    m2 = _mem(e, content="b", now=T[1])
    ev = e.connect_knowledge(m1, m2, "related findings", T[2], commit=True)
    assert ev.change_type == "CONNECTED"
    assert ev.related_memory == m2


def test_connect_unknown_related(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = _mem(e)
    with pytest.raises(UnknownEntityError):
        e.connect_knowledge(m1, "KMM:nope", now=T[2], commit=True)


# ═══════════════ retrieval (deterministic, references only) ═══════════════
def test_retrieve_context(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e, source="kg:regime robustness", content="regime study")
    r = e.retrieve_context("regime robustness study", 5, T[1], commit=True)
    assert r.retrieval_id.startswith("KMR:")
    assert r.is_recommendation is False
    assert len(r.memory_refs) >= 1


def test_retrieve_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e, source="kg:alpha decay", content="decay study")
    _mem(e, source="kg:regime", content="regime study", now=T[1])
    r1 = e.retrieve_context("regime", 5, T[2], commit=False)
    r2 = e.retrieve_context("regime", 5, T[2], commit=False)
    assert r1.memory_refs == r2.memory_refs
    assert r1.scores == r2.scores


def test_retrieve_top_k(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    for i in range(5):
        _mem(e, source=f"kg:{i}", content=f"study {i}", now=T[i])
    r = e.retrieve_context("study", 2, T[9], commit=True)
    assert len(r.memory_refs) == 2


def test_retrieve_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().retrieve_context("anything", 5, T[0], commit=True)
    assert r.memory_refs == []


def test_jaccard():
    assert jaccard("regime robustness", "regime robustness") == 1.0
    assert jaccard("a b", "c d") == 0.0
    assert 0.0 < jaccard("regime filter", "regime study") < 1.0


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers_present():
    for k in ("alpha_intelligence", "knowledge_graph", "agent_governance", "decision_intelligence",
              "simulation", "research_memory", "research_automation", "monitoring", "reliability",
              "autonomous_research", "agent_coordination"):
        assert k in ledger.SOURCE_LAYERS


def test_source_count_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("kg_entities.jsonl")
    with open(p, "w") as f:
        for i in range(4):
            f.write(json.dumps({"entity_id": f"e{i}"}) + "\n")
    before = open(p).read()
    assert ledger.source_count("knowledge_graph") == 4
    assert open(p).read() == before


def test_source_ref_exists(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("rm_lessons.jsonl")
    with open(p, "w") as f:
        f.write(json.dumps({"lesson_id": "rm:l1"}) + "\n")
    assert ledger.source_ref_exists("research_memory", "rm:l1") is True
    assert ledger.source_ref_exists("research_memory", "rm:zz") is False


def test_all_source_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    counts = ledger.all_source_counts()
    assert set(counts) == set(ledger.SOURCE_LAYERS)


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    e.evolve_memory(mem, "CONNECTED", now=T[1], commit=True)
    e.record_lesson("o", "L", now=T[2], commit=True)
    e.store_pattern("SUCCESS_PATTERN", "sig", 2, 0.7, T[3], commit=True)
    e.record_success("o", "s", now=T[4], commit=True)
    e.record_failure("o", "f", now=T[5], commit=True)
    e.retrieve_context("q", 5, T[6], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    p = sp("rmi_memories.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["importance_score"] = 0.999
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_lesson("a", "L1", now=T[0], commit=True)
    e.record_lesson("b", "L2", now=T[1], commit=True)
    p = sp("rmi_lessons.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate_memory(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    p = sp("rmi_memories.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_memory_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    e.evolve_memory(mem, "CONNECTED", now=T[1], commit=True)
    assert memory_lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e, content="a")
    _mem(e, content="b", now=T[1])
    assert duplicate_integrity()["ok"] is True


def test_evolution_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    e.evolve_memory(mem, "REINFORCED", now=T[1], commit=True)
    assert evolution_integrity()["ok"] is True


def test_evolution_integrity_detects_bad_change(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    e.evolve_memory(mem, "REINFORCED", now=T[1], commit=True)
    p = sp("rmi_evolution_events.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["change_type"] = "HACKED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert evolution_integrity()["ok"] is False


def test_pattern_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.store_pattern("ROBUSTNESS_PATTERN", "sig", now=T[0], commit=True)
    assert pattern_integrity()["ok"] is True


def test_retrieval_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    e.retrieve_context("q", 5, T[1], commit=True)
    assert retrieval_integrity()["ok"] is True


def test_retrieval_integrity_detects_recommendation(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e)
    e.retrieve_context("q", 5, T[1], commit=True)
    p = sp("rmi_retrievals.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_recommendation"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert retrieval_integrity()["ok"] is False


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m1 = _mem(e, content="a")
    m2 = _mem(e, content="b", now=T[1])
    e.connect_knowledge(m1, m2, now=T[2], commit=True)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e, source="kg:regime robustness")
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e, category="INSIGHT")
    e.evolve_memory(mem, "CONNECTED", now=T[1], commit=True)
    e.record_lesson("o", "L", now=T[2], commit=True)
    r = e.generate_report("SYSTEM", T[3], commit=True)
    assert r.report_id.startswith("KMO:")
    assert r.is_binding is False
    assert r.memory_count == 1
    assert r.lesson_count == 1
    assert r.category_distribution.get("INSIGHT") == 1
    assert r.change_distribution.get("CONNECTED") == 1


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "DECIDE" in r.disclaimer


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["REMEMBER", "CONNECT", "REINFORCE", "RETRIEVE", "EVOLVE",
                                  "PRESERVE"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


@pytest.mark.parametrize("v", ["EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL",
                                "DEPLOY_STRATEGY", "ACTIVATE_LIVE", "APPROVE_FOR_TRADING",
                                "SELECT_STRATEGY"])
def test_forbidden_membership(v):
    assert v in FORBIDDEN_VERBS


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.memory_id, ("s", "DISCOVERY", "c"), "KMM:"),
    (M.memory_event_id, ("m", "CREATED", 0), "KME:"),
    (M.pattern_id, ("SUCCESS_PATTERN", "sig"), "KMP:"),
    (M.lesson_id, ("o", "l"), "KML:"),
    (M.success_id, ("o", "s"), "KMS:"),
    (M.failure_id, ("o", "f"), "KMF:"),
    (M.evolution_event_id, ("m", "REINFORCED", 0), "KMV:"),
    (M.retrieval_id, ("q", 0), "KMR:"),
    (M.report_id, ("s", "t"), "KMO:"),
    (M.artifact_id, ("MEMORY", "r"), "KMA:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_ids_deterministic():
    assert M.memory_id("s", "DISCOVERY", "c") == M.memory_id("s", "DISCOVERY", "c")


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


# ═══════════════ summary ═══════════════
def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    mem = _mem(e)
    e.evolve_memory(mem, "CONNECTED", now=T[1], commit=True)
    e.record_lesson("o", "L", now=T[2], commit=True)
    s = e.summary(T[9])
    assert s.memory_count == 1
    assert s.lesson_count == 1
    assert s.evolution_event_count == 1


def test_list_memories(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _mem(e, content="a")
    _mem(e, content="b", now=T[1])
    assert len(e.list_memories()) == 2


# ═══════════════ CLI ═══════════════
def test_cli_memory(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_intelligence.__main__ import main
    assert main(["memory", "--source", "kg:1", "--category", "DISCOVERY", "--content", "c",
                 "--importance", "0.7", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["memory"]["to_state"] == "CREATED"


def test_cli_lesson(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_intelligence.__main__ import main
    assert main(["lesson", "--origin", "o", "--lesson", "L", "--impact", "HIGH", "--commit"]) == 0


def test_cli_pattern(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_intelligence.__main__ import main
    assert main(["pattern", "--type", "DATA_PATTERN", "--signature", "sig", "--occurrences", "3",
                 "--commit"]) == 0


def test_cli_evolution(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_intelligence.__main__ import main
    main(["memory", "--source", "s", "--category", "DISCOVERY", "--content", "c", "--commit"])
    mem = json.loads(capsys.readouterr().out)["memory"]["memory_id"]
    assert main(["evolution", "--memory", mem, "--change", "CONNECTED", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["evolution"]["change_type"] == "CONNECTED"


def test_cli_retrieve(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_intelligence.__main__ import main
    main(["memory", "--source", "kg:regime", "--category", "DISCOVERY", "--content", "regime",
          "--commit"])
    capsys.readouterr()
    assert main(["retrieve", "--query", "regime", "--top-k", "3", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["retrieval"]["is_recommendation"] is False


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_intelligence.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_intelligence.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_intelligence.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_memory_intelligence.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().register_memory("s", "DISCOVERY", "c", now=T[0], commit=True)
    with pytest.raises(Exception):
        ev.category = "x"


def test_nine_ledgers():
    assert len(ledger.ALL_LEDGERS) == 9


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rmi_")


def test_required_ledgers_present():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    for req in ("rmi_memories.jsonl", "rmi_patterns.jsonl", "rmi_lessons.jsonl",
                "rmi_successes.jsonl", "rmi_failures.jsonl", "rmi_evolution_events.jsonl",
                "rmi_retrievals.jsonl", "rmi_reports.jsonl", "rmi_artifacts.jsonl"):
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
    bad = ("execute", "deploy", "trade", "allocate", "approve", "select", "execute_trade",
           "place_order", "allocate_capital", "deploy_strategy", "activate_live",
           "approve_for_trading", "select_strategy")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_destructive_ledger_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def overwrite_", "def drop_", "def truncate", "def purge_"):
        assert bad not in src


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src


def test_engine_no_forbidden_methods():
    e = _eng()
    for attr in ("execute", "deploy", "trade", "allocate", "approve", "select"):
        assert not hasattr(e, attr)


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 상위 소스 시드(READ ONLY 대상): P10.5 KG + P20 memory
    with open(sp("kg_entities.jsonl"), "w") as f:
        f.write(json.dumps({"entity_id": "kg:regime"}) + "\n")
    with open(sp("rm_lessons.jsonl"), "w") as f:
        f.write(json.dumps({"lesson_id": "rm:l1"}) + "\n")
    e = _eng()
    # 연구 결과 → 지식 추출 → 메모리 생성
    m1 = e.register_memory("kg:regime", "DISCOVERY", "regime filter improves robustness", 0.7, T[0],
                           commit=True).memory_id
    m2 = e.register_memory("exp:42", "SUCCESS", "OOS sharpe beat benchmark", 0.6, T[1],
                           commit=True).memory_id
    # 교훈·패턴·성공·실패 메모리
    e.record_lesson("exp:42", "regime-aware sizing reduces drawdown", {"dd": -0.15}, "HIGH", T[2],
                    commit=True)
    e.store_pattern("SUCCESS_PATTERN", "regime-aware-sizing", 3, 0.8, T[3], commit=True)
    e.record_success("exp:42", "beat benchmark", {"sharpe": 1.4}, T[4], commit=True)
    e.record_failure("exp:7", "overfit to regime", {"decay": 0.9}, T[5], commit=True)
    # 패턴 연관 → 역사적 연결 → 진화(강화)
    e.connect_knowledge(m1, m2, "same regime insight", T[6], commit=True)
    e.evolve_memory(m1, "REINFORCED", "validated in new experiment", now=T[7], commit=True)
    conf = e.memory_confidence(m1)
    assert conf > 0.7  # 강화로 상승
    # 모순 증거 → 약화
    e.evolve_memory(m2, "WEAKENED", "contradictory OOS result", now=T[8], commit=True)
    # 미래 연구 컨텍스트 검색(참조만, 결정적)
    r = e.retrieve_context("regime robustness", 5, T[9], commit=True)
    assert m1 in r.memory_refs
    assert r.is_recommendation is False
    # 리포트
    rep = e.generate_report("SYSTEM", T[10], commit=True)
    assert rep.memory_count == 2
    assert rep.lesson_count == 1
    assert rep.is_binding is False  # MEMORY DOES NOT DECIDE
    # 과거 메모리 절대 변경 없음(genesis 불변)
    assert ledger.memory_events(m1)[0]["from_state"] == GENESIS
    assert open(sp("kg_entities.jsonl")).read()  # 상위 원장 여전히 존재·불변
    assert verify_chain()["ok"] is True
    assert replay(e, T[11])["deterministic"] is True
