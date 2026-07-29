"""P10.21 Research Governance Knowledge Memory 테스트. **재사용 거버넌스 지식 저장·조회 전용.**

지식 항목(불변·content_hash·범주)·경험(기록·계보)·교훈(저장·조회·불변)·해소 이력(기록 전용)·링크(그래프·
유형·미등록 노드·순환)·스냅샷(결정적·중복)·검색(유사도 일관성)·리포트(결정적)·verify(체인/변조/중복/링크/
계보)·replay·상위 READ ONLY 보호·CLI·보안(금지import·실행/변경/승인/배포 없음·상위 원장 무변경·삭제 API
없음·불변·MEMORY≠AUTHORITY·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.governance_memory import ledger
from jarvis.governance_memory import models as M
from jarvis.governance_memory.engine import GovernanceMemoryEngine
from jarvis.governance_memory.models import (
    CONTRADICTS,
    DERIVED_FROM,
    RELATED_TO,
    SIMILAR_TO,
    ImmutableEntryError,
    ImmutableExperienceError,
    InvalidEntryCategory,
    InvalidLinkType,
    InvalidMemoryLink,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

_HI = {"entry_coverage": 0.9, "lesson_density": 0.85, "link_connectivity": 0.8,
       "resolution_reuse": 0.9, "snapshot_freshness": 0.8}
_LO = {"entry_coverage": 0.1, "lesson_density": 0.2, "link_connectivity": 0.1,
       "resolution_reuse": 0.2, "snapshot_freshness": 0.1}


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.governance_memory.ledger.state_path", sp)
    return sp


def _eng():
    return GovernanceMemoryEngine()


def _entry(eng, cat=None, src="rg:ST1", content="lesson content", meta=None, commit=True):
    return eng.create_entry(cat or M.K_RESEARCH_LESSON, src, content, meta or {}, "", T0,
                            commit=commit)


def _exp(eng, ev="rc:violation1", outcome="FAILURE", impact="HIGH", layer="research_compliance",
         commit=True):
    return eng.record_experience(ev, outcome, impact, "detail", layer, T0, commit=commit)


def _lesson(eng, obs="OOS collapse observed", concl="always walk-forward", commit=True):
    return eng.store_lesson(obs, concl, ["ev1"], "", T0, commit=commit)


def _full(eng):
    """experience→lesson→entry(x2)→link→resolution→snapshot→report end-to-end."""
    x = _exp(eng)
    l = eng.store_lesson("obs", "concl", ["ev1"], x.experience_id, T0, commit=True)
    e1 = eng.create_entry(M.K_RESEARCH_LESSON, "rg:ST1", "c1", {}, l.lesson_id, T0, commit=True)
    e2 = eng.create_entry(M.K_RESEARCH_LESSON, "rg:ST2", "c2", {}, "", T0, commit=True)
    eng.link_memory(e2.entry_id, DERIVED_FROM, e1.entry_id, T0, commit=True)
    eng.record_resolution("issue1", "response1", "SUCCESS", T0, commit=True)
    eng.create_snapshot("snap1", "E1", [e1.entry_id, e2.entry_id], {"cluster": 1}, T0, commit=True)
    eng.generate_report("GLOBAL", _HI, T1, commit=True)
    return x, l, e1, e2


# ── Knowledge Entry ──
def test_entry_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _entry(_eng())
    assert e.entry_id.startswith("GME:")
    assert e.category == M.K_RESEARCH_LESSON
    assert e.content_hash.startswith("sha256:")


def test_entry_invalid_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidEntryCategory):
        _eng().create_entry("not_a_cat", "s", "c", {}, "", T0, commit=True)


def test_entry_all_categories(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, cat in enumerate(M.ENTRY_CATEGORIES):
        e = eng.create_entry(cat, f"s{i}", "c", {}, "", T0, commit=True)
        assert e.category == cat
    assert len(ledger.read_entries()) == len(M.ENTRY_CATEGORIES)


def test_entry_immutable_content(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _entry(eng, content="c1")
    with pytest.raises(ImmutableEntryError):
        _entry(eng, content="c2")


def test_entry_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _entry(eng)
    b = _entry(eng)
    assert a.entry_id == b.entry_id
    assert len(ledger.read_entries()) == 1


def test_entry_content_hash_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _entry(_eng(), content="abc")
    assert e.content_hash == M.knowledge_content_hash("abc")


def test_entry_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _entry(_eng())
    assert e.entry_id == M.entry_id(M.K_RESEARCH_LESSON, "rg:ST1")


def test_entry_not_committed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _entry(_eng(), commit=False)
    assert ledger.read_entries() == []


def test_entry_metadata_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _entry(_eng(), meta={"tag": "risk"})
    assert e.metadata == {"tag": "risk"}


def test_entry_parent_links_lesson(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = _lesson(eng)
    e = eng.create_entry(M.K_RESEARCH_LESSON, "rg:ST1", "c", {}, l.lesson_id, T0, commit=True)
    ea = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == e.entry_id and a["artifact_type"] == M.ART_ENTRY)
    assert ea["parent_artifact"] == M.artifact_id(M.ART_LESSON, l.lesson_id)


# ── Experience ──
def test_experience_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    x = _exp(_eng())
    assert x.experience_id.startswith("GMX:")
    assert x.outcome == "FAILURE"
    assert x.impact == "HIGH"


def test_experience_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _exp(eng, outcome="FAILURE")
    with pytest.raises(ImmutableExperienceError):
        _exp(eng, outcome="SUCCESS")


def test_experience_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _exp(eng)
    b = _exp(eng)
    assert a.experience_id == b.experience_id
    assert len(ledger.read_experiences()) == 1


def test_experience_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    x = _exp(_eng())
    assert x.experience_id == M.experience_id("rc:violation1")


def test_experience_lineage_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    x = _exp(eng)
    assert ledger.artifact_exists(M.artifact_id(M.ART_LAYER, "research_compliance"))
    xa = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == x.experience_id and a["artifact_type"] == M.ART_EXPERIENCE)
    assert xa["parent_artifact"] == M.artifact_id(M.ART_LAYER, "research_compliance")


# ── Lesson ──
def test_lesson_store(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    l = _lesson(_eng())
    assert l.lesson_id.startswith("GML:")
    assert l.conclusion == "always walk-forward"


def test_lesson_immutable_identity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.store_lesson("obs", "concl", ["e1"], "", T0, commit=True)
    b = eng.store_lesson("obs", "concl", ["e2"], "", T0, commit=True)
    assert a.lesson_id == b.lesson_id
    assert a.evidence == b.evidence == ["e1"]  # first wins
    assert len(ledger.read_lessons()) == 1


def test_lesson_retrieval(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    l = _lesson(eng)
    assert ledger.get_lesson(l.lesson_id)["lesson_id"] == l.lesson_id


def test_lesson_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    l = _lesson(_eng())
    assert l.lesson_id == M.lesson_id("OOS collapse observed", "always walk-forward")


def test_lesson_parent_links_experience(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    x = _exp(eng)
    l = eng.store_lesson("o", "c", [], x.experience_id, T0, commit=True)
    la = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == l.lesson_id and a["artifact_type"] == M.ART_LESSON)
    assert la["parent_artifact"] == M.artifact_id(M.ART_EXPERIENCE, x.experience_id)


def test_lesson_frequency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.store_lesson("o1", "same_conclusion", [], "", T0, commit=True)
    eng.store_lesson("o2", "same_conclusion", [], "", T0, commit=True)
    freq = eng.lesson_frequency()
    assert freq.get("same_conclusion") == 2


# ── Resolution History ──
def test_resolution_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().record_resolution("issue1", "response1", "SUCCESS", T0, commit=True)
    assert r.resolution_id.startswith("GMH:")
    assert r.outcome == "SUCCESS"


def test_resolution_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.record_resolution("i1", "r1", "SUCCESS", T0, commit=True)
    b = eng.record_resolution("i1", "r1", "FAILURE", T0, commit=True)
    assert a.resolution_id == b.resolution_id
    assert a.outcome == b.outcome == "SUCCESS"
    assert len(ledger.read_resolutions()) == 1


def test_resolution_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().record_resolution("i1", "r1", "SUCCESS", T0, commit=True)
    assert r.resolution_id == M.resolution_id("i1", "r1")


# ── Memory Link ──
def test_link_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e1 = _entry(eng, src="s1")
    e2 = _entry(eng, src="s2")
    l = eng.link_memory(e1.entry_id, SIMILAR_TO, e2.entry_id, T0, commit=True)
    assert l.link_id.startswith("GMK:")
    assert l.link_type == SIMILAR_TO


def test_link_invalid_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e1 = _entry(eng, src="s1")
    e2 = _entry(eng, src="s2")
    with pytest.raises(InvalidLinkType):
        eng.link_memory(e1.entry_id, "loves", e2.entry_id, T0, commit=True)


def test_link_all_types(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e1 = _entry(eng, src="s1")
    e2 = _entry(eng, src="s2")
    for lt in M.LINK_TYPES:
        l = eng.link_memory(e1.entry_id, lt, e2.entry_id, T0, commit=True)
        assert l.link_type == lt
    assert len(ledger.read_links()) == len(M.LINK_TYPES)


def test_link_missing_from(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e2 = _entry(eng, src="s2")
    with pytest.raises(InvalidMemoryLink):
        eng.link_memory("GME:ghost", SIMILAR_TO, e2.entry_id, T0, commit=True)


def test_link_missing_to(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e1 = _entry(eng, src="s1")
    with pytest.raises(InvalidMemoryLink):
        eng.link_memory(e1.entry_id, SIMILAR_TO, "GME:ghost", T0, commit=True)


def test_link_self_reference(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e1 = _entry(eng, src="s1")
    with pytest.raises(InvalidMemoryLink):
        eng.link_memory(e1.entry_id, SIMILAR_TO, e1.entry_id, T0, commit=True)


def test_link_derived_from_cycle_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _entry(eng, src="a")
    b = _entry(eng, src="b")
    eng.link_memory(a.entry_id, DERIVED_FROM, b.entry_id, T0, commit=True)
    with pytest.raises(InvalidMemoryLink):
        eng.link_memory(b.entry_id, DERIVED_FROM, a.entry_id, T0, commit=True)


def test_link_symmetric_allowed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _entry(eng, src="a")
    b = _entry(eng, src="b")
    eng.link_memory(a.entry_id, SIMILAR_TO, b.entry_id, T0, commit=True)
    # reverse similar_to is allowed (associative, not acyclic)
    eng.link_memory(b.entry_id, SIMILAR_TO, a.entry_id, T0, commit=True)
    assert len(ledger.read_links()) == 2


def test_link_cross_object_types(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    x = _exp(eng)
    l = _lesson(eng)
    link = eng.link_memory(l.lesson_id, DERIVED_FROM, x.experience_id, T0, commit=True)
    assert link.from_ref == l.lesson_id


def test_link_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _entry(eng, src="a")
    b = _entry(eng, src="b")
    l = eng.link_memory(a.entry_id, RELATED_TO, b.entry_id, T0, commit=True)
    assert l.link_id == M.link_id(a.entry_id, RELATED_TO, b.entry_id)


def test_link_cycle_helper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _entry(eng, src="a")
    b = _entry(eng, src="b")
    eng.link_memory(a.entry_id, DERIVED_FROM, b.entry_id, T0, commit=True)
    assert eng.link_cycle() == []


# ── Retrieval / Search ──
def test_find_related(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _entry(eng, src="a")
    b = _entry(eng, src="b")
    eng.link_memory(a.entry_id, RELATED_TO, b.entry_id, T0, commit=True)
    assert eng.find_related(a.entry_id) == [b.entry_id]
    assert eng.find_related(b.entry_id) == [a.entry_id]  # bidirectional


def test_find_related_by_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _entry(eng, src="a")
    b = _entry(eng, src="b")
    c = _entry(eng, src="c")
    eng.link_memory(a.entry_id, SIMILAR_TO, b.entry_id, T0, commit=True)
    eng.link_memory(a.entry_id, RELATED_TO, c.entry_id, T0, commit=True)
    assert eng.find_related(a.entry_id, SIMILAR_TO) == [b.entry_id]


def test_similar_entries(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.create_entry(M.K_FAILURE_PATTERN, "s1", "c", {}, "", T0, commit=True)
    b = eng.create_entry(M.K_FAILURE_PATTERN, "s2", "c", {}, "", T0, commit=True)
    eng.create_entry(M.K_GOVERNANCE_RULE, "s3", "c", {}, "", T0, commit=True)
    assert eng.similar_entries(a.entry_id) == [b.entry_id]


def test_search_consistency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _entry(eng, src="a", cat=M.K_FAILURE_PATTERN)
    b = eng.create_entry(M.K_FAILURE_PATTERN, "b", "c", {}, "", T0, commit=True)
    eng.link_memory(a.entry_id, RELATED_TO, b.entry_id, T0, commit=True)
    assert eng.search(a.entry_id) == eng.search(a.entry_id)  # deterministic


def test_find_related_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().find_related("GME:none") == []


# ── Snapshot ──
def test_snapshot_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().create_snapshot("snap1", "E1", ["GME:a", "GME:b"], {"k": 1}, T0, commit=True)
    assert s.snapshot_id.startswith("GMS:")
    assert s.entry_count == 2


def test_snapshot_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.create_snapshot("snap1", "E1", ["b", "a"], {"k": 1}, T0, commit=False)
    b = eng.create_snapshot("snap1", "E1", ["a", "b"], {"k": 1}, T0, commit=False)
    assert a.snapshot_hash == b.snapshot_hash
    assert a.collected_entries == b.collected_entries == ["a", "b"]


def test_snapshot_duplicate_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_snapshot("snap1", "E1", ["a"], {}, T0, commit=True)
    eng.create_snapshot("snap1", "E1", ["a"], {}, T0, commit=True)
    assert len(ledger.read_snapshots()) == 1


def test_snapshot_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().create_snapshot("snap1", "E1", [], {}, T0, commit=True)
    assert s.snapshot_id == M.snapshot_id("snap1", "E1")


# ── Memory intelligence ──
def test_knowledge_clusters(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _entry(eng, src="a")
    b = _entry(eng, src="b")
    c = _entry(eng, src="c")
    d = _entry(eng, src="d")
    eng.link_memory(a.entry_id, RELATED_TO, b.entry_id, T0, commit=True)
    eng.link_memory(c.entry_id, RELATED_TO, d.entry_id, T0, commit=True)
    clusters = eng.knowledge_clusters()
    assert len(clusters) == 2


def test_knowledge_gaps(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _entry(eng, src="a")
    b = _entry(eng, src="b")
    c = _entry(eng, src="c")  # unlinked
    eng.link_memory(a.entry_id, RELATED_TO, b.entry_id, T0, commit=True)
    assert eng.knowledge_gaps() == [c.entry_id]


def test_connected_components_helper():
    comps = M.connected_components([("a", "b"), ("b", "c"), ("x", "y")])
    assert [len(c) for c in comps] == [3, 2]


# ── Score / analyze ──
def test_memory_score_high():
    assert M.memory_score(_HI) > 0.7


def test_memory_score_low():
    assert M.memory_score(_LO) < 0.4


def test_memory_weights_sum_one():
    assert abs(sum(M.MEMORY_WEIGHTS.values()) - 1.0) < 1e-9


def test_memory_health_labels():
    assert M.memory_health(_HI) == "HEALTHY"
    assert M.memory_health(_LO) == "DEGRADED"
    assert M.memory_health({"entry_coverage": 1.0, "lesson_density": 1.0}) == "WARNING"


def test_analyze(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().analyze(_HI)
    assert res["memory_health"] == "HEALTHY"
    assert res["memory_score"] > 0.7


def test_impact_weight():
    assert M.impact_weight("CRITICAL") == 1.0
    assert M.impact_weight("???") == 0.0


# ── Report ──
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert r.report_id.startswith("GMR:")
    assert r.entry_count >= 2
    assert r.lesson_count >= 1
    assert r.link_count >= 1


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    a = eng.generate_report("GLOBAL", _HI, T2, commit=False)
    b = eng.generate_report("GLOBAL", _HI, T2, commit=False)
    assert a.to_dict() == b.to_dict()


def test_report_clusters(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert r.cluster_count >= 1
    assert r.largest_cluster_size >= 2


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    assert "MEMORY ≠ AUTHORITY" in r.disclaimer


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_report("GLOBAL", _HI, T0, commit=True)
    eng.generate_report("GLOBAL", _HI, T0, commit=True)
    assert len(ledger.read_reports()) == 1


def test_report_no_trading_verbs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    d = r.to_dict()
    d.pop("disclaimer")
    blob = json.dumps(d, ensure_ascii=False).lower()
    for verb in ("buy", "sell", "place_order", "deploy", "allocate_capital"):
        assert verb not in blob


def test_report_category_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    r = eng.generate_report("GLOBAL", _HI, T2, commit=True)
    assert M.K_RESEARCH_LESSON in r.entry_category_distribution


# ── Lineage / verify ──
def test_verify_lineage_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.verify_lineage()["ok"] is True


def test_trace_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    x = _exp(eng)
    l = eng.store_lesson("o", "c", [], x.experience_id, T0, commit=True)
    anc = eng.trace_lineage(M.artifact_id(M.ART_LESSON, l.lesson_id))
    assert M.artifact_id(M.ART_EXPERIENCE, x.experience_id) in anc


def test_verify_chain_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.governance_memory.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] >= 1


def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_memory.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _entry(eng)
    p = sp("gm_entries.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["source_reference"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.governance_memory.verify import verify_ledger
    assert verify_ledger(ledger.ENTRIES)["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _entry(eng, src="s1")
    _entry(eng, src="s2")
    p = sp("gm_entries.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.governance_memory.verify import verify_ledger
    assert verify_ledger(ledger.ENTRIES)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _entry(eng)
    p = sp("gm_entries.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows.append(dict(rows[0]))
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.governance_memory.verify import verify_ledger, duplicate_entry_validation
    assert verify_ledger(ledger.ENTRIES)["ok"] is False
    assert duplicate_entry_validation()["ok"] is False


def test_verify_link_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.governance_memory.verify import link_validation
    assert link_validation()["ok"] is True


def test_verify_detects_dangling_link(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _entry(eng, src="a")
    b = _entry(eng, src="b")
    eng.link_memory(a.entry_id, RELATED_TO, b.entry_id, T0, commit=True)
    # inject a link referencing a ghost node bypassing engine guards
    from jarvis.governance_memory.models import content_hash, link_id
    lid = link_id(a.entry_id, RELATED_TO, "GME:ghost")
    rec = {"link_id": lid, "from_ref": a.entry_id, "link_type": RELATED_TO, "to_ref": "GME:ghost",
           "created_at": T0, "input_hash": "", "record_hash": "",
           "previous_hash": ledger.links_head()["record_hash"]}
    rec["record_hash"] = content_hash(rec)
    ledger.append_link(rec)
    from jarvis.governance_memory.verify import link_validation
    res = link_validation()
    assert res["ok"] is False
    assert any("dangling_reference" in i for i in res["issues"])


def test_verify_detects_link_cycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _entry(eng, src="a")
    b = _entry(eng, src="b")
    eng.link_memory(a.entry_id, DERIVED_FROM, b.entry_id, T0, commit=True)
    # inject reverse derived_from bypassing guard
    from jarvis.governance_memory.models import content_hash, link_id, DERIVED_FROM as DF
    lid = link_id(b.entry_id, DF, a.entry_id)
    rec = {"link_id": lid, "from_ref": b.entry_id, "link_type": DF, "to_ref": a.entry_id,
           "created_at": T0, "input_hash": "", "record_hash": "",
           "previous_hash": ledger.links_head()["record_hash"]}
    rec["record_hash"] = content_hash(rec)
    ledger.append_link(rec)
    from jarvis.governance_memory.verify import link_validation
    res = link_validation()
    assert res["ok"] is False
    assert any("link_cycle" in i for i in res["issues"])


def test_verify_full_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.governance_memory.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["link"]["ok"] is True
    assert res["duplicate"]["ok"] is True
    assert res["lineage"]["ok"] is True


def test_verify_lineage_cycle_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _entry(eng)
    from jarvis.governance_memory.models import content_hash
    h = ledger.artifacts_head()["record_hash"]
    a1 = {"artifact_id": "GMA:c1", "artifact_type": "ENTRY", "ref_id": "x1",
          "parent_artifact": "GMA:c2", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": h}
    a1["record_hash"] = content_hash(a1)
    ledger.append_artifact(a1)
    a2 = {"artifact_id": "GMA:c2", "artifact_type": "ENTRY", "ref_id": "x2",
          "parent_artifact": "GMA:c1", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": a1["record_hash"]}
    a2["record_hash"] = content_hash(a2)
    ledger.append_artifact(a2)
    res = eng.verify_lineage()
    assert res["ok"] is False
    assert any("cycle" in i for i in res["issues"])


# ── replay / summary ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    from jarvis.governance_memory.verify import replay
    assert replay(eng, T0)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert s.entry_count >= 2
    assert s.experience_count >= 1
    assert s.lesson_count >= 1
    assert s.resolution_count >= 1
    assert s.link_count >= 1
    assert s.snapshot_count >= 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    assert eng.summary(T0).to_dict() == eng.summary(T0).to_dict()


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


def test_upstream_layers_covered_read_only():
    for layer in ("governance_feedback", "research_compliance", "research_observability"):
        assert layer in ledger.SOURCE_LEDGERS


# ── CLI ──
def test_cli_entry(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_memory.__main__ import main
    rc = main(["entry", "--category", "research_lesson", "--source-reference", "rg:ST1",
               "--content", "c", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["entry"]["entry_id"].startswith("GME:")


def test_cli_experience(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_memory.__main__ import main
    rc = main(["experience", "--event-reference", "rc:v1", "--outcome", "FAILURE", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["experience"]["experience_id"].startswith("GMX:")


def test_cli_lesson(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_memory.__main__ import main
    rc = main(["lesson", "--observation", "o", "--conclusion", "c", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["lesson"]["lesson_id"].startswith("GML:")


def test_cli_link(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_memory.__main__ import main
    main(["entry", "--category", "research_lesson", "--source-reference", "a", "--commit"])
    ea = json.loads(capsys.readouterr().out)["entry"]["entry_id"]
    main(["entry", "--category", "research_lesson", "--source-reference", "b", "--commit"])
    eb = json.loads(capsys.readouterr().out)["entry"]["entry_id"]
    rc = main(["link", "--from-ref", ea, "--link-type", "similar_to", "--to-ref", eb, "--commit"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["link"]["link_id"].startswith("GMK:")
    assert out["cycle"] == []


def test_cli_search(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_memory.__main__ import main
    main(["entry", "--category", "research_lesson", "--source-reference", "a", "--commit"])
    ea = json.loads(capsys.readouterr().out)["entry"]["entry_id"]
    rc = main(["search", "--ref", ea])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ref"] == ea


def test_cli_snapshot(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_memory.__main__ import main
    rc = main(["snapshot", "--name", "s1", "--epoch", "E1", "--entries", "a,b", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["snapshot"]["snapshot_id"].startswith("GMS:")


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_memory.__main__ import main
    rc = main(["report", "--metrics-json", json.dumps(_HI), "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["report"]["report_id"].startswith("GMR:")


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_memory.__main__ import main
    main(["entry", "--category", "research_lesson", "--source-reference", "a", "--commit"])
    capsys.readouterr()
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_memory.__main__ import main
    main(["entry", "--category", "research_lesson", "--source-reference", "a", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.governance_memory.__main__ import main
    rc = main(["summary"])
    assert rc == 0
    assert "entry_count" in json.loads(capsys.readouterr().out)


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.governance_memory.engine as eng_mod
    import jarvis.governance_memory.models as mdl_mod
    import jarvis.governance_memory.ledger as led_mod
    import jarvis.governance_memory.verify as ver_mod
    import jarvis.governance_memory.__main__ as cli_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod, cli_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "execution", _j + "broker", _j + "order",
                 _j + "portfolio_execution", _j + "capital_allocation", _j + "live_trading",
                 _j + "permission", _j + "risk_controller",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "modify_policy(", "change_permission(", "auto_apply(",
                 "auto_execute("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_execution_keyword_methods():
    import jarvis.governance_memory.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def execute", "def deploy", "def trade", "def place_order",
               "def allocate_capital", "def modify_policy", "def change_permission",
               "def auto_apply", "def auto_execute"):
        assert kw not in src


def test_no_execution_authority_api():
    api = set(dir(GovernanceMemoryEngine))
    for banned in ("execute", "deploy", "trade", "place_order", "allocate_capital",
                   "modify_policy", "change_permission", "auto_apply", "auto_execute"):
        assert banned not in api


def test_memory_not_authority(tmp_path, monkeypatch):
    """지식 항목에 authority/approve/execute/permission 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    e = _entry(_eng())
    d = e.to_dict()
    for banned in ("authority", "approve", "execute", "permission", "deploy"):
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
        m = importlib.import_module(f"jarvis.governance_memory.{mod_name}")
        for name in dir(m):
            low = name.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledger_prefix_gm(tmp_path, monkeypatch):
    for fn, _idf in ledger.ALL_LEDGERS:
        assert fn.startswith("gm_")


