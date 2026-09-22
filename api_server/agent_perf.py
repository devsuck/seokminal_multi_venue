"""Per-agent performance ledger derived from recorded cycle fills.

Each cycle may carry a ``fills`` list ({symbol, side, qty, price} each) when
the agent executed one or more orders that tick (an exit and a same-cycle
entry are common). Older rows only carry the legacy singular ``fill``/
``fill_symbol`` pair — still read for history. This module FIFO-matches those
fills per symbol to produce realized PnL, open positions (qty + average
cost), and a trade log that keeps the *reason* (the cycle's note) for every
entry — so the dashboard can show why each buy/sell happened. Pure
functions: no network, fully testable. Unrealized PnL is layered on by the
caller, which supplies current prices.
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


def _extract_fills(cycle: dict) -> list[dict]:
    fills = cycle.get("fills")
    if isinstance(fills, list):
        out = []
        for f in fills:
            if not isinstance(f, dict):
                continue
            side = str(f.get("side", "")).lower()
            symbol = f.get("symbol") or cycle.get("symbol") or "?"
            try:
                qty = float(f.get("qty", 0))
                price = float(f.get("price", 0))
            except (TypeError, ValueError):
                continue
            if side not in ("buy", "sell") or qty <= 0 or price <= 0:
                continue
            out.append({"side": side, "qty": qty, "price": price, "symbol": symbol})
        return out

    # legacy rows: singular fill/fill_symbol, no fills list.
    fill = cycle.get("fill")
    if not isinstance(fill, dict):
        return []
    side = str(fill.get("side", "")).lower()
    try:
        qty = float(fill.get("qty", 0))
        price = float(fill.get("price", 0))
    except (TypeError, ValueError):
        return []
    if side not in ("buy", "sell") or qty <= 0 or price <= 0:
        return []
    symbol = cycle.get("fill_symbol") or cycle.get("symbol") or "?"
    return [{"side": side, "qty": qty, "price": price, "symbol": symbol}]


def compute_performance(cycles: list[dict]) -> Performance:
    """FIFO-match fills across cycles (oldest first) into a Performance summary."""
    lots: dict[str, deque[_Lot]] = {}
    perf = Performance()

    for cycle in cycles:
        reason = cycle.get("note") or cycle.get("next_trigger") or ""
        for fill in _extract_fills(cycle):
            symbol, side, qty, price = fill["symbol"], fill["side"], fill["qty"], fill["price"]
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
            signed_qty = qty if side == "buy" else -qty
            remaining, realized = abs(signed_qty), 0.0
            # 반대 방향 lot부터 FIFO로 정산 — sell은 기존 롱을 청산, buy는 기존 숏을 커버.
            # book이 비어있거나 같은 방향이면 루프 안 돌고 remaining이 그대로 남아 아래서
            # 새 lot(양수=롱 또는 음수=숏)으로 적립됨 — sell-to-open이 book 비었다고
            # realized=0으로 사라지지 않고 숏 lot으로 추적됨(order_pnl.py와 동일 버그,
            # 회귀: Fork D Finding 2 / Fork C Finding 6 — 같은 근본원인의 독립 구현체).
            while remaining > 1e-9 and book and (book[0].qty > 0) != (signed_qty > 0):
                lot = book[0]
                take = min(remaining, abs(lot.qty))
                if side == "sell":
                    realized += (price - lot.price) * take
                else:
                    realized += (lot.price - price) * take
                lot.qty += take if lot.qty < 0 else -take
                remaining -= take
                if abs(lot.qty) <= 1e-9:
                    book.popleft()
            matched = abs(signed_qty) - remaining
            if remaining > 1e-9:
                book.append(_Lot(qty=remaining if side == "buy" else -remaining, price=price))
            if matched > 1e-9:
                perf.realized_pnl += realized
                trade["realized_pnl"] = round(realized, 4)

            perf.trades.append(trade)

    # Snapshot open positions from remaining lots.
    for symbol, book in lots.items():
        total_qty = sum(l.qty for l in book)
        if abs(total_qty) <= 1e-9:  # 숏은 total_qty가 음수라 <= 1e-9 스킵 조건에 항상 걸림
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
