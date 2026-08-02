"""폴리마켓 초단기(5분/15분) up/down 마켓 차익거래 오더북 수집기 — 상시 실행 진입점.

일반 차익 스캔(run_polymarket_arb_scan.py)은 MIN_DAYS_TO_RESOLUTION=3 플로어 때문에
crypto up/down 마켓을 전부 걸러낸다. 이 진입점은 그 마켓들만 별도로 스캔해서
research/data/polymarket_updown_arb/*.jsonl 에 쌓는다. 오더북 조회/차익 판정은
polymarket_arb.collector.snapshot_market을 그대로 재사용(신규 로직 아님). 판정(go/no-go)은
기존 run_polymarket_arb_validation.py --data-dir research/data/polymarket_updown_arb 를
그대로 재사용한다 — 이 데이터 디렉토리 구조와 무관하게 완전 제네릭이라 신규 검증러너 불필요.

Usage: python -m research.run_polymarket_updown_arb_scan
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path

from polymarket.client import get_updown_markets
from research.polymarket_arb.collector import FEE_BUFFER, snapshot_market
from research.polymarket_arb.updown_selector import select_updown_markets

_DATA_DIR = Path("research/data/polymarket_updown_arb")
POLL_INTERVAL_SEC = 5.0


def append_snapshots(snapshots: list[dict]) -> None:
    if not snapshots:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{dt.date.today().isoformat()}.jsonl"
    with path.open("a") as f:
        for snap in snapshots:
            f.write(json.dumps(snap, ensure_ascii=False) + "\n")


def run_once(fee_buffer: float = FEE_BUFFER) -> list[dict]:
    snapshots = []
    for market in select_updown_markets(get_updown_markets()):
        snap = snapshot_market(market, fee_buffer)
        if snap is not None:
            snapshots.append(snap)
    return snapshots


def run_forever(poll_interval_sec: float = POLL_INTERVAL_SEC, max_iterations: int | None = None) -> None:
    """run_polymarket_arb_scan.py와 동일한 이유로 try/except+지수백오프 추가
    (2026-08-02, polymarket_updown_arb도 예외무가드로 재기동실패 500까지 관측)."""
    i = 0
    backoff = poll_interval_sec
    while max_iterations is None or i < max_iterations:
        try:
            append_snapshots(run_once())
            wait = poll_interval_sec
            backoff = poll_interval_sec
        except Exception:
            logging.exception("updown arb scan 폴링 실패 — 백오프 후 재시도")
            wait = min(backoff, 60.0)
            backoff = min(backoff * 2, 60.0)
        i += 1
        if max_iterations is None or i < max_iterations:
            time.sleep(wait)


if __name__ == "__main__":
    run_forever()
