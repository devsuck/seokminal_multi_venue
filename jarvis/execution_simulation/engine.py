"""Execution Simulation Engine (P7.5) — READY 결정 → 가상 체결. **집행 아님.**

SimulationEngine.simulate(intent, decision, price_provider, ...) →
  ExecutionSimulationReport(SimulatedOrder + SimulatedFill).
**SimulatedOrder는 주문이 아니다 — 가상 체결 레코드일 뿐.** 감사 산출물만.

규칙:
  - READY ExecutionDecision에서만 시작.
  - 가격은 주입된 price_provider만 사용(브로커/라이브 직접호출 없음).
  - BUY: quantity > 0.
  - SELL: quantity <= 현재 '시뮬' 포지션(시뮬 원장 기반, 페이퍼/실포지션 무관).
  - ideal fill · slippage model · fee model 지원.

**MUST NOT: 집행 게이트웨이 import·브로커 호출·페이퍼/포트폴리오/리스크/
레지스트리 변경.** 결정적·append-only·재현가능.
"""
from __future__ import annotations

from jarvis.execution_simulation import ledger
from jarvis.execution_simulation.models import (
    BLOCKED,
    ExecutionSimulationReport,
    REJECTED,
    SIMULATED,
    SimulatedFill,
    SimulatedOrder,
    apply_slippage,
    compute_fees,
    report_hash,
    simulation_id,
)

_EPS = 1e-9
_READY = "READY"


class SimulationEngine:
    """가상 체결 시뮬레이터. 주문/집행/자본 이동 없음."""

    def simulate(self, intent, decision, price_provider, now: str, *,
                 quantity: float | None = None, slippage_bps: float = 0.0,
                 fee_bps: float = 0.0, commit: bool = False) -> ExecutionSimulationReport | None:
        sid = simulation_id(intent.intent_id, now)

        # 중복 방지: 동일 simulation_id 커밋 재시도 → None
        if commit and ledger.simulation_exists(sid):
            return None

        # 1) READY 결정에서만 시작
        status_ready = getattr(decision, "status", None) == _READY
        if not status_ready:
            return self._reject(sid, "decision_not_ready", commit,
                                {"slippage_bps": slippage_bps, "fee_bps": fee_bps})

        # 2) 가격은 주입 provider만
        ref = price_provider(intent.symbol, now)
        if ref is None:
            return self._block(sid, "missing_price", commit,
                               {"slippage_bps": slippage_bps, "fee_bps": fee_bps,
                                "price_source": "injected"})
        ref = float(ref)

        qty = float(quantity if quantity is not None else intent.quantity)
        side = intent.side

        # 3) 수량 검증
        if side == "BUY" and qty <= _EPS:
            return self._reject(sid, "invalid_buy_quantity", commit,
                                {"slippage_bps": slippage_bps, "fee_bps": fee_bps})
        if side == "SELL":
            held = ledger.simulated_position(intent.symbol)
            if qty > held + _EPS:
                return self._reject(sid, "invalid_sell_quantity", commit,
                                    {"slippage_bps": slippage_bps, "fee_bps": fee_bps,
                                     "simulated_position": held})

        # ── 가상 체결 계산(ideal + slippage + fee) ──
        fill_price = apply_slippage(ref, side, slippage_bps)
        slip = round(fill_price - ref, 8)
        fees = compute_fees(fill_price, qty, fee_bps)

        order = SimulatedOrder(simulation_id=sid, intent_id=intent.intent_id,
                               symbol=intent.symbol, side=side, quantity=round(qty, 8),
                               reference_price=round(ref, 8), created_at=now)
        fill = SimulatedFill(simulation_id=sid, fill_price=fill_price,
                             filled_quantity=round(qty, 8), slippage=slip, fees=fees,
                             timestamp=now)
        assumptions = {"slippage_bps": slippage_bps, "fee_bps": fee_bps,
                       "price_source": "injected", "reference_price": round(ref, 8),
                       "model": "ideal+slippage+fee", "note": "가상 체결 — 주문/집행 아님"}
        h = report_hash(sid, SIMULATED, order.to_dict(), fill.to_dict(), assumptions)
        report = ExecutionSimulationReport(simulation_id=sid, status=SIMULATED,
                                           order=order.to_dict(), fill=fill.to_dict(),
                                           assumptions=assumptions, hash=h)
        if commit:
            ledger.append_order(order.to_dict())
            ledger.append_fill(fill.to_dict())
            ledger.append_report(report.to_dict())
        return report

    # ── 거부/차단 리포트(order/fill 없음) ──
    def _reject(self, sid: str, reason: str, commit: bool, assumptions: dict) -> ExecutionSimulationReport:
        return self._terminal(sid, REJECTED, reason, commit, assumptions)

    def _block(self, sid: str, reason: str, commit: bool, assumptions: dict) -> ExecutionSimulationReport:
        return self._terminal(sid, BLOCKED, reason, commit, assumptions)

    def _terminal(self, sid: str, status: str, reason: str, commit: bool,
                  assumptions: dict) -> ExecutionSimulationReport:
        a = {**assumptions, "reason": reason}
        h = report_hash(sid, status, None, None, a)
        report = ExecutionSimulationReport(simulation_id=sid, status=status, order=None,
                                           fill=None, assumptions=a, hash=h)
        if commit:
            ledger.append_report(report.to_dict())
        return report
