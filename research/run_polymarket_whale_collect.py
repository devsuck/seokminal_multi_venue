"""Polymarket whale 체결(fill) 수집기 — Data-API REST 폴링, tmux로 상시 실행.

체결 전용 WSS가 없음(CLOB WSS market 채널은 오더북 델타뿐 — 확인됨,
`research/polymarket_tick/ws_collector.py` 참고). 글로벌 `/trades` 피드를 폴링해
로컬에서 대상 마켓(뉴스/스포츠, `market_selector.select_target_markets()` 기준)으로
필터링한 뒤 저장한다. Gamma 마켓 목록은 5분마다만 재조회(무거움 — 매 폴링마다
부르지 않음). family 태깅은 여기서 한다(스코프 필터링 시점에 이미 알고 있는 값이라
검증러너의 family별 그룹핑을 위해 원본에 붙여 저장 — notional z-score 등 파생 신호
계산은 여전히 가설 모듈 몫).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path

import requests

from polymarket.client import get_markets
from research.polymarket_tick.market_selector import select_target_markets

_DATA_DIR = Path("research/data/polymarket_whale")
_TRADES_URL = "https://data-api.polymarket.com/trades"
_TIMEOUT = 15

POLL_INTERVAL_S = 5.0
MARKET_REFRESH_INTERVAL_S = 300.0
DEDUP_HASH_RING_SIZE = 2000


def append_trades(trades: list[dict]) -> None:
    if not trades:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
    with path.open("a") as f:
        for t in trades:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


def fetch_trades(limit: int = 500) -> list[dict]:
    r = requests.get(_TRADES_URL, params={"limit": limit}, timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def refresh_target_markets() -> dict[str, str]:
    """condition_id -> family("news"|"sports") 매핑. select_target_markets() 통과분만."""
    now = dt.datetime.now(dt.timezone.utc)
    markets = get_markets(limit=500)
    target = select_target_markets(markets, now)
    return {m["condition_id"]: m["family"] for m in target}


def filter_new_trades(
    trades: list[dict],
    target_markets: dict[str, str],
    last_seen_ts: float,
    seen_hashes: list[str],
) -> tuple[list[dict], float, list[str]]:
    """target_markets 통과 + last_seen_ts보다 새 것 + 중복 hash 아닌 것만 남기고
    family 태그를 붙인다. 반환: (필터통과 trades, 갱신된 last_seen_ts, 갱신된
    seen_hashes 링버퍼(최근 DEDUP_HASH_RING_SIZE개))."""
    seen_set = set(seen_hashes)
    out = []
    max_ts = last_seen_ts
    hashes = list(seen_hashes)
    for t in trades:
        cid = t.get("conditionId")
        family = target_markets.get(cid)
        ts = t.get("timestamp")
        h = t.get("transactionHash")
        if family is None:
            continue
        if ts is None or ts < last_seen_ts:
            continue
        if h in seen_set:
            continue
        out.append({**t, "family": family})
        seen_set.add(h)
        hashes.append(h)
        if ts > max_ts:
            max_ts = ts
    if len(hashes) > DEDUP_HASH_RING_SIZE:
        hashes = hashes[-DEDUP_HASH_RING_SIZE:]
    return out, max_ts, hashes


def run_forever(
    *,
    fetch_fn=fetch_trades,
    refresh_fn=refresh_target_markets,
    append_fn=append_trades,
    poll_interval_s: float = POLL_INTERVAL_S,
    market_refresh_interval_s: float = MARKET_REFRESH_INTERVAL_S,
    max_cycles: int | None = None,
) -> None:
    target_markets = refresh_fn()
    last_market_refresh = time.time()
    last_seen_ts = 0.0
    seen_hashes: list[str] = []
    cycle = 0
    while max_cycles is None or cycle < max_cycles:
        try:
            if time.time() - last_market_refresh >= market_refresh_interval_s:
                target_markets = refresh_fn()
                last_market_refresh = time.time()
            trades = fetch_fn()
            new_trades, last_seen_ts, seen_hashes = filter_new_trades(
                trades, target_markets, last_seen_ts, seen_hashes,
            )
            append_fn(new_trades)
        except Exception:
            logging.exception("polymarket whale poll failed, continuing")
        time.sleep(poll_interval_s)
        cycle += 1


if __name__ == "__main__":
    run_forever()
