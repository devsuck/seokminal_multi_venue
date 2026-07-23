"""Policy Governance 원장 (P9.7) — 5개 append-only 해시체인. 진실=JSONL. **삭제/수정 API 없음.**

policies · change_requests(이벤트 소싱) · approvals · snapshots · drift_reports.
각 레코드: previous_hash · record_hash(sha256 콘텐츠). 거버넌스 기록만 — 실제 설정/정책 변경 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드)
POLICIES = ("policies.jsonl", "policy_hash")
CHANGE_REQUESTS = ("change_requests.jsonl", "event_id")   # 이벤트 소싱
APPROVALS = ("approvals.jsonl", "approval_id")
SNAPSHOTS = ("snapshots.jsonl", "snapshot_id")
DRIFT_REPORTS = ("drift_reports.jsonl", "report_id")

ALL_LEDGERS = (POLICIES, CHANGE_REQUESTS, APPROVALS, SNAPSHOTS, DRIFT_REPORTS)


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


# ── Policies ──
def append_policy(rec: dict) -> None:
    _append(POLICIES[0], rec)


def read_policies() -> list[dict]:
    return read_jsonl(POLICIES[0])


def policies_head() -> dict | None:
    return _head(POLICIES[0])


def policy_hash_exists(policy_hash: str) -> bool:
    return _exists(POLICIES[0], POLICIES[1], policy_hash)


# ── Change requests (event-sourced) ──
def append_change_event(rec: dict) -> None:
    _append(CHANGE_REQUESTS[0], rec)


def read_change_events() -> list[dict]:
    return read_jsonl(CHANGE_REQUESTS[0])


def change_events_head() -> dict | None:
    return _head(CHANGE_REQUESTS[0])


def change_event_exists(event_id: str) -> bool:
    return _exists(CHANGE_REQUESTS[0], CHANGE_REQUESTS[1], event_id)


def change_events_for(change_id: str) -> list[dict]:
    return [r for r in read_change_events() if r.get("change_id") == change_id]


# ── Approvals ──
def append_approval(rec: dict) -> None:
    _append(APPROVALS[0], rec)


def read_approvals() -> list[dict]:
    return read_jsonl(APPROVALS[0])


def approvals_head() -> dict | None:
    return _head(APPROVALS[0])


def approval_exists(approval_id: str) -> bool:
    return _exists(APPROVALS[0], APPROVALS[1], approval_id)


# ── Snapshots ──
def append_snapshot(rec: dict) -> None:
    _append(SNAPSHOTS[0], rec)


def read_snapshots() -> list[dict]:
    return read_jsonl(SNAPSHOTS[0])


def snapshots_head() -> dict | None:
    return _head(SNAPSHOTS[0])


def snapshot_exists(snapshot_id: str) -> bool:
    return _exists(SNAPSHOTS[0], SNAPSHOTS[1], snapshot_id)


# ── Drift reports ──
def append_drift_report(rec: dict) -> None:
    _append(DRIFT_REPORTS[0], rec)


def read_drift_reports() -> list[dict]:
    return read_jsonl(DRIFT_REPORTS[0])


def drift_reports_head() -> dict | None:
    return _head(DRIFT_REPORTS[0])


def drift_report_exists(report_id: str) -> bool:
    return _exists(DRIFT_REPORTS[0], DRIFT_REPORTS[1], report_id)
