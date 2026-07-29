"""Paper Execution Engine (P6.2) — APPROVED+ALLOW 제안 → 시뮬 체결. 결정적.

규칙: APPROVED+ALLOW만 실행. BLOCK/pending → 0 order. 게이트웨이 무호출·브로커 없음·
외부 부작용 없음. 중복 실행 방지(같은 제안 두 번 X). dry-run=계산만, commit=원장+감사.
"""
from __future__ import annotations

from jarvis.paper_execution import ledger
from jarvis.paper_execution.models import (
    PAPER_CAPITAL,
    PaperExecutionReport,
    PaperFill,
    PaperOrder,
    apply_fill,
    execution_id,
    fill_id,
    order_id,
    side_for,
    target_weight_of,
    zero_position,
)

_EPS = 1e-9


def _pnl_summary(positions: dict, capital: float) -> tuple[dict, float]:
    realized = round(sum(p["realized_pnl"] for p in positions.values()), 4)
    unreal = round(sum(p["unrealized_pnl"] for p in positions.values()), 4)
    total = round(realized + unreal, 4)
    return {"realized": realized, "unrealized": unreal, "total": total}, round(capital + total, 4)


class PaperExecutionEngine:
    def __init__(self, capital: float = PAPER_CAPITAL) -> None:
        self.capital = capital

    def _empty(self, pid: str, ts: str, note: str) -> PaperExecutionReport:
        positions = ledger.current_positions()
        pnl, pv = _pnl_summary(positions, self.capital)
        return PaperExecutionReport(
            execution_id=execution_id(pid), proposal_id=pid, orders_created=0, fills_created=0,
            positions_after=list(positions.values()), portfolio_value=pv, pnl_summary=pnl,
            timestamp=ts, note=note)

    def execute_proposal(self, proposal: dict, approved: bool, gate_decision: dict | None,
                         price_provider, now: str, ts: str = "", commit: bool = False,
                         principal=None) -> PaperExecutionReport:
        ts = ts or now
        pid = proposal.get("proposal_id", "")

        # ── 게이트 우회 금지: APPROVED + ALLOW만 ──
        if not approved:
            return self._empty(pid, ts, "not_approved")
        if not gate_decision or gate_decision.get("decision") != "ALLOW":
            return self._empty(pid, ts, "gate_not_allow")
        if pid in ledger.executed_proposal_ids():
            return self._empty(pid, ts, "already_executed")

        strat = proposal.get("strategy", "")
        price = price_provider(strat, now)
        if price is None or price <= 0:
            return self._empty(pid, ts, "no_price")

        tw = target_weight_of(proposal)
        cur_row = ledger.current_positions().get(strat)
        cur = _pos_from_row(cur_row) if cur_row else zero_position(strat)
        target_qty = tw * self.capital / price
        delta = target_qty - cur.quantity
        side = side_for(delta)
        qty = round(abs(delta), 8)

        oid = order_id(pid, strat)
        order = PaperOrder(order_id=oid, proposal_id=pid, strategy_id=strat, side=side,
                           target_weight=round(tw, 6), quantity=qty if side != "HOLD" else 0.0,
                           created_at=ts)
        new_pos = apply_fill(cur, side, qty, price) if side != "HOLD" else cur
        fill = None
        if side != "HOLD":
            fill = PaperFill(fill_id=fill_id(oid), order_id=oid, simulated_price=round(price, 6),
                             quantity=qty, timestamp=ts)

        positions = {s: r for s, r in ledger.current_positions().items()}
        positions[strat] = new_pos.to_dict()
        pnl, pv = _pnl_summary(positions, self.capital)
        report = PaperExecutionReport(
            execution_id=execution_id(pid), proposal_id=pid,
            orders_created=(0 if side == "HOLD" else 1),
            fills_created=(0 if side == "HOLD" else 1),
            positions_after=list(positions.values()), portfolio_value=pv, pnl_summary=pnl,
            timestamp=ts, note=f"side={side}")

        if commit:
            self._commit(order, fill, new_pos, report, principal)
        return report

    def _commit(self, order, fill, new_pos, report, principal) -> None:
        from jarvis.agents import PAPER_EXECUTION_AGENT
        from jarvis.audit import record
        from jarvis.permissions import require
        principal = principal or PAPER_EXECUTION_AGENT
        require(principal, "execute_paper_order", report.proposal_id)
        ledger.append_order(order.to_dict())
        if fill is not None:
            ledger.append_fill(fill.to_dict())
        ledger.append_position(new_pos.to_dict())
        ledger.append_report(report.to_dict())
        record({"layer": "paper_execution", "action": "execute_paper_order",
                "proposal_id": report.proposal_id, "execution_id": report.execution_id,
                "side": order.side, "orders_created": report.orders_created,
                "realized_pnl": report.pnl_summary["realized"], "result": "simulated"})


def _pos_from_row(row: dict):
    from jarvis.paper_execution.models import PaperPosition
    return PaperPosition(row["strategy_id"], row["quantity"], row["average_price"],
                         row["market_value"], row["unrealized_pnl"], row["realized_pnl"])


def portfolio_status(capital: float = PAPER_CAPITAL) -> dict:
    positions = ledger.current_positions()
    pnl, pv = _pnl_summary(positions, capital)
    return {"positions": list(positions.values()), "portfolio_value": pv, "pnl_summary": pnl,
            "n_positions": len(positions)}
