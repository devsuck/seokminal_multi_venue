"""폴리마켓 합가격 차익거래 오더북 수집기 — 상시 실행 진입점.

tmux/systemd로 계속 돌려서 research/data/polymarket_arb/*.jsonl 에 스냅샷을
쌓는다. 판정(go/no-go)은 run_polymarket_arb_validation.py 가 사후에 한다.

Usage: python -m research.run_polymarket_arb_scan
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path

from research.polymarket_arb.collector import FEE_BUFFER, POLL_INTERVAL_SEC, TOP_N, run_once

_DATA_DIR = Path("research/data/polymarket_arb")


def append_snapshots(snapshots: list[dict]) -> None:
    if not snapshots:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{dt.date.today().isoformat()}.jsonl"
    with path.open("a") as f:
        for snap in snapshots:
            f.write(json.dumps(snap, ensure_ascii=False) + "\n")


def run_forever(poll_interval_sec: float = POLL_INTERVAL_SEC, max_iterations: int | None = None) -> None:
    """예외 무가드였던 원래 루프가 네트워크 순간장애에도 프로세스를 죽여 워치독 풀재기동에만
    의존했다(2026-08-02 실측: polymarket_arb 22분간 5회 재기동). mlb_specialist와 동일한
    try/except+지수백오프로 자체 복구하게 한다."""
    i = 0
    backoff = poll_interval_sec
    while max_iterations is None or i < max_iterations:
        try:
            append_snapshots(run_once(top_n=TOP_N, fee_buffer=FEE_BUFFER))
            wait = poll_interval_sec
            backoff = poll_interval_sec
        except Exception:
            logging.exception("arb scan 폴링 실패 — 백오프 후 재시도")
            wait = min(backoff, 60.0)
            backoff = min(backoff * 2, 60.0)
        i += 1
        if max_iterations is None or i < max_iterations:
            time.sleep(wait)


if __name__ == "__main__":
    run_forever()
