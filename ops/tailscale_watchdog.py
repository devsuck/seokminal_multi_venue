"""Tailscale 자체 장애 워치독 — 로컬은 살아있는데 tailscale IP로만 안 뚫리면 재시작+알림.

api_watchdog.py는 uvicorn(127.0.0.1) 헬스만 본다 — Tailscale.app/IPNExtension이 죽거나
라우팅이 끊기면 서버는 멀쩡해도 iOS 앱은 원격에서 아예 접근불가인데 아무도 못 잡는다.
이 워치독은 같은 머신에서 127.0.0.1과 자기 tailscale IP 둘 다 찔러 차이가 나면
(로컬 OK, tailscale IP 실패) tailscale 문제로 특정해 Tailscale.app 재시작.

launchd 로그인 아이템(GUI 앱)이라 killall 후 `open -a`로 재기동 — CLI 미설치
(Mac App Store 배포판, tailscale 바이너리 없음, 2026-09-03 확인) 환경 한정.
(api_watchdog.py와 동일 dedup 패턴)
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

# launchd job이 .env를 안 읽어 TELEGRAM_BOT_TOKEN/MOBILE_API_KEY 둘 다 비어있던 문제
# (api_watchdog.py와 동일, 2026-09-03 발견) — 여기서도 직접 로드.
load_dotenv()

LOCAL_URL = "http://127.0.0.1:8000/health"
POLL_INTERVAL_S = 300.0
STARTUP_GRACE_S = 30.0

_DOWN = False


def _own_tailscale_ip() -> str | None:
    """ifconfig에서 tailscale utun의 point-to-point IP(100.64.0.0/10 CGNAT) 추출."""
    out = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=10).stdout
    m = re.search(r"inet (100\.\d{1,3}\.\d{1,3}\.\d{1,3}) -->", out)
    return m.group(1) if m else None


def _url_ok(url: str, timeout: float = 5.0) -> bool:
    """tailscale IP는 모바일 인증 미들웨어(127.0.0.1 외 호스트는 X-Api-Key 강제,
    api_server/main.py `_require_key_for_remote`)를 거치므로 헤더 없인 /health도 401남
    (2026-09-03 실측 — 헤더 없이 붙였다가 오탐 재시작 루프 걸릴 뻔함)."""
    key = os.environ.get("MOBILE_API_KEY", "")
    req = urllib.request.Request(url, headers={"X-Api-Key": key} if key else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return r.status == 200
    except Exception:
        return False


def _restart_tailscale() -> None:
    subprocess.run(["killall", "Tailscale", "IPNExtension"], check=False, timeout=10)
    time.sleep(1)
    subprocess.run(["open", "-a", "Tailscale"], check=False, timeout=10)


def run_once() -> bool:
    """한 사이클: 로컬 vs tailscale IP 헬스 비교 → tailscale만 실패면 재시작+알림. tailscale 정상여부 반환."""
    global _DOWN
    from api_server.lv6_notify import send

    local_ok = _url_ok(LOCAL_URL)
    ip = _own_tailscale_ip()
    # 로컬도 죽었으면 api_watchdog 소관(서버 자체 문제) — 여긴 tailscale 단독 장애만 다룸.
    tailscale_ok = bool(ip) and (not local_ok or _url_ok(f"http://{ip}:8000/health"))

    if not tailscale_ok and local_ok and not _DOWN:
        _DOWN = True
        logging.error("tailscale_watchdog: 로컬 OK, tailscale IP(%s) 접근 실패 — 재시작", ip)
        _restart_tailscale()
        send("⚠️ Tailscale 접근 안 됨(로컬은 정상) — 재시작함")
    elif tailscale_ok and _DOWN:
        _DOWN = False
        logging.info("tailscale_watchdog: 복구 확인")
        send("✅ Tailscale 복구됨")
    return tailscale_ok


def run_forever(poll_interval_s: float = POLL_INTERVAL_S) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.info("tailscale watchdog 시작 (interval=%ss)", poll_interval_s)
    time.sleep(STARTUP_GRACE_S)
    while True:
        try:
            run_once()
        except Exception:  # noqa: BLE001
            logging.exception("tailscale_watchdog 사이클 실패, 계속")
        time.sleep(poll_interval_s)


if __name__ == "__main__":
    run_forever()
