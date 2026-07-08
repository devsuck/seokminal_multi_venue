"""폴리마켓 실시간 틱 수집기 진입점 — tmux로 상시 실행.

5분마다 대상 마켓을 재선정해 WSS를 재구독한다. 내부 상태 없음 —
재시작해도 market_selector로 매번 새로 계산되므로 유실 구간만 생기고 꼬이지 않는다.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from pathlib import Path

from polymarket.client import get_markets
from research.polymarket_tick.market_selector import build_meta_by_token, select_target_markets
from research.polymarket_tick.ws_collector import PolymarketTickWSClient, parse_tick_message

_DATA_DIR = Path("research/data/polymarket_tick")

RESELECT_INTERVAL_SEC = 300.0
RECONNECT_BASE_DELAY = 2.0
RECONNECT_MAX_DELAY = 60.0


def append_ticks(ticks: list[dict]) -> None:
    if not ticks:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
    with path.open("a") as f:
        for t in ticks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


def _default_get_markets() -> list[dict]:
    return get_markets(limit=300)


async def run_forever(
    *,
    client: PolymarketTickWSClient | None = None,
    get_markets_fn=None,
    append_fn=append_ticks,
    reselect_interval_sec: float = RESELECT_INTERVAL_SEC,
    max_cycles: int | None = None,
) -> None:
    client = client or PolymarketTickWSClient()
    get_markets_fn = get_markets_fn or _default_get_markets
    cycle = 0
    delay = RECONNECT_BASE_DELAY
    last_meta_by_token: dict[str, dict] | None = None
    while max_cycles is None or cycle < max_cycles:
        now = dt.datetime.now(dt.timezone.utc)
        try:
            markets = select_target_markets(get_markets_fn(), now=now)
            meta_by_token = build_meta_by_token(markets)
            last_meta_by_token = meta_by_token
        except Exception:
            logging.exception("Gamma re-selection failed, reusing last known markets")
            # Gamma REST 재선정 실패 → 기존 구독(직전 사이클의 meta) 유지, 다음 주기에 재시도
            meta_by_token = last_meta_by_token or {}
        if not meta_by_token:
            await asyncio.sleep(reselect_interval_sec)
            cycle += 1
            continue
        asset_ids = list(meta_by_token.keys())
        try:
            async with asyncio.timeout(reselect_interval_sec):
                async for raw in client.stream_ticks(asset_ids):
                    append_fn(parse_tick_message(raw, meta_by_token))
            delay = RECONNECT_BASE_DELAY
        except TimeoutError:
            delay = RECONNECT_BASE_DELAY
        except Exception:
            logging.exception("WSS stream failed, reconnecting")
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)
        cycle += 1


if __name__ == "__main__":
    asyncio.run(run_forever())
