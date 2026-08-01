"""Polymarket CLOB 오더북 읽기전용 클라이언트 — 공개 endpoint, 인증 불필요.

sharp_wallet 집행봇(api_server/polymarket_sharp_wallet_bot.py) paper 비용모델
(스프레드 실측)에만 쓴다. 실거래 주문은 안 함(polymarket/client.py와 동일
전제) — 상시 폴링/저장 없음, 포지션 진입/청산 시점 1회성 조회만.
docs/superpowers/specs/2026-08-02-polymarket-sharp-wallet-execution-design.md
"""
from __future__ import annotations

import requests

from research.net_utils import call_with_hard_timeout

_BASE = "https://clob.polymarket.com"
_TIMEOUT = 10
_HARD_TIMEOUT = _TIMEOUT + 5.0  # requests timeout이 못 막는 DNS/connect 단계 방어


def _get(token_id: str) -> dict:
    return call_with_hard_timeout(
        lambda: requests.get(f"{_BASE}/book", params={"token_id": token_id}, timeout=_TIMEOUT),
        _HARD_TIMEOUT,
    ).json()


def get_order_book(token_id: str) -> dict | None:
    """{"best_bid": float, "best_ask": float} 반환. 조회 실패/빈 오더북이면 None."""
    try:
        data = _get(token_id)
        bids = data.get("bids") or []
        asks = data.get("asks") or []
        if not bids or not asks:
            return None
        best_bid = max(float(b["price"]) for b in bids)
        best_ask = min(float(a["price"]) for a in asks)
        return {"best_bid": best_bid, "best_ask": best_ask}
    except Exception:
        return None


def spread_bps_from_book(book: dict | None) -> float | None:
    """(ask-bid)/mid*10000. book 없거나 mid<=0이거나 역전(ask<bid, 이상치)이면 None."""
    if not book:
        return None
    bid, ask = book["best_bid"], book["best_ask"]
    mid = (bid + ask) / 2.0
    if mid <= 0 or ask < bid:
        return None
    return (ask - bid) / mid * 10_000.0
