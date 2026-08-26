"""Steward — 데드맨 스위치 heartbeat 엔드포인트.

사람이 살아서 모니터링 중임을 주기적으로 확인. DEADMAN_DAYS(기본 7일) 넘게
호출 없으면 jarvis.execution.broker_bridge._gate()가 신규 진입(BUY)을 자동
차단(청산은 안 막음) — jarvis.execution.deadman 참고.
"""
from __future__ import annotations

from fastapi import APIRouter

from jarvis.execution import deadman

router = APIRouter(prefix="/steward", tags=["steward"])


@router.post("/heartbeat")
def post_heartbeat() -> dict:
    ts = deadman.record_heartbeat()
    return {"ok": True, "ts": ts.isoformat()}


@router.get("/heartbeat")
def get_heartbeat() -> dict:
    hb = deadman.last_heartbeat()
    return {
        "last_heartbeat": hb.isoformat() if hb else None,
        "deadman_days": deadman.deadman_days(),
        "expired": deadman.is_expired(),
    }
