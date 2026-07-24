"""Research Literature Intelligence Engine (P11.3) — 외부 지식(논문)과 연구 시스템 연결. **읽기·기록 전용.**

논문 메타데이터·개념 추출·전략 아이디어 추출·인용 그래프·연구 비교를 수행하고 Papers·Concepts·Citations·
Knowledge Links·Comparisons 를 남긴다. 연구 OS 는 READ ONLY 로만 참조(파일 기반, import 없음). **자동 전략 생성
없음 — 전략 아이디어는 정보용 개념일 뿐이다.** execution/broker/order/portfolio execution/capital allocation/
live trading/permission/risk controller import·호출 없음. LITERATURE ≠ STRATEGY · IDEA ≠ DEPLOYMENT · CITATION ≠
EXECUTION. 상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_literature import ledger
from jarvis.research_literature.models import (
    CONCEPT,
    CONCEPT_TYPES,
    GENESIS,
    LINK_CONCEPT_OS,
    LINK_PAPER_CONCEPT,
    LINK_PAPER_OS,
    LINK_TYPES,
    SOURCE_EXTERNAL,
    STRATEGY_IDEA,
    CitationRecord,
    ComparisonRecord,
    ConceptRecord,
    ImmutableCitationError,
    ImmutableComparisonError,
    ImmutableConceptError,
    ImmutableLinkError,
    ImmutablePaperError,
    InvalidConceptType,
    InvalidLinkType,
    KnowledgeLinkRecord,
    LiteratureSummary,
    PaperRecord,
    SelfCitationError,
    UnknownConceptError,
    UnknownPaperError,
    ancestors,
    citation_id as _citation_id,
    comparison_id as _comparison_id,
    concept_id as _concept_id,
    content_hash,
    detect_cycle,
    fingerprint as _fingerprint,
    input_digest,
    jaccard,
    leaves as _leaves,
    link_id as _link_id,
    paper_id as _paper_id,
    paper_key as _paper_key,
    roots as _roots,
)

_DISCLAIMER = ("Research Literature 데이터 — LITERATURE ≠ STRATEGY · IDEA ≠ DEPLOYMENT · CITATION ≠ EXECUTION. "
               "외부 지식 연결·기록 전용 — 자동 전략 생성/배포/실행 없음. 전략 아이디어는 정보용 개념일 뿐이다.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchLiteratureEngine:
    """외부 문헌 인텔리전스. 불변·append-only·결정적. 전략 생성/배포/실행 권한 없음."""

    # ══════════════ paper metadata ══════════════
    def register_paper(self, title: str, authors=None, year: int = 0, venue: str = "",
                     doi: str = "", url: str = "", now: str = "", *, commit: bool = False) -> PaperRecord:
        """논문 메타데이터 등록(불변). doi 우선 식별, 없으면 정규화 제목+연도."""
        key = _paper_key(doi, title, year)
        pid = _paper_id(key)
        auth = list(authors or [])
        existing = ledger.get_paper(pid)
        if existing is not None:
            if existing.get("title") != title or existing.get("year") != year:
                raise ImmutablePaperError(f"{pid} 논문 불변 — 변경 불가")
            return PaperRecord(**{k: v for k, v in existing.items()
                                  if k in PaperRecord.__dataclass_fields__})
        rec = PaperRecord(
            paper_id=pid, key=key, title=title, authors=auth, year=int(year), venue=venue,
            doi=doi, url=url, fingerprint=_fingerprint(title), source=SOURCE_EXTERNAL,
            created_at=now, input_hash=input_digest(key), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.paper_exists(pid):
            head = ledger.papers_head()
            ledger.append_paper(_seal(rec, head["record_hash"] if head else GENESIS))
        return PaperRecord(**rec)

    def _require_paper(self, pid: str) -> dict:
        rec = ledger.get_paper(pid)
        if rec is None:
            raise UnknownPaperError(f"미등록 논문 {pid}")
        return rec

    # ══════════════ concept / strategy idea extraction ══════════════
    def _record_concept(self, name: str, ctype: str, description: str, parent: str, now: str,
                      *, commit: bool) -> ConceptRecord:
        if ctype not in CONCEPT_TYPES:
            raise InvalidConceptType(f"미등록 개념 종류 {ctype}")
        cid = _concept_id(name)
        existing = ledger.get_concept(cid)
        if existing is not None:
            if existing.get("concept_type") != ctype:
                raise ImmutableConceptError(f"{cid} 개념 불변 — 변경 불가")
            return ConceptRecord(**{k: v for k, v in existing.items()
                                    if k in ConceptRecord.__dataclass_fields__})
        rec = ConceptRecord(concept_id=cid, name=name, concept_type=ctype, description=description,
                            parent_concept=parent, created_at=now, input_hash=input_digest(name),
                            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.concept_exists(cid):
            head = ledger.concepts_head()
            ledger.append_concept(_seal(rec, head["record_hash"] if head else GENESIS))
        return ConceptRecord(**rec)

    def _link(self, ltype: str, source: str, target: str, relation: str, now: str,
            *, commit: bool) -> KnowledgeLinkRecord:
        if ltype not in LINK_TYPES:
            raise InvalidLinkType(f"미등록 링크 종류 {ltype}")
        lid = _link_id(ltype, source, target)
        existing = ledger.get_link(lid)
        if existing is not None:
            return KnowledgeLinkRecord(**{k: v for k, v in existing.items()
                                          if k in KnowledgeLinkRecord.__dataclass_fields__})
        rec = KnowledgeLinkRecord(link_id=lid, link_type=ltype, source_id=source, target_id=target,
                                  relation=relation, created_at=now,
                                  input_hash=input_digest(ltype, source, target),
                                  previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.link_exists(lid):
            head = ledger.links_head()
            ledger.append_link(_seal(rec, head["record_hash"] if head else GENESIS))
        return KnowledgeLinkRecord(**rec)

    def extract_concepts(self, paper: str, concepts: list, now: str = "",
                       *, commit: bool = False) -> list:
        """논문에서 개념 추출·기록 + PAPER_CONCEPT 링크. concepts=[(name,type,desc)]. **추출·기록만.**"""
        self._require_paper(paper)
        out: list = []
        for item in concepts:
            name = item[0]
            ctype = item[1] if len(item) > 1 else CONCEPT
            desc = item[2] if len(item) > 2 else ""
            c = self._record_concept(name, ctype, desc, "", now, commit=commit)
            self._link(LINK_PAPER_CONCEPT, paper, c.concept_id, "mentions", now, commit=commit)
            out.append(c)
        return out

    def extract_strategy_ideas(self, paper: str, ideas: list, now: str = "",
                             *, commit: bool = False) -> list:
        """논문에서 전략 아이디어 추출(정보용 STRATEGY_IDEA 개념). **자동 전략 생성 아님 — 기록만.**"""
        items = [(name, STRATEGY_IDEA, desc) for name, desc in ideas]
        return self.extract_concepts(paper, items, now, commit=commit)

    # ══════════════ citation graph ══════════════
    def add_citation(self, citing_paper: str, cited_paper: str, now: str = "",
                   *, commit: bool = False) -> CitationRecord:
        """인용 간선 추가(citing→cited). 자기 인용 거부. 양쪽 논문 등록 필요."""
        if citing_paper == cited_paper:
            raise SelfCitationError(f"자기 인용 {citing_paper}")
        self._require_paper(citing_paper)
        self._require_paper(cited_paper)
        xid = _citation_id(citing_paper, cited_paper)
        existing = ledger.get_citation(xid)
        if existing is not None:
            return CitationRecord(**{k: v for k, v in existing.items()
                                     if k in CitationRecord.__dataclass_fields__})
        rec = CitationRecord(citation_id=xid, citing_paper=citing_paper, cited_paper=cited_paper,
                             created_at=now, input_hash=input_digest(citing_paper, cited_paper),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.citation_exists(xid):
            head = ledger.citations_head()
            ledger.append_citation(_seal(rec, head["record_hash"] if head else GENESIS))
        return CitationRecord(**rec)

    def _citation_edges(self) -> list:
        return [(c.get("citing_paper"), c.get("cited_paper")) for c in ledger.read_citations()]

    def build_citation_graph(self) -> dict:
        """인용 그래프(노드·간선·roots·leaves·순환). **조회·검증 전용.**"""
        nodes = sorted(p.get("paper_id") for p in ledger.read_papers())
        edges = self._citation_edges()
        cyc = detect_cycle(edges)
        return {"nodes": nodes, "edges": [list(e) for e in edges], "node_count": len(nodes),
                "edge_count": len(edges), "roots": _roots(nodes, edges),
                "leaves": _leaves(nodes, edges), "has_cycle": bool(cyc), "cycle": cyc}

    def trace_citation_lineage(self, paper: str) -> list:
        """논문의 지적 계보(전이적으로 인용하는 모든 논문). **조회 전용.**"""
        return ancestors(self._citation_edges(), paper)

    # ══════════════ knowledge link (연구 OS 연결, READ ONLY) ══════════════
    def link_to_os(self, source_type: str, source_id: str, layer: str, os_ref: str,
                 relation: str = "relates_to", now: str = "", *, commit: bool = False,
                 verify_ref: bool = False) -> KnowledgeLinkRecord:
        """논문/개념을 연구 OS 엔티티에 연결(READ ONLY 참조). **연결만 — OS 변경 없음.**"""
        ltype = LINK_PAPER_OS if source_type == "paper" else LINK_CONCEPT_OS
        if source_type == "paper":
            self._require_paper(source_id)
        elif not ledger.concept_exists(source_id):
            raise UnknownConceptError(f"미등록 개념 {source_id}")
        if verify_ref and not ledger.os_ref_exists(layer, os_ref):
            raise UnknownPaperError(f"OS 참조 없음 {layer}:{os_ref}")
        return self._link(ltype, source_id, f"{layer}:{os_ref}", relation, now, commit=commit)

    # ══════════════ research comparison ══════════════
    def paper_concepts(self, paper: str) -> list:
        """논문이 언급한 개념 id 목록(PAPER_CONCEPT 링크 기반, 결정적)."""
        out = [l.get("target_id") for l in ledger.read_links()
               if l.get("link_type") == LINK_PAPER_CONCEPT and l.get("source_id") == paper]
        return sorted(set(out))

    def compare_papers(self, paper_a: str, paper_b: str, now: str = "",
                     *, commit: bool = False) -> ComparisonRecord:
        """두 논문 개념 중첩(Jaccard) 비교·기록. **비교·기록만 — 전략 생성 아님.**"""
        self._require_paper(paper_a)
        self._require_paper(paper_b)
        ca = set(self.paper_concepts(paper_a))
        cb = set(self.paper_concepts(paper_b))
        shared = sorted(ca & cb)
        only_a = sorted(ca - cb)
        only_b = sorted(cb - ca)
        sim = jaccard(ca, cb)
        cmp_id = _comparison_id(paper_a, paper_b)
        existing = ledger.get_comparison(cmp_id)
        if existing is not None:
            if abs(float(existing.get("similarity", -1)) - sim) > 1e-9:
                raise ImmutableComparisonError(f"{cmp_id} 비교 불변 — 변경 불가")
            return ComparisonRecord(**{k: v for k, v in existing.items()
                                       if k in ComparisonRecord.__dataclass_fields__})
        x, y = tuple(sorted([paper_a, paper_b]))
        rec = ComparisonRecord(
            comparison_id=cmp_id, paper_a=x, paper_b=y, shared_concepts=shared, only_a=only_a,
            only_b=only_b, similarity=sim, summary=f"{len(shared)} shared / sim={sim}",
            created_at=now, input_hash=input_digest(x, y), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.comparison_exists(cmp_id):
            head = ledger.comparisons_head()
            ledger.append_comparison(_seal(rec, head["record_hash"] if head else GENESIS))
        return ComparisonRecord(**rec)

    # ══════════════ duplicate detection ══════════════
    def detect_duplicate_papers(self) -> list:
        """정규화 제목(fingerprint) 공유 논문 그룹 탐지(중복 후보). 결정적."""
        by_fp: dict = {}
        for p in ledger.read_papers():
            by_fp.setdefault(p.get("fingerprint"), []).append(p.get("paper_id"))
        return [sorted(ids) for fp, ids in sorted(by_fp.items()) if len(ids) > 1]

    # ══════════════ concept lineage ══════════════
    def trace_concept_lineage(self, concept: str) -> list:
        by_id = {c.get("concept_id"): c for c in ledger.read_concepts()}
        out: list = []
        seen: set = set()
        cur = by_id.get(concept)
        while cur:
            parent = cur.get("parent_concept")
            if not parent or parent in seen:
                break
            seen.add(parent)
            out.append(parent)
            cur = by_id.get(parent)
        return out

    # ══════════════ knowledge integrity ══════════════
    def knowledge_integrity(self) -> dict:
        """지식 무결성: 인용/링크 dangling·자기인용, 개념 계보 dangling·순환. **탐지·보고만.**"""
        issues: list = []
        pids = {p.get("paper_id") for p in ledger.read_papers()}
        cids = {c.get("concept_id") for c in ledger.read_concepts()}
        for c in ledger.read_citations():
            if c.get("citing_paper") == c.get("cited_paper"):
                issues.append(f"self_citation:{c.get('citation_id')}")
            for f in ("citing_paper", "cited_paper"):
                if c.get(f) not in pids:
                    issues.append(f"dangling_citation:{c.get('citation_id')}:{c.get(f)}")
        for l in ledger.read_links():
            if l.get("link_type") == LINK_PAPER_CONCEPT:
                if l.get("source_id") not in pids:
                    issues.append(f"dangling_link_paper:{l.get('link_id')}")
                if l.get("target_id") not in cids:
                    issues.append(f"dangling_link_concept:{l.get('link_id')}")
        pm = {c.get("concept_id"): c.get("parent_concept") for c in ledger.read_concepts()
              if c.get("parent_concept")}
        for cid, parent in sorted(pm.items()):
            if parent not in cids:
                issues.append(f"dangling_concept_parent:{cid}->{parent}")
        cyc = detect_cycle(list(pm.items()))
        if cyc:
            issues.append("concept_lineage_cycle:" + "->".join(cyc))
        return {"ok": not issues, "issues": sorted(set(issues))}

    # ══════════════ 조회 편의 ══════════════
    def concept_papers(self, concept: str) -> list:
        out = [l.get("source_id") for l in ledger.read_links()
               if l.get("link_type") == LINK_PAPER_CONCEPT and l.get("target_id") == concept]
        return sorted(set(out))

    def list_papers(self) -> list:
        return sorted(p.get("paper_id") for p in ledger.read_papers())

    def strategy_ideas(self) -> list:
        return sorted(c.get("name") for c in ledger.read_concepts()
                      if c.get("concept_type") == STRATEGY_IDEA)

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> LiteratureSummary:
        concepts = ledger.read_concepts()
        ideas = sum(1 for c in concepts if c.get("concept_type") == STRATEGY_IDEA)
        return LiteratureSummary(
            timestamp=now, paper_count=len(ledger.read_papers()), concept_count=len(concepts),
            citation_count=len(ledger.read_citations()), link_count=len(ledger.read_links()),
            comparison_count=len(ledger.read_comparisons()), strategy_idea_count=ideas)
