"""Operations Console 데이터 접근 (P9.5) — **읽기전용 JSONL 리더만.**

허용 원장(전부 다른 계층 소유): system_health_reports · alerts · incidents · escalations ·
emergency_decisions · recovery_readiness · recovery_attestations · recovery_evidence.
**이 모듈에는 append/write 함수가 없다 — 오직 읽기.** 원장 생성/수정/삭제 없음.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

# (파일명, id 필드, 해시 필드, content 재계산 가능여부)
#   재계산 True = P9.2/9.3/9.4 공통 content_hash 스킴(record_hash) → 변조 탐지 가능
#   재계산 False = P9.1 report_hash(별도 스킴) → 링크 무결성만 검증
HEALTH = ("system_health_reports.jsonl", "report_id", "report_hash", False)
ALERTS = ("alerts.jsonl", "alert_id", "record_hash", True)
INCIDENTS = ("incidents.jsonl", "event_id", "record_hash", True)
ESCALATIONS = ("escalations.jsonl", "escalation_id", "record_hash", True)
EMERGENCY = ("emergency_decisions.jsonl", "decision_id", "record_hash", True)
READINESS = ("recovery_readiness.jsonl", "report_id", "record_hash", True)
ATTESTATIONS = ("recovery_attestations.jsonl", "attestation_id", "record_hash", True)

# 감사(체인) 검증 대상 원장
AUDIT_LEDGERS = (HEALTH, ALERTS, INCIDENTS, ESCALATIONS, EMERGENCY, READINESS, ATTESTATIONS)

_EVIDENCE = "recovery_evidence.jsonl"


def read_jsonl(filename: str) -> list[dict]:
    """원장을 데이터로만 읽는다(없으면 []). **쓰기 없음.**"""
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


def read_health() -> list[dict]:
    return read_jsonl(HEALTH[0])


def read_alerts() -> list[dict]:
    return read_jsonl(ALERTS[0])


def read_incidents() -> list[dict]:
    return read_jsonl(INCIDENTS[0])


def read_escalations() -> list[dict]:
    return read_jsonl(ESCALATIONS[0])


def read_emergency() -> list[dict]:
    return read_jsonl(EMERGENCY[0])


def read_readiness() -> list[dict]:
    return read_jsonl(READINESS[0])


def read_attestations() -> list[dict]:
    return read_jsonl(ATTESTATIONS[0])


def read_evidence() -> list[dict]:
    return read_jsonl(_EVIDENCE)


def latest(filename: str) -> dict:
    recs = read_jsonl(filename)
    return recs[-1] if recs else {}
