"""Order Lifecycle State Machine (P8.2) — 유효 전이 규칙만. 결정적·순수함수.

정상 경로: CREATED → VALIDATED → SUBMITTED → ACKNOWLEDGED → PARTIALLY_FILLED* → FILLED.
터미널 상태(FILLED/REJECTED/CANCELLED/FAILED/EXPIRED)에서 나가는 전이 없음.
무효 예: CREATED→FILLED · FILLED→SUBMITTED · CANCELLED→FILLED.
**상태만 판정 — 주문/집행/브로커 없음.**
"""
from __future__ import annotations

from jarvis.order_lifecycle.models import OrderLifecycleState as S

# 각 상태에서 허용되는 다음 상태 집합
_TRANSITIONS: dict[str, set[str]] = {
    S.CREATED.value: {S.VALIDATED.value, S.REJECTED.value, S.FAILED.value, S.EXPIRED.value},
    S.VALIDATED.value: {S.SUBMITTED.value, S.REJECTED.value, S.FAILED.value, S.EXPIRED.value,
                        S.CANCELLED.value},
    S.SUBMITTED.value: {S.ACKNOWLEDGED.value, S.PARTIALLY_FILLED.value, S.FILLED.value,
                        S.REJECTED.value, S.FAILED.value, S.EXPIRED.value, S.CANCEL_PENDING.value},
    S.ACKNOWLEDGED.value: {S.PARTIALLY_FILLED.value, S.FILLED.value, S.CANCEL_PENDING.value,
                           S.REJECTED.value, S.FAILED.value, S.EXPIRED.value},
    S.PARTIALLY_FILLED.value: {S.PARTIALLY_FILLED.value, S.FILLED.value, S.CANCEL_PENDING.value,
                               S.CANCELLED.value, S.FAILED.value, S.EXPIRED.value},
    S.CANCEL_PENDING.value: {S.CANCELLED.value, S.FILLED.value, S.PARTIALLY_FILLED.value,
                             S.FAILED.value, S.EXPIRED.value},
    # 터미널 — 전이 없음
    S.FILLED.value: set(),
    S.REJECTED.value: set(),
    S.CANCELLED.value: set(),
    S.FAILED.value: set(),
    S.EXPIRED.value: set(),
}

_ALL = {s.value for s in S}


class InvalidTransition(Exception):
    """무효 상태전이."""


def is_valid_transition(previous_state: str, new_state: str) -> bool:
    if new_state not in _ALL:
        return False
    return new_state in _TRANSITIONS.get(previous_state, set())


def is_terminal(state: str) -> bool:
    from jarvis.order_lifecycle.models import TERMINAL
    return state in TERMINAL


def allowed_next(state: str) -> set[str]:
    return set(_TRANSITIONS.get(state, set()))
