"""Access Governance 원장 (P9.10) — 6개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

물리 파일은 ag_ 접두사(기존 approvals 원장과 충돌 회피). 각 레코드: previous_hash · record_hash.
신원/접근 거버넌스 기록만 — 실제 권한 부여·permission 변경·operator action 실행 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드) — ag_ 네임스페이스
OPERATORS = ("ag_operators.jsonl", "identity_hash")
ROLES = ("ag_roles.jsonl", "role_hash")
SESSIONS = ("ag_sessions.jsonl", "session_id")
ACCESS_REQUESTS = ("ag_access_requests.jsonl", "event_id")   # 이벤트 소싱
APPROVALS = ("ag_approvals.jsonl", "approval_id")
AUDIT_REPORTS = ("ag_audit_reports.jsonl", "report_id")

ALL_LEDGERS = (OPERATORS, ROLES, SESSIONS, ACCESS_REQUESTS, APPROVALS, AUDIT_REPORTS)


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


# ── Operators ──
def append_operator(rec: dict) -> None:
    _append(OPERATORS[0], rec)


def read_operators() -> list[dict]:
    return read_jsonl(OPERATORS[0])


def operators_head() -> dict | None:
    return _head(OPERATORS[0])


def identity_hash_exists(h: str) -> bool:
    return _exists(OPERATORS[0], OPERATORS[1], h)


# ── Roles ──
def append_role(rec: dict) -> None:
    _append(ROLES[0], rec)


def read_roles() -> list[dict]:
    return read_jsonl(ROLES[0])


def roles_head() -> dict | None:
    return _head(ROLES[0])


def role_hash_exists(h: str) -> bool:
    return _exists(ROLES[0], ROLES[1], h)


# ── Sessions ──
def append_session(rec: dict) -> None:
    _append(SESSIONS[0], rec)


def read_sessions() -> list[dict]:
    return read_jsonl(SESSIONS[0])


def sessions_head() -> dict | None:
    return _head(SESSIONS[0])


def session_exists(session_id: str) -> bool:
    return _exists(SESSIONS[0], SESSIONS[1], session_id)


# ── Access requests (event-sourced) ──
def append_access_event(rec: dict) -> None:
    _append(ACCESS_REQUESTS[0], rec)


def read_access_events() -> list[dict]:
    return read_jsonl(ACCESS_REQUESTS[0])


def access_events_head() -> dict | None:
    return _head(ACCESS_REQUESTS[0])


def access_event_exists(event_id: str) -> bool:
    return _exists(ACCESS_REQUESTS[0], ACCESS_REQUESTS[1], event_id)


def access_events_for(request_id: str) -> list[dict]:
    return [r for r in read_access_events() if r.get("request_id") == request_id]


# ── Approvals ──
def append_approval(rec: dict) -> None:
    _append(APPROVALS[0], rec)


def read_approvals() -> list[dict]:
    return read_jsonl(APPROVALS[0])


def approvals_head() -> dict | None:
    return _head(APPROVALS[0])


def approval_exists(approval_id: str) -> bool:
    return _exists(APPROVALS[0], APPROVALS[1], approval_id)


# ── Audit reports ──
def append_audit_report(rec: dict) -> None:
    _append(AUDIT_REPORTS[0], rec)


def read_audit_reports() -> list[dict]:
    return read_jsonl(AUDIT_REPORTS[0])


def audit_reports_head() -> dict | None:
    return _head(AUDIT_REPORTS[0])


def audit_report_exists(report_id: str) -> bool:
    return _exists(AUDIT_REPORTS[0], AUDIT_REPORTS[1], report_id)
