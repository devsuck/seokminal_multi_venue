"""IB reqHistoricalData 인트라데이 다운로더 — 청크·페이싱·재개.

IB 페이싱: 히스토리컬 ~6 req/min. 요청 간 pace_s(기본 11s) 대기.
백워드 청킹: endDateTime을 과거로 이동하며 target_start까지 수집.
useRTH=True(정규장만) → ORB/VWAP 계산 깨끗. whatToShow=TRADES.
"""
from __future__ import annotations

import asyncio
import datetime as dt

from ib_async import IB
from ib_async.contract import Stock


def _to_epoch(d) -> int:
    """BarData.date(datetime/date/epoch str/int) → UTC epoch sec."""
    if isinstance(d, (int, float)):
        return int(d)
    if isinstance(d, str):
        # formatDate=2 → epoch 문자열
        try:
            return int(d)
        except ValueError:
            return int(dt.datetime.fromisoformat(d).timestamp())
    if isinstance(d, dt.datetime):
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return int(d.timestamp())
    if isinstance(d, dt.date):
        return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp())
    raise TypeError(f"unhandled bar date type {type(d)!r}: {d!r}")


async def download_symbol(
    ib: IB,
    symbol: str,
    bar_size: str = "15 mins",
    duration_per_chunk: str = "1 Y",
    years: float = 2.0,
    stop_before_ts: int | None = None,
    pace_s: float = 11.0,
    max_chunks: int = 200,
    log=print,
) -> list[dict]:
    """symbol의 인트라데이 봉을 백워드로 수집 → rows(dict). 이미 연결된 ib 사용.

    stop_before_ts: 이 epoch 이하까지 오면 중단(재개 시 기존 최신 ts 전달).
    """
    contract = Stock(symbol, "SMART", "USD")
    await ib.qualifyContractsAsync(contract)

    target_start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=365 * years)
    target_start_ts = int(target_start.timestamp())
    if stop_before_ts is not None:
        target_start_ts = max(target_start_ts, stop_before_ts)

    rows: list[dict] = []
    end: dt.datetime | str = ""  # "" = now
    seen_earliest: int | None = None

    for chunk in range(max_chunks):
        bars = await ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end,
            durationStr=duration_per_chunk,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,
            formatDate=2,  # epoch
        )
        if not bars:
            log(f"  [{symbol}] chunk {chunk}: 0 bars → stop")
            break
        for b in bars:
            ts = _to_epoch(b.date)
            rows.append({
                "ts_utc": ts, "open": float(b.open), "high": float(b.high),
                "low": float(b.low), "close": float(b.close), "volume": float(b.volume),
            })
        earliest = _to_epoch(bars[0].date)
        log(f"  [{symbol}] chunk {chunk}: {len(bars)} bars, earliest="
            f"{dt.datetime.fromtimestamp(earliest, dt.timezone.utc).date()}")

        if earliest <= target_start_ts:
            break
        if seen_earliest is not None and earliest >= seen_earliest:
            log(f"  [{symbol}] no backward progress → stop")
            break
        seen_earliest = earliest
        end = dt.datetime.fromtimestamp(earliest - 1, dt.timezone.utc)
        await asyncio.sleep(pace_s)  # IB 페이싱 준수

    return rows
