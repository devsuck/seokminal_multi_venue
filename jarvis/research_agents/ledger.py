"""Research Agents 원장 (P11.1) — 6개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일 ragt_ 접두사(Research AGenT). 각 레코드: id · timestamp · previous_hash · record_hash. 연구 보조
에이전트 — 읽기·분석·리포트만, TRADE/EXECUTE/DEPLOY/ALLOCATE 없음. Research OS 는 **READ ONLY** — 파일만 읽고
절대 쓰지 않는다. import 결합 없음. 활동(ragt_activity)은 append-only 감사 원장.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — 본 레이어 소유 원장 (ragt_ 접두사)
AGENTS = ("ragt_agents.jsonl", "agent_id")          # Agent Registry
PROFILES = ("ragt_profiles.jsonl", "profile_id")    # Agent Profiles
TASKS = ("ragt_tasks.jsonl", "task_event_id")       # Agent Tasks (lifecycle events)
MESSAGES = ("ragt_messages.jsonl", "message_id")    # Agent Messages
REPORTS = ("ragt_reports.jsonl", "report_id")       # Agent Reports
ACTIVITY = ("ragt_activity.jsonl", "activity_id")   # Agent Activity (audit trail)

ALL_LEDGERS = (AGENTS, PROFILES, TASKS, MESSAGES, REPORTS, ACTIVITY)

# ── Research OS 소스 원장(READ ONLY). import 결합 없음, 파일만 읽는다. ──
# 에이전트 유형별 기본 참조 소스(연구 보조를 위한 읽기 대상).
SOURCE_LEDGERS = {
    "os_registry": ("rosc_registry.jsonl", "module_id"),
    "os_snapshot": ("rosc_snapshots.jsonl", "snapshot_id"),
    "control_plane": ("rcp_overview.jsonl", "overview_id"),
    "api_endpoints": ("rapi_endpoints.jsonl", "endpoint_id"),
    "data": ("dg_datasets.jsonl", "dataset_hash"),
    "alpha": ("ai_signals.jsonl", "signal_hash"),
    "backtest": ("pr_backtests.jsonl", "backtest_id"),
    "risk": ("rr_assessments.jsonl", "assessment_id"),
    "knowledge": ("ki_insights.jsonl", "insight_id"),
}

# 에이전트 유형 → 기본 참조 소스 role.
AGENT_DEFAULT_SOURCE = {
    "DATA_ANALYST": "data",
    "STRATEGY_RESEARCH": "alpha",
    "BACKTEST_ANALYST": "backtest",
    "RISK_ANALYST": "risk",
    "REVIEWER": "knowledge",
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


# ── Research OS READ ONLY ──
def source_exists(filename: str) -> bool:
    return os.path.exists(state_path(filename))


def read_source(filename: str) -> list[dict]:
    """Research OS 소스 원장을 읽기 전용으로 로드. 절대 쓰지 않는다."""
    return read_jsonl(filename)


def read_role(role: str) -> list[dict]:
    spec = SOURCE_LEDGERS.get(role)
    return read_source(spec[0]) if spec else []


# ── Agents (Registry) ──
def append_agent(rec: dict) -> None:
    _append(AGENTS[0], rec)


def read_agents() -> list[dict]:
    return read_jsonl(AGENTS[0])


def agents_head() -> dict | None:
    return _head(AGENTS[0])


def agent_exists(agent_id: str) -> bool:
    return _exists(AGENTS[0], AGENTS[1], agent_id)


def get_agent(agent_id: str) -> dict | None:
    return _get(AGENTS[0], AGENTS[1], agent_id)


# ── Profiles ──
def append_profile(rec: dict) -> None:
    _append(PROFILES[0], rec)


def read_profiles() -> list[dict]:
    return read_jsonl(PROFILES[0])


def profiles_head() -> dict | None:
    return _head(PROFILES[0])


def profile_exists(profile_id: str) -> bool:
    return _exists(PROFILES[0], PROFILES[1], profile_id)


def get_profile(profile_id: str) -> dict | None:
    return _get(PROFILES[0], PROFILES[1], profile_id)


# ── Tasks (lifecycle events) ──
def append_task(rec: dict) -> None:
    _append(TASKS[0], rec)


def read_tasks() -> list[dict]:
    return read_jsonl(TASKS[0])


def tasks_head() -> dict | None:
    return _head(TASKS[0])


def task_event_exists(task_event_id: str) -> bool:
    return _exists(TASKS[0], TASKS[1], task_event_id)


def task_events(task_id: str) -> list[dict]:
    return [r for r in read_tasks() if r.get("task_id") == task_id]


# ── Messages ──
def append_message(rec: dict) -> None:
    _append(MESSAGES[0], rec)


def read_messages() -> list[dict]:
    return read_jsonl(MESSAGES[0])


def messages_head() -> dict | None:
    return _head(MESSAGES[0])


def message_exists(message_id: str) -> bool:
    return _exists(MESSAGES[0], MESSAGES[1], message_id)


def get_message(message_id: str) -> dict | None:
    return _get(MESSAGES[0], MESSAGES[1], message_id)


# ── Reports ──
def append_report(rec: dict) -> None:
    _append(REPORTS[0], rec)


def read_reports() -> list[dict]:
    return read_jsonl(REPORTS[0])


def reports_head() -> dict | None:
    return _head(REPORTS[0])


def report_exists(report_id: str) -> bool:
    return _exists(REPORTS[0], REPORTS[1], report_id)


def get_report(report_id: str) -> dict | None:
    return _get(REPORTS[0], REPORTS[1], report_id)


# ── Activity (audit trail) ──
def append_activity(rec: dict) -> None:
    _append(ACTIVITY[0], rec)


def read_activity() -> list[dict]:
    return read_jsonl(ACTIVITY[0])


def activity_head() -> dict | None:
    return _head(ACTIVITY[0])


def activity_exists(activity_id: str) -> bool:
    return _exists(ACTIVITY[0], ACTIVITY[1], activity_id)
