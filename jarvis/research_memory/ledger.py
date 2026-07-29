"""Research Memory Intelligence 원장 (P10.14) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 rm_ 접두사. 각 레코드: id · timestamp · previous_hash · record_hash. 연구 기억 기록만 —
실행/거래/배포/학습갱신 없음. 상위 레이어(P10.5/7/8/11/12/13)는 **READ ONLY**.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rm_ 접두사)
MEMORIES = ("rm_memories.jsonl", "event_id")            # 이벤트 소싱
LESSONS = ("rm_lessons.jsonl", "lesson_id")
PATTERNS = ("rm_patterns.jsonl", "pattern_id")
CONNECTIONS = ("rm_connections.jsonl", "connection_id")
RETRIEVALS = ("rm_retrievals.jsonl", "retrieval_id")
CLUSTERS = ("rm_clusters.jsonl", "cluster_id")
REPORTS = ("rm_reports.jsonl", "report_id")
ARTIFACTS = ("rm_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (MEMORIES, LESSONS, PATTERNS, CONNECTIONS, RETRIEVALS, CLUSTERS, REPORTS,
               ARTIFACTS)

# 상위 레이어 물리 원장(READ ONLY 데이터 소스) — import 결합 없음, 파일만 읽는다.
SOURCE_LEDGERS = {
    "research_kg": ("kg_entities.jsonl", "entity_id"),
    "decision_intelligence": ("di_reports.jsonl", "report_id"),
    "simulation_environment": ("sim_results.jsonl", "result_id"),
    "causal_intelligence": ("ci_evidences.jsonl", "evidence_id"),
    "meta_intelligence": ("mi_insights.jsonl", "event_id"),
    "self_improvement_intelligence": ("si_recommendations.jsonl", "event_id"),
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


# ── 상위 레이어 READ ONLY 소스 ──
def read_source(filename: str) -> list[dict]:
    """상위 레이어 원장을 읽기 전용으로 로드. 절대 쓰지 않는다."""
    return read_jsonl(filename)


# ── Memories (event-sourced) ──
def append_memory_event(rec: dict) -> None:
    _append(MEMORIES[0], rec)


def read_memory_events() -> list[dict]:
    return read_jsonl(MEMORIES[0])


def memories_head() -> dict | None:
    return _head(MEMORIES[0])


def memory_event_exists(event_id: str) -> bool:
    return _exists(MEMORIES[0], MEMORIES[1], event_id)


def memory_events_for(memory_id: str) -> list[dict]:
    return [r for r in read_memory_events() if r.get("memory_id") == memory_id]


def distinct_memories() -> list[dict]:
    out: dict = {}
    for r in read_memory_events():
        mid = r.get("memory_id")
        if mid not in out:
            out[mid] = r
    return list(out.values())


def memory_exists(memory_id: str) -> bool:
    return any(r.get("memory_id") == memory_id for r in read_memory_events())


# ── Lessons ──
def append_lesson(rec: dict) -> None:
    _append(LESSONS[0], rec)


def read_lessons() -> list[dict]:
    return read_jsonl(LESSONS[0])


def lessons_head() -> dict | None:
    return _head(LESSONS[0])


def lesson_exists(lesson_id: str) -> bool:
    return _exists(LESSONS[0], LESSONS[1], lesson_id)


def get_lesson(lesson_id: str) -> dict | None:
    for r in read_lessons():
        if r.get("lesson_id") == lesson_id:
            return r
    return None


# ── Patterns ──
def append_pattern(rec: dict) -> None:
    _append(PATTERNS[0], rec)


def read_patterns() -> list[dict]:
    return read_jsonl(PATTERNS[0])


def patterns_head() -> dict | None:
    return _head(PATTERNS[0])


def pattern_exists(pattern_id: str) -> bool:
    return _exists(PATTERNS[0], PATTERNS[1], pattern_id)


# ── Connections ──
def append_connection(rec: dict) -> None:
    _append(CONNECTIONS[0], rec)


def read_connections() -> list[dict]:
    return read_jsonl(CONNECTIONS[0])


def connections_head() -> dict | None:
    return _head(CONNECTIONS[0])


def connection_exists(connection_id: str) -> bool:
    return _exists(CONNECTIONS[0], CONNECTIONS[1], connection_id)


# ── Retrievals ──
def append_retrieval(rec: dict) -> None:
    _append(RETRIEVALS[0], rec)


def read_retrievals() -> list[dict]:
    return read_jsonl(RETRIEVALS[0])


def retrievals_head() -> dict | None:
    return _head(RETRIEVALS[0])


def retrieval_exists(retrieval_id: str) -> bool:
    return _exists(RETRIEVALS[0], RETRIEVALS[1], retrieval_id)


# ── Clusters ──
def append_cluster(rec: dict) -> None:
    _append(CLUSTERS[0], rec)


def read_clusters() -> list[dict]:
    return read_jsonl(CLUSTERS[0])


def clusters_head() -> dict | None:
    return _head(CLUSTERS[0])


def cluster_exists(cluster_id: str) -> bool:
    return _exists(CLUSTERS[0], CLUSTERS[1], cluster_id)


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


# ── Artifacts ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
