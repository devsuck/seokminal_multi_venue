"""api_server 헬스 워치독 — /health 죽거나 메모리 폭주하면 텔레그램 알림 + 강제 재기동.

launchd KeepAlive는 프로세스가 죽어야만 재기동한다. uvicorn이 살아있는데
이벤트루프만 멈춘 경우(행) KeepAlive는 못 잡는다 — 이 워치독이 /health
폴링으로 그 틈을 메운다. 죽은 걸 발견하면 포트 kill(→launchd가 되살림)
+ 텔레그램 알림, 복구되면 복구 알림. 군대 등 장기 무인 운영 대비
(collector_watchdog.py와 동일 dedup 패턴, 알림 채널만 데스크톱→텔레그램).

2026-09-03: 실사용 중 /health가 ~10분 주기로 반복 실패하는 걸 발견 — 원인은
uvicorn RSS가 3GB 안팎까지 불어나며 시스템 전체 스왑 스래싱(여러 research
collector와 메모리 경합) → 이벤트루프가 10초 헬스체크 타임아웃 넘게 멈춤.
근본 원인(리서치 collector들과의 메모리 경합)은 트레이딩 전략에 걸쳐있어
당장 건드릴 수 없으니, 같은 패턴으로 RSS 상한 체크도 추가해 선제적으로
재기동(스왑 임계치 넘기 전에 끊고 감).
"""
from __future__ import annotations

import logging
import subprocess
import time
import urllib.error
import urllib.request

import psutil
from dotenv import load_dotenv

# launchd job은 최소 환경변수만 물려받음(PATH 등, .env 안 읽힘 — 2026-09-03 `launchctl print`로
# 확인: TELEGRAM_BOT_TOKEN 자체가 없어 텔레그램 알림이 조용히 no-op이었음, lv6_notify._send가
# 토큰 없으면 debug 로그만 남기고 드롭해서 안 보였음). 여기서 직접 로드해 os.environ에 채운다.
load_dotenv()

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
POLL_INTERVAL_S = 300.0
PORT = 8000
RSS_LIMIT_MB = 4000.0  # 이 넘으면 스왑 스래싱으로 행 걸리기 전에 선제 재기동

_DOWN = False  # 직전 사이클 상태 — 복구 알림 트리거용


def _healthy(base_url: str, timeout: float = 10.0) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=timeout) as r:  # noqa: S310
            return r.status == 200
    except Exception:
        return False


def _rss_mb_over_limit(port: int = PORT, limit_mb: float = RSS_LIMIT_MB) -> float | None:
    """포트 리스닝 중인 프로세스 RSS(MB)가 limit_mb 넘으면 그 값, 아니면 None."""
    pid = subprocess.run(["bash", "-c", f"lsof -ti:{port}"], capture_output=True, text=True, timeout=10).stdout.strip()
    if not pid:
        return None
    try:
        rss_mb = psutil.Process(int(pid)).memory_info().rss / (1024 * 1024)
    except (psutil.NoSuchProcess, ValueError):
        return None
    return rss_mb if rss_mb > limit_mb else None


def _kill_port(port: int = PORT) -> None:
    subprocess.run(["bash", "-c", f"lsof -ti:{port} | xargs kill -9"], check=False, timeout=10)


def run_once(base_url: str = DEFAULT_BASE_URL) -> bool:
    """한 사이클: 헬스체크+RSS체크 → 다운/과다면 kill+알림, 복구면 복구알림. healthy 여부 반환."""
    global _DOWN
    from api_server.lv6_notify import send

    healthy = _healthy(base_url)
    over_rss = None if not healthy else _rss_mb_over_limit()

    if (not healthy or over_rss) and not _DOWN:
        _DOWN = True
        if over_rss:
            logging.error("api_watchdog: RSS %.0fMB 초과 — 선제 재기동", over_rss)
            _kill_port()
            send(f"⚠️ api_server 메모리 {over_rss:.0f}MB 초과 — 선제 재기동함")
        else:
            logging.error("api_watchdog: /health 실패 — 강제 재기동 시도")
            _kill_port()
            send("⚠️ api_server 헬스체크 실패 — 강제 재기동함 (launchd가 되살릴 것)")
        healthy = False
    elif healthy and not over_rss and _DOWN:
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
