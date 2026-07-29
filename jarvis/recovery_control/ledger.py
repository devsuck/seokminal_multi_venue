"""Recovery Control 원장 (P9.4) — 4개 append-only 해시체인 + 관측 입력 데이터 리더. 진실=JSONL.

recovery_evidence.jsonl · recovery_readiness.jsonl · recovery_checklists.jsonl ·
recovery_attestations.jsonl. 관측 입력(P9.1 헬스·P9.2 인시던트/에스컬레이션·P9.3 비상/복구·
집행경계)은 *데이터 파일로만* 읽는다 — 해당 계층 코드를 import 하지 않는다. 복구 관제 기록만.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드)
EVIDENCE = ("recovery_evidence.jsonl", "evidence_id")
READINESS = ("recovery_readiness.jsonl", "report_id")
CHECKLISTS = ("recovery_checklists.jsonl", "checklist_id")
ATTESTATIONS = ("recovery_attestations.jsonl", "attestation_id")

ALL_LEDGERS = (EVIDENCE, READINESS, CHECKLISTS, ATTESTATIONS)

# 관측 입력(다른 계층 소유) — 읽기전용 데이터 파일
_HEALTH_LEDGER = "system_health_reports.jsonl"       # P9.1
_INCIDENTS_LEDGER = "incidents.jsonl"                # P9.2
_ESCALATIONS_LEDGER = "escalations.jsonl"            # P9.2
_EMERGENCY_LEDGER = "emergency_decisions.jsonl"      # P9.3
_RECOVERY_REQUESTS_LEDGER = "recovery_requests.jsonl"    # P9.3
_RECOVERY_EVENTS_LEDGER = "recovery_events.jsonl"        # P9.3
_LIVE_LEDGER = "live_execution_responses.jsonl"      # P8.1(집행경계 관측만)


def _append(filename: str, record: dict) -> None:
    p = state_path(filename)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _read(filename: str) -> list[dict]:
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
    recs = _read(filename)
    return recs[-1] if recs else None


def _exists(filename: str, id_field: str, rid: str) -> bool:
    return any(r.get(id_field) == rid for r in _read(filename))


# ── Evidence ──
def append_evidence(rec: dict) -> None:
    _append(EVIDENCE[0], rec)


def read_evidence() -> list[dict]:
    return _read(EVIDENCE[0])


def evidence_exists(evidence_id: str) -> bool:
    return _exists(EVIDENCE[0], EVIDENCE[1], evidence_id)


def evidence_head() -> dict | None:
    return _head(EVIDENCE[0])


# ── Readiness ──
def append_readiness(rec: dict) -> None:
    _append(READINESS[0], rec)


def read_readiness() -> list[dict]:
    return _read(READINESS[0])


def readiness_exists(report_id: str) -> bool:
    return _exists(READINESS[0], READINESS[1], report_id)


def readiness_head() -> dict | None:
    return _head(READINESS[0])


# ── Checklists ──
def append_checklist(rec: dict) -> None:
    _append(CHECKLISTS[0], rec)


def read_checklists() -> list[dict]:
    return _read(CHECKLISTS[0])


def checklist_exists(checklist_id: str) -> bool:
    return _exists(CHECKLISTS[0], CHECKLISTS[1], checklist_id)


def checklists_head() -> dict | None:
    return _head(CHECKLISTS[0])


# ── Attestations ──
def append_attestation(rec: dict) -> None:
    _append(ATTESTATIONS[0], rec)


def read_attestations() -> list[dict]:
    return _read(ATTESTATIONS[0])


def attestation_exists(attestation_id: str) -> bool:
    return _exists(ATTESTATIONS[0], ATTESTATIONS[1], attestation_id)


def attestations_head() -> dict | None:
    return _head(ATTESTATIONS[0])


# ── 관측 입력 리더(데이터 파일로만) ──
def latest_health() -> dict:
    recs = _read(_HEALTH_LEDGER)
    return recs[-1] if recs else {}


def read_incident_rows() -> list[dict]:
    return _read(_INCIDENTS_LEDGER)


def read_escalation_rows() -> list[dict]:
    return _read(_ESCALATIONS_LEDGER)


def read_emergency_decisions() -> list[dict]:
    return _read(_EMERGENCY_LEDGER)


def read_recovery_requests() -> list[dict]:
    return _read(_RECOVERY_REQUESTS_LEDGER)


def read_recovery_events() -> list[dict]:
    return _read(_RECOVERY_EVENTS_LEDGER)


def read_live_execution_rows() -> list[dict]:
    return _read(_LIVE_LEDGER)
