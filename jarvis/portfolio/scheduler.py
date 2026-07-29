"""Portfolio Evaluation Scheduler (P2.4 F2) — 포트폴리오 평가를 언제 돌릴지 결정.

시간기반(daily/weekly/monthly) + 이벤트기반(레짐변화·drawdown 임계·비중 drift·신규전략).
**평가 여부만 결정 — 집행 없음.** 결정적 · no-lookahead(과거 타임스탬프+현재상태만).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

FREQUENCY_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}


@dataclass(frozen=True)
class SchedulerConfig:
    frequency: str = "daily"
    drawdown_trigger: float = 0.10    # 이 값 상향돌파 시 이벤트
    drift_trigger: float = 0.10       # 비중 drift 이 이상 시 이벤트


@dataclass(frozen=True)
class EvaluationContext:
    now: str
    last_eval: str | None = None
    last_rebalance: str | None = None
    current_regime: str | None = None
    previous_regime: str | None = None
    current_drawdown: float | None = None
    previous_drawdown: float | None = None
    weight_drift: float | None = None
    active_strategies: list | None = None
    previous_active: list | None = None


@dataclass(frozen=True)
class PortfolioEvaluationDecision:
    should_run: bool
    trigger_type: str                 # time | regime_change | drawdown | drift | new_strategy | none
    reasons: list
    timestamp: str
    triggers: list = field(default_factory=list)

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def _days(a: str, b: str) -> int:
    return (_dt.date.fromisoformat(b[:10]) - _dt.date.fromisoformat(a[:10])).days


def should_evaluate(ctx: EvaluationContext,
                    config: SchedulerConfig | None = None) -> PortfolioEvaluationDecision:
    c = config or SchedulerConfig()
    triggers: list[str] = []
    reasons: list[str] = []

    # ── 시간기반 ──
    freq_days = FREQUENCY_DAYS.get(c.frequency, 1)
    if ctx.last_eval is None:
        triggers.append("time"); reasons.append("no_prior_evaluation")
    elif _days(ctx.last_eval, ctx.now) >= freq_days:
        triggers.append("time")
        reasons.append(f"{c.frequency}_elapsed({_days(ctx.last_eval, ctx.now)}d>={freq_days}d)")

    # ── 레짐 변화 ──
    if (ctx.current_regime and ctx.previous_regime
            and ctx.current_regime != ctx.previous_regime):
        triggers.append("regime_change")
        reasons.append(f"regime {ctx.previous_regime}→{ctx.current_regime}")

    # ── drawdown 임계 상향돌파 ──
    if ctx.current_drawdown is not None and ctx.current_drawdown >= c.drawdown_trigger:
        crossed = ctx.previous_drawdown is None or ctx.previous_drawdown < c.drawdown_trigger
        if crossed:
            triggers.append("drawdown")
            reasons.append(f"drawdown {round(ctx.current_drawdown,4)}>={c.drawdown_trigger}")

    # ── 비중 drift ──
    if ctx.weight_drift is not None and ctx.weight_drift >= c.drift_trigger:
        triggers.append("drift")
        reasons.append(f"weight_drift {round(ctx.weight_drift,4)}>={c.drift_trigger}")

    # ── 신규 전략 활성화 ──
    if ctx.active_strategies is not None and ctx.previous_active is not None:
        new = sorted(set(ctx.active_strategies) - set(ctx.previous_active))
        if new:
            triggers.append("new_strategy")
            reasons.append(f"new_active:{new}")

    should = len(triggers) > 0
    return PortfolioEvaluationDecision(
        should_run=should, trigger_type=triggers[0] if triggers else "none",
        reasons=reasons or ["no_trigger"], timestamp=ctx.now, triggers=triggers)
