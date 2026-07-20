"""폴리마켓 이벤트 내 후보군 YES가격 합산 괴리 스캐너 — 상시 실행 진입점.

tmux/systemd로 계속 돌려서 research/data/polymarket_event_divergence/*.jsonl
에 스냅샷을 쌓는다. 어느 정도 괴리가 실제 시그널인지 판단하는 로직은 이 파일
스코프 밖 — 수집만 한다.

Usage: python -m research.run_polymarket_event_divergence_scan
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path

from research.polymarket_event_divergence.collector import POLL_INTERVAL_SEC, TOP_N_EVENTS, run_once

_DATA_DIR = Path("research/data/polymarket_event_divergence")


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
        try:
            append_snapshots(run_once(top_n=TOP_N_EVENTS))
        except Exception:
            logging.exception("이벤트 괴리 스캔 실패 — 이번 사이클 스킵")
        i += 1
        if max_iterations is None or i < max_iterations:
            time.sleep(poll_interval_sec)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
