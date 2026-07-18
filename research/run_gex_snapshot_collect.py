"""Deribit GEX(감마 익스포저) 스냅샷 수집기 — tmux로 상시 실행.

오더플로우+GEX 결합 가설 백테스트용 원시 데이터 축적이 목적. orderflow/gex.py의
fetch_gex_by_strike를 그대로 재사용(신규 계산 로직 없음, 라이브 대시보드와 동일 소스)해
60초마다 폴링, 스트라이크별 원시 레벨을 그대로 저장한다(집계된 net_gex 부호 같은 파생
지표는 저장 시점이 아니라 분석 시점에 계산 — 나중에 레짐 정의를 바꿔도 재수집 불필요).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from pathlib import Path

from orderflow.gex import GEX_POLL_INTERVAL_SEC, fetch_gex_by_strike

_DATA_DIR = Path("research/data/gex_snapshot")

CURRENCIES = ["BTC", "ETH"]


def append_snapshot(currency: str, snapshot: dict) -> None:
    if not snapshot.get("levels"):
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{currency}_{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")


async def run_forever(
    *,
    currencies: list[str] = CURRENCIES,
    fetch_fn=fetch_gex_by_strike,
    append_fn=append_snapshot,
    poll_interval: float = GEX_POLL_INTERVAL_SEC,
    max_cycles: int | None = None,
) -> None:
    cycle = 0
    while max_cycles is None or cycle < max_cycles:
        for currency in currencies:
            try:
                snapshot = await fetch_fn(currency)
                append_fn(currency, snapshot)
            except Exception:
                logging.exception("GEX 스냅샷 수집 실패: %s", currency)
        await asyncio.sleep(poll_interval)
        cycle += 1


if __name__ == "__main__":
    asyncio.run(run_forever())
