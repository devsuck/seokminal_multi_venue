"""Research Memory Intelligence 원장 (P27) — 9개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rmi_ 접두사(Research Memory Intelligence). 각 레코드: id · timestamp · previous_hash · record_hash.
지식 메모리 기록만 — 실행·거래·배포 없음. 상위 계층(P10~P26)은 **READ ONLY** — 파일만 읽는다(소유 결합 없음, 변경 없음).
P10.5 KG·P20 Research Memory 소유권 불변. 진화는 과거 메모리 변경이 아니라 새 append 이벤트로만 이뤄진다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

MEMORIES = ("rmi_memories.jsonl", "memory_event_id")             # 지식 메모리 생애주기(ES)
PATTERNS = ("rmi_patterns.jsonl", "pattern_id")                  # 패턴 기록
LESSONS = ("rmi_lessons.jsonl", "lesson_id")                     # 연구 교훈
SUCCESSES = ("rmi_successes.jsonl", "success_id")                # 성공 메모리
FAILURES = ("rmi_failures.jsonl", "failure_id")                  # 실패 메모리
EVOLUTION_EVENTS = ("rmi_evolution_events.jsonl", "event_id")    # 지식 진화 이벤트
RETRIEVALS = ("rmi_retrievals.jsonl", "retrieval_id")           # 메모리 검색 기록
REPORTS = ("rmi_reports.jsonl", "report_id")                    # 진화 리포트
ARTIFACTS = ("rmi_artifacts.jsonl", "artifact_id")             # 메모리 계보

ALL_LEDGERS = (MEMORIES, PATTERNS, LESSONS, SUCCESSES, FAILURES, EVOLUTION_EVENTS, RETRIEVALS,
               REPORTS, ARTIFACTS)

# ── 지식 관측 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "alpha_intelligence": ("ai_experiments.jsonl", "experiment_id"),      # P10.3
    "knowledge_graph": ("kg_entities.jsonl", "entity_id"),                # P10.5
    "agent_governance": ("arg_agents.jsonl", "agent_id"),                # P10.6
    "decision_intelligence": ("di_candidates.jsonl", "event_id"),        # P10.7
    "simulation": ("sim_scenarios.jsonl", "event_id"),                   # P10.8
    "research_memory": ("rm_lessons.jsonl", "lesson_id"),                # P20
    "research_automation": ("ra_workflows.jsonl", "workflow_event_id"),   # P22
    "monitoring": ("rmon_anomalies.jsonl", "anomaly_id"),                # P23
    "reliability": ("rel_incidents.jsonl", "incident_event_id"),         # P24
    "autonomous_research": ("ar_cycles.jsonl", "cycle_event_id"),        # P25
    "agent_coordination": ("racd_consensus.jsonl", "consensus_id"),      # P26
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


# ── 관측 대상 READ ONLY ──
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


append_memory_event, read_memory_events, memories_head, memory_event_exists = _readers(MEMORIES)
append_pattern, read_patterns, patterns_head, pattern_exists = _readers(PATTERNS)
append_lesson, read_lessons, lessons_head, lesson_exists = _readers(LESSONS)
append_success, read_successes, successes_head, success_exists = _readers(SUCCESSES)
append_failure, read_failures, failures_head, failure_exists = _readers(FAILURES)
append_evolution, read_evolution_events, evolution_head, evolution_exists = _readers(EVOLUTION_EVENTS)
append_retrieval, read_retrievals, retrievals_head, retrieval_exists = _readers(RETRIEVALS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


# ── 그룹 조회 ──
def memory_events(mem) -> list[dict]:
    return [r for r in read_memory_events() if r.get("memory_id") == mem]


def memory_ids() -> list[str]:
    return sorted({r.get("memory_id") for r in read_memory_events() if r.get("memory_id")})


def evolution_for(mem) -> list[dict]:
    return [r for r in read_evolution_events() if r.get("memory_id") == mem]


def memory_genesis(mem) -> dict | None:
    evs = memory_events(mem)
    return evs[0] if evs else None
