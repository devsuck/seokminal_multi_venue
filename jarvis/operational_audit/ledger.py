"""Operational Audit 원장 (P9.6) — 4개 append-only 해시체인 + 감사 입력 데이터 리더. 진실=JSONL.

자체 원장(append-only): audit_events · operator_actions · configuration_snapshots ·
compliance_reports. 감사 입력(P9.1~P9.5 원장)은 *데이터 파일로만* 읽는다 — 해당 계층 코드를
import 하지 않는다. 감사 기록만 — 집행/주문/브로커/킬스위치/복구실행/권한변경 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# 자체 append-only 원장 (파일명, id 필드)
AUDIT_EVENTS = ("audit_events.jsonl", "event_id")
OPERATOR_ACTIONS = ("operator_actions.jsonl", "action_id")
CONFIG_SNAPSHOTS = ("configuration_snapshots.jsonl", "snapshot_id")
COMPLIANCE_REPORTS = ("compliance_reports.jsonl", "report_id")

ALL_LEDGERS = (AUDIT_EVENTS, OPERATOR_ACTIONS, CONFIG_SNAPSHOTS, COMPLIANCE_REPORTS)

# 감사 입력원(다른 계층 소유) — 읽기전용 데이터 파일 + (id 필드, 해시 필드, content 재계산 가능)
SRC_HEALTH = ("system_health_reports.jsonl", "report_id", "report_hash", False)   # P9.1
SRC_ALERTS = ("alerts.jsonl", "alert_id", "record_hash", True)                    # P9.2
SRC_INCIDENTS = ("incidents.jsonl", "event_id", "record_hash", True)             # P9.2
SRC_ESCALATIONS = ("escalations.jsonl", "escalation_id", "record_hash", True)    # P9.2
SRC_EMERGENCY = ("emergency_decisions.jsonl", "decision_id", "record_hash", True)   # P9.3
SRC_RECOVERY_REQUESTS = ("recovery_requests.jsonl", "request_id", "record_hash", True)   # P9.3
SRC_RECOVERY_APPROVALS = ("recovery_approvals.jsonl", "approval_id", "record_hash", True)  # P9.3
SRC_RECOVERY_EVENTS = ("recovery_events.jsonl", "event_id", "record_hash", True)   # P9.3
SRC_READINESS = ("recovery_readiness.jsonl", "report_id", "record_hash", True)    # P9.4
SRC_ATTESTATIONS = ("recovery_attestations.jsonl", "attestation_id", "record_hash", True)  # P9.4
SRC_CONSOLE_ACCESS = ("console_access.jsonl", "access_id", "record_hash", True)   # P9.5(선택)

# 체인 무결성 감사 대상 소스 원장
SOURCE_CHAINS = (SRC_HEALTH, SRC_ALERTS, SRC_INCIDENTS, SRC_ESCALATIONS, SRC_EMERGENCY,
                 SRC_RECOVERY_REQUESTS, SRC_RECOVERY_APPROVALS, SRC_RECOVERY_EVENTS,
                 SRC_READINESS, SRC_ATTESTATIONS)


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


# ── 자체 원장 append/read ──
def append_audit_event(rec: dict) -> None:
    _append(AUDIT_EVENTS[0], rec)


def read_audit_events() -> list[dict]:
    return read_jsonl(AUDIT_EVENTS[0])


def audit_event_exists(event_id: str) -> bool:
    return _exists(AUDIT_EVENTS[0], AUDIT_EVENTS[1], event_id)


def audit_events_head() -> dict | None:
    return _head(AUDIT_EVENTS[0])


def append_operator_action(rec: dict) -> None:
    _append(OPERATOR_ACTIONS[0], rec)


def read_operator_actions() -> list[dict]:
    return read_jsonl(OPERATOR_ACTIONS[0])


def operator_action_exists(action_id: str) -> bool:
    return _exists(OPERATOR_ACTIONS[0], OPERATOR_ACTIONS[1], action_id)


def operator_actions_head() -> dict | None:
    return _head(OPERATOR_ACTIONS[0])


def append_config_snapshot(rec: dict) -> None:
    _append(CONFIG_SNAPSHOTS[0], rec)


def read_config_snapshots() -> list[dict]:
    return read_jsonl(CONFIG_SNAPSHOTS[0])


def config_snapshot_exists(snapshot_id: str) -> bool:
    return _exists(CONFIG_SNAPSHOTS[0], CONFIG_SNAPSHOTS[1], snapshot_id)


def config_snapshots_head() -> dict | None:
    return _head(CONFIG_SNAPSHOTS[0])


def append_compliance_report(rec: dict) -> None:
    _append(COMPLIANCE_REPORTS[0], rec)


def read_compliance_reports() -> list[dict]:
    return read_jsonl(COMPLIANCE_REPORTS[0])


def compliance_report_exists(report_id: str) -> bool:
    return _exists(COMPLIANCE_REPORTS[0], COMPLIANCE_REPORTS[1], report_id)


def compliance_reports_head() -> dict | None:
    return _head(COMPLIANCE_REPORTS[0])


# ── 감사 입력 리더(데이터 파일로만) ──
def read_source(cfg) -> list[dict]:
    return read_jsonl(cfg[0])
