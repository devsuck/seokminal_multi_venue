"""Autonomous Research Evaluation 원장 (P12.5) — 6개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 are_ 접두사(Autonomous Research Evaluation). 각 레코드: id · timestamp · previous_hash · record_hash.
평가·점수 기록만 — 승인/배포/선택/자본 배분 없음. 상위 계층(P12.1~P12.4, P10.7)은 **READ ONLY** — 파일만 읽는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (are_ 접두사)
REGISTRY = ("are_registry.jsonl", "evaluation_event_id")     # Evaluation Registry(event-sourced)
CRITERIA = ("are_criteria.jsonl", "criterion_id")            # Evaluation Criteria
SCORES = ("are_scores.jsonl", "score_id")                    # Research Scores
BENCHMARKS = ("are_benchmarks.jsonl", "benchmark_id")        # Benchmark Records
REPORTS = ("are_reports.jsonl", "report_id")                 # Quality Reports
LINEAGE = ("are_lineage.jsonl", "artifact_id")               # Evaluation Lineage

ALL_LEDGERS = (REGISTRY, CRITERIA, SCORES, BENCHMARKS, REPORTS, LINEAGE)

# ── 상위 소스 원장(READ ONLY) — 소스 참조 검증용. import 결합 없음, 파일만 읽는다. ──
SOURCE_LEDGERS = {
    "decision_intelligence": ("di_frameworks.jsonl", "framework_id"),        # P10.7
    "autonomous_research_pipeline": ("arp_cycles.jsonl", "cycle_id"),        # P12.1
    "autonomous_experiment_scheduler": ("aes_schedules.jsonl", "schedule_event_id"),  # P12.2
    "research_agent_coordinator": ("rac_ownership.jsonl", "ownership_event_id"),  # P12.3
    "adaptive_research_loop": ("arl_proposals.jsonl", "proposal_event_id"),  # P12.4
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


# ── 상위 소스 READ ONLY ──
def source_ref_exists(layer: str, ref: str) -> bool:
    spec = SOURCE_LEDGERS.get(layer)
    if not spec:
        return False
    p = state_path(spec[0])
    if not os.path.exists(p):
        return False
    return any(r.get(spec[1]) == ref for r in read_jsonl(spec[0]))


# ── Registry (event-sourced evaluations) ──
def append_evaluation_event(rec: dict) -> None:
    _append(REGISTRY[0], rec)


def read_evaluation_events() -> list[dict]:
    return read_jsonl(REGISTRY[0])


def registry_head() -> dict | None:
    return _head(REGISTRY[0])


def evaluation_event_exists(evaluation_event_id: str) -> bool:
    return _exists(REGISTRY[0], REGISTRY[1], evaluation_event_id)


def evaluation_events(evaluation_id: str) -> list[dict]:
    return [r for r in read_evaluation_events() if r.get("evaluation_id") == evaluation_id]


def evaluation_ids() -> list[str]:
    return sorted({r.get("evaluation_id") for r in read_evaluation_events()
                   if r.get("evaluation_id")})


# ── Criteria ──
def append_criterion(rec: dict) -> None:
    _append(CRITERIA[0], rec)


def read_criteria() -> list[dict]:
    return read_jsonl(CRITERIA[0])


def criteria_head() -> dict | None:
    return _head(CRITERIA[0])


def criterion_exists(criterion_id: str) -> bool:
    return _exists(CRITERIA[0], CRITERIA[1], criterion_id)


def get_criterion(criterion_id: str) -> dict | None:
    return _get(CRITERIA[0], CRITERIA[1], criterion_id)


def dimension_weights() -> dict:
    """차원별 가중치(기준의 weight, 없으면 1.0). 여러 기준이면 첫 등장 우선(결정적)."""
    out: dict = {}
    for c in read_criteria():
        dim = c.get("dimension")
        if dim and dim not in out:
            out[dim] = float(c.get("weight", 1.0))
    return out


# ── Scores ──
def append_score(rec: dict) -> None:
    _append(SCORES[0], rec)


def read_scores() -> list[dict]:
    return read_jsonl(SCORES[0])


def scores_head() -> dict | None:
    return _head(SCORES[0])


def score_exists(score_id: str) -> bool:
    return _exists(SCORES[0], SCORES[1], score_id)


def get_score(score_id: str) -> dict | None:
    return _get(SCORES[0], SCORES[1], score_id)


def evaluation_scores(evaluation_id: str) -> list[dict]:
    return [r for r in read_scores() if r.get("evaluation_id") == evaluation_id]


# ── Benchmarks ──
def append_benchmark(rec: dict) -> None:
    _append(BENCHMARKS[0], rec)


def read_benchmarks() -> list[dict]:
    return read_jsonl(BENCHMARKS[0])


def benchmarks_head() -> dict | None:
    return _head(BENCHMARKS[0])


def benchmark_exists(benchmark_id: str) -> bool:
    return _exists(BENCHMARKS[0], BENCHMARKS[1], benchmark_id)


def get_benchmark(benchmark_id: str) -> dict | None:
    return _get(BENCHMARKS[0], BENCHMARKS[1], benchmark_id)


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


# ── Lineage (artifacts) ──
def append_artifact(rec: dict) -> None:
    _append(LINEAGE[0], rec)


def read_artifacts() -> list[dict]:
    return read_jsonl(LINEAGE[0])


def lineage_head() -> dict | None:
    return _head(LINEAGE[0])


def artifact_exists(artifact_id: str) -> bool:
    return _exists(LINEAGE[0], LINEAGE[1], artifact_id)
