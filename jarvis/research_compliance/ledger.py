"""Research Compliance 원장 (P10.19) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 rc_ 접두사. 각 레코드: id · timestamp · previous_hash · record_hash. 컴플라이언스 관찰·기록만 —
위반 자동 수정/실행/배포 승인/permission 변경 없음. 상위 레이어(P9.8~P10.18)는 **READ ONLY**.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rc_ 접두사)
RULES = ("rc_rules.jsonl", "rule_id")
CHECKS = ("rc_checks.jsonl", "check_id")
EVIDENCE = ("rc_evidence.jsonl", "evidence_id")
REVIEWS = ("rc_reviews.jsonl", "review_id")
VIOLATIONS = ("rc_violations.jsonl", "event_id")           # 이벤트 소싱
RECOMMENDATIONS = ("rc_recommendations.jsonl", "recommendation_id")
REPORTS = ("rc_reports.jsonl", "report_id")
ARTIFACTS = ("rc_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (RULES, CHECKS, EVIDENCE, REVIEWS, VIOLATIONS, RECOMMENDATIONS, REPORTS, ARTIFACTS)

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


# ── Rules (불변) ──
def append_rule(rec: dict) -> None:
    _append(RULES[0], rec)


def read_rules() -> list[dict]:
    return read_jsonl(RULES[0])


def rules_head() -> dict | None:
    return _head(RULES[0])


def rule_exists(rule_id: str) -> bool:
    return _exists(RULES[0], RULES[1], rule_id)


def get_rule(rule_id: str) -> dict | None:
    for r in read_rules():
        if r.get("rule_id") == rule_id:
            return r
    return None


# ── Checks (불변) ──
def append_check(rec: dict) -> None:
    _append(CHECKS[0], rec)


def read_checks() -> list[dict]:
    return read_jsonl(CHECKS[0])


def checks_head() -> dict | None:
    return _head(CHECKS[0])


def check_exists(check_id: str) -> bool:
    return _exists(CHECKS[0], CHECKS[1], check_id)


def get_check(check_id: str) -> dict | None:
    for r in read_checks():
        if r.get("check_id") == check_id:
            return r
    return None


# ── Evidence (불변) ──
def append_evidence(rec: dict) -> None:
    _append(EVIDENCE[0], rec)


def read_evidence() -> list[dict]:
    return read_jsonl(EVIDENCE[0])


def evidence_head() -> dict | None:
    return _head(EVIDENCE[0])


def evidence_exists(evidence_id: str) -> bool:
    return _exists(EVIDENCE[0], EVIDENCE[1], evidence_id)


def get_evidence(evidence_id: str) -> dict | None:
    for r in read_evidence():
        if r.get("evidence_id") == evidence_id:
            return r
    return None


# ── Reviews (불변) ──
def append_review(rec: dict) -> None:
    _append(REVIEWS[0], rec)


def read_reviews() -> list[dict]:
    return read_jsonl(REVIEWS[0])


def reviews_head() -> dict | None:
    return _head(REVIEWS[0])


def review_exists(review_id: str) -> bool:
    return _exists(REVIEWS[0], REVIEWS[1], review_id)


def get_review(review_id: str) -> dict | None:
    for r in read_reviews():
        if r.get("review_id") == review_id:
            return r
    return None


# ── Violations (event-sourced) ──
def append_violation_event(rec: dict) -> None:
    _append(VIOLATIONS[0], rec)


def read_violation_events() -> list[dict]:
    return read_jsonl(VIOLATIONS[0])


def violations_head() -> dict | None:
    return _head(VIOLATIONS[0])


def violation_event_exists(event_id: str) -> bool:
    return _exists(VIOLATIONS[0], VIOLATIONS[1], event_id)


def violation_events_for(violation_id: str) -> list[dict]:
    return [r for r in read_violation_events() if r.get("violation_id") == violation_id]


def distinct_violations() -> list[dict]:
    out: dict = {}
    for r in read_violation_events():
        vid = r.get("violation_id")
        if vid not in out:
            out[vid] = r
    return list(out.values())


def violation_exists(violation_id: str) -> bool:
    return any(r.get("violation_id") == violation_id for r in read_violation_events())


# ── Recommendations (불변) ──
def append_recommendation(rec: dict) -> None:
    _append(RECOMMENDATIONS[0], rec)


def read_recommendations() -> list[dict]:
    return read_jsonl(RECOMMENDATIONS[0])


def recommendations_head() -> dict | None:
    return _head(RECOMMENDATIONS[0])


def recommendation_exists(recommendation_id: str) -> bool:
    return _exists(RECOMMENDATIONS[0], RECOMMENDATIONS[1], recommendation_id)


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
