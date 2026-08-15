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
import time
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
# cross_venue_skew.py는 IMBALANCE_DEPTH_N=5(상위 5레벨)만 쓰고 RESAMPLE_GRID_S=1.0(1초
# 격자)로 리샘플한다 — 라이브 래더용 5000레벨 풀북을 100ms마다 그대로 저장하면 분석에
# 안 쓰이는 데이터가 대부분이라 디스크만 축낸다(하루 27G까지 폭주한 원인). 여유를 두고
# 상위 50레벨 유지 + 1초 간격으로만 기록.
STORAGE_MAX_LEVELS = 50
MIN_WRITE_INTERVAL_S = 1.0
# 어댑터가 스냅샷마다 객체화할 레벨 수. 기본값(binance 5000/okx 400)은 라이브 대시보드 래더
# 배율용이고, 여기선 STORAGE_MAX_LEVELS=50까지만 저장하므로 나머지는 만들자마자 버려진다 —
# emit당 OrderBookLevel 1만 개 할당이 GC로 CPU를 다 먹던 원인(2026-08-14 프로파일: 실행
# 시간의 24%가 gc_collect_main). 로컬 오더북 dict는 어댑터가 풀뎁스로 계속 유지하므로
# diff 병합 정확도는 그대로.
COLLECT_MAX_LEVELS = 100

_last_write_ts: dict[tuple[str, str], float] = {}


def _trim_levels(snapshot: dict, max_levels: int = STORAGE_MAX_LEVELS) -> dict:
    return {**snapshot, "bids": snapshot["bids"][:max_levels], "asks": snapshot["asks"][:max_levels]}


def append_snapshots(venue: str, coin: str, snapshots: list[OrderBookSnapshot]) -> None:
    """스로틀 통과분만 `model_dump()` — 매 WS메시지마다 직렬화하던 게 CPU 낭비였음(대부분 버려짐)."""
    if not snapshots:
        return
    now = time.monotonic()
    key = (venue, coin)
    if now - _last_write_ts.get(key, float("-inf")) < MIN_WRITE_INTERVAL_S:
        return
    _last_write_ts[key] = now
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{venue}_{coin}_{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
    with path.open("a") as f:
        for s in snapshots:
            f.write(json.dumps(_trim_levels(s.model_dump()), ensure_ascii=False) + "\n")


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
        # HL l2Book은 서버가 이미 좁게(양쪽 ~20레벨) 보내줘서 자를 게 없다.
        return client.stream(coin)
    return client.stream_depth(coin, max_levels=COLLECT_MAX_LEVELS)


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
                    append_fn(venue, coin, [event])
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
