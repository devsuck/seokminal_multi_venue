"""Polymarket 이벤트 내 후보군 YES가격 합산 괴리 탐지 — 폴링 스캐너.

polymarket_arb는 단일 마켓의 YES+NO 합가격만 보지만, 여긴 같은 event_id로
묶인 여러 후보 마켓들의 YES가격 합을 본다(후보군이 상호배타적이므로 이론상
합이 ~100%에 수렴해야 함). 어느 정도 괴리가 실제 시그널인지 판단하는 로직은
이 모듈 스코프 밖 — 수집만 한다.
"""
from __future__ import annotations

import datetime as dt

from polymarket.client import get_markets

# polymarket_arb/collector.py와 동일값(복제, import 금지)
MIN_LIQUIDITY = 5000.0
MIN_DAYS_TO_RESOLUTION = 3

TOP_N_EVENTS = 50
POLL_INTERVAL_SEC = 30


def group_by_event(markets: list[dict]) -> dict[str, list[dict]]:
    """event_id 기준 그룹핑. 소속 마켓 1개뿐인 이벤트는 제외(비교 대상 없음)."""
    groups: dict[str, list[dict]] = {}
    for m in markets:
        event_id = m.get("event_id")
        if not event_id:
            continue
        groups.setdefault(event_id, []).append(m)
    return {eid: ms for eid, ms in groups.items() if len(ms) >= 2}


def compute_divergence(event_markets: list[dict]) -> dict | None:
    """단일 이벤트 소속 마켓들의 YES가격 합산 괴리 스냅샷.

    필터(활성/주문가능/yes_price 존재/잔여기간/유동성 합) 불통과 시 None.
    """
    if len(event_markets) < 2:
        return None
    today = dt.date.today()
    total_liquidity = 0.0
    for m in event_markets:
        if not m["active"] or m["closed"] or not m["accepting_orders"]:
            return None
        if m.get("yes_price") is None:
            return None
        try:
            end = dt.date.fromisoformat(m["end_date"])
        except (ValueError, TypeError):
            return None
        if (end - today).days < MIN_DAYS_TO_RESOLUTION:
            return None
        total_liquidity += m["liquidity"]
    if total_liquidity < MIN_LIQUIDITY:
        return None

    yes_sum = round(sum(m["yes_price"] for m in event_markets), 4)
    first = event_markets[0]
    return {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "event_id": first["event_id"],
        "event_title": first["event_title"],
        "n_markets": len(event_markets),
        "yes_sum": yes_sum,
        "divergence": round(yes_sum - 1.0, 4),
        "total_liquidity": round(total_liquidity, 2),
        "markets": [
            {"condition_id": m["condition_id"], "question": m["question"],
             "yes_price": m["yes_price"], "liquidity": m["liquidity"]}
            for m in event_markets
        ],
    }


def run_once(top_n: int = TOP_N_EVENTS) -> list[dict]:
    markets = get_markets(limit=300)
    groups = group_by_event(markets)
    snapshots = []
    for event_markets in groups.values():
        snap = compute_divergence(event_markets)
        if snap is not None:
            snapshots.append(snap)
    snapshots.sort(key=lambda s: abs(s["divergence"]), reverse=True)
    return snapshots[:top_n]
