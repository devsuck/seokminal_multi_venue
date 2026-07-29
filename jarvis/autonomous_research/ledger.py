"""Autonomous Research 원장 (P25) — 8개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 ar_ 접두사(Autonomous Research). 각 레코드: id · timestamp · previous_hash · record_hash. 연구 지능
기록만 — 실행·거래·배포 없음. 상위 계층(P10~P24)은 **READ ONLY** — 파일만 읽는다(소유 결합 없음, 변경 없음).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

CYCLES = ("ar_cycles.jsonl", "cycle_event_id")                     # 연구 사이클 생애주기(ES)
OPPORTUNITIES = ("ar_opportunities.jsonl", "opportunity_id")       # 기회 탐지
PROPOSALS = ("ar_proposals.jsonl", "proposal_event_id")           # 제안 생애주기(ES)
EXPERIMENT_PLANS = ("ar_experiment_plans.jsonl", "plan_id")       # 실험 계획(실행 없음)
FEEDBACK = ("ar_feedback.jsonl", "feedback_id")                   # 학습 피드백
LEARNING_EVENTS = ("ar_learning_events.jsonl", "learning_event_id")  # 학습 이벤트
REPORTS = ("ar_reports.jsonl", "report_id")                       # 진화 리포트
ARTIFACTS = ("ar_artifacts.jsonl", "artifact_id")                # 연구 지능 계보

ALL_LEDGERS = (CYCLES, OPPORTUNITIES, PROPOSALS, EXPERIMENT_PLANS, FEEDBACK, LEARNING_EVENTS,
               REPORTS, ARTIFACTS)

# ── 연구 이력 관측 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "strategy_research_governance": ("rg_experiments.jsonl", "experiment_id"),  # P10.2
    "alpha_intelligence": ("ai_experiments.jsonl", "experiment_id"),           # P10.3
    "portfolio_research": ("pr_backtests.jsonl", "backtest_id"),               # P10.4
    "knowledge_graph": ("kg_entities.jsonl", "entity_id"),                     # P10.5
    "agent_governance": ("arg_agents.jsonl", "agent_id"),                      # P10.6
    "decision_intelligence": ("di_candidates.jsonl", "event_id"),             # P10.7
    "simulation": ("sim_scenarios.jsonl", "event_id"),                        # P10.8
    "production_readiness": ("pd_candidates.jsonl", "candidate_id"),          # P21
    "automation": ("ra_workflows.jsonl", "workflow_event_id"),                # P22
    "monitoring": ("rmon_anomalies.jsonl", "anomaly_id"),                     # P23
    "reliability": ("rel_incidents.jsonl", "incident_event_id"),             # P24
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


def source_records(layer) -> list[dict]:
    spec = SOURCE_LAYERS.get(layer)
    if not spec:
        return []
    return read_jsonl(spec[0])


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


append_cycle_event, read_cycle_events, cycles_head, cycle_event_exists = _readers(CYCLES)
append_opportunity, read_opportunities, opportunities_head, opportunity_exists = _readers(OPPORTUNITIES)
append_proposal_event, read_proposal_events, proposals_head, proposal_event_exists = _readers(PROPOSALS)
append_plan, read_experiment_plans, plans_head, plan_exists = _readers(EXPERIMENT_PLANS)
append_feedback, read_feedback, feedback_head, feedback_exists = _readers(FEEDBACK)
append_learning, read_learning_events, learning_head, learning_exists = _readers(LEARNING_EVENTS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


# ── 그룹 조회 ──
def cycle_events(cyc) -> list[dict]:
    return [r for r in read_cycle_events() if r.get("cycle_id") == cyc]


def cycle_ids() -> list[str]:
    return sorted({r.get("cycle_id") for r in read_cycle_events() if r.get("cycle_id")})


def proposal_events(prop) -> list[dict]:
    return [r for r in read_proposal_events() if r.get("proposal_id") == prop]


def proposal_ids() -> list[str]:
    return sorted({r.get("proposal_id") for r in read_proposal_events() if r.get("proposal_id")})


def plans_for(prop) -> list[dict]:
    return [r for r in read_experiment_plans() if r.get("proposal_id") == prop]


def feedback_for(cyc) -> list[dict]:
    return [r for r in read_feedback() if r.get("cycle_id") == cyc]


def learning_for(cyc) -> list[dict]:
    return [r for r in read_learning_events() if r.get("cycle_id") == cyc]
