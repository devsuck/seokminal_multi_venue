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
from research.net_utils import call_with_hard_timeout
from research.polymarket_tick.market_selector import select_target_markets

_DATA_DIR = Path("research/data/polymarket_whale")
_TRADES_URL = "https://data-api.polymarket.com/trades"
_TIMEOUT = 15
_HARD_TIMEOUT = _TIMEOUT + 5.0  # requests timeout이 못 막는 DNS/connect 단계 방어

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
    r = call_with_hard_timeout(
        lambda: requests.get(_TRADES_URL, params={"limit": limit}, timeout=_TIMEOUT), _HARD_TIMEOUT
    )
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
    target_markets: dict[str, str] = {}
    try:
        target_markets = refresh_fn()
    except Exception:
        logging.exception("polymarket whale 최초 마켓리스트 조회 실패 — 빈 target으로 시작, 다음 갱신주기에 재시도")
    last_market_refresh = time.time()
    last_seen_ts = 0.0
    seen_hashes: list[str] = []
    cycle = 0
    backoff = poll_interval_s
    while max_cycles is None or cycle < max_cycles:
        # 마켓리스트 갱신과 체결 폴링을 별개 try로 분리 — 갱신이 실패해도(DNS 등)
        # 체결 폴링은 막히면 안 됨(2026-07-30: 같은 try에 묶여있어서 refresh가
        # 계속 실패하는 동안 fetch_fn이 한 사이클도 못 돌고 2.8시간 데이터 공백 발생).
        if time.time() - last_market_refresh >= market_refresh_interval_s:
            try:
                target_markets = refresh_fn()
                last_market_refresh = time.time()
            except Exception:
                logging.exception("polymarket whale 마켓리스트 갱신 실패 — 기존 target 유지, 체결 폴링은 계속")
        try:
            trades = fetch_fn()
            new_trades, last_seen_ts, seen_hashes = filter_new_trades(
                trades, target_markets, last_seen_ts, seen_hashes,
            )
            append_fn(new_trades)
            wait = poll_interval_s
            backoff = poll_interval_s
        except Exception:
            # run_polymarket_arb_scan.py와 동일 패턴(2026-08-02 도입): 네트워크 순간장애
            # 시 고정 5초 재폴링 대신 지수백오프로 API 두들기는 빈도를 낮춘다.
            logging.exception("polymarket whale poll failed, backing off")
            wait = min(backoff, 60.0)
            backoff = min(backoff * 2, 60.0)
        time.sleep(wait)
        cycle += 1


if __name__ == "__main__":
    run_forever()
