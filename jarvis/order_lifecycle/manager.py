"""Order Lifecycle Manager (P8.2) — P8.1 요청/응답의 생애주기 관측·기록.

책임: ①P8.1 요청에서 생애주기 레코드 생성 ②브로커 응답 객체 수용 ③상태전이 검증
④불변 이벤트 append(해시체인) ⑤이벤트 원장에서 현재 상태 재구성.

**MUST NOT: 주문 생성·브로커 어댑터 호출·집행 게이트웨이 호출·포지션/포트폴리오/
리스크/ARM 변경.** 오직 관측·기록. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.order_lifecycle import ledger
from jarvis.order_lifecycle.models import (
    GENESIS,
    OrderLifecycleEvent,
    OrderLifecycleState as S,
    event_hash,
    event_id,
)
from jarvis.order_lifecycle.state_machine import InvalidTransition, is_valid_transition

# P8.1 응답 status → 관측 상태
_RESPONSE_MAP = {"ACCEPTED": S.ACKNOWLEDGED.value, "REJECTED": S.REJECTED.value}


class OrderLifecycleManager:
    """생애주기 관측 기록기. 집행/브로커/포지션 무접촉."""

    # ── ① 생성 ──────────────────────────────────────────────
    def create(self, request, now: str, reason: str = "created from P8.1 request",
               source: str = "p8.1_request", commit: bool = False) -> OrderLifecycleEvent | None:
        req = request.to_dict() if hasattr(request, "to_dict") else request
        oid = req["request_id"]
        eid = event_id(oid, S.CREATED.value, now)
        if ledger.event_exists(eid):
            return None   # 이미 생성됨(중복 방지)
        ev = self._make(eid, oid, "", S.CREATED.value, now, reason, source, GENESIS)
        if commit:
            if ledger.event_exists(eid):
                return None
            ledger.append_event(ev.to_dict())
        return ev

    # ── ③④ 전이 ────────────────────────────────────────────
    def transition(self, order_id: str, new_state: str, now: str, reason: str = "",
                   source: str = "manager", commit: bool = False) -> OrderLifecycleEvent | None:
        head = ledger.chain_head(order_id)
        if head is None:
            raise InvalidTransition(f"no lifecycle for {order_id} (create first)")
        eid = event_id(order_id, new_state, now)
        if ledger.event_exists(eid):
            return None   # 동일 논리 이벤트 재전달 → 멱등 무연산
        prev_state = head["new_state"]
        prev_hash = head["event_hash"]
        if not is_valid_transition(prev_state, new_state):
            raise InvalidTransition(f"{prev_state} -> {new_state} invalid")
        ev = self._make(eid, order_id, prev_state, new_state, now, reason, source, prev_hash)
        if commit:
            ledger.append_event(ev.to_dict())
        return ev

    # ── ② 브로커 응답 수용(관측) ────────────────────────────
    def accept_response(self, order_id: str, response, now: str,
                        commit: bool = False) -> OrderLifecycleEvent | None:
        r = response.to_dict() if hasattr(response, "to_dict") else response
        status = r.get("status", "")
        new_state = _RESPONSE_MAP.get(status)
        if new_state is None:
            raise InvalidTransition(f"unmapped broker response status: {status}")
        reason = f"broker_response:{status} order={r.get('broker_order_id', '')}"
        return self.transition(order_id, new_state, now, reason=reason,
                               source="broker_response", commit=commit)

    # ── ⑤ 현재 상태 재구성 ──────────────────────────────────
    def current_state(self, order_id: str) -> str | None:
        evs = ledger.events_for(order_id)
        return evs[-1]["new_state"] if evs else None

    def history(self, order_id: str) -> list[dict]:
        return ledger.events_for(order_id)

    # ── 내부 ────────────────────────────────────────────────
    def _make(self, eid: str, oid: str, prev_state: str, new_state: str, now: str,
              reason: str, source: str, prev_hash: str) -> OrderLifecycleEvent:
        eh = event_hash(eid, oid, prev_state, new_state, now, reason, source, prev_hash)
        return OrderLifecycleEvent(
            event_id=eid, order_id=oid, previous_state=prev_state, new_state=new_state,
            timestamp=now, reason=reason, source=source, previous_hash=prev_hash, event_hash=eh)
