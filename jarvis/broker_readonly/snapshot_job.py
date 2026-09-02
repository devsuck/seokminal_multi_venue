"""일일 포트폴리오 스냅샷 (P8) — equity curve 데이터 소스.
alert_push_loop과 동일 패턴: 실패해도 다음 주기 재시도, 서버 안 죽임."""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
from pathlib import Path

from jarvis.broker_readonly.aggregator import PortfolioAggregator

_SNAPSHOT_PATH = Path("data/portfolio_snapshots.jsonl")
_INTERVAL_SEC = 24 * 3600


def _append_snapshot(mode: str, total_equity_usd: float, path: Path | None = None) -> dict:
    entry = {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(), "mode": mode,
              "total_equity_usd": total_equity_usd}
    target = path if path is not None else _SNAPSHOT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


async def _snapshot_once() -> None:
    for mode in ("live", "paper"):
        try:
            summary = await PortfolioAggregator(mode).summary()
            _append_snapshot(mode, summary["total_equity_usd"])
        except Exception:
            pass


async def snapshot_loop() -> None:
    while True:
        await _snapshot_once()
        await asyncio.sleep(_INTERVAL_SEC)
