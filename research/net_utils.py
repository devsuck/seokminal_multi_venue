"""OS 레벨 DNS/connect 블로킹 방어 유틸.

`requests`의 `timeout=`은 소켓이 만들어진 *이후* 단계만 커버한다 — `getaddrinfo()`는
소켓 생성 전에 libc가 직접 블로킹 호출하는 단계라 Python 어떤 timeout으로도 못 막는다.
리졸버가 macOS 슬립/웨이크·네트워크 전환 등으로 멈추면 재시도 루프가 아니라 프로세스
자체가 CPU 0%로 통째로 굳는다(2026-07-30, `polymarket_event_divergence` 10일 중
2회 재현 확인). 데몬 스레드에서 호출을 돌리고 그 스레드 join을 timeout으로 기다려서
"응답 없음"을 정상적인 예외 경로로 되돌린다.

스레드 자체는 못 죽인다(Python 한계) — timeout 나면 그 스레드는 계속 블로킹된 채로
누수되지만 daemon=True라 프로세스 종료는 안 막고, 발생 빈도가 낮아(며칠에 한번) 누적
영향은 무시할 수준으로 판단."""
from __future__ import annotations

import queue
import threading
from typing import Callable, TypeVar

T = TypeVar("T")


def call_with_hard_timeout(fn: Callable[[], T], timeout_s: float) -> T:
    result_q: "queue.Queue[tuple[str, object]]" = queue.Queue(maxsize=1)

    def _run() -> None:
        try:
            result_q.put(("ok", fn()))
        except Exception as e:  # noqa: BLE001 - 호출부에서 그대로 재발생
            result_q.put(("err", e))

    threading.Thread(target=_run, daemon=True).start()
    try:
        kind, payload = result_q.get(timeout=timeout_s)
    except queue.Empty:
        raise TimeoutError(
            f"{timeout_s}s 내 응답 없음 — DNS/connect가 OS 레벨에서 멈춘 것으로 추정"
        ) from None
    if kind == "err":
        raise payload  # type: ignore[misc]
    return payload  # type: ignore[return-value]
