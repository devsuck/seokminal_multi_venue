"""4소스 컨버전스 원시 leg 상시 로깅 — 상시 실행 진입점.

insider/convergence.py의 compute_convergence()는 score>=2만 반환하고 저장도 안 함.
score==1(단일 소스) 대조군까지 쌓아야 나중에 "컨버전스가 단일소스보다 forward return이
나은가"를 비교할 수 있어서, compute_convergence() 대신 각 leg 태깅 함수를 직접 호출해
raw leg 전부(score 무관)를 로깅한다.

KR(dart_exec + dart_corp_action)은 과거 몇 개월 백필이 가능하지만(kr_dart_convergence_backfill.py),
US(congress) API는 최신 스냅샷만 주고 페이지네이션도 없어 과거 조회 자체가 불가능 —
options_uoa도 point-in-time이라 마찬가지. 이 상시 로거가 그 두 소스의 유일한 히스토리
축적 경로다.

Usage: python -m research.run_convergence_signal_collect
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from collections import Counter
from pathlib import Path

from insider.convergence import _tag_kr_legs, _tag_uoa_legs, _tag_us_legs_without_uoa
from research.collector_heartbeat import touch_heartbeat

_DATA_DIR = Path("research/data/convergence_legs")
POLL_INTERVAL_SEC = 21600.0  # 6시간 간격 — 신호는 날짜단위라 options_uoa만큼 촘촘할 필요 없음, DART/EDGAR 예산 고려
DAYS_WINDOW = 7  # 각 leg 함수의 기본 실시간 조회창(dart_autobot이 쓰는 것과 동일)
_UOA_TICKER_CAP = 15


def _collect_us_legs(days: int) -> list[dict]:
    legs = _tag_us_legs_without_uoa(days)
    # convergence.compute_convergence()와 동일한 편향 방지 로직(알파벳순 대신 겹침 많은 티커부터).
    ticker_counts = Counter(leg["ticker"] for leg in legs)
    uoa_tickers = sorted(ticker_counts, key=lambda t: (-ticker_counts[t], t))[:_UOA_TICKER_CAP]
    legs += _tag_uoa_legs(uoa_tickers)
    return legs


def event_key(row: dict, scan_date: str | None = None) -> str:
    return f"{row['source']}|{row['ticker']}|{row['direction']}|{row['trade_date']}"


def load_existing_keys(scan_date: str) -> set[str]:
    path = _DATA_DIR / f"{scan_date}.jsonl"
    if not path.exists():
        return set()
    keys = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            keys.add(event_key(json.loads(line)))
    return keys


def run_once(days: int = DAYS_WINDOW) -> list[dict]:
    scan_date = dt.date.today().isoformat()
    existing = load_existing_keys(scan_date)
    legs: list[dict] = []
    try:
        legs += _tag_kr_legs(days)
    except Exception:
        logging.exception("kr leg 수집 실패")
    try:
        legs += _collect_us_legs(days)
    except Exception:
        logging.exception("us leg 수집 실패")
    new_legs = [leg for leg in legs if event_key(leg) not in existing]
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    for leg in new_legs:
        leg["detected_at"] = now
    return new_legs


def append_events(events: list[dict]) -> None:
    if not events:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{dt.date.today().isoformat()}.jsonl"
    with path.open("a") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def run_forever(poll_interval_sec: float = POLL_INTERVAL_SEC, max_iterations: int | None = None) -> None:
    i = 0
    backoff = poll_interval_sec
    while max_iterations is None or i < max_iterations:
        try:
            append_events(run_once())
            # 신규 0건이어도(장 마감/휴일 등) 폴링은 성공한 것 — 함대 헬스가 죽음으로 오탐하지 않게
            touch_heartbeat(_DATA_DIR)
            wait = poll_interval_sec
            backoff = poll_interval_sec
        except Exception:
            logging.exception("convergence signal collect 폴링 실패 — 백오프 후 재시도")
            wait = min(backoff, 60.0)
            backoff = min(backoff * 2, 60.0)
        i += 1
        if max_iterations is None or i < max_iterations:
            time.sleep(wait)


if __name__ == "__main__":
    run_forever()
