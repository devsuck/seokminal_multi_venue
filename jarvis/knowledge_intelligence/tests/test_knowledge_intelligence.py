"""P10.27 Advanced Research Knowledge Intelligence 테스트. **상위 지식 인텔리전스 분석 전용.**

연구 유사도(결정적 Jaccard·불변)·실패 실험 검색·전략 패밀리 클러스터링(결정적·그래프 무결성)·모순 탐지(불변)·
연구 패턴(불변)·지식 추천(정보용 인사이트·불변)·리포트(결정적)·verify(체인/변조/중복/그래프/계보)·replay·
상위 READ ONLY 보호·CLI·보안(금지import·선택/승인/배포 없음·상위 원장 무변경·삭제 API 없음·불변·RECOMMENDATION
≠ACTION·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.knowledge_intelligence import ledger
from jarvis.knowledge_intelligence import models as M
from jarvis.knowledge_intelligence.engine import KnowledgeIntelligenceEngine
from jarvis.knowledge_intelligence.models import (
    REFUTES,
    SUPPORTS,
    ImmutableContradictionError,
    ImmutableInsightError,
    ImmutablePatternError,
    ImmutableSimilarityError,
    InvalidInsightType,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.knowledge_intelligence.ledger.state_path", sp)
    return sp


def _eng():
    return KnowledgeIntelligenceEngine()


# ── research_similarity ──
def test_similarity_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().research_similarity("A", ["x", "y", "z"], "B", ["x", "y", "w"], "jaccard", T0,
                                   commit=True)
    assert s.similarity_id.startswith("KIS:")
    assert s.score == round(2 / 4, 8)  # {x,y} / {x,y,z,w}


def test_similarity_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.research_similarity("A", ["x", "y"], "B", ["x"], "jaccard", T0, commit=False)
    b = eng.research_similarity("A", ["x", "y"], "B", ["x"], "jaccard", T0, commit=False)
    assert a.score == b.score


def test_similarity_symmetric_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert M.similarity_id("A", "B") == M.similarity_id("B", "A")


def test_similarity_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    b = eng.research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    assert a.similarity_id == b.similarity_id
    assert len(ledger.read_similarity()) == 1


def test_similarity_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.research_similarity("A", ["x", "y"], "B", ["x"], "jaccard", T0, commit=True)
    with pytest.raises(ImmutableSimilarityError):
        eng.research_similarity("A", ["x", "y", "z"], "B", ["x"], "jaccard", T0, commit=True)


def test_similarity_records_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    assert ledger.artifact_exists(M.artifact_id(M.ART_SIMILARITY, s.similarity_id))
    assert ledger.artifact_exists(M.artifact_id(M.ART_OBJECT, "A"))


def test_similarity_not_committed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=False)
    assert ledger.read_similarity() == []


def test_jaccard_helper():
    assert M.jaccard(["a", "b"], ["a", "b"]) == 1.0
    assert M.jaccard(["a"], ["b"]) == 0.0
    assert M.jaccard([], []) == 0.0
    assert M.jaccard(["a", "b", "c"], ["a"]) == round(1 / 3, 8)


def test_most_similar(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.research_similarity("A", ["x", "y", "z"], "B", ["x", "y"], "jaccard", T0, commit=True)
    eng.research_similarity("A", ["x", "y", "z"], "C", ["x"], "jaccard", T0, commit=True)
    ms = eng.most_similar("A")
    assert ms == ["B", "C"]  # B more similar than C


# ── strategy_family_clustering ──
def test_clustering_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    items = [("s1", ["momentum"]), ("s2", ["momentum"]), ("s3", ["meanrev"])]
    cs = _eng().strategy_family_clustering(items, 1, T0, commit=True)
    sizes = sorted(c.size for c in cs)
    assert sizes == [1, 2]


def test_clustering_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    items = [("s2", ["a"]), ("s1", ["a"]), ("s3", ["b"])]
    a = eng.strategy_family_clustering(items, 1, T0, commit=False)
    b = eng.strategy_family_clustering(items, 1, T0, commit=False)
    assert [c.members for c in a] == [c.members for c in b]


def test_clustering_members_sorted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    items = [("s3", ["a"]), ("s1", ["a"]), ("s2", ["a"])]
    cs = _eng().strategy_family_clustering(items, 1, T0, commit=True)
    assert cs[0].members == ["s1", "s2", "s3"]


def test_clustering_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    items = [("s1", ["a"]), ("s2", ["a"])]
    eng.strategy_family_clustering(items, 1, T0, commit=True)
    eng.strategy_family_clustering(items, 1, T0, commit=True)
    assert len(ledger.read_clusters()) == 1


def test_clustering_min_shared(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    items = [("s1", ["a", "b"]), ("s2", ["a", "c"])]
    cs2 = _eng().strategy_family_clustering(items, 2, T1, commit=False)  # need 2 shared -> separate
    assert sorted(c.size for c in cs2) == [1, 1]


def test_cluster_of(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.strategy_family_clustering([("s1", ["a"]), ("s2", ["a"])], 1, T0, commit=True)
    assert eng.cluster_of("s1") == ["s1", "s2"]


def test_connected_components_helper():
    comps = M.connected_components([("a", "b"), ("b", "c"), ("x", "y")])
    assert [len(c) for c in comps] == [3, 2]


def test_cluster_by_tokens_helper():
    clusters = M.cluster_by_tokens([("a", ["t1"]), ("b", ["t1"]), ("c", ["t2"])])
    assert [len(c) for c in clusters] == [2, 1]


def test_cluster_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    cs = _eng().strategy_family_clustering([("s1", ["a"]), ("s2", ["a"])], 1, T0, commit=True)
    assert cs[0].cluster_id == M.cluster_id("s1", ["s1", "s2"])


# ── contradiction_detection ──
def test_contradiction_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    claims = [{"ref": "r1", "subject": "momentum_works", "stance": SUPPORTS},
              {"ref": "r2", "subject": "momentum_works", "stance": REFUTES}]
    cs = _eng().contradiction_detection(claims, T0, commit=True)
    assert len(cs) == 1
    assert cs[0].supporting == ["r1"]
    assert cs[0].refuting == ["r2"]


def test_contradiction_none_when_agree(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    claims = [{"ref": "r1", "subject": "s", "stance": SUPPORTS},
              {"ref": "r2", "subject": "s", "stance": SUPPORTS}]
    cs = _eng().contradiction_detection(claims, T0, commit=True)
    assert cs == []


def test_contradiction_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.contradiction_detection([{"ref": "r1", "subject": "s", "stance": SUPPORTS},
                                 {"ref": "r2", "subject": "s", "stance": REFUTES}], T0, commit=True)
    with pytest.raises(ImmutableContradictionError):
        eng.contradiction_detection([{"ref": "r3", "subject": "s", "stance": SUPPORTS},
                                     {"ref": "r2", "subject": "s", "stance": REFUTES}], T0,
                                    commit=True)


def test_contradiction_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    claims = [{"ref": "r1", "subject": "s", "stance": SUPPORTS},
              {"ref": "r2", "subject": "s", "stance": REFUTES}]
    eng.contradiction_detection(claims, T0, commit=True)
    eng.contradiction_detection(claims, T0, commit=True)
    assert len(ledger.read_contradictions()) == 1


def test_contradiction_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    cs = _eng().contradiction_detection([{"ref": "r1", "subject": "s", "stance": SUPPORTS},
                                         {"ref": "r2", "subject": "s", "stance": REFUTES}], T0,
                                        commit=True)
    assert cs[0].contradiction_id == M.contradiction_id("s")


def test_detect_contradictions_helper():
    out = M.detect_contradictions([{"ref": "a", "subject": "x", "stance": SUPPORTS},
                                   {"ref": "b", "subject": "x", "stance": REFUTES},
                                   {"ref": "c", "subject": "y", "stance": SUPPORTS}])
    assert len(out) == 1
    assert out[0]["subject"] == "x"


# ── failed_experiment_retrieval ──
def test_failed_experiment_retrieval(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("gm_entries.jsonl"), "w") as f:
        f.write(json.dumps({"entry_id": "E1", "category": "failure_pattern"}) + "\n")
        f.write(json.dumps({"entry_id": "E2", "category": "research_lesson"}) + "\n")
        f.write(json.dumps({"entry_id": "E3", "category": "failure_pattern"}) + "\n")
    refs = _eng().failed_experiment_retrieval("governance_memory", now=T0, commit=True)
    assert refs == ["governance_memory:E1", "governance_memory:E3"]


def test_failed_experiment_records_pattern(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("gm_entries.jsonl"), "w") as f:
        f.write(json.dumps({"entry_id": "E1", "category": "failure_pattern"}) + "\n")
    _eng().failed_experiment_retrieval("governance_memory", now=T0, commit=True)
    pats = ledger.read_patterns()
    assert len(pats) == 1
    assert pats[0]["pattern_type"] == M.P_REPEATED_FAILURE


def test_failed_experiment_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().failed_experiment_retrieval("governance_memory", now=T0, commit=True) == []


def test_failed_experiment_unknown_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().failed_experiment_retrieval("nope", now=T0, commit=True) == []


# ── Research Pattern ──
def test_pattern_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _eng().record_pattern(M.P_COMMON_FAMILY, "momentum", 3, ["s1", "s2", "s3"], T0, commit=True)
    assert p.pattern_id.startswith("KIP:")
    assert p.confidence == 1.0  # 3 occ, 3 members


def test_pattern_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_pattern(M.P_COMMON_FAMILY, "s", 2, ["a"], T0, commit=True)
    with pytest.raises(ImmutablePatternError):
        eng.record_pattern(M.P_COMMON_FAMILY, "s", 5, ["a", "b"], T0, commit=True)


def test_pattern_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.record_pattern(M.P_COMMON_FAMILY, "s", 2, ["a"], T0, commit=True)
    b = eng.record_pattern(M.P_COMMON_FAMILY, "s", 2, ["a"], T0, commit=True)
    assert a.pattern_id == b.pattern_id
    assert len(ledger.read_patterns()) == 1


def test_pattern_confidence_helper():
    assert M.pattern_confidence(3, 3) == 1.0
    assert M.pattern_confidence(0, 0) == 0.0


def test_pattern_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _eng().record_pattern(M.P_COMMON_FAMILY, "s", 1, [], T0, commit=True)
    assert p.pattern_id == M.pattern_id(M.P_COMMON_FAMILY, "s")


# ── knowledge_recommendation / insights ──
def test_recommendation_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    i = _eng().knowledge_recommendation("momentum_family", "consider walk-forward", "s1",
                                        ["s2"], 0.7, T0, commit=True)
    assert i.insight_id.startswith("KII:")
    assert i.insight_type == M.INSIGHT_RECOMMENDATION


def test_insight_invalid_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidInsightType):
        _eng().record_insight("NOPE", "s", "c", "", [], 0.0, T0, commit=True)


def test_insight_all_types(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, it in enumerate(M.INSIGHT_TYPES):
        ins = eng.record_insight(it, f"s{i}", "c", "", [], 0.0, T0, commit=True)
        assert ins.insight_type == it
    assert len(ledger.read_insights()) == len(M.INSIGHT_TYPES)


def test_insight_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_insight(M.INSIGHT_RECOMMENDATION, "s", "content1", "r", [], 0.0, T0, commit=True)
    with pytest.raises(ImmutableInsightError):
        eng.record_insight(M.INSIGHT_RECOMMENDATION, "s", "content2", "r", [], 0.0, T0, commit=True)


def test_insight_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.record_insight(M.INSIGHT_PATTERN, "s", "c", "r", [], 0.0, T0, commit=True)
    b = eng.record_insight(M.INSIGHT_PATTERN, "s", "c", "r", [], 0.0, T0, commit=True)
    assert a.insight_id == b.insight_id
    assert len(ledger.read_insights()) == 1


def test_insight_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    i = _eng().knowledge_recommendation("s", "c", "r", [], 0.0, T0, commit=True)
    assert i.insight_id == M.insight_id(M.INSIGHT_RECOMMENDATION, "s", "r")


def test_recommendation_informational_no_action_field(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    i = _eng().knowledge_recommendation("s", "c", "", [], 0.0, T0, commit=True)
    d = i.to_dict()
    for banned in ("action", "select", "approve", "deploy", "execute"):
        assert banned not in d


# ── Report ──
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    eng.strategy_family_clustering([("A", ["x"]), ("B", ["x"])], 1, T0, commit=True)
    eng.knowledge_recommendation("s", "c", "", [], 0.5, T0, commit=True)
    r = eng.generate_report("GLOBAL", {}, T1, commit=True)
    assert r.report_id.startswith("KIR:")
    assert r.similarity_count >= 1
    assert r.cluster_count >= 1
    assert r.recommendation_count >= 1


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.knowledge_recommendation("s", "c", "", [], 0.5, T0, commit=True)
    a = eng.generate_report("GLOBAL", {}, T1, commit=False)
    b = eng.generate_report("GLOBAL", {}, T1, commit=False)
    assert a.to_dict() == b.to_dict()


def test_report_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_insight(M.INSIGHT_PATTERN, "s", "c", "", [], 0.0, T0, commit=True)
    eng.record_pattern(M.P_COMMON_FAMILY, "s", 1, [], T0, commit=True)
    r = eng.generate_report("GLOBAL", {}, T1, commit=True)
    assert M.INSIGHT_PATTERN in r.insight_type_distribution
    assert M.P_COMMON_FAMILY in r.pattern_type_distribution


def test_report_largest_cluster(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.strategy_family_clustering([("a", ["t"]), ("b", ["t"]), ("c", ["t"])], 1, T0, commit=True)
    r = eng.generate_report("GLOBAL", {}, T1, commit=True)
    assert r.largest_cluster_size == 3


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", {}, T0, commit=True)
    assert "RECOMMENDATION ≠ ACTION" in r.disclaimer


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_report("GLOBAL", {}, T0, commit=True)
    eng.generate_report("GLOBAL", {}, T0, commit=True)
    assert len(ledger.read_reports()) == 1


def test_report_no_action_verbs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", {}, T0, commit=True)
    d = r.to_dict()
    d.pop("disclaimer")
    blob = json.dumps(d, ensure_ascii=False).lower()
    for verb in ("execute", "deploy", "approve", "select_strategy", "place_order"):
        assert verb not in blob


# ── Lineage / verify ──
def test_verify_lineage_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    assert eng.verify_lineage()["ok"] is True


def test_trace_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    s = eng.research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    anc = eng.trace_lineage(M.artifact_id(M.ART_SIMILARITY, s.similarity_id))
    assert M.artifact_id(M.ART_OBJECT, "A") in anc


def test_verify_chain_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    eng.strategy_family_clustering([("A", ["x"]), ("B", ["x"])], 1, T0, commit=True)
    from jarvis.knowledge_intelligence.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] >= 1


def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.knowledge_intelligence.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    p = sp("ki_similarity.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["score"] = 0.999
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.knowledge_intelligence.verify import verify_ledger
    assert verify_ledger(ledger.SIMILARITY)["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.record_insight(M.INSIGHT_PATTERN, "s1", "c", "", [], 0.0, T0, commit=True)
    eng.record_insight(M.INSIGHT_PATTERN, "s2", "c", "", [], 0.0, T0, commit=True)
    p = sp("ki_insights.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.knowledge_intelligence.verify import verify_ledger
    assert verify_ledger(ledger.INSIGHTS)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    p = sp("ki_similarity.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows.append(dict(rows[0]))
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.knowledge_intelligence.verify import verify_ledger
    assert verify_ledger(ledger.SIMILARITY)["ok"] is False


def test_verify_graph_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.strategy_family_clustering([("a", ["t"]), ("b", ["t"])], 1, T0, commit=True)
    from jarvis.knowledge_intelligence.verify import graph_integrity
    assert graph_integrity()["ok"] is True


def test_verify_detects_cluster_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.strategy_family_clustering([("a", ["t"]), ("b", ["t"])], 1, T0, commit=True)
    p = sp("ki_clusters.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["members"] = ["a", "b", "GHOST"]  # members_hash mismatch
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.knowledge_intelligence.verify import graph_integrity
    res = graph_integrity()
    assert res["ok"] is False
    assert any("members_hash_mismatch" in i for i in res["issues"])


def test_verify_full_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    eng.strategy_family_clustering([("A", ["x"]), ("B", ["x"])], 1, T0, commit=True)
    from jarvis.knowledge_intelligence.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["graph"]["ok"] is True
    assert res["lineage"]["ok"] is True


def test_verify_lineage_cycle_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    from jarvis.knowledge_intelligence.models import content_hash
    h = ledger.artifacts_head()["record_hash"]
    a1 = {"artifact_id": "KIA:c1", "artifact_type": "SIMILARITY", "ref_id": "x1",
          "parent_artifact": "KIA:c2", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": h}
    a1["record_hash"] = content_hash(a1)
    ledger.append_artifact(a1)
    a2 = {"artifact_id": "KIA:c2", "artifact_type": "SIMILARITY", "ref_id": "x2",
          "parent_artifact": "KIA:c1", "created_at": T0, "input_hash": "", "record_hash": "",
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
    eng.research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    from jarvis.knowledge_intelligence.verify import replay
    assert replay(eng, T0)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    eng.strategy_family_clustering([("A", ["x"]), ("B", ["x"])], 1, T0, commit=True)
    eng.contradiction_detection([{"ref": "r1", "subject": "s", "stance": SUPPORTS},
                                 {"ref": "r2", "subject": "s", "stance": REFUTES}], T0, commit=True)
    eng.record_pattern(M.P_COMMON_FAMILY, "s", 1, [], T0, commit=True)
    eng.knowledge_recommendation("s", "c", "", [], 0.0, T0, commit=True)
    s = eng.summary(T0)
    assert s.similarity_count >= 1
    assert s.cluster_count >= 1
    assert s.contradiction_count >= 1
    assert s.pattern_count >= 1
    assert s.insight_count >= 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.knowledge_recommendation("s", "c", "", [], 0.0, T0, commit=True)
    assert eng.summary(T0).to_dict() == eng.summary(T0).to_dict()


# ── 상위 READ ONLY ──
def test_list_source_objects_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_objects("research_kg") == []


def test_list_source_objects_reads(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("kg_entities.jsonl"), "w") as f:
        f.write(json.dumps({"entity_id": "K1"}) + "\n")
        f.write(json.dumps({"entity_id": "K2"}) + "\n")
    out = _eng().list_source_objects("research_kg")
    assert out == ["research_kg:K1", "research_kg:K2"]


def test_source_read_only_no_write(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    src = sp("gm_entries.jsonl")
    with open(src, "w") as f:
        f.write(json.dumps({"entry_id": "E1", "category": "failure_pattern"}) + "\n")
    before = open(src).read()
    eng = _eng()
    eng.failed_experiment_retrieval("governance_memory", now=T0, commit=True)
    assert open(src).read() == before


def test_unknown_source_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_objects("nonexistent") == []


def test_source_count(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("kg_entities.jsonl"), "w") as f:
        f.write(json.dumps({"entity_id": "K1"}) + "\n")
    assert ledger.source_count("research_kg") == 1
    assert ledger.source_count("nope") == 0


def test_source_layers_are_the_three():
    assert set(ledger.SOURCE_LEDGERS) == {"research_kg", "governance_memory", "research_lifecycle"}


# ── CLI ──
def test_cli_similarity(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.knowledge_intelligence.__main__ import main
    rc = main(["similarity", "--ref-a", "A", "--tokens-a", "x,y", "--ref-b", "B", "--tokens-b",
               "x", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["similarity"]["similarity_id"].startswith("KIS:")


def test_cli_cluster(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.knowledge_intelligence.__main__ import main
    rc = main(["cluster", "--items-json", json.dumps([["a", ["t"]], ["b", ["t"]]]), "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["clusters"][0]["cluster_id"].startswith("KIC:")


def test_cli_contradict(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.knowledge_intelligence.__main__ import main
    claims = [{"ref": "r1", "subject": "s", "stance": "SUPPORTS"},
              {"ref": "r2", "subject": "s", "stance": "REFUTES"}]
    rc = main(["contradict", "--claims-json", json.dumps(claims), "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["contradictions"][0]["contradiction_id"].startswith(
        "KIX:")


def test_cli_failures(tmp_path, monkeypatch, capsys):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("gm_entries.jsonl"), "w") as f:
        f.write(json.dumps({"entry_id": "E1", "category": "failure_pattern"}) + "\n")
    from jarvis.knowledge_intelligence.__main__ import main
    rc = main(["failures", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["failed_experiments"] == ["governance_memory:E1"]


def test_cli_recommend(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.knowledge_intelligence.__main__ import main
    rc = main(["recommend", "--subject", "s", "--content", "c", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["recommendation"]["insight_id"].startswith("KII:")


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.knowledge_intelligence.__main__ import main
    rc = main(["report", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["report"]["report_id"].startswith("KIR:")


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.knowledge_intelligence.__main__ import main
    main(["recommend", "--subject", "s", "--content", "c", "--commit"])
    capsys.readouterr()
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.knowledge_intelligence.__main__ import main
    main(["recommend", "--subject", "s", "--content", "c", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.knowledge_intelligence.__main__ import main
    rc = main(["summary"])
    assert rc == 0
    assert "insight_count" in json.loads(capsys.readouterr().out)


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.knowledge_intelligence.engine as eng_mod
    import jarvis.knowledge_intelligence.models as mdl_mod
    import jarvis.knowledge_intelligence.ledger as led_mod
    import jarvis.knowledge_intelligence.verify as ver_mod
    import jarvis.knowledge_intelligence.__main__ as cli_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod, cli_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "execution", _j + "broker", _j + "order",
                 _j + "portfolio_execution", _j + "capital_allocation", _j + "live_trading",
                 _j + "permission", _j + "risk_controller",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital(", "select_strategy(", "approve_strategy("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_action_methods():
    import jarvis.knowledge_intelligence.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def select", "def approve", "def deploy", "def execute", "def activate",
               "def trade"):
        assert kw not in src


def test_no_action_authority_api():
    api = set(dir(KnowledgeIntelligenceEngine))
    for banned in ("select", "approve", "deploy", "execute", "activate", "trade"):
        assert banned not in api


def test_live_execution_disabled_invariant():
    import jarvis.config as _cfg
    assert _cfg.live_execution_enabled() is False
    assert _cfg.AUTONOMY_LEVEL < _cfg.MIN_LIVE_LEVEL


def test_autonomy_unchanged(tmp_path, monkeypatch):
    import jarvis.config as _cfg
    before = _cfg.AUTONOMY_LEVEL
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    eng.knowledge_recommendation("s", "c", "", [], 0.0, T0, commit=True)
    assert _cfg.AUTONOMY_LEVEL == before
    assert _cfg.live_execution_enabled() is False


def test_no_delete_or_update_api():
    import importlib
    for mod_name in ("engine", "ledger"):
        m = importlib.import_module(f"jarvis.knowledge_intelligence.{mod_name}")
        for name in dir(m):
            low = name.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledger_prefix_ki(tmp_path, monkeypatch):
    for fn, _idf in ledger.ALL_LEDGERS:
        assert fn.startswith("ki_")


def test_all_ledgers_distinct():
    names = [fn for fn, _ in ledger.ALL_LEDGERS]
    assert len(names) == len(set(names)) == 7


def test_engine_no_upstream_layer_import():
    import jarvis.knowledge_intelligence.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for up in ("import jarvis.research_kg", "import jarvis.governance_memory",
               "import jarvis.research_lifecycle"):
        assert up not in src


# ── 추가 커버리지 ──
def test_id_prefixes_distinct():
    prefixes = {
        M.similarity_id("a", "b")[:4],
        M.cluster_id("a", ["a"])[:4],
        M.contradiction_id("a")[:4],
        M.pattern_id("a", "b")[:4],
        M.insight_id("a", "b", "c")[:4],
        M.report_id("a")[:4],
        M.artifact_id("a", "b")[:4],
    }
    assert len(prefixes) == 7


def test_content_hash_excludes_chain_fields():
    r1 = {"a": 1, "previous_hash": "x", "record_hash": "y"}
    r2 = {"a": 1, "previous_hash": "z", "record_hash": "w"}
    assert M.content_hash(r1) == M.content_hash(r2)


def test_input_digest_order_matters():
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_members_hash_order_independent():
    assert M.members_hash(["b", "a"]) == M.members_hash(["a", "b"])


def test_detect_cycle_finds():
    assert M.detect_cycle([("a", "b"), ("b", "a")])


def test_detect_cycle_none():
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []


def test_insight_types_count():
    assert len(M.INSIGHT_TYPES) == 5


def test_pattern_types_count():
    assert len(M.PATTERN_TYPES) == 4


def test_node_types_count():
    assert len(M.NODE_TYPES) == 8


def test_no_commit_no_files(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=False)
    for fn, _ in ledger.ALL_LEDGERS:
        assert ledger.read_jsonl(fn) == []


def test_similarity_to_dict_roundtrip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    d = s.to_dict()
    assert d["similarity_id"] == s.similarity_id
    assert set(("ref_a", "ref_b", "score", "method")).issubset(d)


def test_report_metrics_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", {"k": 1}, T0, commit=True)
    assert r.metrics == {"k": 1}


def test_multiple_scopes_distinct_reports(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_report("A", {}, T0, commit=True)
    eng.generate_report("B", {}, T0, commit=True)
    assert len(ledger.read_reports()) == 2


def test_similarity_input_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    assert s.input_hash == M.input_digest("A", "B")


def test_cluster_members_hash_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    cs = _eng().strategy_family_clustering([("a", ["t"]), ("b", ["t"])], 1, T0, commit=True)
    assert cs[0].members_hash == M.members_hash(["a", "b"])


def test_source_ledgers_not_ki_prefixed():
    for layer, (fn, idf) in ledger.SOURCE_LEDGERS.items():
        assert not fn.startswith("ki_")
        assert isinstance(idf, str)


def test_engine_reused(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.research_similarity("A", ["x"], "B", ["x"], "jaccard", T0, commit=True)
    b = eng.research_similarity("C", ["x"], "D", ["x"], "jaccard", T0, commit=True)
    assert a.similarity_id != b.similarity_id
    assert len(ledger.read_similarity()) == 2


def test_disclaimer_full_phrases(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", {}, T0, commit=True)
    for phrase in ("RECOMMENDATION ≠ ACTION", "SIMILARITY ≠ SELECTION", "CLUSTER ≠ APPROVAL",
                   "INSIGHT ≠ DEPLOYMENT"):
        assert phrase in r.disclaimer


def test_recommendation_is_insight_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    i = _eng().knowledge_recommendation("s", "c", "", [], 0.0, T0, commit=True)
    assert i.insight_type == M.INSIGHT_RECOMMENDATION
    r = _eng().generate_report("GLOBAL", {}, T1, commit=True)
    # recommendation counted separately
    assert r.recommendation_count >= 0
