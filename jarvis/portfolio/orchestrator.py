"""Portfolio Orchestrator (P2.4) — 기존 제안 파이프라인 '위'의 오케스트레이션 계층.

기존 로직 무수정. Allocation→RiskScaler→DecisionEngine 결과를 받아
Scheduler·Turnover·Journal·StateMachine을 조율한다. **제안 전용 — 주문 없음.**

dry_run=True(기본): 상태 무변경(저널/상태/회전율 원장 기록 안 함), 계산만.
"""
from __future__ import annotations

from jarvis.portfolio.allocator import RiskConstraints, propose_allocation
from jarvis.portfolio.decision_engine import CurrentPortfolio, propose_rebalance
from jarvis.portfolio.journal import PortfolioDecisionRecord, last_timestamp, record_decision
from jarvis.portfolio.regime import detect_portfolio_regime
from jarvis.portfolio.risk_quality import check_matrix
from jarvis.portfolio.risk_scaler import scale_allocation
from jarvis.portfolio.scheduler import (
    EvaluationContext,
    SchedulerConfig,
    should_evaluate,
)
from jarvis.portfolio.state import ALLOWED_TRANSITIONS, PortfolioState, PortfolioStateMachine
from jarvis.portfolio.turnover import TurnoverConfig, check_turnover, record_turnover

# 결정 → 목표 상태
_DECISION_STATE = {
    "REBALANCE": PortfolioState.REBALANCE_PENDING.value,
    "RISK_REDUCTION": PortfolioState.RISK_REDUCTION.value,
    "HOLD": PortfolioState.MONITORING.value,
    "BLOCKED": PortfolioState.MONITORING.value,
}


def _drift(before: dict, target: dict) -> float | None:
    if not before:
        return None
    keys = set(before) | set(target)
    return round(sum(abs(before.get(k, 0.0) - target.get(k, 0.0)) for k in keys) / 2.0, 6)


class PortfolioOrchestrator:
    def __init__(self, scheduler_config: SchedulerConfig | None = None,
                 turnover_config: TurnoverConfig | None = None,
                 constraints: RiskConstraints | None = None) -> None:
        self.sched_c = scheduler_config or SchedulerConfig()
        self.turn_c = turnover_config or TurnoverConfig()
        self.constraints = constraints or RiskConstraints()

    def evaluate(self, matrix, current: CurrentPortfolio | None, now: str, ts: str = "",
                 *, last_eval: str | None = None, previous_regime: str | None = None,
                 regime_detector=None, dry_run: bool = True) -> dict:
        ts = ts or now
        sm = PortfolioStateMachine()
        state_before = sm.current()

        # ── 입력 계산(기존 파이프라인 호출 — 무수정) ──
        quality = check_matrix(matrix)
        regime = detect_portfolio_regime(matrix, weights=None, as_of=now,
                                         detector=regime_detector)
        alloc = propose_allocation(matrix, self.constraints, as_of=now, ts=ts)
        scaled = scale_allocation(alloc, matrix, regime=regime, ts=ts, quality=quality)
        target = dict(scaled.strategy_weights)
        before = dict(current.weights) if (current and current.known) else {}
        drift = _drift(before, target)
        active = sorted(target)

        # ── 스케줄러 ──
        ctx = EvaluationContext(
            now=now, last_eval=last_eval if last_eval is not None else last_timestamp(),
            last_rebalance=(current.last_rebalance if current else None),
            current_regime=regime.get("current_regime"), previous_regime=previous_regime,
            current_drawdown=scaled.diagnostics.get("drawdown"), weight_drift=drift,
            active_strategies=active)
        sched = should_evaluate(ctx, self.sched_c)

        reasons: list = []
        blockers: list = []
        rebalance = None
        turnover_check = None

        if not sched.should_run:
            decision = "HOLD"
            reasons = ["not_scheduled"] + sched.reasons
        else:
            rebalance = propose_rebalance(scaled, current, now=now, ts=ts)
            turnover_check = check_turnover(rebalance.total_turnover, now, self.turn_c)
            if rebalance.cooldown_active:
                decision, blockers = "BLOCKED", ["cooldown"]
            elif not turnover_check.approved:
                decision, blockers = "BLOCKED", [turnover_check.reason]
            elif quality.recommended_mode == "exclude":
                decision, blockers = "BLOCKED", ["quality_exclude"]
            elif rebalance.any_rebalance:
                decision = "REBALANCE"
                reasons = [p.rationale for p in rebalance.proposals if p.decision == "rebalance"]
            elif (scaled.regime_multiplier < 1.0 or scaled.drawdown_adjustment < 1.0
                  or scaled.gross_exposure < 0.999):
                decision = "RISK_REDUCTION"
                reasons = [f"regime_mult={scaled.regime_multiplier}",
                           f"dd_adj={scaled.drawdown_adjustment}",
                           f"gross={scaled.gross_exposure}"]
            else:
                decision, reasons = "HOLD", ["on_target"]
            reasons += sched.reasons

        rec = PortfolioDecisionRecord(
            timestamp=ts,
            inputs={"regime": regime.get("current_regime"),
                    "volatility": scaled.current_volatility,
                    "quality_score": quality.confidence_score,
                    "active_strategies": active,
                    "correlation_state": matrix.correlation()},
            before=before, after=target, decision=decision,
            reasons=reasons, blockers=blockers,
            metadata={"scheduler": sched.to_dict(), "gross_exposure": scaled.gross_exposure,
                      "turnover_check": turnover_check.to_dict() if turnover_check else None,
                      "quality_mode": quality.recommended_mode, "dry_run": dry_run})

        result = {"decision": decision, "state_before": state_before,
                  "scheduler": sched.to_dict(), "record": rec.to_dict(),
                  "turnover_check": turnover_check.to_dict() if turnover_check else None,
                  "dry_run": dry_run, "mutated": False}

        if dry_run:
            return result

        # ── 상태 변경(non-dry-run) ──
        if state_before == PortfolioState.INITIALIZING.value:
            sm.transition(PortfolioState.MONITORING, "orchestrator_init", ts)
        record_decision(rec)
        if decision == "REBALANCE" and turnover_check and turnover_check.approved:
            record_turnover(rebalance.total_turnover, now, ts)
        target_state = _DECISION_STATE.get(decision, PortfolioState.MONITORING.value)
        self._safe_transition(sm, target_state, f"decision={decision}", ts)
        result["mutated"] = True
        result["state_after"] = sm.current()
        return result

    @staticmethod
    def _safe_transition(sm: PortfolioStateMachine, target: str, reason: str, ts: str) -> None:
        cur = sm.current()
        if cur == target:
            return
        if target in ALLOWED_TRANSITIONS.get(cur, set()):
            sm.transition(target, reason, ts)
        elif (PortfolioState.MONITORING.value in ALLOWED_TRANSITIONS.get(cur, set())
              and target in ALLOWED_TRANSITIONS.get(PortfolioState.MONITORING.value, set())):
            sm.transition(PortfolioState.MONITORING, "route_via_monitoring", ts)
            sm.transition(target, reason, ts)
        # 도달 불가면 상태 유지(저널엔 이미 결정 기록됨)


def evaluate_portfolio(matrix, current, now, ts="", **kw) -> dict:
    return PortfolioOrchestrator().evaluate(matrix, current, now, ts, **kw)
