"""Order Lifecycle 검증 (P8.2) — 결정적 재현·해시체인 무결성·무효전이 탐지.

replay_state: 이벤트 원장에서 상태 재구성(동일입력→동일결과).
verify_chain: previous_hash 연결·event_hash 재계산 일치·전이 유효성 확인.
**읽기전용 — 어떤 것도 변경/집행하지 않음.**
"""
from __future__ import annotations

from jarvis.order_lifecycle import ledger
from jarvis.order_lifecycle.models import GENESIS, event_hash
from jarvis.order_lifecycle.state_machine import is_valid_transition


def replay_state(order_id: str) -> str | None:
    """이벤트를 순서대로 적용해 최종 상태 재구성. 무효전이 만나면 None."""
    evs = ledger.events_for(order_id)
    if not evs:
        return None
    state = None
    for i, e in enumerate(evs):
        prev, new = e["previous_state"], e["new_state"]
        if i == 0:
            if prev != "" or e["previous_hash"] != GENESIS:
                return None
        else:
            if prev != state:
                return None
            if not is_valid_transition(prev, new):
                return None
        state = new
    return state


def verify_chain(order_id: str) -> dict:
    """해시체인 무결성. 각 이벤트: 재계산 event_hash 일치 + previous_hash 연결."""
    evs = ledger.events_for(order_id)
    if not evs:
        return {"ok": True, "n": 0, "reason": "empty"}
    prev_hash = GENESIS
    for i, e in enumerate(evs):
        recomputed = event_hash(e["event_id"], e["order_id"], e["previous_state"],
                                e["new_state"], e["timestamp"], e.get("reason", ""),
                                e.get("source", "manager"), e["previous_hash"])
        if recomputed != e["event_hash"]:
            return {"ok": False, "broken_at": i, "reason": "event_hash_mismatch"}
        if e["previous_hash"] != prev_hash:
            return {"ok": False, "broken_at": i, "reason": "previous_hash_broken"}
        if i > 0 and not is_valid_transition(e["previous_state"], e["new_state"]):
            return {"ok": False, "broken_at": i, "reason": "invalid_transition"}
        prev_hash = e["event_hash"]
    return {"ok": True, "n": len(evs), "reason": "chain_intact"}


def verify_all() -> dict:
    """모든 주문 체인 무결성 요약."""
    orders = sorted({e.get("order_id") for e in ledger.read_events()})
    results = {oid: verify_chain(oid) for oid in orders}
    return {"orders": len(orders), "all_ok": all(r["ok"] for r in results.values()),
            "results": results}
