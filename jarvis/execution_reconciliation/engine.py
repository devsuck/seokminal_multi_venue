"""Execution Reconciliation Engine (P7.6) — 집행 결과 검증. **집행 아님.**

ExecutionExpectation + ExecutionSimulationReport →
  [수량·가격·수수료·슬리피지·타이밍] → ExecutionValidationReport(PASS/WARNING/FAILED).
**주문/체결 생성 없음** — 이미 있는 (가상) 결과가 의도와 맞는지 검증만.

소유권 경계:
  ExecutionControl(P7.4)   집행 허용 여부 결정.
  ExecutionSimulation(P7.5) 가상 집행 생성.
  ExecutionReconciliation(P7.6) 집행 '결과'가 의도와 일치하는지 검증.  ← 본 모듈

**MUST NOT: 주문 생성·거래 집행·포지션 변경·브로커 호출·집행 게이트웨이 호출.**
결정적·append-only·재현가능. 시뮬 원장 읽기전용(변경 없음).
"""
from __future__ import annotations

from jarvis.execution_reconciliation import ledger
from jarvis.execution_reconciliation.models import (
    ExecutionExpectation,
    ExecutionValidationReport,
    FAILED,
    ValidationThresholds,
    grade,
    input_hash,
    max_status,
    seconds_between,
    validation_hash,
    validation_id,
)

_BPS = 10_000.0
_EPS = 1e-12
_SIMULATED = "SIMULATED"


def perfect_expectation(sim_report, intent_time: str) -> ExecutionExpectation:
    """시뮬 결과를 그대로 기대값으로 삼는 완전일치 기대(PASS 데모/검증용)."""
    d = sim_report.to_dict() if hasattr(sim_report, "to_dict") else sim_report
    o, f = d["order"], d["fill"]
    return ExecutionExpectation(
        intent_id=o["intent_id"], symbol=o["symbol"], side=o["side"],
        expected_quantity=float(f["filled_quantity"]), expected_price=float(f["fill_price"]),
        expected_fee=float(f["fees"]), timestamp=intent_time)


class ExecutionReconciliationEngine:
    def __init__(self, thresholds: ValidationThresholds | None = None) -> None:
        self.t = thresholds or ValidationThresholds()

    def validate(self, expectation: ExecutionExpectation, sim_report, now: str = "",
                 commit: bool = False) -> ExecutionValidationReport:
        d = sim_report.to_dict() if hasattr(sim_report, "to_dict") else (sim_report or {})
        exp = expectation.to_dict()
        ih = input_hash(exp, d or {})
        vid = validation_id(expectation.intent_id, ih)

        # ── 시뮬 결과 부재/미체결 → FAILED(차단) ──
        if not d or d.get("status") != _SIMULATED or not d.get("fill") or not d.get("order"):
            checks = [{"name": "simulation_present", "status": FAILED, "deviation": None,
                       "tolerance": None, "detail": "missing or non-SIMULATED report"}]
            return self._finish(vid, expectation.intent_id, FAILED, checks, {}, ih, now, commit,
                                reason="missing_simulation")

        fill, order = d["fill"], d["order"]
        assumptions = d.get("assumptions", {}) or {}
        actual_qty = float(fill["filled_quantity"])
        fill_price = float(fill["fill_price"])
        actual_fee = float(fill["fees"])
        realized_slip = float(fill.get("slippage", 0.0))
        ref = float(assumptions.get("reference_price", order.get("reference_price", fill_price)))
        assumed_slip_bps = float(assumptions.get("slippage_bps", 0.0))

        t = self.t
        # 1) 수량
        qdev = round(abs(expectation.expected_quantity - actual_qty), 10)
        qstat = grade(qdev, t.quantity_tolerance, t.fail_multiplier)
        # 2) 가격(기대가 대비 bps)
        base_p = abs(expectation.expected_price) or _EPS
        pdev = round(abs(expectation.expected_price - fill_price) / base_p * _BPS, 8)
        pstat = grade(pdev, t.price_tolerance_bps, t.fail_multiplier)
        # 3) 수수료(명목 대비 bps)
        notional = abs(expectation.expected_price * expectation.expected_quantity) or _EPS
        fdev = round(abs(expectation.expected_fee - actual_fee) / notional * _BPS, 8)
        fstat = grade(fdev, t.fee_tolerance_bps, t.fail_multiplier)
        # 4) 슬리피지(가정 vs 실현, bps of reference)
        realized_slip_bps = abs(realized_slip) / (abs(ref) or _EPS) * _BPS
        sdev = round(abs(assumed_slip_bps - realized_slip_bps), 8)
        sstat = grade(sdev, t.price_tolerance_bps, t.fail_multiplier)
        # 5) 타이밍(의도 시각 vs 체결 시각, 초)
        secs = seconds_between(expectation.timestamp, fill.get("timestamp", ""))
        tdev = round(secs, 6) if secs is not None else None
        tstat = grade(tdev if tdev is not None else float("inf"), t.timing_seconds, t.fail_multiplier)

        checks = [
            {"name": "quantity", "status": qstat, "deviation": qdev, "tolerance": t.quantity_tolerance},
            {"name": "price", "status": pstat, "deviation": pdev, "tolerance": t.price_tolerance_bps},
            {"name": "fee", "status": fstat, "deviation": fdev, "tolerance": t.fee_tolerance_bps},
            {"name": "slippage", "status": sstat, "deviation": sdev, "tolerance": t.price_tolerance_bps},
            {"name": "timing", "status": tstat, "deviation": tdev, "tolerance": t.timing_seconds},
        ]
        deviations = {"quantity": qdev, "price_bps": pdev, "fee_bps": fdev,
                      "slippage_bps": sdev, "timing_seconds": tdev}
        status = max_status([c["status"] for c in checks])
        return self._finish(vid, expectation.intent_id, status, checks, deviations, ih, now, commit)

    def _finish(self, vid: str, intent_id: str, status: str, checks: list, deviations: dict,
                ih: str, now: str, commit: bool, reason: str = "") -> ExecutionValidationReport:
        vh = validation_hash(vid, intent_id, status, checks, deviations, ih)
        report = ExecutionValidationReport(
            validation_id=vid, intent_id=intent_id, status=status, checks=checks,
            deviations=deviations, timestamp=now, input_hash=ih, hash=vh)
        if commit and not ledger.validation_exists(vid):
            ledger.append_report(report.to_dict())
            ev = {"event": "validation_recorded", "validation_id": vid, "intent_id": intent_id,
                  "status": status, "timestamp": now}
            if reason:
                ev["reason"] = reason
            ledger.append_event(ev)
        return report
