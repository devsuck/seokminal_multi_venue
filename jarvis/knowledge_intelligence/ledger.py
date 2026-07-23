"""Knowledge Intelligence 원장 (P10.27) — 7개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 ki_ 접두사(Knowledge Intelligence). 각 레코드: id · timestamp · previous_hash · record_hash. 상위
지식 인텔리전스 분석·기록만 — 자동 선택·승인·배포 없음. 상위 소스(P10.5 kg_·P10.21 gm_·P10.26 rl_)는 **READ ONLY**.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (ki_ 접두사)
INSIGHTS = ("ki_insights.jsonl", "insight_id")
SIMILARITY = ("ki_similarity.jsonl", "similarity_id")
CLUSTERS = ("ki_clusters.jsonl", "cluster_id")
CONTRADICTIONS = ("ki_contradictions.jsonl", "contradiction_id")
PATTERNS = ("ki_patterns.jsonl", "pattern_id")
REPORTS = ("ki_reports.jsonl", "report_id")
ARTIFACTS = ("ki_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (INSIGHTS, SIMILARITY, CLUSTERS, CONTRADICTIONS, PATTERNS, REPORTS, ARTIFACTS)

# 상위 소스 원장(READ ONLY) — P10.5/P10.21/P10.26. import 결합 없음, 파일만 읽는다.
SOURCE_LEDGERS = {
    "research_kg": ("kg_entities.jsonl", "entity_id"),
    "governance_memory": ("gm_entries.jsonl", "entry_id"),
    "research_lifecycle": ("rl_projects.jsonl", "event_id"),
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


# ── 상위 소스 READ ONLY ──
def read_source(filename: str) -> list[dict]:
    """상위 소스 원장을 읽기 전용으로 로드. 절대 쓰지 않는다."""
    return read_jsonl(filename)


def source_count(layer: str) -> int:
    spec = SOURCE_LEDGERS.get(layer)
    if not spec:
        return 0
    return len(read_source(spec[0]))


# ── Insights (불변) ──
def append_insight(rec: dict) -> None:
    _append(INSIGHTS[0], rec)


def read_insights() -> list[dict]:
    return read_jsonl(INSIGHTS[0])


def insights_head() -> dict | None:
    return _head(INSIGHTS[0])


def insight_exists(insight_id: str) -> bool:
    return _exists(INSIGHTS[0], INSIGHTS[1], insight_id)


def get_insight(insight_id: str) -> dict | None:
    for r in read_insights():
        if r.get("insight_id") == insight_id:
            return r
    return None


# ── Similarity (불변) ──
def append_similarity(rec: dict) -> None:
    _append(SIMILARITY[0], rec)


def read_similarity() -> list[dict]:
    return read_jsonl(SIMILARITY[0])


def similarity_head() -> dict | None:
    return _head(SIMILARITY[0])


def similarity_exists(similarity_id: str) -> bool:
    return _exists(SIMILARITY[0], SIMILARITY[1], similarity_id)


def get_similarity(similarity_id: str) -> dict | None:
    for r in read_similarity():
        if r.get("similarity_id") == similarity_id:
            return r
    return None


# ── Clusters (불변) ──
def append_cluster(rec: dict) -> None:
    _append(CLUSTERS[0], rec)


def read_clusters() -> list[dict]:
    return read_jsonl(CLUSTERS[0])


def clusters_head() -> dict | None:
    return _head(CLUSTERS[0])


def cluster_exists(cluster_id: str) -> bool:
    return _exists(CLUSTERS[0], CLUSTERS[1], cluster_id)


def get_cluster(cluster_id: str) -> dict | None:
    for r in read_clusters():
        if r.get("cluster_id") == cluster_id:
            return r
    return None


# ── Contradictions (불변) ──
def append_contradiction(rec: dict) -> None:
    _append(CONTRADICTIONS[0], rec)


def read_contradictions() -> list[dict]:
    return read_jsonl(CONTRADICTIONS[0])


def contradictions_head() -> dict | None:
    return _head(CONTRADICTIONS[0])


def contradiction_exists(contradiction_id: str) -> bool:
    return _exists(CONTRADICTIONS[0], CONTRADICTIONS[1], contradiction_id)


def get_contradiction(contradiction_id: str) -> dict | None:
    for r in read_contradictions():
        if r.get("contradiction_id") == contradiction_id:
            return r
    return None


# ── Patterns (불변) ──
def append_pattern(rec: dict) -> None:
    _append(PATTERNS[0], rec)


def read_patterns() -> list[dict]:
    return read_jsonl(PATTERNS[0])


def patterns_head() -> dict | None:
    return _head(PATTERNS[0])


def pattern_exists(pattern_id: str) -> bool:
    return _exists(PATTERNS[0], PATTERNS[1], pattern_id)


def get_pattern(pattern_id: str) -> dict | None:
    for r in read_patterns():
        if r.get("pattern_id") == pattern_id:
            return r
    return None


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


# ── Artifacts (계보) ──
def append_artifact(rec: dict) -> None:
    _append(ARTIFACTS[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(ARTIFACTS[0])


def artifacts_head() -> dict | None:
    return _head(ARTIFACTS[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(ARTIFACTS[0], ARTIFACTS[1], artifact_id)
