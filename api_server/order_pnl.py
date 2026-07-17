"""Cross-venue realized PnL — FIFO-matches OMS-tracked fills per (venue, symbol).

Sourced from oms.py's live order state, not order_audit.jsonl: the audit log
only records the snapshot returned by place_order(), which for KIS/IB is
filled=0 (fills confirm asynchronously, not at submission) — oms.py is the
only place that reflects post-submission fills, fed by the cancel/status-poll
calls that follow. KIS never reports a fill price at all, so KR fills fall
back to the originally requested price (from the audit log's request payload,
via ``price_fallback_from_audit``) and are tagged price_source="estimated" —
never presented as a confirmed broker fill price.

Fee/slippage is not broker-reported anywhere in this codebase either; it's an
operator-supplied bps estimate (``fee_model.py``), applied symmetrically to
both legs of every matched trade. Defaults to 0 (no adjustment).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from api_server import fee_model


@dataclass
class _Lot:
    qty: float
    price: float


@dataclass
class VenuePnL:
    venue: str
    trades: list[dict] = field(default_factory=list)
    gross_realized_pnl: float = 0.0
    fees: float = 0.0
    net_realized_pnl: float = 0.0
    open_positions: list[dict] = field(default_factory=list)  # {symbol, qty, avg_price}
    unpriced_fills: int = 0  # filled orders with no known price at all — excluded from PnL


def price_fallback_from_audit(audit_entries: list[dict]) -> dict[tuple[str, str], float]:
    """(venue, order_id) -> originally requested price, from order_audit
    entries. Only meaningful for venues whose broker never reports a real
    fill price (KIS); harmless to build for all venues since OMS's own price
    always wins when present."""
    out: dict[tuple[str, str], float] = {}
    for e in audit_entries:
        result, request, venue = e.get("result"), e.get("request"), e.get("venue")
        if not result or not request or not venue:
            continue
        order_id = result.get("order_id") or result.get("id")
        if order_id is None:
            continue
        price = request.get("price")
        if price is None:
            price = request.get("limit_price")
        if price is None:
            continue
        out[(venue, str(order_id))] = float(price)
    return out


def compute_realized_pnl(
    orders: list[dict],
    price_fallback: dict[tuple[str, str], float] | None = None,
) -> list[VenuePnL]:
    """``orders`` is oms.list_orders()-shaped (must include filled/symbol/
    side/price/order_id/created_ts/updated_ts)."""
    price_fallback = price_fallback or {}
    by_venue: dict[str, list[dict]] = {}
    for o in orders:
        if o["filled"] <= 0:
            continue
        by_venue.setdefault(o["venue"], []).append(o)

    results = []
    for venue, venue_orders in by_venue.items():
        venue_orders.sort(key=lambda o: o["created_ts"])
        bps = fee_model.fee_bps(venue)
        lots: dict[str, deque[_Lot]] = {}
        perf = VenuePnL(venue=venue)

        for o in venue_orders:
            price = o.get("price")
            price_source = "broker"
            if price is None:
                price = price_fallback.get((venue, o["order_id"]))
                price_source = "estimated"
            if price is None:
                perf.unpriced_fills += 1
                continue

            side = (o.get("side") or "").lower()
            if side not in ("buy", "sell"):
                continue
            symbol = o.get("symbol") or "?"
            qty = o["filled"]
            perf.fees += price * qty * bps / 10_000.0

            trade = {
                "order_id": o["order_id"], "symbol": symbol, "side": side,
                "qty": qty, "price": price, "price_source": price_source,
                "ts": o["updated_ts"], "realized_pnl": None,
            }

            book = lots.setdefault(symbol, deque())
            if side == "buy":
                book.append(_Lot(qty=qty, price=price))
            else:  # sell — realize against oldest lots (FIFO)
                remaining, realized = qty, 0.0
                while remaining > 1e-9 and book:
                    lot = book[0]
                    take = min(remaining, lot.qty)
                    realized += (price - lot.price) * take
                    lot.qty -= take
                    remaining -= take
                    if lot.qty <= 1e-9:
                        book.popleft()
                perf.gross_realized_pnl += realized
                trade["realized_pnl"] = round(realized, 4)

            perf.trades.append(trade)

        for symbol, book in lots.items():
            total_qty = sum(l.qty for l in book)
            if total_qty <= 1e-9:
                continue
            cost = sum(l.qty * l.price for l in book)
            perf.open_positions.append({
                "symbol": symbol, "qty": round(total_qty, 6), "avg_price": round(cost / total_qty, 4),
            })

        perf.gross_realized_pnl = round(perf.gross_realized_pnl, 4)
        perf.fees = round(perf.fees, 4)
        perf.net_realized_pnl = round(perf.gross_realized_pnl - perf.fees, 4)
        results.append(perf)

    return results
