"""옵션 비정상거래량(UOA) 이벤트 로깅 — 상시 실행 진입점.

`insider/options_uoa_client.py`는 스캔만 하고 결과를 저장하지 않는다. "탐지 임계값을
올리면 엣지가 나오나?"를 검증하려면 먼저 이벤트를 쌓아야 한다 — 이 진입점은 그 로깅만
한다(사후 N일 수익률 추적/임계값 스윕/BH-FDR 등록은 데이터 쌓인 뒤 별도 스크립트).

티커 유니버스는 `/insider/options-uoa` 엔드포인트(api_server/main.py) 미지정시 폴백과
동일 — 최근 Form4·의회매매 공시 티커(다른 insider leg가 이미 플래그한 종목만 본다는
기존 API 예산 제약을 그대로 따름).

Usage: python -m research.run_options_uoa_collect
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path

from insider.congress_client import get_congress_trades
from insider.finnhub_client import get_recent_feed
from insider.options_uoa_client import get_unusual_options_activity
from research.collector_heartbeat import touch_heartbeat

_DATA_DIR = Path("research/data/options_uoa")
POLL_INTERVAL_SEC = 1800.0  # 옵션체인 스캔이라 느림 — 30분 간격
MAX_TICKERS = 15


def candidate_tickers(max_tickers: int = MAX_TICKERS) -> list[str]:
    seen: list[str] = []
    try:
        for r in get_recent_feed(days=7, max_filings=60):
            if r.get("ticker") and r["ticker"] not in seen:
                seen.append(r["ticker"])
    except Exception:
        pass
    try:
        for r in get_congress_trades(limit=80):
            if r.get("ticker") and r["ticker"] not in seen:
                seen.append(r["ticker"])
    except Exception:
        pass
    return seen[:max_tickers]


def event_key(row: dict, scan_date: str) -> str:
    return f"{row['contract_symbol']}|{scan_date}"


def load_existing_keys(scan_date: str) -> set[str]:
    path = _DATA_DIR / f"{scan_date}.jsonl"
    if not path.exists():
        return set()
    keys = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            keys.add(event_key(json.loads(line), scan_date))
    return keys


def run_once() -> list[dict]:
    scan_date = dt.date.today().isoformat()
    existing = load_existing_keys(scan_date)
    rows = get_unusual_options_activity(candidate_tickers())
    new_rows = [r for r in rows if event_key(r, scan_date) not in existing]
    for r in new_rows:
        r["detected_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return new_rows


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
            # 이벤트 0건이어도(미장 마감 등) 폴링은 성공한 것 — 함대 헬스가 죽음으로 오탐하지 않게
            touch_heartbeat(_DATA_DIR)
            wait = poll_interval_sec
            backoff = poll_interval_sec
        except Exception:
            logging.exception("options uoa collect 폴링 실패 — 백오프 후 재시도")
            wait = min(backoff, 60.0)
            backoff = min(backoff * 2, 60.0)
        i += 1
        if max_iterations is None or i < max_iterations:
            time.sleep(wait)


if __name__ == "__main__":
    run_forever()
