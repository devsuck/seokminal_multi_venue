"""Research Literature 원장 (P11.3) — 5개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 rli_ 접두사(Research Literature Intelligence). 각 레코드: id · timestamp · previous_hash · record_hash.
외부 지식(논문)과 연구 시스템 연결 — 읽기·기록만, 자동 전략 생성 없음. 연구 OS 는 **READ ONLY** — 파일만 읽고
절대 쓰지 않는다. import 결합 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rli_ 접두사)
PAPERS = ("rli_papers.jsonl", "paper_id")
CONCEPTS = ("rli_concepts.jsonl", "concept_id")
CITATIONS = ("rli_citations.jsonl", "citation_id")
LINKS = ("rli_links.jsonl", "link_id")
COMPARISONS = ("rli_comparisons.jsonl", "comparison_id")

ALL_LEDGERS = (PAPERS, CONCEPTS, CITATIONS, LINKS, COMPARISONS)

# ── 연구 OS 소스 원장(READ ONLY) — 지식 링크 대상 검증용. import 결합 없음, 파일만 읽는다. ──
SOURCE_LEDGERS = {
    "research_kg": ("kg_entities.jsonl", "entity_id"),
    "knowledge_intelligence": ("ki_insights.jsonl", "insight_id"),
    "research_governance": ("rg_strategy_versions.jsonl", "version_id"),
}


def _append(filename: str, record: dict) -> None:
    p = state_path(filename)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_jsonl(filename: str) -> list[dict]:
    p = state_path(filename)
    if not os.path.exists(p):
        return []
    out: list[dict] = []
    with open(p) as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except (ValueError, json.JSONDecodeError):
                continue
    return out


def _head(filename: str) -> dict | None:
    recs = read_jsonl(filename)
    return recs[-1] if recs else None


def _exists(filename: str, id_field: str, rid: str) -> bool:
    return any(r.get(id_field) == rid for r in read_jsonl(filename))


def _get(filename: str, id_field: str, rid: str) -> dict | None:
    for r in read_jsonl(filename):
        if r.get(id_field) == rid:
            return r
    return None


# ── 연구 OS READ ONLY ──
def source_exists(filename: str) -> bool:
    return os.path.exists(state_path(filename))


def read_source(filename: str) -> list[dict]:
    """연구 OS 소스 원장을 읽기 전용으로 로드. 절대 쓰지 않는다."""
    return read_jsonl(filename)


def os_ref_exists(layer: str, ref: str) -> bool:
    spec = SOURCE_LEDGERS.get(layer)
    if not spec:
        return False
    return any(r.get(spec[1]) == ref for r in read_source(spec[0]))


# ── Papers ──
def append_paper(rec: dict) -> None:
    _append(PAPERS[0], rec)


def read_papers() -> list[dict]:
    return read_jsonl(PAPERS[0])


def papers_head() -> dict | None:
    return _head(PAPERS[0])


def paper_exists(paper_id: str) -> bool:
    return _exists(PAPERS[0], PAPERS[1], paper_id)


def get_paper(paper_id: str) -> dict | None:
    return _get(PAPERS[0], PAPERS[1], paper_id)


# ── Concepts ──
def append_concept(rec: dict) -> None:
    _append(CONCEPTS[0], rec)


def read_concepts() -> list[dict]:
    return read_jsonl(CONCEPTS[0])


def concepts_head() -> dict | None:
    return _head(CONCEPTS[0])


def concept_exists(concept_id: str) -> bool:
    return _exists(CONCEPTS[0], CONCEPTS[1], concept_id)


def get_concept(concept_id: str) -> dict | None:
    return _get(CONCEPTS[0], CONCEPTS[1], concept_id)


# ── Citations ──
def append_citation(rec: dict) -> None:
    _append(CITATIONS[0], rec)


def read_citations() -> list[dict]:
    return read_jsonl(CITATIONS[0])


def citations_head() -> dict | None:
    return _head(CITATIONS[0])


def citation_exists(citation_id: str) -> bool:
    return _exists(CITATIONS[0], CITATIONS[1], citation_id)


def get_citation(citation_id: str) -> dict | None:
    return _get(CITATIONS[0], CITATIONS[1], citation_id)


# ── Knowledge Links ──
def append_link(rec: dict) -> None:
    _append(LINKS[0], rec)


def read_links() -> list[dict]:
    return read_jsonl(LINKS[0])


def links_head() -> dict | None:
    return _head(LINKS[0])


def link_exists(link_id: str) -> bool:
    return _exists(LINKS[0], LINKS[1], link_id)


def get_link(link_id: str) -> dict | None:
    return _get(LINKS[0], LINKS[1], link_id)


# ── Comparisons ──
def append_comparison(rec: dict) -> None:
    _append(COMPARISONS[0], rec)


def read_comparisons() -> list[dict]:
    return read_jsonl(COMPARISONS[0])


def comparisons_head() -> dict | None:
    return _head(COMPARISONS[0])


def comparison_exists(comparison_id: str) -> bool:
    return _exists(COMPARISONS[0], COMPARISONS[1], comparison_id)


def get_comparison(comparison_id: str) -> dict | None:
    return _get(COMPARISONS[0], COMPARISONS[1], comparison_id)
