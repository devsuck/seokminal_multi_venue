"""Governance Feedback 원장 (P10.20) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 gf_ 접두사. 각 레코드: id · timestamp · previous_hash · record_hash. 거버넌스 피드백 학습
기록만 — 정책/permission/config 변경·자동 수정·승인·실행 없음. 상위 레이어(P9.8~P10.19)는 **READ ONLY**.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (gf_ 접두사)
FEEDBACK = ("gf_feedback.jsonl", "feedback_id")
ISSUES = ("gf_issues.jsonl", "event_id")                  # 이벤트 소싱
PATTERNS = ("gf_patterns.jsonl", "pattern_id")
THEMES = ("gf_themes.jsonl", "theme_id")
AGGREGATIONS = ("gf_aggregations.jsonl", "aggregation_id")
REVIEWS = ("gf_reviews.jsonl", "review_id")
REPORTS = ("gf_reports.jsonl", "report_id")
ARTIFACTS = ("gf_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (FEEDBACK, ISSUES, PATTERNS, THEMES, AGGREGATIONS, REVIEWS, REPORTS, ARTIFACTS)

# 상위 레이어 물리 원장(READ ONLY 데이터 소스) — import 결합 없음, 파일만 읽는다.
# 논리 레이어명 -> (대표 원장 파일명, id 필드)
SOURCE_LEDGERS = {
    "data_governance": ("dg_datasets.jsonl", "dataset_id"),
    "model_governance": ("mg_models.jsonl", "model_id"),
    "access_governance": ("ag_operators.jsonl", "identity_hash"),
    "research_data": ("datasets.jsonl", "dataset_id"),
    "research_governance": ("rg_strategies.jsonl", "strategy_id"),
    "alpha_intelligence": ("ai_signals.jsonl", "signal_id"),
    "portfolio_research": ("pr_portfolios.jsonl", "portfolio_id"),
    "research_kg": ("kg_entities.jsonl", "entity_id"),
    "agent_governance": ("arg_agents.jsonl", "agent_id"),
    "decision_intelligence": ("di_candidates.jsonl", "candidate_id"),
    "simulation_environment": ("sim_scenarios.jsonl", "scenario_id"),
    "research_validation": ("rv_validations.jsonl", "event_id"),
    "research_observatory": ("ob_snapshots.jsonl", "event_id"),
    "causal_intelligence": ("ci_hypotheses.jsonl", "event_id"),
    "meta_intelligence": ("mi_patterns.jsonl", "event_id"),
    "self_improvement_intelligence": ("si_opportunities.jsonl", "event_id"),
    "research_memory": ("rm_memories.jsonl", "event_id"),
    "research_planning": ("rp_opportunities.jsonl", "event_id"),
    "research_evolution": ("ev_research_objects.jsonl", "object_id"),
    "research_os": ("ros_layers.jsonl", "event_id"),
    "research_orchestration": ("or_workflows.jsonl", "event_id"),
    "research_observability": ("mh_health_records.jsonl", "health_id"),
    "research_compliance": ("rc_rules.jsonl", "rule_id"),
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


def source_count(layer: str) -> int:
    spec = SOURCE_LEDGERS.get(layer)
    if not spec:
        return 0
    return len(read_source(spec[0]))


# ── Feedback (불변) ──
def append_feedback(rec: dict) -> None:
    _append(FEEDBACK[0], rec)


def read_feedback() -> list[dict]:
    return read_jsonl(FEEDBACK[0])


def feedback_head() -> dict | None:
    return _head(FEEDBACK[0])


def feedback_exists(feedback_id: str) -> bool:
    return _exists(FEEDBACK[0], FEEDBACK[1], feedback_id)


def get_feedback(feedback_id: str) -> dict | None:
    for r in read_feedback():
        if r.get("feedback_id") == feedback_id:
            return r
    return None


def feedback_by_category(category: str) -> list[dict]:
    return [r for r in read_feedback() if r.get("category") == category]


# ── Issues (event-sourced) ──
def append_issue_event(rec: dict) -> None:
    _append(ISSUES[0], rec)


def read_issue_events() -> list[dict]:
    return read_jsonl(ISSUES[0])


def issues_head() -> dict | None:
    return _head(ISSUES[0])


def issue_event_exists(event_id: str) -> bool:
    return _exists(ISSUES[0], ISSUES[1], event_id)


def issue_events_for(issue_id: str) -> list[dict]:
    return [r for r in read_issue_events() if r.get("issue_id") == issue_id]


def distinct_issues() -> list[dict]:
    out: dict = {}
    for r in read_issue_events():
        iid = r.get("issue_id")
        if iid not in out:
            out[iid] = r
    return list(out.values())


def issue_exists(issue_id: str) -> bool:
    return any(r.get("issue_id") == issue_id for r in read_issue_events())


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


# ── Themes (불변) ──
def append_theme(rec: dict) -> None:
    _append(THEMES[0], rec)


def read_themes() -> list[dict]:
    return read_jsonl(THEMES[0])


def themes_head() -> dict | None:
    return _head(THEMES[0])


def theme_exists(theme_id: str) -> bool:
    return _exists(THEMES[0], THEMES[1], theme_id)


def get_theme(theme_id: str) -> dict | None:
    for r in read_themes():
        if r.get("theme_id") == theme_id:
            return r
    return None


# ── Aggregations (불변) ──
def append_aggregation(rec: dict) -> None:
    _append(AGGREGATIONS[0], rec)


def read_aggregations() -> list[dict]:
    return read_jsonl(AGGREGATIONS[0])


def aggregations_head() -> dict | None:
    return _head(AGGREGATIONS[0])


def aggregation_exists(aggregation_id: str) -> bool:
    return _exists(AGGREGATIONS[0], AGGREGATIONS[1], aggregation_id)


# ── Reviews (불변) ──
def append_review(rec: dict) -> None:
    _append(REVIEWS[0], rec)


def read_reviews() -> list[dict]:
    return read_jsonl(REVIEWS[0])


def reviews_head() -> dict | None:
    return _head(REVIEWS[0])


def review_exists(review_id: str) -> bool:
    return _exists(REVIEWS[0], REVIEWS[1], review_id)


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
