"""Research Agent Coordination 원장 (P26) — 9개 append-only SHA256 해시체인. 진실=JSONL. **삭제/수정 없음.**

물리 파일 racd_ 접두사(Research Agent CoorDination; rac_ 는 기존 소유 → 충돌 회피). 각 레코드: id · timestamp ·
previous_hash · record_hash. 협업 조정 기록만 — 실행·거래·배포·권한 변경 없음. 상위 계층(P10~P25)은 **READ ONLY** —
파일만 읽는다(소유 결합 없음, 변경 없음). P10.6 Agent Governance 가 권한·정체성·행동 제한의 소유자.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

AGENTS = ("racd_agents.jsonl", "agent_id")                     # 연구 에이전트 레지스트리
ROLES = ("racd_roles.jsonl", "role_id")                        # 역할 정의
TEAMS = ("racd_teams.jsonl", "team_id")                        # 팀 구조
SESSIONS = ("racd_sessions.jsonl", "session_event_id")         # 협업 세션 생애주기(ES)
TASKS = ("racd_tasks.jsonl", "task_event_id")                  # 작업 위임 생애주기(ES)
MESSAGES = ("racd_messages.jsonl", "message_id")               # 토론 이벤트
CONSENSUS = ("racd_consensus.jsonl", "consensus_id")           # 합의 기록
REPORTS = ("racd_reports.jsonl", "report_id")                  # 조정 리포트
ARTIFACTS = ("racd_artifacts.jsonl", "artifact_id")            # 협업 계보

ALL_LEDGERS = (AGENTS, ROLES, TEAMS, SESSIONS, TASKS, MESSAGES, CONSENSUS, REPORTS, ARTIFACTS)

# ── 협업 관측 대상(READ ONLY 소스) — import 결합 없음, 파일만 읽는다. ──
SOURCE_LAYERS = {
    "knowledge_graph": ("kg_entities.jsonl", "entity_id"),               # P10.5
    "agent_governance": ("arg_agents.jsonl", "agent_id"),               # P10.6 (권한 소유자)
    "decision_intelligence": ("di_candidates.jsonl", "event_id"),       # P10.7
    "simulation": ("sim_scenarios.jsonl", "event_id"),                  # P10.8
    "research_automation": ("ra_workflows.jsonl", "workflow_event_id"),  # P22
    "monitoring": ("rmon_health_checks.jsonl", "health_id"),            # P23
    "reliability": ("rel_incidents.jsonl", "incident_event_id"),       # P24
    "autonomous_research": ("ar_cycles.jsonl", "cycle_event_id"),      # P25
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


append_agent, read_agents, agents_head, agent_exists = _readers(AGENTS)
append_role, read_roles, roles_head, role_exists = _readers(ROLES)
append_team, read_teams, teams_head, team_exists = _readers(TEAMS)
append_session_event, read_session_events, sessions_head, session_event_exists = _readers(SESSIONS)
append_task_event, read_task_events, tasks_head, task_event_exists = _readers(TASKS)
append_message, read_messages, messages_head, message_exists = _readers(MESSAGES)
append_consensus, read_consensus, consensus_head, consensus_exists = _readers(CONSENSUS)
append_report, read_reports, reports_head, report_exists = _readers(REPORTS)
append_artifact, read_artifacts, artifacts_head, artifact_exists = _readers(ARTIFACTS)


# ── 그룹 조회 ──
def session_events(sess) -> list[dict]:
    return [r for r in read_session_events() if r.get("session_id") == sess]


def session_ids() -> list[str]:
    return sorted({r.get("session_id") for r in read_session_events() if r.get("session_id")})


def task_events(task) -> list[dict]:
    return [r for r in read_task_events() if r.get("task_id") == task]


def task_ids() -> list[str]:
    return sorted({r.get("task_id") for r in read_task_events() if r.get("task_id")})


def tasks_in_session(sess) -> list[str]:
    return sorted({r.get("task_id") for r in read_task_events() if r.get("session_id") == sess})


def messages_in_session(sess) -> list[dict]:
    return [r for r in read_messages() if r.get("session_id") == sess]


def consensus_in_session(sess) -> list[dict]:
    return [r for r in read_consensus() if r.get("session_id") == sess]
