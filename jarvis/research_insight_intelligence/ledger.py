"""Research Insight Intelligence 원장 (P28) — 8개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rii_ 접두사(Research Insight Intelligence). 각 레코드: id · timestamp · previous_hash · record_hash.
해석·통찰 기록만 — 실행·거래·배포·선택 없음. 상위 계층(P10~P27)은 **READ ONLY** — 파일만 읽는다(소유 결합 없음, 변경 없음).
INSIGHT ≠ DECISION · INSIGHT ≠ RECOMMENDATION.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

INSIGHTS = ("rii_insights.jsonl", "insight_event_id")             # 통찰 생애주기(ES)
CONTEXTS = ("rii_contexts.jsonl", "context_id")                  # 맥락 분석
INTERPRETATIONS = ("rii_interpretations.jsonl", "interpretation_id")  # 증거 해석
EVIDENCE_LINKS = ("rii_evidence_links.jsonl", "evidence_link_id")  # 증거 연결
RESEARCH_GAPS = ("rii_research_gaps.jsonl", "gap_id")            # 연구 공백
RELATIONSHIPS = ("rii_relationships.jsonl", "relationship_id")   # 통찰 관계
REPORTS = ("rii_reports.jsonl", "report_id")                    # 해석 리포트
ARTIFACTS = ("rii_artifacts.jsonl", "artifact_id")             # 통찰 계보

ALL_LEDGERS = (INSIGHTS, CONTEXTS, INTERPRETATIONS, EVIDENCE_LINKS, RESEARCH_GAPS, RELATIONSHIPS,
               REPORTS, ARTIFACTS)

# ── 해석 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "knowledge_graph": ("kg_entities.jsonl", "entity_id"),               # P10.5
    "decision_intelligence": ("di_candidates.jsonl", "event_id"),       # P10.7
    "simulation": ("sim_scenarios.jsonl", "event_id"),                  # P10.8
    "research_memory": ("rm_lessons.jsonl", "lesson_id"),               # P20
    "monitoring": ("rmon_anomalies.jsonl", "anomaly_id"),               # P23
    "reliability": ("rel_incidents.jsonl", "incident_event_id"),        # P24
    "autonomous_research": ("ar_cycles.jsonl", "cycle_event_id"),       # P25
    "agent_coordination": ("racd_consensus.jsonl", "consensus_id"),     # P26
    "memory_intelligence": ("rmi_memories.jsonl", "memory_event_id"),   # P27
}


def _append(filename, record) -> None:
    p = state_path(filename)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_jsonl(filename) -> list[dict]:
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


def _head(filename):
    recs = read_jsonl(filename)
    return recs[-1] if recs else None


def _exists(filename, id_field, rid) -> bool:
    return any(r.get(id_field) == rid for r in read_jsonl(filename))


# ── 해석 대상 READ ONLY ──
def source_count(layer) -> int:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return 0
    return len(read_jsonl(spec[0]))


def source_present(layer) -> bool:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return False
    return os.path.exists(state_path(spec[0]))


def source_ref_exists(layer, rid) -> bool:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return False
    return _exists(spec[0], spec[1], rid)


def all_source_counts() -> dict:
    return {k: source_count(k) for k in sorted(SOURCE_LAYERS)}


# ── helper 팩토리 ──
def _readers(spec):
    fname, idf = spec

    def append(rec):
        _append(fname, rec)

    def read():
        return read_jsonl(fname)

    def head():
        return _head(fname)

    def exists(rid):
        return _exists(fname, idf, rid)

    return append, read, head, exists


append_insight_event, read_insight_events, insights_head, insight_event_exists = _readers(INSIGHTS)
append_context, read_contexts, contexts_head, context_exists = _readers(CONTEXTS)
append_interpretation, read_interpretations, interpretations_head, interpretation_exists = _readers(INTERPRETATIONS)
append_evidence_link, read_evidence_links, evidence_links_head, evidence_link_exists = _readers(EVIDENCE_LINKS)
append_gap, read_research_gaps, gaps_head, gap_exists = _readers(RESEARCH_GAPS)
append_relationship, read_relationships, relationships_head, relationship_exists = _readers(RELATIONSHIPS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


# ── 그룹 조회 ──
def insight_events(ins) -> list[dict]:
    return [r for r in read_insight_events() if r.get("insight_id") == ins]


def insight_ids() -> list[str]:
    return sorted({r.get("insight_id") for r in read_insight_events() if r.get("insight_id")})


def interpretations_for(ins) -> list[dict]:
    return [r for r in read_interpretations() if r.get("insight_id") == ins]


def evidence_for(ins) -> list[dict]:
    return [r for r in read_evidence_links() if r.get("insight_id") == ins]
