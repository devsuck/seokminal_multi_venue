"""벤뉴별(HL/Binance/OKX) BTC/ETH 오더북 스냅샷 수집기 — tmux로 상시 실행.

`orderflow/multi_venue_adapter.py`의 풀링을 거치지 않고 각 벤뉴 어댑터를 직접
물어 벤뉴별 원장을 그대로 저장한다(라이브 대시보드 코드패스 무수정). 크로스벤뉴
스큐(임밸런스 괴리) 계산은 `research/hypotheses/cross_venue_skew.py`에서 나중에
수행 — 수집기는 가공하지 않는다.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from pathlib import Path

from orderflow.binance_adapter import BinanceOrderflowClient
from orderflow.hl_adapter import HyperliquidOrderflowClient
from orderflow.models import OrderBookSnapshot
from orderflow.okx_adapter import OkxOrderflowClient

_DATA_DIR = Path("research/data/cross_venue_skew")

COINS = ["BTC", "ETH"]
VENUES = ["hl", "binance", "okx"]
RECONNECT_BASE_DELAY = 2.0
RECONNECT_MAX_DELAY = 60.0


def append_snapshots(venue: str, coin: str, snapshots: list[dict]) -> None:
    if not snapshots:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{venue}_{coin}_{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
    with path.open("a") as f:
        for s in snapshots:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def _make_client(venue: str):
    if venue == "hl":
        return HyperliquidOrderflowClient()
    if venue == "binance":
        return BinanceOrderflowClient()
    if venue == "okx":
        return OkxOrderflowClient()
    raise ValueError(f"unknown venue: {venue}")


def _venue_stream(client, venue: str, coin: str):
    if venue == "hl":
        return client.stream(coin)
    return client.stream_depth(coin)


async def run_venue_coin_forever(
    venue: str,
    coin: str,
    *,
    client=None,
    append_fn=append_snapshots,
    max_cycles: int | None = None,
) -> None:
    client = client or _make_client(venue)
    cycle = 0
    delay = RECONNECT_BASE_DELAY
    while max_cycles is None or cycle < max_cycles:
        received_snapshot = False
        try:
            async for event in _venue_stream(client, venue, coin):
                if isinstance(event, OrderBookSnapshot):
                    received_snapshot = True
                    append_fn(venue, coin, [event.model_dump()])
            if received_snapshot:
                # 정상 수신하다 스트림 종료 — 백오프 불필요
                delay = RECONNECT_BASE_DELAY
            else:
                # 구독 직후 스냅샷 하나 없이 끊긴 경우 — 핫루프 방지로 백오프
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
        except Exception:
            logging.exception("cross-venue skew stream failed for %s/%s, reconnecting", venue, coin)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)
        cycle += 1


async def run_forever(
    *,
    venues: list[str] = VENUES,
    coins: list[str] = COINS,
    client_factory=_make_client,
    append_fn=append_snapshots,
    max_cycles: int | None = None,
) -> None:
    await asyncio.gather(
        *(
            run_venue_coin_forever(
                venue, coin, client=client_factory(venue), append_fn=append_fn, max_cycles=max_cycles,
            )
            for venue in venues
            for coin in coins
        )
    )


if __name__ == "__main__":
    asyncio.run(run_forever())
