"""Execution Risk Enforcement Engine (P8.5) — 제출 직전 최종 리스크 게이트. **집행 아님.**

이미 승인된 집행요청 + 읽기전용 RiskContext → 13개 결정론적 검사 → ALLOW/BLOCK.
**하나라도 FAILED → 반드시 BLOCK.** 주문 생성/제출 없음·브로커 호출 없음·상태 변경 없음.

아키텍처: ExecutionDecision(P7.4) → Readiness(P7.7) → Cost(P8.4) → [Execution Risk] →
ALLOW/BLOCK → Live Execution Adapter(P8.1).

**MUST NOT: 주문 제출·브로커 API 호출·집행 게이트웨이/어댑터 import·포지션/포트폴리오/
페이퍼/라이브/레지스트리/리스크거버너 변경.** 오직 READ. 결정적·append-only·재현가능.
"""
from __future__ import annotations

from jarvis.execution_risk import ledger
from jarvis.execution_risk.models import (
    ALLOW,
    BLOCK,
    ExecutionRiskReport,
    FAILED,
    GENESIS,
    RiskCheck,
    WARNING,
    input_hash,
    report_hash,
    report_id,
    severity_for,
)
from jarvis.execution_risk.policy import (
    ExecutionRiskPolicy,
    RiskContext,
    grade_gate,
    grade_max,
)

# 검사 순서(결정적)
_ORDER = ["max_position_size", "max_notional_exposure", "portfolio_concentration",
          "daily_realized_loss", "daily_drawdown", "max_leverage", "max_turnover",
          "consecutive_failures", "broker_health", "market_data_freshness",
          "trading_halt", "kill_switch", "emergency_stop"]


class ExecutionRiskEngine:
    """제출 직전 리스크 집행검사기. 읽기전용·결정적."""

    def evaluate(self, request, context: RiskContext, policy: ExecutionRiskPolicy | None = None,
                 now: str = "", *, commit: bool = False) -> ExecutionRiskReport:
        req = request.to_dict() if hasattr(request, "to_dict") else (request or {})
        rid_req = req.get("request_id", "")
        policy = policy or ExecutionRiskPolicy()
        ctx = context or RiskContext()
        wr = policy.warn_ratio

        # 관측값(미주입 시 요청/보수 폴백)
        pos = ctx.position_size if ctx.position_size is not None else abs(float(req.get("quantity", 0.0)))
        notional = ctx.notional if ctx.notional is not None else abs(
            float(req.get("quantity", 0.0)) * float(req.get("limit_price") or 0.0))
        conc = ctx.concentration if ctx.concentration is not None else 0.0

        checks: list[RiskCheck] = []

        def _num(name, value, limit):
            st = grade_max(float(value), float(limit), wr)
            checks.append(RiskCheck(name, st, severity_for(st), round(float(value), 8),
                                    float(limit), f"{value} vs limit {limit}"))

        def _gate(name, bad, detail):
            st = grade_gate(bool(bad))
            checks.append(RiskCheck(name, st, severity_for(st), bool(bad), None, detail))

        # 1~8: 수치 한도
        _num("max_position_size", pos, policy.max_position_size)
        _num("max_notional_exposure", notional, policy.max_notional)
        _num("portfolio_concentration", conc, policy.max_concentration)
        _num("daily_realized_loss", abs(ctx.daily_realized_loss), policy.daily_loss_limit)
        _num("daily_drawdown", ctx.drawdown, policy.max_drawdown)
        _num("max_leverage", ctx.leverage, policy.max_leverage)
        _num("max_turnover", ctx.turnover, policy.max_turnover)
        _num("consecutive_failures", ctx.consecutive_failures, policy.max_consecutive_failures)
        # 9~13: 이진 게이트(위험상태 → FAILED)
        _gate("broker_health", not ctx.broker_healthy, "broker unhealthy/unavailable")
        _gate("market_data_freshness", not ctx.market_fresh, "market data stale/unavailable")
        _gate("trading_halt", ctx.trading_halted, "trading halted")
        _gate("kill_switch", ctx.kill_switch, "kill switch active")
        _gate("emergency_stop", ctx.emergency_stop, "emergency manual stop active")

        checks.sort(key=lambda c: _ORDER.index(c.name))
        chk_dicts = [c.to_dict() for c in checks]
        failures = [c["name"] for c in chk_dicts if c["status"] == FAILED]
        warnings = [c["name"] for c in chk_dicts if c["status"] == WARNING]
        overall = BLOCK if failures else ALLOW
        blocker_reason = "; ".join(failures) if failures else ""

        ih = input_hash(rid_req, ctx.to_dict(), policy.to_dict())
        rid = report_id(rid_req, ih)
        rh = report_hash(rid, rid_req, overall, chk_dicts, failures, warnings, ih)
        report = ExecutionRiskReport(
            report_id=rid, request_id=rid_req, timestamp=now, overall_status=overall,
            individual_checks=chk_dicts, warnings=warnings, failures=failures,
            blocker_reason=blocker_reason, input_hash=ih, report_hash=rh)
        if commit and not ledger.event_exists(rid):
            head = ledger.chain_head()
            prev_hash = head["report_hash"] if head else GENESIS
            ledger.append_event({"event_id": rid, "request_id": rid_req,
                                 "overall_status": overall, "input_hash": ih, "report_hash": rh,
                                 "previous_hash": prev_hash, "blocker_reason": blocker_reason,
                                 "timestamp": now})
        return report
