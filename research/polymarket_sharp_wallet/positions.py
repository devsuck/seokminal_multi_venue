"""Polymarket 지갑별 현재 포지션 조회 — data-api.polymarket.com/positions, 무인증.

sharp_wallet 집행봇이 포지션 진입 시점에 그 anchor를 낸 지갑의 순보유를
참고 필드로만 기록한다(게이트/사이징에 미반영 — 통계검증 안 된 신호이므로).
leaderboard.py와 동일하게 단순 requests, 재시도/하드타임아웃 없음 — 실패해도
포지션 진입 자체는 안 막는 참고필드라 호출부에서 통째로 흡수한다.
docs/superpowers/specs/2026-08-02-polymarket-sharp-wallet-execution-design.md
"""
from __future__ import annotations

import requests

POSITIONS_URL = "https://data-api.polymarket.com/positions"
_TIMEOUT = 15


def fetch_wallet_positions(wallet: str) -> list[dict]:
    """실패/비정상 응답이면 빈 리스트."""
    try:
        r = requests.get(POSITIONS_URL, params={"user": wallet}, timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []
