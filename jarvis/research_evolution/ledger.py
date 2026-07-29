"""Research Evolution Governance 원장 (P10.16) — 9개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 ev_ 접두사. 각 레코드: id · timestamp · previous_hash · record_hash. 학습 기록 저장·분석만 —
실행/거래/배포/strategy·model·parameter 수정 없음. 상위 레이어(P9.8~P10.15)는 **READ ONLY**.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (ev_ 접두사)
RESEARCH_OBJECTS = ("ev_research_objects.jsonl", "object_id")
CYCLES = ("ev_evolution_cycles.jsonl", "event_id")            # 이벤트 소싱
PROPOSALS = ("ev_improvement_proposals.jsonl", "event_id")    # 이벤트 소싱
ITERATIONS = ("ev_iterations.jsonl", "iteration_id")
FAILURES = ("ev_failures.jsonl", "failure_id")
LEARNING_RECORDS = ("ev_learning_records.jsonl", "learning_id")
TRANSFERS = ("ev_transfers.jsonl", "transfer_id")
REPORTS = ("ev_reports.jsonl", "report_id")
ARTIFACTS = ("ev_artifacts.jsonl", "artifact_id")

ALL_LEDGERS = (RESEARCH_OBJECTS, CYCLES, PROPOSALS, ITERATIONS, FAILURES, LEARNING_RECORDS,
               TRANSFERS, REPORTS, ARTIFACTS)

# 상위 레이어 물리 원장(READ ONLY 데이터 소스) — import 결합 없음, 파일만 읽는다.
# 논리 레이어명 -> (대표 원장 파일명, id 필드)
SOURCE_LEDGERS = {
    "research_governance": ("rg_strategies.jsonl", "strategy_id"),
    "alpha_intelligence": ("ai_signals.jsonl", "signal_id"),
    "portfolio_research": ("pr_portfolios.jsonl", "portfolio_id"),
    "research_kg": ("kg_entities.jsonl", "entity_id"),
    "decision_intelligence": ("di_candidates.jsonl", "candidate_id"),
    "simulation_environment": ("sim_scenarios.jsonl", "scenario_id"),
    "research_validation": ("rv_validations.jsonl", "event_id"),
    "causal_intelligence": ("ci_hypotheses.jsonl", "event_id"),
    "meta_intelligence": ("mi_patterns.jsonl", "event_id"),
    "self_improvement_intelligence": ("si_opportunities.jsonl", "event_id"),
    "research_memory": ("rm_memories.jsonl", "event_id"),
    "research_planning": ("rp_opportunities.jsonl", "event_id"),
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


# ── Research Objects (불변) ──
def append_research_object(rec: dict) -> None:
    _append(RESEARCH_OBJECTS[0], rec)


def read_research_objects() -> list[dict]:
    return read_jsonl(RESEARCH_OBJECTS[0])


def research_objects_head() -> dict | None:
    return _head(RESEARCH_OBJECTS[0])


def research_object_exists(object_id: str) -> bool:
    return _exists(RESEARCH_OBJECTS[0], RESEARCH_OBJECTS[1], object_id)


def get_research_object(object_id: str) -> dict | None:
    for r in read_research_objects():
        if r.get("object_id") == object_id:
            return r
    return None


# ── Evolution Cycles (event-sourced) ──
def append_cycle_event(rec: dict) -> None:
    _append(CYCLES[0], rec)


def read_cycle_events() -> list[dict]:
    return read_jsonl(CYCLES[0])


def cycles_head() -> dict | None:
    return _head(CYCLES[0])


def cycle_event_exists(event_id: str) -> bool:
    return _exists(CYCLES[0], CYCLES[1], event_id)


def cycle_events_for(cycle_id: str) -> list[dict]:
    return [r for r in read_cycle_events() if r.get("cycle_id") == cycle_id]


def distinct_cycles() -> list[dict]:
    out: dict = {}
    for r in read_cycle_events():
        cid = r.get("cycle_id")
        if cid not in out:
            out[cid] = r
    return list(out.values())


def cycle_exists(cycle_id: str) -> bool:
    return any(r.get("cycle_id") == cycle_id for r in read_cycle_events())


# ── Improvement Proposals (event-sourced) ──
def append_proposal_event(rec: dict) -> None:
    _append(PROPOSALS[0], rec)


def read_proposal_events() -> list[dict]:
    return read_jsonl(PROPOSALS[0])


def proposals_head() -> dict | None:
    return _head(PROPOSALS[0])


def proposal_event_exists(event_id: str) -> bool:
    return _exists(PROPOSALS[0], PROPOSALS[1], event_id)


def proposal_events_for(proposal_id: str) -> list[dict]:
    return [r for r in read_proposal_events() if r.get("proposal_id") == proposal_id]


def distinct_proposals() -> list[dict]:
    out: dict = {}
    for r in read_proposal_events():
        pid = r.get("proposal_id")
        if pid not in out:
            out[pid] = r
    return list(out.values())


def proposal_exists(proposal_id: str) -> bool:
    return any(r.get("proposal_id") == proposal_id for r in read_proposal_events())


# ── Iterations ──
def append_iteration(rec: dict) -> None:
    _append(ITERATIONS[0], rec)


def read_iterations() -> list[dict]:
    return read_jsonl(ITERATIONS[0])


def iterations_head() -> dict | None:
    return _head(ITERATIONS[0])


def iteration_exists(iteration_id: str) -> bool:
    return _exists(ITERATIONS[0], ITERATIONS[1], iteration_id)


def iterations_for(cycle_ref: str) -> list[dict]:
    return [r for r in read_iterations() if r.get("cycle_ref") == cycle_ref]


# ── Failures (불변) ──
def append_failure(rec: dict) -> None:
    _append(FAILURES[0], rec)


def read_failures() -> list[dict]:
    return read_jsonl(FAILURES[0])


def failures_head() -> dict | None:
    return _head(FAILURES[0])


def failure_exists(failure_id: str) -> bool:
    return _exists(FAILURES[0], FAILURES[1], failure_id)


def get_failure(failure_id: str) -> dict | None:
    for r in read_failures():
        if r.get("failure_id") == failure_id:
            return r
    return None


# ── Learning Records (불변) ──
def append_learning(rec: dict) -> None:
    _append(LEARNING_RECORDS[0], rec)


def read_learning() -> list[dict]:
    return read_jsonl(LEARNING_RECORDS[0])


def learning_head() -> dict | None:
    return _head(LEARNING_RECORDS[0])


def learning_exists(learning_id: str) -> bool:
    return _exists(LEARNING_RECORDS[0], LEARNING_RECORDS[1], learning_id)


def get_learning(learning_id: str) -> dict | None:
    for r in read_learning():
        if r.get("learning_id") == learning_id:
            return r
    return None


# ── Knowledge Transfers (불변) ──
def append_transfer(rec: dict) -> None:
    _append(TRANSFERS[0], rec)


def read_transfers() -> list[dict]:
    return read_jsonl(TRANSFERS[0])


def transfers_head() -> dict | None:
    return _head(TRANSFERS[0])


def transfer_exists(transfer_id: str) -> bool:
    return _exists(TRANSFERS[0], TRANSFERS[1], transfer_id)


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
