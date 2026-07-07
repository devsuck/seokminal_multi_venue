"""폴리마켓 합가격 차익거래 오더북 수집기 — 상시 실행 진입점.

tmux/systemd로 계속 돌려서 research/data/polymarket_arb/*.jsonl 에 스냅샷을
쌓는다. 판정(go/no-go)은 run_polymarket_arb_validation.py 가 사후에 한다.

Usage: python -m research.run_polymarket_arb_scan
"""
from __future__ import annotations

import datetime as dt
import json
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
    i = 0
    while max_iterations is None or i < max_iterations:
        append_snapshots(run_once(top_n=TOP_N, fee_buffer=FEE_BUFFER))
        i += 1
        if max_iterations is None or i < max_iterations:
            time.sleep(poll_interval_sec)


if __name__ == "__main__":
    run_forever()
