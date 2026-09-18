"""IB Gateway(VM 헤드리스, ibg-controller) 상태 프록시.

ibg-controller의 /health(기본 포트 8080)를 폴링해 대시보드가 읽기 쉬운 형태로
반환한다. VM에 아직 배포 전이거나 컨테이너가 죽어 있어도(연결 거부/타임아웃/
JSON 파싱 실패 등 무엇이든) 500을 내지 않고 connected=False로 정상 폴백한다 —
이 엔드포인트 자체는 인프라 전제 없이 항상 응답 가능해야 함.
"""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/ib", tags=["ib"])


def _health_url() -> str:
    return os.environ.get("IB_GATEWAY_HEALTH_URL", "http://127.0.0.1:8080/health")


@router.get("/gateway/status")
def get_gateway_status() -> dict:
    try:
        resp = httpx.get(_health_url(), timeout=2.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return {
            "connected": False,
            "last_auth_ts": None,
            "next_reset_eta": None,
            "needs_manual_action": False,
            "error": "ib_gateway_unreachable",
        }
    return {
        "connected": bool(data.get("connected", data.get("authenticated", False))),
        "last_auth_ts": data.get("last_auth_ts") or data.get("lastAuthTime"),
        "next_reset_eta": data.get("next_reset_eta") or data.get("nextReset"),
        "needs_manual_action": bool(data.get("needs_manual_action", False)),
    }