def test_gm_not_mg(tmp_path, monkeypatch):
    """gm_ ≠ mg_ Model Governance 경계 보존."""
    for fn, _idf in ledger.ALL_LEDGERS:
        assert not fn.startswith("mg_")


def test_all_ledgers_distinct():
    names = [fn for fn, _ in ledger.ALL_LEDGERS]
    assert len(names) == len(set(names)) == 8


def test_engine_no_upstream_layer_import():
    import jarvis.governance_memory.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for up in ("import jarvis.governance_feedback", "import jarvis.research_compliance",
               "import jarvis.research_memory", "import jarvis.meta_intelligence"):
        assert up not in src


# ── 추가 커버리지 ──
def test_id_prefixes_distinct():
    prefixes = {
        M.entry_id("a", "b")[:4],
        M.experience_id("a")[:4],
        M.lesson_id("a", "b")[:4],
        M.resolution_id("a", "b")[:4],
        M.link_id("a", "b", "c")[:4],
        M.snapshot_id("a", "b")[:4],
        M.report_id("a")[:4],
        M.artifact_id("a", "b")[:4],
    }
    assert len(prefixes) == 8


def test_content_hash_excludes_chain_fields():
    r1 = {"a": 1, "previous_hash": "x", "record_hash": "y"}
    r2 = {"a": 1, "previous_hash": "z", "record_hash": "w"}
    assert M.content_hash(r1) == M.content_hash(r2)


