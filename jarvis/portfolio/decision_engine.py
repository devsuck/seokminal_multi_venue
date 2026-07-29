"""Portfolio Decision Engine (P2.3) — 리스크조정 배분 → 리밸런스 '제안'.

RiskAdjustedAllocation(목표) + 현재 보유 → 전략별 RebalanceProposal.
게이트: 최소 리밸런스 임계 · 거래비용-편익 필터 · 리밸런스 쿨다운.

**제안 전용 — 주문 안 냄. 집행/리스크거버너 무수정.** 결정적 · no-lookahead.
비편익 모델: benefit=coeff·Δ²(편차 교정 효용), cost=rate·|Δ| → 무거래 밴드 형성.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import asdict, dataclass, field

_EPS = 1e-12


@dataclass(frozen=True)
class RebalanceConfig:
    min_delta: float = 0.03          # 최소 리밸런스 임계(비중 변화)
    cost_bps: float = 40.0           # 거래비용(단방향)
    benefit_coeff: float = 0.1       # 편차 교정 효용계수(benefit=coeff·Δ²)
    cooldown_days: int = 7           # 직전 리밸런스 후 이 기간엔 재리밸런스 금지

    @property
    def cost_rate(self) -> float:
        return self.cost_bps / 1e4


@dataclass(frozen=True)
class CurrentPortfolio:
    weights: dict[str, float]        # sid → 현재 비중
    last_rebalance: str | None = None
    known: bool = True               # False = 보유 미상(보수 폴백)


@dataclass(frozen=True)
class RebalanceProposal:
    strategy_id: str
    current_weight: float | None
    target_weight: float
    delta: float | None
    turnover: float
    estimated_cost: float
    decision: str                    # rebalance | hold
    rationale: str
    timestamp: str


@dataclass(frozen=True)
class RebalanceDecision:
    proposals: list[RebalanceProposal]
    total_turnover: float
    total_estimated_cost: float
    any_rebalance: bool
    cooldown_active: bool
    timestamp: str
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _days(a: str, b: str) -> int:
    return (_dt.date.fromisoformat(b[:10]) - _dt.date.fromisoformat(a[:10])).days


class PortfolioDecisionEngine:
    def __init__(self, config: RebalanceConfig | None = None) -> None:
        self.c = config or RebalanceConfig()

    def propose(self, risk_adjusted, current: CurrentPortfolio | None,
                now: str = "", ts: str = "") -> RebalanceDecision:
        target = dict(getattr(risk_adjusted, "strategy_weights", {}) or {})
        now = now or ts

        # ── 보유 미상 → 보수 폴백(거래 제안 안 함) ──
        if current is None or not current.known:
            props = []
            for sid in sorted(target):
                tw = round(target[sid], 6)
                props.append(RebalanceProposal(
                    strategy_id=sid, current_weight=None, target_weight=tw, delta=None,
                    turnover=0.0, estimated_cost=0.0, decision="hold",
                    rationale="보유 미상 → 온타겟 가정(보수, 무거래)", timestamp=ts))
            return RebalanceDecision(props, 0.0, 0.0, False, False, ts,
                                     {"reason": "missing_holdings_conservative"})

        cur = current.weights or {}
        cooldown_active = bool(
            current.last_rebalance and now
            and _days(current.last_rebalance, now) < self.c.cooldown_days)

        proposals = []
        total_turnover = 0.0
        total_cost = 0.0
        for sid in sorted(set(target) | set(cur)):
            cw = float(cur.get(sid, 0.0))
            tw = float(target.get(sid, 0.0))
            delta = tw - cw
            ad = abs(delta)
            turnover = round(ad, 6)
            est_cost = round(ad * self.c.cost_rate, 8)
            total_turnover += ad
            total_cost += ad * self.c.cost_rate

            benefit = self.c.benefit_coeff * delta * delta
            cost = self.c.cost_rate * ad
            if cooldown_active:
                decision, why = "hold", f"cooldown({_days(current.last_rebalance, now)}d<{self.c.cooldown_days}d)"
            elif ad < self.c.min_delta:
                decision, why = "hold", f"below_threshold(|Δ|={round(ad,4)}<{self.c.min_delta})"
            elif benefit <= cost:
                decision, why = "hold", f"cost_exceeds_benefit(benefit={round(benefit,6)}≤cost={round(cost,6)})"
            else:
                kind = "enter" if cw < _EPS else ("exit" if tw < _EPS else "rebalance")
                decision, why = "rebalance", f"{kind}(|Δ|={round(ad,4)}, benefit={round(benefit,6)}>cost={round(cost,6)})"
            proposals.append(RebalanceProposal(
                strategy_id=sid, current_weight=round(cw, 6), target_weight=round(tw, 6),
                delta=round(delta, 6), turnover=turnover, estimated_cost=est_cost,
                decision=decision, rationale=why, timestamp=ts))

        any_reb = any(p.decision == "rebalance" for p in proposals)
        return RebalanceDecision(
            proposals=sorted(proposals, key=lambda p: -abs(p.delta or 0.0)),
            total_turnover=round(total_turnover / 2.0, 6),
            total_estimated_cost=round(total_cost, 8),
            any_rebalance=any_reb, cooldown_active=cooldown_active, timestamp=ts,
            diagnostics={"n": len(proposals), "cooldown_active": cooldown_active,
                         "config": {"min_delta": self.c.min_delta, "cost_bps": self.c.cost_bps,
                                    "benefit_coeff": self.c.benefit_coeff,
                                    "cooldown_days": self.c.cooldown_days}})


def propose_rebalance(risk_adjusted, current: CurrentPortfolio | None,
                      config: RebalanceConfig | None = None,
                      now: str = "", ts: str = "") -> RebalanceDecision:
    """편의 진입점 — 계산만(기록은 rebalance_ledger.write_proposal)."""
    return PortfolioDecisionEngine(config).propose(risk_adjusted, current, now, ts)
