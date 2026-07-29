"""Research Agent Execution Coordinator 원장 (P12.3) — 6개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 rac_ 접두사(Research Agent Coordinator) — 기존 rco_ 계층과 구별. 각 레코드: id · timestamp ·
previous_hash · record_hash. 에이전트 조정 기록만 — 외부 행위 실행 없음. 상위 계층(P10.6, P11.13, P12.1, P12.2)은
**READ ONLY** — 소스 참조는 파일만 읽고 절대 쓰지 않는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (rac_ 접두사)
REGISTRY = ("rac_registry.jsonl", "agent_registration_id")   # Agent Assignment Registry
OWNERSHIP = ("rac_ownership.jsonl", "ownership_event_id")     # Research Task Ownership(event-sourced)
PROGRESS = ("rac_progress.jsonl", "progress_id")             # Agent Progress Records
COLLABORATIONS = ("rac_collaborations.jsonl", "collaboration_id")  # Collaboration Sessions
HANDOFFS = ("rac_handoffs.jsonl", "handoff_id")              # Handoff Records
REPORTS = ("rac_reports.jsonl", "report_id")                 # Coordinator Reports

ALL_LEDGERS = (REGISTRY, OWNERSHIP, PROGRESS, COLLABORATIONS, HANDOFFS, REPORTS)

# ── 상위 소스 원장(READ ONLY) — 소스 참조 검증용. import 결합 없음, 파일만 읽는다. ──
SOURCE_LEDGERS = {
    "agent_governance": ("arg_agents.jsonl", "event_id"),                    # P10.6
    "research_organization": ("rorg_organizations.jsonl", "org_event_id"),   # P11.13
    "autonomous_research_pipeline": ("arp_cycles.jsonl", "cycle_id"),        # P12.1
    "autonomous_experiment_scheduler": ("aes_schedules.jsonl", "schedule_event_id"),  # P12.2
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


# ── Registry (agent roster) ──
def append_agent(rec: dict) -> None:
    _append(REGISTRY[0], rec)


def read_agents() -> list[dict]:
    return read_jsonl(REGISTRY[0])


def registry_head() -> dict | None:
    return _head(REGISTRY[0])


def agent_exists(agent_registration_id: str) -> bool:
    return _exists(REGISTRY[0], REGISTRY[1], agent_registration_id)


def get_agent(agent_registration_id: str) -> dict | None:
    return _get(REGISTRY[0], REGISTRY[1], agent_registration_id)


def agent_registered(coordinator: str, agent: str) -> bool:
    return any(r.get("coordinator") == coordinator and r.get("agent") == agent
               for r in read_agents())


# ── Ownership (event-sourced) ──
def append_ownership_event(rec: dict) -> None:
    _append(OWNERSHIP[0], rec)


def read_ownership_events() -> list[dict]:
    return read_jsonl(OWNERSHIP[0])


def ownership_head() -> dict | None:
    return _head(OWNERSHIP[0])


def ownership_event_exists(ownership_event_id: str) -> bool:
    return _exists(OWNERSHIP[0], OWNERSHIP[1], ownership_event_id)


def assignment_events(assignment_id: str) -> list[dict]:
    return [r for r in read_ownership_events() if r.get("assignment_id") == assignment_id]


def assignment_ids() -> list[str]:
    return sorted({r.get("assignment_id") for r in read_ownership_events()
                   if r.get("assignment_id")})


def task_assignments(task_ref: str) -> list[str]:
    return sorted({r.get("assignment_id") for r in read_ownership_events()
                   if r.get("task_ref") == task_ref and r.get("assignment_id")})


def coordinator_assignments(coordinator: str) -> list[str]:
    return sorted({r.get("assignment_id") for r in read_ownership_events()
                   if r.get("coordinator") == coordinator and r.get("assignment_id")})


# ── Progress ──
def append_progress(rec: dict) -> None:
    _append(PROGRESS[0], rec)


def read_progress() -> list[dict]:
    return read_jsonl(PROGRESS[0])


def progress_head() -> dict | None:
    return _head(PROGRESS[0])


def progress_exists(progress_id: str) -> bool:
    return _exists(PROGRESS[0], PROGRESS[1], progress_id)


def assignment_progress(assignment_id: str) -> list[dict]:
    return [r for r in read_progress() if r.get("assignment_id") == assignment_id]


# ── Collaborations ──
def append_collaboration(rec: dict) -> None:
    _append(COLLABORATIONS[0], rec)


def read_collaborations() -> list[dict]:
    return read_jsonl(COLLABORATIONS[0])


def collaborations_head() -> dict | None:
    return _head(COLLABORATIONS[0])


def collaboration_exists(collaboration_id: str) -> bool:
    return _exists(COLLABORATIONS[0], COLLABORATIONS[1], collaboration_id)


def task_collaborations(task_ref: str) -> list[dict]:
    return [r for r in read_collaborations() if r.get("task_ref") == task_ref]


# ── Handoffs ──
def append_handoff(rec: dict) -> None:
    _append(HANDOFFS[0], rec)


def read_handoffs() -> list[dict]:
    return read_jsonl(HANDOFFS[0])


def handoffs_head() -> dict | None:
    return _head(HANDOFFS[0])


def handoff_exists(handoff_id: str) -> bool:
    return _exists(HANDOFFS[0], HANDOFFS[1], handoff_id)


def assignment_handoffs(assignment_id: str) -> list[dict]:
    return [r for r in read_handoffs() if r.get("assignment_id") == assignment_id]


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)
