"""Continuous Learning 원장 (P20) — 8개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 cl_ 접두사(Continuous Learning). 각 레코드: id · timestamp · previous_hash · record_hash · metadata ·
source_reference. 기억·검색·분석만 — 실행/학습적용 없음. 상위 계층(P10.x/P18/P19)은 **READ ONLY** — 파일만 읽는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 계층 소유 원장 (cl_ 접두사)
MEMORIES = ("cl_memories.jsonl", "memory_event_id")                    # 기억 생애주기(ES)
EXPERIMENT_MEMORIES = ("cl_experiment_memories.jsonl", "experiment_memory_id")  # 실험 기억
FAILURE_RECORDS = ("cl_failure_records.jsonl", "failure_id")           # 실패 기억(음성 지식)
SUCCESS_PATTERNS = ("cl_success_patterns.jsonl", "pattern_id")         # 성공 패턴
RESEARCH_LESSONS = ("cl_research_lessons.jsonl", "lesson_event_id")    # 교훈 생애주기(ES)
RETRIEVAL_EVENTS = ("cl_retrieval_events.jsonl", "retrieval_id")       # 검색 이벤트
LEARNING_METRICS = ("cl_learning_metrics.jsonl", "metric_id")         # 학습 지표(관찰)
ARTIFACTS = ("cl_artifacts.jsonl", "artifact_id")                     # 아티팩트 계보

ALL_LEDGERS = (MEMORIES, EXPERIMENT_MEMORIES, FAILURE_RECORDS, SUCCESS_PATTERNS, RESEARCH_LESSONS,
               RETRIEVAL_EVENTS, LEARNING_METRICS, ARTIFACTS)

# ── 상위 소스(READ ONLY) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "knowledge_graph": ("kg_entities.jsonl", "event_id"),               # P10.5
    "agent_governance": ("arg_agents.jsonl", "event_id"),               # P10.6
    "decision_intelligence": ("di_candidates.jsonl", "event_id"),       # P10.7
    "simulation": ("sim_scenarios.jsonl", "event_id"),                  # P10.8
    "research_operations": ("ro_workflows.jsonl", "workflow_event_id"),  # P18
    "research_collaboration": ("rcol_collaborations.jsonl", "collab_event_id"),  # P19
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


# ── 상위 소스 READ ONLY ──
def source_count(layer) -> int:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return 0
    return len(read_jsonl(spec[0]))


def source_ref_exists(layer, ref) -> bool:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return False
    p = state_path(spec[0])
    if not os.path.exists(p):
        return False
    return any(r.get(spec[1]) == ref for r in read_jsonl(spec[0]))


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
append_experiment, read_experiments, experiments_head, experiment_exists = _readers(EXPERIMENT_MEMORIES)
append_failure, read_failures, failures_head, failure_exists = _readers(FAILURE_RECORDS)
append_pattern, read_patterns, patterns_head, pattern_exists = _readers(SUCCESS_PATTERNS)
append_lesson_event, read_lesson_events, lessons_head, lesson_event_exists = _readers(RESEARCH_LESSONS)
append_retrieval, read_retrievals, retrievals_head, retrieval_exists = _readers(RETRIEVAL_EVENTS)
append_metric, read_metrics, metrics_head, metric_exists = _readers(LEARNING_METRICS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


# ── 그룹 조회 ──
def memory_events(mem) -> list[dict]:
    return [r for r in read_memory_events() if r.get("memory_id") == mem]


def memory_ids() -> list[str]:
    return sorted({r.get("memory_id") for r in read_memory_events() if r.get("memory_id")})


def lesson_events(les) -> list[dict]:
    return [r for r in read_lesson_events() if r.get("lesson_id") == les]


def lesson_ids() -> list[str]:
    return sorted({r.get("lesson_id") for r in read_lesson_events() if r.get("lesson_id")})
