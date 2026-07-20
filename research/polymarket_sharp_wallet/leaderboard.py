"""Polymarket 공식 리더보드 조회 — 전체기간 PnL 상위 지갑을 "샤프월렛" 명단으로 쓴다.

`docs/superpowers/specs/2026-07-20-polymarket-sharp-wallet-design.md` §3,5 참고.
자체 트랙레코드를 쌓는 대신 data-api.polymarket.com/v1/leaderboard(무인증)를
그대로 신뢰한다 — 상수는 설계 시점 고정값이며 결과를 본 뒤 바꾸지 않는다.
"""
from __future__ import annotations

import requests

LEADERBOARD_URL = "https://data-api.polymarket.com/v1/leaderboard"
LEADERBOARD_CATEGORY = "OVERALL"
LEADERBOARD_TIME_PERIOD = "ALL"
LEADERBOARD_LIMIT = 50
_TIMEOUT = 15


def fetch_leaderboard() -> list[dict]:
    """GET 요청 후 rank/proxyWallet/pnl/vol만 남긴 리스트 반환. 응답이 리스트가
    아니면(API 오류 등) 빈 리스트."""
    r = requests.get(LEADERBOARD_URL, params={
        "category": LEADERBOARD_CATEGORY,
        "timePeriod": LEADERBOARD_TIME_PERIOD,
        "orderBy": "PNL",
        "limit": LEADERBOARD_LIMIT,
        "offset": 0,
    }, timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        return []
    return [
        {"rank": e["rank"], "proxyWallet": e["proxyWallet"], "pnl": e["pnl"], "vol": e["vol"]}
        for e in data
    ]


def build_sharp_wallet_set(entries: list[dict]) -> dict[str, dict]:
    """proxyWallet(lowercase) -> {rank, pnl} 매핑. 대소문자 비교 문제 방지용."""
    return {e["proxyWallet"].lower(): {"rank": e["rank"], "pnl": e["pnl"]} for e in entries}
