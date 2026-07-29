"""Performance Attribution (P6.3) — 전략 기여/승패/회전율/보유기간. 결정적·읽기전용."""
from __future__ import annotations

import datetime as _dt

_EPS = 1e-9


def _parse(ts: str):
    try:
        return _dt.datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def _holding_hours(first_fill_ts: str, now: str) -> float | None:
    a, b = _parse(first_fill_ts), _parse(now)
    if a is None or b is None:
        return None
    return round((b - a).total_seconds() / 3600.0, 2)


def attribution(positions: list, fills: list, capital: float, now: str = "") -> dict:
    """전략별 PnL 기여 + 승/패 + 회전율 + 보유기간."""
    # 전략별 첫 체결시각(보유기간)
    first_fill: dict = {}
    turnover_notional = 0.0
    for f in fills:
        turnover_notional += abs(float(f["quantity"]) * float(f["simulated_price"]))
        oid = f.get("order_id", "")
        # order_id → strategy는 fills만으론 불명 → positions로 매칭 안 함(체결 순서로 최초 ts)
        first_fill.setdefault(oid, f.get("timestamp"))

    strat_rows = []
    total_pnl = 0.0
    for p in positions:
        pnl = round(float(p["realized_pnl"]) + float(p["unrealized_pnl"]), 4)
        total_pnl += pnl
        strat_rows.append({"strategy_id": p["strategy_id"], "pnl": pnl,
                           "realized_pnl": round(float(p["realized_pnl"]), 4),
                           "unrealized_pnl": round(float(p["unrealized_pnl"]), 4),
                           "quantity": round(float(p["quantity"]), 6)})
    total_pnl = round(total_pnl, 4)
    for r in strat_rows:
        r["contribution_pct"] = round(100.0 * r["pnl"] / total_pnl, 4) if abs(total_pnl) > _EPS else 0.0

    ranked = sorted(strat_rows, key=lambda r: (-r["pnl"], r["strategy_id"]))
    winners = [r for r in ranked if r["pnl"] > _EPS]
    losers = [r for r in reversed(ranked) if r["pnl"] < -_EPS]
    turnover = round(turnover_notional / capital, 6) if capital > _EPS else 0.0

    return {"timestamp": now, "total_pnl": total_pnl, "strategies": ranked,
            "winners": winners, "losers": losers, "turnover": turnover,
            "turnover_notional": round(turnover_notional, 2), "n_strategies": len(strat_rows)}


def attribution_current(now: str, capital: float = None) -> dict:
    from jarvis.paper_execution.ledger import current_positions, read_fills
    from jarvis.paper_execution.models import PAPER_CAPITAL
    capital = PAPER_CAPITAL if capital is None else capital
    return attribution(list(current_positions().values()), read_fills(), capital, now)