def test_input_digest_order_matters():
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_knowledge_content_hash_deterministic():
    assert M.knowledge_content_hash("x") == M.knowledge_content_hash("x")
    assert M.knowledge_content_hash("x") != M.knowledge_content_hash("y")


def test_snapshot_hash_sorts_entries():
    assert M.snapshot_hash(["b", "a"], {}) == M.snapshot_hash(["a", "b"], {})


def test_detect_cycle_finds():
    assert M.detect_cycle([("a", "b"), ("b", "a")])


def test_detect_cycle_none():
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []


def test_entry_categories_count():
    assert len(M.ENTRY_CATEGORIES) == 6


def test_link_types_count():
    assert len(M.LINK_TYPES) == 4


def test_node_types_count():
    assert len(M.NODE_TYPES) == 7


def test_acyclic_link_types():
    assert M.ACYCLIC_LINK_TYPES == (DERIVED_FROM,)


def test_no_commit_no_files(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _entry(eng, commit=False)
    _exp(eng, commit=False)
    for fn, _ in ledger.ALL_LEDGERS:
        assert ledger.read_jsonl(fn) == []


def test_entry_to_dict_roundtrip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _entry(_eng())
    d = e.to_dict()
    assert d["entry_id"] == e.entry_id
    assert set(("category", "source_reference", "content_hash", "metadata")).issubset(d)


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


def test_entry_input_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _entry(_eng())
    assert e.input_hash == M.input_digest(M.K_RESEARCH_LESSON, "rg:ST1")


def test_experience_kept_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    x = _exp(_eng())
    assert x.event_reference == "rc:violation1"


def test_snapshot_summary_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().create_snapshot("s1", "E1", ["a"], {"clusters": 3}, T0, commit=True)
    assert s.summary == {"clusters": 3}


def test_summary_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full(eng)
    s = eng.summary(T0)
    assert M.K_RESEARCH_LESSON in s.entry_category_distribution
    assert DERIVED_FROM in s.link_type_distribution


def test_knowledge_gaps_empty_when_all_linked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _entry(eng, src="a")
    b = _entry(eng, src="b")
    eng.link_memory(a.entry_id, RELATED_TO, b.entry_id, T0, commit=True)
    assert eng.knowledge_gaps() == []


def test_source_ledgers_not_gm_prefixed():
    for layer, (fn, idf) in ledger.SOURCE_LEDGERS.items():
        assert not fn.startswith("gm_")
        assert isinstance(idf, str)


def test_engine_reused(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    e1 = _entry(eng, src="a")
    e2 = _entry(eng, src="b")
    assert e1.entry_id != e2.entry_id
    assert len(ledger.read_entries()) == 2


def test_disclaimer_full_phrases(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", _HI, T0, commit=True)
    for phrase in ("MEMORY ≠ AUTHORITY", "SIMILARITY ≠ DECISION",
                   "HISTORICAL PATTERN ≠ FUTURE ACTION", "KNOWLEDGE ≠ PERMISSION"):
        assert phrase in r.disclaimer


def test_memory_score_partial_metrics():
    s = M.memory_score({"entry_coverage": 1.0, "lesson_density": 1.0})
    assert abs(s - (0.25 + 0.25)) < 1e-9
