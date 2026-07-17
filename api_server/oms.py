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


def record_event(venue: str, result: dict, *, symbol: str | None = None, side: str | None = None) -> None:
    """Feed a broker response (place/cancel/status result) through the state
    machine. No-op if there's no order_id (order never reached the broker).

    ``symbol``/``side`` are only known at placement time (the request, not
    the broker response) — callers pass them on the place call and omit them
    on cancel/status calls; once set they stick. ``price`` is pulled from
    ``avg_fill_price``/``filled_avg_price`` when the broker response carries
    one (IB, Alpaca) — KIS never does, so KR orders stay priceless here and
    the PnL layer falls back to the originally requested price for those.
    Price/symbol/side are metadata, not state, so — unlike status/filled/
    remaining — they keep refining even after the order reaches a terminal
    state (a late status poll can be the first call that finally reports the
    real fill price)."""
    order_id = result.get("order_id")
    if not order_id:
        return
    order_id = str(order_id)
    key = (venue, order_id)
    filled = float(result.get("filled") or 0.0)
    remaining = float(result.get("remaining") or 0.0)
    status = _derive_status(result.get("status"), filled, remaining)
    price = result.get("avg_fill_price")
    if price is None:
        price = result.get("filled_avg_price")
    now = _dt.datetime.now(_dt.UTC).isoformat()

    entry = _orders.get(key)
    already_terminal = entry is not None and entry["status"] in _TERMINAL

    if entry is None:
        entry = {
            "venue": venue,
            "order_id": order_id,
            "status": status,
            "filled": filled,
            "remaining": remaining,
            "symbol": symbol,
            "side": side,
            "price": price,
            "created_ts": now,
            "updated_ts": now,
            "history": [],
        }
        _orders[key] = entry
    else:
        if symbol is not None:
            entry["symbol"] = symbol
        if side is not None:
            entry["side"] = side
        if price is not None:
            entry["price"] = price

    if already_terminal:
        # 종결 상태 이후 들어오는 업데이트는 상태/체결량을 덮어쓰지 않음(브로커 쪽
        # 지연/모순 응답 방어) — history에만 남겨서 무슨 일이 있었는지는 보이게 한다.
        entry["history"].append({"ts": now, "status": status, "filled": filled, "remaining": remaining})
        return

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
