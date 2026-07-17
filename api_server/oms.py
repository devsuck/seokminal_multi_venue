"""In-process order state machine — derives canonical order status from raw
broker responses and tracks fill progression per order.

Complements the durable JSONL trail (`order_audit.py`): that file is the
append-only event record; this module is a live, in-memory *current-state*
view built from the same place/cancel/status responses as they occur during
this process's lifetime. Not persisted — a restart loses tracked state, same
trade-off as `idempotency.py` (only needs to survive as long as the process
does; the JSONL audit trail is the thing that must survive a restart).
"""
from __future__ import annotations

import datetime as _dt

_TERMINAL = {"FILLED", "CANCELLED", "REJECTED"}
_CANCELLED_RAW = {"CANCELLED", "APICANCELLED"}
_REJECTED_RAW = {"REJECTED", "INACTIVE"}

_orders: dict[tuple[str, str], dict] = {}


def _derive_status(raw_status: str | None, filled: float, remaining: float) -> str:
    s = (raw_status or "").strip().upper()
    if s in _CANCELLED_RAW:
        return "CANCELLED"
    if s in _REJECTED_RAW:
        return "REJECTED"
    if filled and not remaining:
        return "FILLED"
    if filled and remaining:
        return "PARTIALLY_FILLED"
    return "OPEN"


def record_event(venue: str, result: dict) -> None:
    """Feed a broker response (place/cancel/status result) through the state
    machine. No-op if there's no order_id (order never reached the broker)."""
    order_id = result.get("order_id")
    if not order_id:
        return
    order_id = str(order_id)
    key = (venue, order_id)
    filled = float(result.get("filled") or 0.0)
    remaining = float(result.get("remaining") or 0.0)
    status = _derive_status(result.get("status"), filled, remaining)
    now = _dt.datetime.now(_dt.UTC).isoformat()

    entry = _orders.get(key)
    if entry is not None and entry["status"] in _TERMINAL:
        # 종결 상태 이후 들어오는 업데이트는 상태를 덮어쓰지 않음(브로커 쪽 지연/
        # 모순 응답 방어) — history에만 남겨서 무슨 일이 있었는지는 보이게 한다.
        entry["history"].append({"ts": now, "status": status, "filled": filled, "remaining": remaining})
        return

    if entry is None:
        entry = {
            "venue": venue,
            "order_id": order_id,
            "status": status,
            "filled": filled,
            "remaining": remaining,
            "created_ts": now,
            "updated_ts": now,
            "history": [],
        }
        _orders[key] = entry

    entry["status"] = status
    entry["filled"] = filled
    entry["remaining"] = remaining
    entry["updated_ts"] = now
    entry["history"].append({"ts": now, "status": status, "filled": filled, "remaining": remaining})


def get_order(venue: str, order_id: str) -> dict | None:
    return _orders.get((venue, str(order_id)))


def list_orders(venue: str | None = None, status: str | None = None, limit: int = 200) -> list[dict]:
    """Most-recently-updated first."""
    items = list(_orders.values())
    if venue:
        items = [o for o in items if o["venue"] == venue]
    if status:
        items = [o for o in items if o["status"] == status.upper()]
    items.sort(key=lambda o: o["updated_ts"], reverse=True)
    return items[:limit]
