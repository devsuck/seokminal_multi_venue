"""Polymarket CLOB 오더북 폴링 — 유동성 상위 마켓 선정 + 스냅샷 1틱 생성.

I/O 계층. 차익 판정 로직은 detector.py로 분리해서 순수함수로 테스트한다.
"""
from __future__ import annotations

import datetime as dt
import time

import requests

from polymarket.client import get_markets
from research.polymarket_arb.detector import evaluate_snapshot

_CLOB_BASE = "https://clob.polymarket.com"
_TIMEOUT = 10

# api_server/polymarket_bot.py 다각화봇 기본 필터와 동일값. research/는 기존
# 컨벤션상 api_server를 import하지 않으므로 값만 복제한다 (import 금지).
MIN_LIQUIDITY = 5000.0
MIN_PRICE = 0.10
MAX_PRICE = 0.90
MIN_DAYS_TO_RESOLUTION = 3

TOP_N = 50
POLL_INTERVAL_SEC = 10
FEE_BUFFER = 0.01


def select_liquid_markets(top_n: int = TOP_N) -> list[dict]:
    """유동성 상위 top_n개 이진마켓 선정 (다각화봇과 동일 필터 기준 + 오더북 조회 가능한 마켓만)."""
    today = dt.date.today()
    candidates = []
    for m in get_markets(limit=300):
        if not m["active"] or m["closed"] or not m["accepting_orders"]:
            continue
        if m["liquidity"] < MIN_LIQUIDITY:
            continue
        if not (MIN_PRICE <= m["yes_price"] <= MAX_PRICE):
            continue
        try:
            end = dt.date.fromisoformat(m["end_date"])
        except ValueError:
            continue
        if (end - today).days < MIN_DAYS_TO_RESOLUTION:
            continue
        if m.get("clob_token_ids") in (None, (None, None)):
            continue
        candidates.append(m)
    candidates.sort(key=lambda x: x["liquidity"], reverse=True)
    return candidates[:top_n]


def fetch_book(token_id: str, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        try:
            r = requests.get(f"{_CLOB_BASE}/book", params={"token_id": token_id}, timeout=_TIMEOUT)
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def best_levels(book: dict) -> dict:
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    best_bid = max(bids, key=lambda b: float(b["price"]), default=None)
    best_ask = min(asks, key=lambda a: float(a["price"]), default=None)
    return {
        "bid": float(best_bid["price"]) if best_bid else None,
        "bid_size": float(best_bid["size"]) if best_bid else None,
        "ask": float(best_ask["price"]) if best_ask else None,
        "ask_size": float(best_ask["size"]) if best_ask else None,
    }


def snapshot_market(market: dict, fee_buffer: float = FEE_BUFFER) -> dict | None:
    yes_id, no_id = market["clob_token_ids"]
    yes_book = fetch_book(yes_id)
    no_book = fetch_book(no_id)
    if yes_book is None or no_book is None:
        return None
    yes_levels = best_levels(yes_book)
    no_levels = best_levels(no_book)
    if yes_levels["ask"] is None or no_levels["ask"] is None:
        return None
    evald = evaluate_snapshot(yes_levels["ask"], no_levels["ask"], fee_buffer)
    return {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "condition_id": market["condition_id"],
        "question": market["question"],
        "yes_bid": yes_levels["bid"], "yes_ask": yes_levels["ask"], "yes_ask_size": yes_levels["ask_size"],
        "no_bid": no_levels["bid"], "no_ask": no_levels["ask"], "no_ask_size": no_levels["ask_size"],
        "sum_ask": evald["sum_ask"],
        "liquidity": market["liquidity"],
        "is_opportunity": evald["is_opportunity"],
    }


def run_once(top_n: int = TOP_N, fee_buffer: float = FEE_BUFFER) -> list[dict]:
    snapshots = []
    for market in select_liquid_markets(top_n):
        snap = snapshot_market(market, fee_buffer)
        if snap is not None:
            snapshots.append(snap)
    return snapshots
