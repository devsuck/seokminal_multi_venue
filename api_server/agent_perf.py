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

from api_server import schema_guard


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

    n_fill_bearing = 0

    for cycle in cycles:
        reason = cycle.get("note") or cycle.get("next_trigger") or ""
        if schema_guard.has_fill_payload(cycle):
            n_fill_bearing += 1
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

    # 체결 페이로드는 쌓였는데 한 건도 매칭 안 됐으면 스키마 드리프트다.
    # (2026-08 `fill` vs `fills` 사고가 이 조합으로 -94.64%를 만들었다.)
    schema_guard.detect_drift(
        "agent_perf.compute_performance",
        n_evidence=n_fill_bearing,
        n_extracted=len(perf.trades),
        hint="사이클에 fills/fill 페이로드가 있는데 _extract_fills가 전부 버렸다 — 체결 스키마 확인",
    )

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
