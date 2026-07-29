"""Research Planning Intelligence 원장 (P10.15) — 8개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 rp_ 접두사. 각 레코드: id · timestamp · previous_hash · record_hash. 계획 기록만 —
실행/거래/배포/배분 없음. 상위 레이어(P10.5/7/8/11/12/13/14)는 **READ ONLY**.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rp_ 접두사)
OPPORTUNITIES = ("rp_opportunities.jsonl", "event_id")      # 이벤트 소싱
PLANS = ("rp_plans.jsonl", "plan_id")
HYPOTHESES = ("rp_hypotheses.jsonl", "hypothesis_id")
BLUEPRINTS = ("rp_blueprints.jsonl", "blueprint_id")
DEPENDENCIES = ("rp_dependencies.jsonl", "dependency_id")
PRIORITIES = ("rp_priorities.jsonl", "priority_id")
REPORTS = ("rp_reports.jsonl", "report_id")
ARTIFACTS = ("rp_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (OPPORTUNITIES, PLANS, HYPOTHESES, BLUEPRINTS, DEPENDENCIES, PRIORITIES, REPORTS,
               ARTIFACTS)

# 상위 레이어 물리 원장(READ ONLY 데이터 소스) — import 결합 없음, 파일만 읽는다.
SOURCE_LEDGERS = {
    "research_kg": ("kg_entities.jsonl", "entity_id"),
    "decision_intelligence": ("di_candidates.jsonl", "candidate_id"),
    "simulation_environment": ("sim_results.jsonl", "result_id"),
    "causal_intelligence": ("ci_hypotheses.jsonl", "event_id"),
    "meta_intelligence": ("mi_patterns.jsonl", "event_id"),
    "self_improvement_intelligence": ("si_opportunities.jsonl", "event_id"),
    "research_memory": ("rm_memories.jsonl", "event_id"),
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


def opportunity_exists(opportunity_id: str) -> bool:
    return any(r.get("opportunity_id") == opportunity_id for r in read_opportunity_events())


# ── Plans ──
def append_plan(rec: dict) -> None:
    _append(PLANS[0], rec)


def read_plans() -> list[dict]:
    return read_jsonl(PLANS[0])


def plans_head() -> dict | None:
    return _head(PLANS[0])


def plan_exists(plan_id: str) -> bool:
    return _exists(PLANS[0], PLANS[1], plan_id)


def get_plan(plan_id: str) -> dict | None:
    for r in read_plans():
        if r.get("plan_id") == plan_id:
            return r
    return None


# ── Hypotheses ──
def append_hypothesis(rec: dict) -> None:
    _append(HYPOTHESES[0], rec)


def read_hypotheses() -> list[dict]:
    return read_jsonl(HYPOTHESES[0])


def hypotheses_head() -> dict | None:
    return _head(HYPOTHESES[0])


def hypothesis_exists(hypothesis_id: str) -> bool:
    return _exists(HYPOTHESES[0], HYPOTHESES[1], hypothesis_id)


# ── Blueprints ──
def append_blueprint(rec: dict) -> None:
    _append(BLUEPRINTS[0], rec)


def read_blueprints() -> list[dict]:
    return read_jsonl(BLUEPRINTS[0])


def blueprints_head() -> dict | None:
    return _head(BLUEPRINTS[0])


def blueprint_exists(blueprint_id: str) -> bool:
    return _exists(BLUEPRINTS[0], BLUEPRINTS[1], blueprint_id)


# ── Dependencies ──
def append_dependency(rec: dict) -> None:
    _append(DEPENDENCIES[0], rec)


def read_dependencies() -> list[dict]:
    return read_jsonl(DEPENDENCIES[0])


def dependencies_head() -> dict | None:
    return _head(DEPENDENCIES[0])


def dependency_exists(dependency_id: str) -> bool:
    return _exists(DEPENDENCIES[0], DEPENDENCIES[1], dependency_id)


# ── Priorities ──
def append_priority(rec: dict) -> None:
    _append(PRIORITIES[0], rec)


def read_priorities() -> list[dict]:
    return read_jsonl(PRIORITIES[0])


def priorities_head() -> dict | None:
    return _head(PRIORITIES[0])


def priority_exists(priority_id: str) -> bool:
    return _exists(PRIORITIES[0], PRIORITIES[1], priority_id)


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
