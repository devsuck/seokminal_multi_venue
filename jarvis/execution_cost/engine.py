"""Execution Cost Accounting Engine (P8.4) — 집행비용 회계. **집행 아님.**

ExecutionCostInput + CostRates → CostComponents → ExecutionCostReport →
append-only 해시체인 원장. 기대비용 대비 실현비용 비교(EXPECTED/WARNING/FAILED).

**MUST NOT: 주문 제출·브로커 write·집행 게이트웨이 호출·포지션/포트폴리오/리스크 변경.**
결정적·재현가능. BUY/SELL·부분체결·다중체결 집계 지원.
"""
from __future__ import annotations

from jarvis.execution_cost import ledger
from jarvis.execution_cost.calculator import calculate, cost_bps, gross_value
from jarvis.execution_cost.models import (
    CostRates,
    CostThresholds,
    EXPECTED,
    ExecutionCostInput,
    ExecutionCostReport,
    FAILED,
    GENESIS,
    WARNING,
    input_hash,
    report_hash,
    report_id,
)

_EPS = 1e-12


def cost_input_from_fills(order_id: str, symbol: str, side: str, expected_price: float,
                          fills: list, timestamp: str = "") -> ExecutionCostInput:
    """다중/부분 체결 → 수량가중평균가로 집계한 ExecutionCostInput."""
    ded, seen = [], set()
    for f in fills:
        d = f.to_dict() if hasattr(f, "to_dict") else f
        fid = d.get("fill_id")
        if fid in seen:
            continue
        seen.add(fid)
        ded.append(d)
    tq = sum(float(f.get("quantity", 0.0)) for f in ded)
    if abs(tq) > _EPS:
        wap = sum(float(f.get("quantity", 0.0)) * float(f.get("fill_price", 0.0))
                  for f in ded) / tq
    else:
        wap = 0.0
    ts = timestamp or max((f.get("timestamp", "") for f in ded), default="")
    gross = gross_value(tq, wap)
    return ExecutionCostInput(order_id=order_id, symbol=symbol, side=side, quantity=round(tq, 8),
                              expected_price=float(expected_price), fill_price=round(wap, 8),
                              gross_value=gross, timestamp=ts)


class CostAccountingEngine:
    def __init__(self, rates: CostRates | None = None,
                 thresholds: CostThresholds | None = None) -> None:
        self.rates = rates or CostRates()
        self.t = thresholds or CostThresholds()

    def calculate(self, inp: ExecutionCostInput, now: str = "", *,
                  mid_price: float | None = None, commit: bool = False) -> ExecutionCostReport:
        d = inp.to_dict() if hasattr(inp, "to_dict") else inp
        comps = calculate(inp, self.rates, mid_price)
        gross = float(d["gross_value"])
        cbps = cost_bps(comps.total_cost, gross)
        exp_bps = self.t.expected_cost_bps
        variance = round(cbps - exp_bps, 8)

        if cbps <= exp_bps * self.t.warning_multiplier + _EPS:
            status = EXPECTED
        elif cbps <= exp_bps * self.t.failure_multiplier + _EPS:
            status = WARNING
        else:
            status = FAILED

        ih = input_hash(d, {"commission_rate": self.rates.commission_rate,
                            "exchange_fee_rate": self.rates.exchange_fee_rate,
                            "fx_rate_cost": self.rates.fx_rate_cost,
                            "market_impact_rate": self.rates.market_impact_rate},
                        mid_price if mid_price is not None else float(d["expected_price"]),
                        {"expected_cost_bps": exp_bps, "warning_multiplier": self.t.warning_multiplier,
                         "failure_multiplier": self.t.failure_multiplier})
        rid = report_id(d["order_id"], ih)
        rh = report_hash(rid, d["order_id"], comps.to_dict(), comps.total_cost, cbps,
                         exp_bps, variance, status, ih)
        report = ExecutionCostReport(
            report_id=rid, order_id=d["order_id"], gross_value=gross,
            cost_components=comps.to_dict(), total_cost=comps.total_cost, cost_bps=cbps,
            expected_cost_bps=exp_bps, variance_bps=variance, status=status,
            input_hash=ih, report_hash=rh, timestamp=now)
        if commit and not ledger.event_exists(rid):
            head = ledger.chain_head()
            prev_hash = head["cost_hash"] if head else GENESIS
            ledger.append_event({"event_id": rid, "order_id": d["order_id"], "cost_hash": rh,
                                 "previous_hash": prev_hash, "status": status, "timestamp": now})
        return report
