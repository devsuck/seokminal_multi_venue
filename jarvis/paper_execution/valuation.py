"""Portfolio Valuation Engine (P6.3) — mark-to-market NAV/노출/PnL/drawdown. 결정적.

입력: PaperPosition + PriceSnapshot(주입). 출력: PortfolioSnapshot.
회계: cash = capital - deployed_cost + realized; NAV = cash + Σ(qty×mark).
paper_portfolio.jsonl append-only(재구축 가능).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

from jarvis.config import state_path
from jarvis.paper_execution.market_data import FlatMarkProvider

_LEDGER = "paper_portfolio.jsonl"
_EPS = 1e-9


@dataclass(frozen=True)
class PortfolioSnapshot:
    timestamp: str
    nav: float
    cash_balance: float
    gross_exposure: float
    net_exposure: float
    unrealized_pnl: float
    realized_pnl: float
    daily_return: float
    drawdown: float
    positions: list = field(default_factory=list)
    stale_symbols: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def valuate(positions: list, provider, capital: float, now: str,
            prev_nav: float | None = None, peak_nav: float | None = None) -> PortfolioSnapshot:
    deployed_cost = 0.0
    realized = 0.0
    mkt_value = 0.0
    unreal = 0.0
    stale: list[str] = []
    marked: list[dict] = []
    for p in positions:
        sid = p["strategy_id"]
        qty = float(p["quantity"])
        avg = float(p["average_price"])
        realized += float(p["realized_pnl"])
        deployed_cost += qty * avg
        snap = provider.get(sid, now)
        if snap is None:
            stale.append(sid)
            mark = avg                      # 결측 → 평단 flat mark(정직)
        else:
            mark = snap.price
        mv = qty * mark
        mkt_value += mv
        unreal += qty * (mark - avg)
        marked.append({"strategy_id": sid, "quantity": round(qty, 8),
                       "average_price": round(avg, 6), "mark_price": round(mark, 6),
                       "market_value": round(mv, 4), "unrealized_pnl": round(qty * (mark - avg), 4),
                       "realized_pnl": round(float(p["realized_pnl"]), 4)})

    cash = capital - deployed_cost + realized
    nav = cash + mkt_value
    gross = round(sum(abs(m["market_value"]) for m in marked) / nav, 6) if nav > _EPS else 0.0
    net = round(sum(m["market_value"] for m in marked) / nav, 6) if nav > _EPS else 0.0
    daily_return = round((nav - prev_nav) / prev_nav, 8) if prev_nav and prev_nav > _EPS else 0.0
    peak = max(peak_nav or nav, nav)
    drawdown = round((peak - nav) / peak, 8) if peak > _EPS else 0.0

    return PortfolioSnapshot(
        timestamp=now, nav=round(nav, 4), cash_balance=round(cash, 4),
        gross_exposure=gross, net_exposure=net, unrealized_pnl=round(unreal, 4),
        realized_pnl=round(realized, 4), daily_return=daily_return, drawdown=drawdown,
        positions=marked, stale_symbols=sorted(stale))


# ── append-only NAV 원장 ──
def read_valuations() -> list[dict]:
    p = state_path(_LEDGER)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _history_nav() -> tuple[float | None, float | None]:
    """(prev_nav, peak_nav) — 이력에서."""
    rows = read_valuations()
    if not rows:
        return None, None
    navs = [float(r["nav"]) for r in rows]
    return navs[-1], max(navs)


def _default_provider(positions: list, now: str) -> FlatMarkProvider:
    return FlatMarkProvider({p["strategy_id"]: p["average_price"] for p in positions}, now)


def valuate_current(now: str, provider=None, capital: float = None, commit: bool = False,
                    principal=None) -> PortfolioSnapshot:
    from jarvis.paper_execution.ledger import current_positions
    from jarvis.paper_execution.models import PAPER_CAPITAL
    capital = PAPER_CAPITAL if capital is None else capital
    positions = list(current_positions().values())
    provider = provider or _default_provider(positions, now)
    prev_nav, peak_nav = _history_nav()
    snap = valuate(positions, provider, capital, now, prev_nav, peak_nav)
    if commit:
        _commit(snap, principal)
    return snap


def _commit(snap: PortfolioSnapshot, principal) -> None:
    from jarvis.agents import PAPER_EXECUTION_AGENT
    from jarvis.audit import record
    from jarvis.permissions import require
    principal = principal or PAPER_EXECUTION_AGENT
    require(principal, "record_paper_valuation", snap.timestamp)
    p = state_path(_LEDGER)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    row = {"timestamp": snap.timestamp, "nav": snap.nav, "gross_exposure": snap.gross_exposure,
           "net_exposure": snap.net_exposure, "unrealized_pnl": snap.unrealized_pnl,
           "realized_pnl": snap.realized_pnl, "drawdown": snap.drawdown,
           "positions": snap.positions, "capital": "paper"}
    with open(p, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    record({"layer": "paper_execution", "action": "record_paper_valuation",
            "nav": snap.nav, "drawdown": snap.drawdown, "gross_exposure": snap.gross_exposure,
            "result": "recorded"})
