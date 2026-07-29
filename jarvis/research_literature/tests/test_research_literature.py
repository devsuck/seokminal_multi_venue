"""P11.3 Research Literature Intelligence 테스트. **외부 지식 연결 — 읽기·기록 전용.**

논문 메타데이터(불변·중복탐지)·개념 추출(불변·종류)·전략 아이디어 추출(정보용·자동전략생성 없음)·인용 그래프
(자기인용 거부·roots/leaves/순환)·지식 링크(OS READ ONLY)·연구 비교(Jaccard·불변)·계보(인용/개념)·지식 무결성·
verify(체인/변조/중복/인용/계보)·replay·CLI·보안(금지import·전략 생성/배포/실행 없음·OS 원장 무변경·삭제 API
없음·불변·LITERATURE≠STRATEGY·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_literature import ledger
from jarvis.research_literature import models as M
from jarvis.research_literature.engine import ResearchLiteratureEngine
from jarvis.research_literature.models import (
    CONCEPT,
    DATASET,
    METHOD,
    METRIC,
    STRATEGY_IDEA,
    ImmutableComparisonError,
    ImmutableConceptError,
    ImmutablePaperError,
    InvalidConceptType,
    InvalidLinkType,
    SelfCitationError,
    UnknownConceptError,
    UnknownPaperError,
)

T0 = "2026-07-24T00:00:00Z"
T1 = "2026-07-24T00:01:00Z"
T2 = "2026-07-24T00:02:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_literature.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchLiteratureEngine()


def _seed(sp, filename, rows):
    with open(sp(filename), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _paper(e, title="Momentum Strategies", doi="10.1/x", year=1993, now=T0):
    return e.register_paper(title, ["Jegadeesh", "Titman"], year, "JF", doi, "", now,
                            commit=True).paper_id


# ══════════════ register_paper ══════════════
def test_register_paper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _eng().register_paper("Title X", ["A"], 2020, "V", "10.1/x", "", T0, commit=True)
    assert p.paper_id.startswith("RLP:")
    assert p.source == "EXTERNAL"


def test_register_deterministic_by_doi(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().register_paper("T", [], 2020, "", "10.1/x", "", T0, commit=False)
    b = _eng().register_paper("T different", [], 2021, "", "10.1/x", "", T1, commit=False)
    assert a.paper_id == b.paper_id  # 같은 doi → 같은 id


def test_register_by_title_when_no_doi(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().register_paper("Same Title", [], 2020, "", "", "", T0, commit=False)
    b = _eng().register_paper("same   title", [], 2020, "", "", "", T1, commit=False)
    assert a.paper_id == b.paper_id  # 정규화 제목+연도


def test_register_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _paper(e)
    _paper(e, now=T1)
    assert len(ledger.read_papers()) == 1


def test_register_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_paper("T", [], 2020, "", "10.1/x", "", T0, commit=True)
    with pytest.raises(ImmutablePaperError):
        e.register_paper("T changed", [], 2020, "", "10.1/x", "", T1, commit=True)


def test_register_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_paper("T", [], 2020, "", "10.1/x", "", T0, commit=False)
    assert ledger.read_papers() == []


# ══════════════ concept extraction ══════════════
def test_extract_concepts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    cs = e.extract_concepts(p, [("momentum", CONCEPT, "d"), ("sharpe", METRIC, "")], T0,
                            commit=True)
    assert len(cs) == 2
    assert cs[0].concept_id.startswith("RLC:")


def test_extract_creates_links(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    e.extract_concepts(p, [("momentum", CONCEPT, "")], T0, commit=True)
    links = [l for l in ledger.read_links() if l["link_type"] == "PAPER_CONCEPT"]
    assert len(links) == 1


def test_extract_unknown_paper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownPaperError):
        _eng().extract_concepts("RLP:ghost", [("x", CONCEPT, "")], T0, commit=True)


def test_extract_invalid_kind(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    with pytest.raises(InvalidConceptType):
        e.extract_concepts(p, [("x", "BOGUS", "")], T0, commit=True)


@pytest.mark.parametrize("ctype", list(M.CONCEPT_TYPES))
def test_extract_all_concept_types(tmp_path, monkeypatch, ctype):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    c = e.extract_concepts(p, [(f"c_{ctype}", ctype, "")], T0, commit=True)[0]
    assert c.concept_type == ctype


def test_concept_dedup_across_papers(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p1 = _paper(e, "P1", "10.1/1")
    p2 = _paper(e, "P2", "10.1/2")
    e.extract_concepts(p1, [("momentum", CONCEPT, "")], T0, commit=True)
    e.extract_concepts(p2, [("Momentum", CONCEPT, "")], T0, commit=True)  # 정규화 동일
    assert len(ledger.read_concepts()) == 1  # 개념 전역 dedup


def test_concept_immutable_type_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    e.extract_concepts(p, [("x", CONCEPT, "")], T0, commit=True)
    with pytest.raises(ImmutableConceptError):
        e.extract_concepts(p, [("x", METHOD, "")], T1, commit=True)


def test_concept_papers_reverse(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p1 = _paper(e, "P1", "10.1/1")
    p2 = _paper(e, "P2", "10.1/2")
    c = e.extract_concepts(p1, [("momentum", CONCEPT, "")], T0, commit=True)[0]
    e.extract_concepts(p2, [("momentum", CONCEPT, "")], T0, commit=True)
    assert e.concept_papers(c.concept_id) == sorted([p1, p2])


# ══════════════ strategy idea extraction (no auto strategy creation) ══════════════
def test_extract_strategy_ideas(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    ideas = e.extract_strategy_ideas(p, [("cross-sectional momentum", "buy winners")], T0,
                                     commit=True)
    assert ideas[0].concept_type == STRATEGY_IDEA


def test_strategy_ideas_are_informational_concepts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    e.extract_strategy_ideas(p, [("idea1", "d")], T0, commit=True)
    # 전략 아이디어는 개념 원장에만 존재 — 별도 전략/실행 원장 없음
    assert "idea1" in e.strategy_ideas()
    fns = {l[0] for l in ledger.ALL_LEDGERS}
    assert "rli_strategies.jsonl" not in fns  # 전략 생성 원장 없음


def test_strategy_idea_count_in_summary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    e.extract_strategy_ideas(p, [("i1", ""), ("i2", "")], T0, commit=True)
    assert e.summary(T1).strategy_idea_count == 2


# ══════════════ citation graph ══════════════
def test_add_citation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    c = e.add_citation(a, b, T0, commit=True)
    assert c.citation_id.startswith("RLX:")


def test_citation_self_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e)
    with pytest.raises(SelfCitationError):
        e.add_citation(a, a, T0, commit=True)


def test_citation_unknown_paper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e)
    with pytest.raises(UnknownPaperError):
        e.add_citation(a, "RLP:ghost", T0, commit=True)


def test_citation_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    e.add_citation(a, b, T0, commit=True)
    e.add_citation(a, b, T1, commit=True)
    assert len(ledger.read_citations()) == 1


def test_citation_graph(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    c = _paper(e, "C", "10.1/c")
    e.add_citation(a, b, T0, commit=True)
    e.add_citation(b, c, T0, commit=True)
    g = e.build_citation_graph()
    assert g["node_count"] == 3
    assert g["edge_count"] == 2
    assert g["has_cycle"] is False
    assert g["roots"] == [a]  # a 는 아무도 인용 안 함
    assert g["leaves"] == [c]  # c 는 아무것도 인용 안 함


def test_citation_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    c = _paper(e, "C", "10.1/c")
    e.add_citation(a, b, T0, commit=True)
    e.add_citation(b, c, T0, commit=True)
    assert e.trace_citation_lineage(a) == sorted([b, c])


def test_citation_cycle_detected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    e.add_citation(a, b, T0, commit=True)
    e.add_citation(b, a, T0, commit=True)  # 상호 인용(허용하나 순환 탐지)
    assert e.build_citation_graph()["has_cycle"] is True


# ══════════════ knowledge link (OS READ ONLY) ══════════════
def test_link_to_os(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    l = e.link_to_os("paper", p, "research_kg", "ent1", "grounds", T0, commit=True)
    assert l.link_type == "PAPER_OS"
    assert l.target_id == "research_kg:ent1"


def test_link_to_os_verify_ref(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "kg_entities.jsonl", [{"entity_id": "ent1"}])
    e = _eng()
    p = _paper(e)
    l = e.link_to_os("paper", p, "research_kg", "ent1", "grounds", T0, commit=True,
                     verify_ref=True)
    assert l.target_id == "research_kg:ent1"


def test_link_to_os_verify_missing_ref(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    with pytest.raises(UnknownPaperError):
        e.link_to_os("paper", p, "research_kg", "ghost", "g", T0, commit=True, verify_ref=True)


def test_link_concept_to_os(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    c = e.extract_concepts(p, [("momentum", CONCEPT, "")], T0, commit=True)[0]
    l = e.link_to_os("concept", c.concept_id, "knowledge_intelligence", "ins1", "r", T0,
                     commit=True)
    assert l.link_type == "CONCEPT_OS"


def test_link_concept_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownConceptError):
        _eng().link_to_os("concept", "RLC:ghost", "research_kg", "e", "r", T0, commit=True)


def test_os_source_never_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "kg_entities.jsonl", [{"entity_id": "ent1"}])
    before = open(sp("kg_entities.jsonl")).read()
    e = _eng()
    p = _paper(e)
    e.link_to_os("paper", p, "research_kg", "ent1", "g", T0, commit=True, verify_ref=True)
    assert open(sp("kg_entities.jsonl")).read() == before


# ══════════════ research comparison ══════════════
def test_compare_papers(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    e.extract_concepts(a, [("momentum", CONCEPT, ""), ("value", CONCEPT, "")], T0, commit=True)
    e.extract_concepts(b, [("momentum", CONCEPT, ""), ("size", CONCEPT, "")], T0, commit=True)
    cmp = e.compare_papers(a, b, T1, commit=True)
    assert cmp.comparison_id.startswith("RLM:")
    assert cmp.similarity == round(1 / 3, 8)  # {momentum} / {momentum,value,size}
    assert len(cmp.shared_concepts) == 1


def test_compare_symmetric_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    x = e.compare_papers(a, b, T0, commit=False)
    y = e.compare_papers(b, a, T0, commit=False)
    assert x.comparison_id == y.comparison_id


def test_compare_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    e.compare_papers(a, b, T0, commit=True)
    e.compare_papers(a, b, T1, commit=True)
    assert len(ledger.read_comparisons()) == 1


def test_compare_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    e.extract_concepts(a, [("x", CONCEPT, "")], T0, commit=True)
    x = e.compare_papers(a, b, T0, commit=False)
    y = e.compare_papers(a, b, T0, commit=False)
    assert x.to_dict() == y.to_dict()


# ══════════════ duplicate detection ══════════════
def test_duplicate_papers(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    # 같은 제목, 다른 doi → 다른 id, 같은 fingerprint → 중복 후보
    p1 = e.register_paper("Momentum Effect", [], 1993, "", "10.1/a", "", T0, commit=True).paper_id
    p2 = e.register_paper("momentum   effect", [], 1993, "", "10.1/b", "", T0,
                          commit=True).paper_id
    dups = e.detect_duplicate_papers()
    assert [sorted([p1, p2])] == dups


def test_no_duplicates_when_distinct(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _paper(e, "A", "10.1/a")
    _paper(e, "B", "10.1/b")
    assert e.detect_duplicate_papers() == []


# ══════════════ concept lineage ══════════════
def test_concept_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    root = e.extract_concepts(p, [("factor investing", CONCEPT, "")], T0, commit=True)[0]
    child = e._record_concept("momentum factor", CONCEPT, "", root.concept_id, T0, commit=True)
    assert e.trace_concept_lineage(child.concept_id) == [root.concept_id]


# ══════════════ knowledge integrity ══════════════
def test_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    e.extract_concepts(a, [("x", CONCEPT, "")], T0, commit=True)
    e.add_citation(a, b, T0, commit=True)
    assert e.knowledge_integrity()["ok"] is True


def test_integrity_detects_dangling_citation(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    e.add_citation(a, b, T0, commit=True)
    # b 논문 레코드를 원장에서 위조 제거(파일 재작성)
    p = sp("rli_papers.jsonl")
    rows = [json.loads(x) for x in open(p)]
    rows = [r for r in rows if r["paper_id"] == a]
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert e.knowledge_integrity()["ok"] is False


# ══════════════ verify / replay ══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_literature.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_literature.verify import verify_chain
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    e.extract_concepts(a, [("momentum", CONCEPT, "")], T0, commit=True)
    e.add_citation(a, b, T0, commit=True)
    e.compare_papers(a, b, T0, commit=True)
    res = verify_chain()
    assert res["ok"] is True
    assert res["citation"]["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _paper(e)
    p = sp("rli_papers.jsonl")
    rows = [json.loads(x) for x in open(p)]
    rows[0]["title"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_literature.verify import verify_chain
    assert verify_chain()["ok"] is False


def test_verify_duplicates_reported(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_literature.verify import verify_chain
    e = _eng()
    e.register_paper("Same", [], 2020, "", "10.1/a", "", T0, commit=True)
    e.register_paper("same", [], 2020, "", "10.1/b", "", T0, commit=True)
    res = verify_chain()
    assert res["duplicates"]["ok"] is False


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_literature.verify import replay
    e = _eng()
    _paper(e)
    assert replay(e, T1)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    e.extract_concepts(a, [("x", CONCEPT, "")], T0, commit=True)
    e.add_citation(a, b, T0, commit=True)
    s = e.summary(T1)
    assert s.paper_count == 2
    assert s.concept_count == 1
    assert s.citation_count == 1


# ══════════════ 순수 함수 ══════════════
def test_jaccard_pure():
    assert M.jaccard(["a", "b"], ["a", "c"]) == round(1 / 3, 8)
    assert M.jaccard([], []) == 0.0


def test_normalize_fingerprint():
    assert M.normalize("  Hello   World ") == "hello world"
    assert M.fingerprint("A B") == M.fingerprint("a  b")


def test_detect_cycle_pure():
    assert M.detect_cycle([("a", "b")]) == []
    cyc = M.detect_cycle([("a", "b"), ("b", "a")])
    assert cyc and cyc[0] == cyc[-1]


def test_ancestors_pure():
    assert M.ancestors([("a", "b"), ("b", "c")], "a") == ["b", "c"]


def test_roots_leaves_pure():
    assert M.roots(["a", "b"], [("a", "b")]) == ["a"]
    assert M.leaves(["a", "b"], [("a", "b")]) == ["b"]


def test_paper_key_doi_priority():
    assert M.paper_key("10.1/X", "T", 2020).startswith("doi:")
    assert M.paper_key("", "T", 2020).startswith("title:")


# ══════════════ 보안 / 불변식 (no auto strategy creation) ══════════════
def test_no_forbidden_imports():
    import ast
    forbidden = ("execution", "broker", "order", "portfolio_execution", "capital_allocation",
                 "live_trading", "permission", "risk_controller")
    base = os.path.dirname(os.path.dirname(__file__))
    for fn in ("engine.py", "ledger.py", "models.py", "verify.py", "__main__.py", "__init__.py"):
        tree = ast.parse(open(os.path.join(base, fn)).read())
        for n in ast.walk(tree):
            mods = []
            if isinstance(n, ast.Import):
                mods = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                mods = [n.module or ""]
            for m in mods:
                for fb in forbidden:
                    assert not (m == f"jarvis.{fb}" or m.startswith(f"jarvis.{fb}.")), (fn, m)


def test_engine_no_strategy_creation_methods():
    e = ResearchLiteratureEngine()
    for bad in ("create_strategy", "register_strategy", "deploy", "execute", "trade", "allocate",
                "activate", "promote", "approve"):
        assert not hasattr(e, bad), bad


def test_no_strategy_creation_in_source():
    base = os.path.dirname(os.path.dirname(__file__))
    for fn in ("engine.py", "models.py"):
        src = open(os.path.join(base, fn)).read()
        for bad in ("def create_strategy", "def register_strategy", "def deploy", "def execute",
                    "def trade", "def allocate"):
            assert bad not in src, (fn, bad)


def test_forbidden_verbs_defined():
    assert M.is_forbidden_verb("CREATE_STRATEGY") is True
    assert M.is_forbidden_verb("DEPLOY") is True
    assert M.is_forbidden_verb("EXTRACT") is False


def test_no_delete_or_update_api():
    import inspect
    src = inspect.getsource(ledger)
    for bad in ("def delete", "def update", "def remove", "def overwrite", "def edit_"):
        assert bad not in src, bad


def test_ledger_only_appends():
    import inspect
    src = inspect.getsource(ledger)
    assert '"a"' in src
    assert 'open(p, "w"' not in src


def test_disclaimer_marks_no_strategy():
    from jarvis.research_literature.engine import _DISCLAIMER
    assert "LITERATURE ≠ STRATEGY" in _DISCLAIMER
    assert "IDEA ≠ DEPLOYMENT" in _DISCLAIMER


def test_records_frozen():
    p = M.PaperRecord(paper_id="RLP:x", key="k", title="t", authors=[], year=2020, venue="",
                      doi="", url="", fingerprint="f", source="EXTERNAL", created_at=T0)
    with pytest.raises(Exception):
        p.title = "y"  # type: ignore


def test_only_rli_files_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    e.extract_concepts(a, [("x", CONCEPT, "")], T0, commit=True)
    e.add_citation(a, b, T0, commit=True)
    e.compare_papers(a, b, T0, commit=True)
    for fn in os.listdir(tmp_path):
        assert fn.startswith("rli_"), fn


# ══════════════ 커버리지: id 접두사·상수 ══════════════
def test_id_prefixes_distinct():
    ids = {M.paper_id("k")[:4], M.concept_id("n")[:4], M.citation_id("a", "b")[:4],
           M.link_id("t", "s", "d")[:4], M.comparison_id("a", "b")[:4]}
    assert len(ids) == 5


def test_five_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 5
    fns = {l[0] for l in ledger.ALL_LEDGERS}
    assert len(fns) == 5
    assert all(f.startswith("rli_") for f in fns)


def test_six_concept_types():
    assert len(M.CONCEPT_TYPES) == 6


def test_four_link_types():
    assert len(M.LINK_TYPES) == 4


def test_content_hash_excludes_hash_fields():
    r = {"a": 1, "previous_hash": "p", "record_hash": "r"}
    assert M.content_hash(r) == M.content_hash({"a": 1, "previous_hash": "z", "record_hash": "q"})


def test_input_digest_deterministic():
    assert M.input_digest("a", "b") == M.input_digest("a", "b")
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_list_papers_and_ideas(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    e.extract_strategy_ideas(p, [("idea", "d")], T0, commit=True)
    assert p in e.list_papers()
    assert "idea" in e.strategy_ideas()


# ══════════════ CLI ══════════════
def _run(argv, capsys):
    from jarvis.research_literature.__main__ import main
    rc = main(argv)
    return rc, capsys.readouterr().out


def test_cli_paper(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["paper", "--title", "T", "--doi", "10.1/x", "--year", "2020", "--commit"],
                   capsys)
    assert rc == 0
    assert json.loads(out)["paper"]["title"] == "T"


def test_cli_concepts_and_ideas(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["paper", "--title", "T", "--doi", "10.1/x", "--commit"], capsys)
    e = _eng()
    p = e.list_papers()[0]
    rc, out = _run(["concepts", "--paper", p, "--items", "momentum:CONCEPT,sharpe:METRIC",
                    "--commit"], capsys)
    assert rc == 0
    assert len(json.loads(out)["concepts"]) == 2
    rc2, out2 = _run(["ideas", "--paper", p, "--items", "idea1:buy winners", "--commit"], capsys)
    assert rc2 == 0
    assert json.loads(out2)["ideas"][0]["concept_type"] == "STRATEGY_IDEA"


def test_cli_cite_and_graph(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    rc, out = _run(["cite", "--citing", a, "--cited", b, "--commit"], capsys)
    assert rc == 0
    rc2, out2 = _run(["graph"], capsys)
    assert rc2 == 0
    assert json.loads(out2)["edge_count"] == 1


def test_cli_compare(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    rc, out = _run(["compare", "--a", a, "--b", b, "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["comparison"]["comparison_id"].startswith("RLM:")


def test_cli_duplicates(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_paper("Same", [], 2020, "", "10.1/a", "", T0, commit=True)
    e.register_paper("same", [], 2020, "", "10.1/b", "", T0, commit=True)
    rc, out = _run(["duplicates"], capsys)
    assert rc == 0
    assert len(json.loads(out)["duplicates"]) == 1


def test_cli_integrity(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["integrity"], capsys)
    assert rc == 0
    assert json.loads(out)["ok"] is True


def test_cli_papers(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _paper(_eng())
    rc, out = _run(["papers"], capsys)
    assert rc == 0
    assert len(json.loads(out)["papers"]) == 1


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["verify"], capsys)
    assert rc == 0
    assert json.loads(out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _paper(_eng())
    rc, out = _run(["replay"], capsys)
    assert rc == 0
    assert json.loads(out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["summary"], capsys)
    assert rc == 0
    assert "paper_count" in json.loads(out)


# ══════════════ 추가 커버리지 ══════════════
@pytest.mark.parametrize("ltype", list(M.LINK_TYPES))
def test_link_types_valid(ltype):
    assert ltype in M.LINK_TYPES


def test_invalid_link_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    with pytest.raises(InvalidLinkType):
        e._link("BOGUS", p, "x", "r", T0, commit=True)


def test_concept_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    e.extract_concepts(p, [("x", CONCEPT, "")], T0, commit=False)
    assert ledger.read_concepts() == []


def test_citation_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    e.add_citation(a, b, T0, commit=False)
    assert ledger.read_citations() == []


def test_comparison_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    e.compare_papers(a, b, T0, commit=False)
    assert ledger.read_comparisons() == []


def test_link_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    e.link_to_os("paper", p, "research_kg", "e", "r", T0, commit=False)
    assert ledger.read_links() == []


def test_empty_citation_graph(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _paper(e)
    g = e.build_citation_graph()
    assert g["edge_count"] == 0
    assert g["has_cycle"] is False


def test_lineage_no_parent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    c = e.extract_concepts(p, [("solo", CONCEPT, "")], T0, commit=True)[0]
    assert e.trace_concept_lineage(c.concept_id) == []


def test_citation_lineage_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    assert e.trace_citation_lineage(p) == []


def test_paper_concepts_none(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = _paper(e)
    assert e.paper_concepts(p) == []


def test_compare_disjoint_zero_similarity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    e.extract_concepts(a, [("x", CONCEPT, "")], T0, commit=True)
    e.extract_concepts(b, [("y", CONCEPT, "")], T0, commit=True)
    cmp = e.compare_papers(a, b, T1, commit=True)
    assert cmp.similarity == 0.0
    assert cmp.shared_concepts == []


def test_compare_identical_full_similarity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    e.extract_concepts(a, [("x", CONCEPT, "")], T0, commit=True)
    e.extract_concepts(b, [("x", CONCEPT, "")], T0, commit=True)
    cmp = e.compare_papers(a, b, T1, commit=True)
    assert cmp.similarity == 1.0


def test_multiple_citations_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    c = _paper(e, "C", "10.1/c")
    d = _paper(e, "D", "10.1/d")
    e.add_citation(a, b, T0, commit=True)
    e.add_citation(a, c, T0, commit=True)
    e.add_citation(b, d, T0, commit=True)
    assert e.trace_citation_lineage(a) == sorted([b, c, d])


def test_duplicate_group_three(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    ids = [e.register_paper("Alpha", [], 2020, "", f"10.1/{i}", "", T0, commit=True).paper_id
           for i in range(3)]
    dups = e.detect_duplicate_papers()
    assert dups == [sorted(ids)]


def test_strategy_ideas_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().strategy_ideas() == []


def test_paper_fingerprint_matches(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    p = e.register_paper("The Title", [], 2020, "", "10.1/x", "", T0, commit=True)
    assert p.fingerprint == M.fingerprint("The Title")


def test_verify_lineage_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_literature.verify import lineage_integrity
    e = _eng()
    p = _paper(e)
    root = e.extract_concepts(p, [("root", CONCEPT, "")], T0, commit=True)[0]
    e._record_concept("child", CONCEPT, "", root.concept_id, T0, commit=True)
    assert lineage_integrity()["ok"] is True


def test_verify_citation_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_literature.verify import citation_graph_integrity
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    e.add_citation(a, b, T0, commit=True)
    assert citation_graph_integrity()["ok"] is True


def test_comparison_symmetric_order_in_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = _paper(e, "A", "10.1/a")
    b = _paper(e, "B", "10.1/b")
    # paper_a/paper_b 는 정렬 저장
    cmp = e.compare_papers(b, a, T0, commit=True)
    assert [cmp.paper_a, cmp.paper_b] == sorted([a, b])


# ══════════════ 통합 시나리오 ══════════════
def test_end_to_end_literature(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "kg_entities.jsonl", [{"entity_id": "momentum_ent"}])
    e = _eng()
    jt = e.register_paper("Returns to Buying Winners", ["Jegadeesh", "Titman"], 1993, "JF",
                          "10.1111/jt93", "", T0, commit=True).paper_id
    fama = e.register_paper("Common Risk Factors", ["Fama", "French"], 1993, "JFE",
                            "10.1016/ff93", "", T0, commit=True).paper_id
    e.extract_concepts(jt, [("momentum", CONCEPT, ""), ("cross-sectional", METHOD, "")], T0,
                       commit=True)
    e.extract_concepts(fama, [("value", CONCEPT, ""), ("size", CONCEPT, ""),
                              ("cross-sectional", METHOD, "")], T0, commit=True)
    e.extract_strategy_ideas(jt, [("buy 12m winners", "hold 3m")], T0, commit=True)
    e.add_citation(jt, fama, T0, commit=True)
    e.link_to_os("paper", jt, "research_kg", "momentum_ent", "grounds", T0, commit=True,
                 verify_ref=True)
    cmp = e.compare_papers(jt, fama, T1, commit=True)
    assert "cross-sectional" not in cmp.shared_concepts  # concept ids, not names
    assert cmp.similarity > 0  # cross-sectional 공유
    g = e.build_citation_graph()
    assert g["edge_count"] == 1
    assert e.trace_citation_lineage(jt) == [fama]
    from jarvis.research_literature.verify import verify_chain
    v = verify_chain()
    assert v["ok"] is True
    assert v["citation"]["ok"] and v["lineage"]["ok"]
    s = e.summary(T1)
    assert s.paper_count == 2
    assert s.strategy_idea_count == 1
    # OS 원장 무변경
    assert open(sp("kg_entities.jsonl")).read().count("momentum_ent") == 1
