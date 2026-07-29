"""Research Self-Improvement Intelligence 원장 (P10.13) — 8개 append-only 해시체인. 진실=JSONL.

**삭제/수정 API 없음.** 물리 파일 si_ 접두사(P10.8 simulation 의 sim_ 과 구별). 각 레코드: id ·
timestamp · previous_hash · record_hash. 개선 분석 기록만 — 실행/거래/배포/수정 없음. 상위 레이어
(P10.2~P10.12) 원장은 **READ ONLY** 로만 읽는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (si_ 접두사)
OPPORTUNITIES = ("si_opportunities.jsonl", "event_id")      # 이벤트 소싱
WORKFLOWS = ("si_workflows.jsonl", "workflow_id")
BOTTLENECKS = ("si_bottlenecks.jsonl", "bottleneck_id")
RECOMMENDATIONS = ("si_recommendations.jsonl", "event_id")  # 이벤트 소싱
TEMPLATES = ("si_templates.jsonl", "template_id")
EVIDENCES = ("si_evidences.jsonl", "evidence_id")
REPORTS = ("si_reports.jsonl", "report_id")
ARTIFACTS = ("si_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (OPPORTUNITIES, WORKFLOWS, BOTTLENECKS, RECOMMENDATIONS, TEMPLATES, EVIDENCES,
               REPORTS, ARTIFACTS)

# 상위 레이어 물리 원장(READ ONLY 데이터 소스) — import 결합 없음, 파일만 읽는다.
SOURCE_LEDGERS = {
    "research_governance": ("rg_strategies.jsonl", "strategy_id"),
    "alpha_intelligence": ("ai_experiments.jsonl", "experiment_id"),
    "research_kg": ("kg_relationships.jsonl", "relationship_id"),
    "decision_intelligence": ("di_decision_sessions.jsonl", "session_id"),
    "simulation_environment": ("sim_results.jsonl", "result_id"),
    "causal_intelligence": ("ci_evidences.jsonl", "evidence_id"),
    "meta_intelligence": ("mi_patterns.jsonl", "pattern_id"),
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


# ── Opportunities (event-sourced) ──
def append_opportunity_event(rec: dict) -> None:
    _append(OPPORTUNITIES[0], rec)


def read_opportunity_events() -> list[dict]:
    return read_jsonl(OPPORTUNITIES[0])


def opportunities_head() -> dict | None:
    return _head(OPPORTUNITIES[0])


def opportunity_event_exists(event_id: str) -> bool:
    return _exists(OPPORTUNITIES[0], OPPORTUNITIES[1], event_id)


def opportunity_events_for(opportunity_id: str) -> list[dict]:
    return [r for r in read_opportunity_events() if r.get("opportunity_id") == opportunity_id]


def distinct_opportunities() -> list[dict]:
    out: dict = {}
    for r in read_opportunity_events():
        oid = r.get("opportunity_id")
        if oid not in out:
            out[oid] = r
    return list(out.values())


# ── Workflows ──
def append_workflow(rec: dict) -> None:
    _append(WORKFLOWS[0], rec)


def read_workflows() -> list[dict]:
    return read_jsonl(WORKFLOWS[0])


def workflows_head() -> dict | None:
    return _head(WORKFLOWS[0])


def workflow_exists(workflow_id: str) -> bool:
    return _exists(WORKFLOWS[0], WORKFLOWS[1], workflow_id)


def get_workflow(workflow_id: str) -> dict | None:
    for r in read_workflows():
        if r.get("workflow_id") == workflow_id:
            return r
    return None


# ── Bottlenecks ──
def append_bottleneck(rec: dict) -> None:
    _append(BOTTLENECKS[0], rec)


def read_bottlenecks() -> list[dict]:
    return read_jsonl(BOTTLENECKS[0])


def bottlenecks_head() -> dict | None:
    return _head(BOTTLENECKS[0])


def bottleneck_exists(bottleneck_id: str) -> bool:
    return _exists(BOTTLENECKS[0], BOTTLENECKS[1], bottleneck_id)


# ── Recommendations (event-sourced) ──
def append_recommendation_event(rec: dict) -> None:
    _append(RECOMMENDATIONS[0], rec)


def read_recommendation_events() -> list[dict]:
    return read_jsonl(RECOMMENDATIONS[0])


def recommendations_head() -> dict | None:
    return _head(RECOMMENDATIONS[0])


def recommendation_event_exists(event_id: str) -> bool:
    return _exists(RECOMMENDATIONS[0], RECOMMENDATIONS[1], event_id)


def recommendation_events_for(recommendation_id: str) -> list[dict]:
    return [r for r in read_recommendation_events()
            if r.get("recommendation_id") == recommendation_id]


def distinct_recommendations() -> list[dict]:
    out: dict = {}
    for r in read_recommendation_events():
        rid = r.get("recommendation_id")
        if rid not in out:
            out[rid] = r
    return list(out.values())


# ── Templates ──
def append_template(rec: dict) -> None:
    _append(TEMPLATES[0], rec)


def read_templates() -> list[dict]:
    return read_jsonl(TEMPLATES[0])


def templates_head() -> dict | None:
    return _head(TEMPLATES[0])


def template_exists(template_id: str) -> bool:
    return _exists(TEMPLATES[0], TEMPLATES[1], template_id)


# ── Evidences ──
def append_evidence(rec: dict) -> None:
    _append(EVIDENCES[0], rec)


def read_evidences() -> list[dict]:
    return read_jsonl(EVIDENCES[0])


def evidences_head() -> dict | None:
    return _head(EVIDENCES[0])


def evidence_exists(evidence_id: str) -> bool:
    return _exists(EVIDENCES[0], EVIDENCES[1], evidence_id)


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
