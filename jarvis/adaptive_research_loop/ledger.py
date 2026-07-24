"""Adaptive Research Loop 원장 (P12.4) — 6개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 arl_ 접두사(Adaptive Research Loop). 각 레코드: id · timestamp · previous_hash · record_hash. 개선
피드백 기록만 — 자동 수정 없음. 상위 계층(P12.1, P12.2, P12.3, P11.10)은 **READ ONLY** — 파일만 읽고 쓰지 않는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (arl_ 접두사)
CYCLES = ("arl_cycles.jsonl", "cycle_id")                    # Loop Cycles
FEEDBACK = ("arl_feedback.jsonl", "feedback_id")             # Research Feedback
PROPOSALS = ("arl_proposals.jsonl", "proposal_event_id")     # Improvement Proposals(event-sourced)
METRICS = ("arl_metrics.jsonl", "metric_id")                 # Efficiency Metrics
ADAPTATIONS = ("arl_adaptations.jsonl", "adaptation_id")     # Adaptation History
REPORTS = ("arl_reports.jsonl", "report_id")                 # Reports

ALL_LEDGERS = (CYCLES, FEEDBACK, PROPOSALS, METRICS, ADAPTATIONS, REPORTS)

# ── 상위 소스 원장(READ ONLY) — 소스 참조 검증용. import 결합 없음, 파일만 읽는다. ──
SOURCE_LEDGERS = {
    "research_improvement": ("rimp_registry.jsonl", "registry_id"),          # P11.10
    "autonomous_research_pipeline": ("arp_cycles.jsonl", "cycle_id"),        # P12.1
    "autonomous_experiment_scheduler": ("aes_schedules.jsonl", "schedule_event_id"),  # P12.2
    "research_agent_coordinator": ("rac_ownership.jsonl", "ownership_event_id"),  # P12.3
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


# ── Cycles ──
def append_cycle(rec: dict) -> None:
    _append(CYCLES[0], rec)


def read_cycles() -> list[dict]:
    return read_jsonl(CYCLES[0])


def cycles_head() -> dict | None:
    return _head(CYCLES[0])


def cycle_exists(cycle_id: str) -> bool:
    return _exists(CYCLES[0], CYCLES[1], cycle_id)


def get_cycle(cycle_id: str) -> dict | None:
    return _get(CYCLES[0], CYCLES[1], cycle_id)


# ── Feedback ──
def append_feedback(rec: dict) -> None:
    _append(FEEDBACK[0], rec)


def read_feedback() -> list[dict]:
    return read_jsonl(FEEDBACK[0])


def feedback_head() -> dict | None:
    return _head(FEEDBACK[0])


def feedback_exists(feedback_id: str) -> bool:
    return _exists(FEEDBACK[0], FEEDBACK[1], feedback_id)


def get_feedback(feedback_id: str) -> dict | None:
    return _get(FEEDBACK[0], FEEDBACK[1], feedback_id)


def cycle_feedback(cycle_id: str) -> list[dict]:
    return [r for r in read_feedback() if r.get("cycle_id") == cycle_id]


# ── Proposals (event-sourced) ──
def append_proposal_event(rec: dict) -> None:
    _append(PROPOSALS[0], rec)


def read_proposal_events() -> list[dict]:
    return read_jsonl(PROPOSALS[0])


def proposals_head() -> dict | None:
    return _head(PROPOSALS[0])


def proposal_event_exists(proposal_event_id: str) -> bool:
    return _exists(PROPOSALS[0], PROPOSALS[1], proposal_event_id)


def proposal_events(proposal_id: str) -> list[dict]:
    return [r for r in read_proposal_events() if r.get("proposal_id") == proposal_id]


def proposal_ids() -> list[str]:
    return sorted({r.get("proposal_id") for r in read_proposal_events() if r.get("proposal_id")})


def cycle_proposals(cycle_id: str) -> list[str]:
    return sorted({r.get("proposal_id") for r in read_proposal_events()
                   if r.get("cycle_id") == cycle_id and r.get("proposal_id")})


# ── Metrics ──
def append_metric(rec: dict) -> None:
    _append(METRICS[0], rec)


def read_metrics() -> list[dict]:
    return read_jsonl(METRICS[0])


def metrics_head() -> dict | None:
    return _head(METRICS[0])


def metric_exists(metric_id: str) -> bool:
    return _exists(METRICS[0], METRICS[1], metric_id)


def get_metric(metric_id: str) -> dict | None:
    return _get(METRICS[0], METRICS[1], metric_id)


# ── Adaptations ──
def append_adaptation(rec: dict) -> None:
    _append(ADAPTATIONS[0], rec)


def read_adaptations() -> list[dict]:
    return read_jsonl(ADAPTATIONS[0])


def adaptations_head() -> dict | None:
    return _head(ADAPTATIONS[0])


def adaptation_exists(adaptation_id: str) -> bool:
    return _exists(ADAPTATIONS[0], ADAPTATIONS[1], adaptation_id)


def proposal_adaptations(proposal_id: str) -> list[dict]:
    return [r for r in read_adaptations() if r.get("proposal_id") == proposal_id]


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)
