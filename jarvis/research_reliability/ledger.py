"""Research Reliability 원장 (P24) — 8개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rel_ 접두사(RELiability). 각 레코드: id · timestamp · previous_hash · record_hash. 신뢰성 기록·검증만
— 실행·복구실행·배포 없음. 상위 계층(P10~P23)은 **READ ONLY** — 파일만 읽는다(소유 결합 없음, 변경 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

INCIDENTS = ("rel_incidents.jsonl", "incident_event_id")             # 장애 생애주기(ES)
RECOVERY_PLANS = ("rel_recovery_plans.jsonl", "plan_id")            # 복구 계획(자동 실행 없음)
RECOVERY_EVENTS = ("rel_recovery_events.jsonl", "event_id")        # 복구 시도 기록
INTEGRITY_CHECKS = ("rel_integrity_checks.jsonl", "check_id")      # 무결성 검사
RELIABILITY_METRICS = ("rel_reliability_metrics.jsonl", "metric_id")  # 신뢰성 지표(관찰만)
POSTMORTEMS = ("rel_postmortems.jsonl", "postmortem_event_id")     # 포스트모템 생애주기(ES)
REPORTS = ("rel_reports.jsonl", "report_id")                       # 신뢰성 리포트
ARTIFACTS = ("rel_artifacts.jsonl", "artifact_id")                # 신뢰성 계보

ALL_LEDGERS = (INCIDENTS, RECOVERY_PLANS, RECOVERY_EVENTS, INTEGRITY_CHECKS, RELIABILITY_METRICS,
               POSTMORTEMS, REPORTS, ARTIFACTS)

# ── 신뢰성 관측 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "knowledge_graph": ("kg_entities.jsonl", "entity_id"),               # P10.5
    "agent_governance": ("arg_agents.jsonl", "agent_id"),               # P10.6
    "decision_intelligence": ("di_candidates.jsonl", "event_id"),       # P10.7
    "simulation": ("sim_scenarios.jsonl", "event_id"),                  # P10.8
    "research_operations": ("ro_events.jsonl", "event_id"),             # P18
    "research_collaboration": ("rcol_collaborations.jsonl", "collaboration_id"),  # P19
    "research_memory": ("rm_lessons.jsonl", "lesson_id"),               # P20
    "production_readiness": ("pd_candidates.jsonl", "candidate_id"),    # P21
    "research_automation": ("ra_workflows.jsonl", "workflow_event_id"),  # P22
    "monitoring": ("rmon_health_checks.jsonl", "health_id"),            # P23
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


append_incident_event, read_incident_events, incidents_head, incident_event_exists = _readers(INCIDENTS)
append_plan, read_recovery_plans, plans_head, plan_exists = _readers(RECOVERY_PLANS)
append_recovery_event, read_recovery_events, recovery_events_head, recovery_event_exists = _readers(RECOVERY_EVENTS)
append_check, read_integrity_checks, checks_head, check_exists = _readers(INTEGRITY_CHECKS)
append_metric, read_reliability_metrics, metrics_head, metric_exists = _readers(RELIABILITY_METRICS)
append_postmortem_event, read_postmortem_events, postmortems_head, postmortem_event_exists = _readers(POSTMORTEMS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


# ── 그룹 조회 ──
def incident_events(inc) -> list[dict]:
    return [r for r in read_incident_events() if r.get("incident_id") == inc]


def incident_ids() -> list[str]:
    return sorted({r.get("incident_id") for r in read_incident_events() if r.get("incident_id")})


def postmortem_events(pm) -> list[dict]:
    return [r for r in read_postmortem_events() if r.get("postmortem_id") == pm]


def postmortem_ids() -> list[str]:
    return sorted({r.get("postmortem_id") for r in read_postmortem_events() if r.get("postmortem_id")})


def plans_for(inc) -> list[dict]:
    return [r for r in read_recovery_plans() if r.get("incident_id") == inc]


def recovery_events_for(inc) -> list[dict]:
    return [r for r in read_recovery_events() if r.get("incident_id") == inc]
