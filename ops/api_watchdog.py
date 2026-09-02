"""api_server 헬스 워치독 — /health 죽으면 텔레그램 알림 + 강제 재기동.

launchd KeepAlive는 프로세스가 죽어야만 재기동한다. uvicorn이 살아있는데
이벤트루프만 멈춘 경우(행) KeepAlive는 못 잡는다 — 이 워치독이 /health
폴링으로 그 틈을 메운다. 죽은 걸 발견하면 포트 kill(→launchd가 되살림)
+ 텔레그램 알림, 복구되면 복구 알림. 군대 등 장기 무인 운영 대비
(collector_watchdog.py와 동일 dedup 패턴, 알림 채널만 데스크톱→텔레그램).
"""
from __future__ import annotations

import logging
import subprocess
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
POLL_INTERVAL_S = 300.0
PORT = 8000

_DOWN = False  # 직전 사이클 상태 — 복구 알림 트리거용


def _healthy(base_url: str, timeout: float = 10.0) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=timeout) as r:  # noqa: S310
            return r.status == 200
    except Exception:
        return False


def _kill_port(port: int = PORT) -> None:
    subprocess.run(["bash", "-c", f"lsof -ti:{port} | xargs kill -9"], check=False, timeout=10)


def run_once(base_url: str = DEFAULT_BASE_URL) -> bool:
    """한 사이클: 헬스체크 → 다운이면 kill+알림, 복구면 복구알림. healthy 여부 반환."""
    global _DOWN
    from api_server.lv6_notify import send

    healthy = _healthy(base_url)
    if not healthy and not _DOWN:
        _DOWN = True
        logging.error("api_watchdog: /health 실패 — 강제 재기동 시도")
        _kill_port()
        send("⚠️ api_server 헬스체크 실패 — 강제 재기동함 (launchd가 되살릴 것)")
    elif healthy and _DOWN:
        _DOWN = False
        logging.info("api_watchdog: 복구 확인")
        send("✅ api_server 복구됨")
    return healthy


STARTUP_GRACE_S = 30.0  # launchd가 api/watchdog 둘 다 RunAtLoad로 동시에 띄워서, uvicorn
                         # import(수천줄 FastAPI 앱)가 끝나기 전에 워치독이 먼저 찔러 오탐하는 것 방지


def run_forever(base_url: str = DEFAULT_BASE_URL, poll_interval_s: float = POLL_INTERVAL_S) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.info("api watchdog 시작: %s (interval=%ss)", base_url, poll_interval_s)
    time.sleep(STARTUP_GRACE_S)
    while True:
        try:
            run_once(base_url)
        except Exception:  # noqa: BLE001
            logging.exception("api_watchdog 사이클 실패, 계속")
        time.sleep(poll_interval_s)


if __name__ == "__main__":
    run_forever()
