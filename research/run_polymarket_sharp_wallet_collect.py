"""Polymarket 샤프월렛 체결(fill) 수집기 — Data-API REST 폴링, tmux로 상시 실행.

whale 수집기(`research/run_polymarket_whale_collect.py`)와 동일한 무한루프+폴링
골격(글로벌 `/trades` 피드, transactionHash 기반 dedup, try/except 사이클스킵)을
재사용하되 필터 기준이 다르다: 마켓 family가 아니라 "이 체결의 지갑이(공식
리더보드 top 50 기준) 샤프월렛인지". 리더보드는 1일 1회만 재조회(PnL 랭킹은
느리게 변함 — 매 폴링마다 부르지 않음).

왜 컨텍스트 체결까지 저장하는가: forward-return 계산엔 각 마켓의 조밀한 가격
시계열이 필요하다. 샤프월렛 체결만 저장하면 마켓당 표본이 1건뿐인 경우가
대부분이라(top 50 지갑이 특정 마켓에 동시에 다 몰릴 리 없음) ffill 리샘플이
사실상 "영원히 anchor 가격 고정"이 되어 forward return이 항상 0으로 나온다.
해결: 샤프월렛 체결(anchor)이 마켓 X에서 감지되면, 그 시점부터 MAX_HORIZON_S초
동안 마켓 X의 모든 체결(지갑 무관, context)을 같이 저장해 가격 시계열을
조밀하게 만든다(`docs/superpowers/specs/2026-07-20-polymarket-sharp-wallet-design.md`
§6 참고). 상수는 전부 설계 시점 고정값이며 결과를 본 뒤 바꾸지 않는다.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path

import requests

from research.polymarket_sharp_wallet.leaderboard import (
    build_sharp_wallet_set,
    fetch_leaderboard,
)

_DATA_DIR = Path("research/data/polymarket_sharp_wallet")
_TRADES_URL = "https://data-api.polymarket.com/trades"
_TIMEOUT = 15

POLL_INTERVAL_S = 5.0
LEADERBOARD_REFRESH_INTERVAL_S = 86400.0
MIN_NOTIONAL_USD = 50.0
MAX_HORIZON_S = 300.0
DEDUP_HASH_RING_SIZE = 5000


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


def refresh_leaderboard() -> dict[str, dict]:
    """proxyWallet(lowercase) -> {rank, pnl} 매핑(공식 리더보드 top 50)."""
    return build_sharp_wallet_set(fetch_leaderboard())


def prune_stale_watch(watch_until: dict[str, float], now: float) -> dict[str, float]:
    """watch_until[cid] < now - MAX_HORIZON_S인 항목 제거(무한 성장 방지)."""
    cutoff = now - MAX_HORIZON_S
    return {cid: until for cid, until in watch_until.items() if until >= cutoff}


def filter_new_trades(
    trades: list[dict],
    sharp_wallets: dict[str, dict],
    watch_until: dict[str, float],
    last_seen_ts: float,
    seen_hashes: list[str],
) -> tuple[list[dict], float, list[str], dict[str, float]]:
    """anchor(샤프월렛 체결, notional>=MIN_NOTIONAL_USD) 또는 context(watch_until
    안의 체결)만 남기고 나머지는 버린다. anchor 감지 시 watch_until[cid]를
    trade_ts+MAX_HORIZON_S로 갱신(연장 포함). 반환: (필터통과 trades, 갱신된
    last_seen_ts, 갱신된 seen_hashes 링버퍼(최근 DEDUP_HASH_RING_SIZE개), 갱신된
    watch_until)."""
    seen_set = set(seen_hashes)
    hashes = list(seen_hashes)
    watch_until = dict(watch_until)
    out = []
    max_ts = last_seen_ts
    for t in trades:
        cid = t.get("conditionId")
        ts = t.get("timestamp")
        h = t.get("transactionHash")
        if ts is None or ts < last_seen_ts:
            continue
        if h in seen_set:
            continue
        wallet = (t.get("proxyWallet") or "").lower()
        notional = float(t["price"]) * float(t["size"])
        sharp = sharp_wallets.get(wallet)
        is_anchor = sharp is not None and notional >= MIN_NOTIONAL_USD
        is_context = cid in watch_until and ts <= watch_until[cid]
        if not (is_anchor or is_context):
            continue
        if is_anchor:
            watch_until[cid] = ts + MAX_HORIZON_S
        out.append({
            **t, "notional_usd": notional, "is_sharp_wallet": is_anchor,
            "wallet_rank": sharp["rank"] if sharp else None,
            "wallet_pnl": sharp["pnl"] if sharp else None,
        })
        seen_set.add(h)
        hashes.append(h)
        if ts > max_ts:
            max_ts = ts
    if len(hashes) > DEDUP_HASH_RING_SIZE:
        hashes = hashes[-DEDUP_HASH_RING_SIZE:]
    return out, max_ts, hashes, watch_until


def run_forever(
    *,
    fetch_fn=fetch_trades,
    leaderboard_fn=refresh_leaderboard,
    append_fn=append_trades,
    poll_interval_s: float = POLL_INTERVAL_S,
    leaderboard_refresh_interval_s: float = LEADERBOARD_REFRESH_INTERVAL_S,
    max_cycles: int | None = None,
) -> None:
    sharp_wallets = leaderboard_fn()
    last_leaderboard_refresh = time.time()
    watch_until: dict[str, float] = {}
    last_seen_ts = 0.0
    seen_hashes: list[str] = []
    cycle = 0
    while max_cycles is None or cycle < max_cycles:
        try:
            now = time.time()
            if now - last_leaderboard_refresh >= leaderboard_refresh_interval_s:
                sharp_wallets = leaderboard_fn()
                last_leaderboard_refresh = now
            trades = fetch_fn()
            new_trades, last_seen_ts, seen_hashes, watch_until = filter_new_trades(
                trades, sharp_wallets, watch_until, last_seen_ts, seen_hashes,
            )
            watch_until = prune_stale_watch(watch_until, now)
            append_fn(new_trades)
        except Exception:
            logging.exception("polymarket sharp-wallet poll failed, continuing")
        time.sleep(poll_interval_s)
        cycle += 1


if __name__ == "__main__":
    run_forever()
