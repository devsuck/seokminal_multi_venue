"""수집기 함대 워치독 — /lab/fleet 폴링 → dead(+옵션 stale) 수집기 자동 재기동.

발열/고아 사건 계열의 근본대책 중 하나: 수집기가 조용히 죽으면 엣지가 소리없이
썩는다. 이 워치독은 서버의 `/lab/fleet`(신선도 verdict)를 주기적으로 읽어 dead(또는
설정 시 stale)인 수집기를 `/lab/collectors/{key}/restart`로 되살린다. 재기동 자체가
멱등(같은 세션명 kill 후 재생성)이라 중복 실행에 안전하다.

launchd vs tmux 결정과 무관하게 기존 restart 엔드포인트만 쓰므로 지금 바로 붙일 수 있다.
맥 설치: ops/README.md 참고(cron 또는 launchd). 재기동 판정(to_restart)은 순수함수라 테스트됨.
"""
from __future__ import annotations

import logging
import time
import urllib.request

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
POLL_INTERVAL_S = 120.0


def to_restart(fleet: dict, restart_stale: bool = False) -> list[str]:
    """함대 응답 → 재기동할 수집기 key 리스트. dead는 항상, stale/stuck은 옵션.
    순수함수(IO 없음)."""
    targets = {"dead"} | ({"stale", "stuck"} if restart_stale else set())
    return [c["key"] for c in fleet.get("collectors", []) if c.get("verdict") in targets]


def _get_json(url: str, timeout: float = 10.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
        import json
        return json.loads(r.read().decode())


def _post(url: str, timeout: float = 15.0) -> None:
    req = urllib.request.Request(url, method="POST")
    with urllib.request.urlopen(req, timeout=timeout):  # noqa: S310
        pass


def run_once(base_url: str = DEFAULT_BASE_URL, restart_stale: bool = False) -> list[str]:
    """한 사이클: fleet 조회 → 대상 재기동. 재기동한 key 리스트 반환.

    stuck(장시간 stale 방치)과 flapping(반복 재기동 중)은 restart_stale이 꺼져 있어도
    재기동과 무관하게 로그를 남긴다 — polymarket_event_divergence가 9시간 stale로
    방치됐던 사건은 아무도 /lab/fleet을 안 봐서 생긴 문제였고, stale은 기본적으로
    워치독이 손대지 않는 상태라 로그로라도 티를 내야 한다."""
    fleet = _get_json(f"{base_url}/lab/fleet")

    for c in fleet.get("collectors", []):
        if c.get("verdict") == "stuck":
            logging.error("watchdog: %s 장시간 stale(stuck, %ss) — 수동 확인 필요", c["key"], c.get("age_sec"))
        if c.get("flapping"):
            logging.warning("watchdog: %s 24h 내 %d회 재기동 — 반복 다운 의심", c["key"], c.get("restart_count_24h", 0))

    disk = fleet.get("disk") or {}
    if disk.get("verdict") in ("warn", "critical"):
        logging.warning("watchdog: 디스크 여유공간 %s (%.1fGB)", disk["verdict"], disk.get("free_gb") or -1)

    targets = to_restart(fleet, restart_stale)
    for key in targets:
        try:
            _post(f"{base_url}/lab/collectors/{key}/restart")
            logging.warning("watchdog: 수집기 재기동 %s", key)
        except Exception:  # noqa: BLE001
            logging.exception("watchdog: 재기동 실패 %s", key)
    return targets


def run_forever(base_url: str = DEFAULT_BASE_URL, poll_interval_s: float = POLL_INTERVAL_S,
                restart_stale: bool = False) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.info("collector watchdog 시작: %s (interval=%ss, stale재기동=%s)",
                 base_url, poll_interval_s, restart_stale)
    while True:
        try:
            run_once(base_url, restart_stale)
        except Exception:  # noqa: BLE001
            logging.exception("watchdog 사이클 실패, 계속")
        time.sleep(poll_interval_s)


if __name__ == "__main__":
    import sys
    stale = "--restart-stale" in sys.argv
    run_forever(restart_stale=stale)
