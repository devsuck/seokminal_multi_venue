"""Per-agent performance ledger derived from recorded cycle fills.

Each cycle may carry a ``fill`` object ({side, qty, price}) when the agent
actually executed an order. This module FIFO-matches those fills per symbol to
produce realized PnL, open positions (qty + average cost), and a trade log that
keeps the *reason* (the cycle's note) for every entry — so the dashboard can
show why each buy/sell happened. Pure functions: no network, fully testable.
Unrealized PnL is layered on by the caller, which supplies current prices.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class _Lot:
    qty: float
    price: float


@dataclass
class Performance:
    trades: list[dict] = field(default_factory=list)
    realized_pnl: float = 0.0
    open_positions: list[dict] = field(default_factory=list)  # {symbol, qty, avg_price}
    invested: float = 0.0  # cost basis currently tied up in open positions


def _extract_fill(cycle: dict) -> dict | None:
    fill = cycle.get("fill")
    if not isinstance(fill, dict):
        return None
    side = str(fill.get("side", "")).lower()
    try:
        qty = float(fill.get("qty", 0))
        price = float(fill.get("price", 0))
    except (TypeError, ValueError):
        return None
    if side not in ("buy", "sell") or qty <= 0 or price <= 0:
        return None
    return {"side": side, "qty": qty, "price": price}


def compute_performance(cycles: list[dict]) -> Performance:
    """FIFO-match fills across cycles (oldest first) into a Performance summary."""
    lots: dict[str, deque[_Lot]] = {}
    perf = Performance()

    for cycle in cycles:
        fill = _extract_fill(cycle)
        if fill is None:
            continue
        symbol = cycle.get("symbol") or "?"
        side, qty, price = fill["side"], fill["qty"], fill["price"]
        reason = cycle.get("note") or cycle.get("next_trigger") or ""
        trade = {
            "ts": cycle.get("ts"),
            "cycle": cycle.get("cycle"),
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "reason": reason,
            "realized_pnl": None,
        }

        book = lots.setdefault(symbol, deque())
        if side == "buy":
            book.append(_Lot(qty=qty, price=price))
        else:  # sell — realize against oldest lots (FIFO)
            remaining = qty
            realized = 0.0
            while remaining > 1e-9 and book:
                lot = book[0]
                take = min(remaining, lot.qty)
                realized += (price - lot.price) * take
                lot.qty -= take
                remaining -= take
                if lot.qty <= 1e-9:
                    book.popleft()
            perf.realized_pnl += realized
            trade["realized_pnl"] = round(realized, 4)

        perf.trades.append(trade)

    # Snapshot open positions from remaining lots.
    for symbol, book in lots.items():
        total_qty = sum(l.qty for l in book)
        if total_qty <= 1e-9:
            continue
        cost = sum(l.qty * l.price for l in book)
        avg = cost / total_qty
        perf.open_positions.append({
            "symbol": symbol,
            "qty": round(total_qty, 6),
            "avg_price": round(avg, 4),
        })
        perf.invested += cost

    perf.realized_pnl = round(perf.realized_pnl, 4)
    perf.invested = round(perf.invested, 4)
    return perf
