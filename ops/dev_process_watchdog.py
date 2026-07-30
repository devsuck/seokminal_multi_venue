"""개발용 프로세스(vitest watch 등) 방치 감시 — 발열 사건 재발 방지.

`npm test`는 `package.json`에서 `vitest run`(1회성)으로 고정돼 있지만, 터미널에서
직접 `vitest`(인자 없이)를 치면 기본이 watch 모드라 안 닫고 자리를 뜨면 CPU 100%로
몇 시간~며칠 방치될 수 있다(2026-07-30 9시간+ 방치 사건 실사례). 수집기 워치독
(`collector_watchdog.py`)과 같은 모양: ps 스캔(IO) → 순수판정(classify_processes) →
초과분 SIGTERM. vitest worker 패턴만 명시적으로 잡는다 — uvicorn/수집기/next dev 같은
상시 프로세스는 화이트리스트에 없어도 패턴에 안 걸리므로 안전.
"""
from __future__ import annotations

import re

# vitest fork/worker 프로세스만 대상. 넓게 잡지 않는 이유: 잘못 걸려서 상시
# 프로세스를 죽이는 사고가 안 걸리는 정확도 부족보다 훨씬 나쁨.
KILL_PATTERNS = [
    re.compile(r"vitest/dist/workers/forks\.js"),
    re.compile(r"vitest/dist/worker\.js"),
]
MAX_ELAPSED_S = 1800.0  # 30분 — 정상 스위트 실행시간보다 넉넉히 크게(오탐 방지)


def parse_etime(etime: str) -> float:
    """ps -o etime 포맷("MM:SS"/"HH:MM:SS"/"D-HH:MM:SS") → 초."""
    days = 0
    rest = etime
    if "-" in etime:
        d, rest = etime.split("-", 1)
        days = int(d)
    parts = [int(p) for p in rest.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return days * 86400 + h * 3600 + m * 60 + s


def classify_processes(rows: list[dict], max_elapsed_s: float = MAX_ELAPSED_S) -> list[dict]:
    """rows: [{"pid":.., "etime": "05:56", "command": "..."}] → kill 대상만.
    순수함수(IO 없음)."""
    targets = []
    for r in rows:
        if not any(p.search(r["command"]) for p in KILL_PATTERNS):
            continue
        if parse_etime(r["etime"]) >= max_elapsed_s:
            targets.append(r)
    return targets


def _ps_rows() -> list[dict]:
    import subprocess

    out = subprocess.run(
        ["ps", "-Ao", "pid,etime,command"], capture_output=True, text=True, timeout=10,
    ).stdout
    rows = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        pid, etime, command = line.split(maxsplit=2)
        rows.append({"pid": int(pid), "etime": etime, "command": command})
    return rows


def run_once(max_elapsed_s: float = MAX_ELAPSED_S) -> list[int]:
    """한 사이클: ps 스캔 → 방치 vitest SIGTERM. 종료시킨 pid 리스트 반환."""
    import logging
    import os
    import signal

    targets = classify_processes(_ps_rows(), max_elapsed_s)
    killed = []
    for t in targets:
        try:
            os.kill(t["pid"], signal.SIGTERM)
            logging.warning("dev_process_watchdog: 방치 vitest 종료 pid=%s etime=%s", t["pid"], t["etime"])
            killed.append(t["pid"])
        except ProcessLookupError:
            pass
    return killed


def run_forever(poll_interval_s: float = 300.0, max_elapsed_s: float = MAX_ELAPSED_S) -> None:
    import logging
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.info("dev_process_watchdog 시작 (interval=%ss, max_elapsed=%ss)", poll_interval_s, max_elapsed_s)
    while True:
        try:
            run_once(max_elapsed_s)
        except Exception:  # noqa: BLE001
            logging.exception("dev_process_watchdog 사이클 실패, 계속")
        time.sleep(poll_interval_s)


if __name__ == "__main__":
    run_forever()
