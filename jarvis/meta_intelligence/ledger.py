"""Research Meta Intelligence 원장 (P10.12) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 mi_ 접두사(model_governance 의 mg_ 와 구별). 각 레코드: id · timestamp · previous_hash ·
record_hash. 메타 연구 기록만 — 실행/거래/배포 없음. 상위 레이어(P10.2~P10.11)는 **READ ONLY**.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (mi_ 접두사)
PATTERNS = ("mi_patterns.jsonl", "event_id")            # 이벤트 소싱
METHODS = ("mi_methods.jsonl", "method_id")
OUTCOMES = ("mi_outcomes.jsonl", "event_id")            # 이벤트 소싱
FAILURES = ("mi_failures.jsonl", "failure_id")
QUALITY_SCORES = ("mi_quality_scores.jsonl", "score_id")
INSIGHTS = ("mi_insights.jsonl", "event_id")            # 이벤트 소싱
REPORTS = ("mi_reports.jsonl", "report_id")
ARTIFACTS = ("mi_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (PATTERNS, METHODS, OUTCOMES, FAILURES, QUALITY_SCORES, INSIGHTS, REPORTS,
               ARTIFACTS)

# 상위 레이어 물리 원장(READ ONLY 데이터 소스) — import 결합 없음, 파일만 읽는다.
SOURCE_LEDGERS = {
    "research_governance": ("rg_experiments.jsonl", "experiment_id"),
    "alpha_intelligence": ("ai_signals.jsonl", "signal_id"),
    "portfolio_research": ("pr_portfolios.jsonl", "portfolio_id"),
    "research_kg": ("kg_relationships.jsonl", "relationship_id"),
    "decision_intelligence": ("di_scorecards.jsonl", "scorecard_id"),
    "simulation_environment": ("sim_results.jsonl", "result_id"),
    "causal_intelligence": ("ci_evidences.jsonl", "evidence_id"),
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


# ── Patterns (event-sourced) ──
def append_pattern_event(rec: dict) -> None:
    _append(PATTERNS[0], rec)


def read_pattern_events() -> list[dict]:
    return read_jsonl(PATTERNS[0])


def patterns_head() -> dict | None:
    return _head(PATTERNS[0])


def pattern_event_exists(event_id: str) -> bool:
    return _exists(PATTERNS[0], PATTERNS[1], event_id)


def pattern_events_for(pattern_id: str) -> list[dict]:
    return [r for r in read_pattern_events() if r.get("pattern_id") == pattern_id]


def distinct_patterns() -> list[dict]:
    out: dict = {}
    for r in read_pattern_events():
        pid = r.get("pattern_id")
        if pid not in out:
            out[pid] = r
    return list(out.values())


# ── Methods ──
def append_method(rec: dict) -> None:
    _append(METHODS[0], rec)


def read_methods() -> list[dict]:
    return read_jsonl(METHODS[0])


def methods_head() -> dict | None:
    return _head(METHODS[0])


def method_exists(method_id: str) -> bool:
    return _exists(METHODS[0], METHODS[1], method_id)


# ── Outcomes (event-sourced) ──
def append_outcome_event(rec: dict) -> None:
    _append(OUTCOMES[0], rec)


def read_outcome_events() -> list[dict]:
    return read_jsonl(OUTCOMES[0])


def outcomes_head() -> dict | None:
    return _head(OUTCOMES[0])


def outcome_event_exists(event_id: str) -> bool:
    return _exists(OUTCOMES[0], OUTCOMES[1], event_id)


def outcome_events_for(outcome_id: str) -> list[dict]:
    return [r for r in read_outcome_events() if r.get("outcome_id") == outcome_id]


def distinct_outcomes() -> list[dict]:
    out: dict = {}
    for r in read_outcome_events():
        oid = r.get("outcome_id")
        if oid not in out:
            out[oid] = r
    return list(out.values())


# ── Failures ──
def append_failure(rec: dict) -> None:
    _append(FAILURES[0], rec)


def read_failures() -> list[dict]:
    return read_jsonl(FAILURES[0])


def failures_head() -> dict | None:
    return _head(FAILURES[0])


def failure_exists(failure_id: str) -> bool:
    return _exists(FAILURES[0], FAILURES[1], failure_id)


# ── Quality scores ──
def append_quality_score(rec: dict) -> None:
    _append(QUALITY_SCORES[0], rec)


def read_quality_scores() -> list[dict]:
    return read_jsonl(QUALITY_SCORES[0])


def quality_head() -> dict | None:
    return _head(QUALITY_SCORES[0])


def quality_score_exists(score_id: str) -> bool:
    return _exists(QUALITY_SCORES[0], QUALITY_SCORES[1], score_id)


# ── Insights (event-sourced) ──
def append_insight_event(rec: dict) -> None:
    _append(INSIGHTS[0], rec)


def read_insight_events() -> list[dict]:
    return read_jsonl(INSIGHTS[0])


def insights_head() -> dict | None:
    return _head(INSIGHTS[0])


def insight_event_exists(event_id: str) -> bool:
    return _exists(INSIGHTS[0], INSIGHTS[1], event_id)


def insight_events_for(insight_id: str) -> list[dict]:
    return [r for r in read_insight_events() if r.get("insight_id") == insight_id]


def distinct_insights() -> list[dict]:
    out: dict = {}
    for r in read_insight_events():
        iid = r.get("insight_id")
        if iid not in out:
            out[iid] = r
    return list(out.values())


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
