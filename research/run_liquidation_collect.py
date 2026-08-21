"""청산 이벤트 수집기 — 상시구동(tmux/launchd 전제, 여기선 미등록).

`orderflow/binance_adapter.py`의 `stream_liquidations`(Binance 선물 forceOrder WS, 대시보드
브로드캐스트만 하고 저장은 안 하던 것)를 구독해 `research/data/liquidation_store.py`에 적재한다.
"""
from __future__ import annotations

import asyncio
import logging
import time

from orderflow.binance_adapter import BinanceOrderflowClient
from research.data.liquidation_store import save_liquidations

COINS = ["BTC", "ETH"]
VENUE = "binance"
FLUSH_INTERVAL_S = 30.0
RECONNECT_BASE_DELAY = 2.0
RECONNECT_MAX_DELAY = 60.0


def _to_row(event) -> dict:
    return {"ts": int(event.ts), "side": event.side, "qty": event.size, "price": event.price, "venue": VENUE}


async def run_coin_forever(
    coin: str,
    *,
    client=None,
    save_fn=save_liquidations,
    now_fn=time.monotonic,
    flush_interval_s: float = FLUSH_INTERVAL_S,
    max_cycles: int | None = None,
) -> None:
    client = client or BinanceOrderflowClient()
    buffer: list[dict] = []
    last_flush = now_fn()
    cycle = 0
    delay = RECONNECT_BASE_DELAY
    while max_cycles is None or cycle < max_cycles:
        received = False
        try:
            async for event in client.stream_liquidations(coin):
                received = True
                buffer.append(_to_row(event))
                if now_fn() - last_flush >= flush_interval_s and buffer:
                    save_fn(coin, buffer)
                    buffer = []
                    last_flush = now_fn()
            if buffer:
                save_fn(coin, buffer)
                buffer = []
            delay = RECONNECT_BASE_DELAY if received else min(delay * 2, RECONNECT_MAX_DELAY)
            if not received:
                await asyncio.sleep(delay)
        except Exception:
            logging.exception("liquidation stream failed for %s/%s, reconnecting", VENUE, coin)
            if buffer:
                save_fn(coin, buffer)
                buffer = []
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)
        cycle += 1


async def run_forever(*, coins: list[str] = COINS, max_cycles: int | None = None) -> None:
    await asyncio.gather(*(run_coin_forever(coin, max_cycles=max_cycles) for coin in coins))


if __name__ == "__main__":
    asyncio.run(run_forever())
