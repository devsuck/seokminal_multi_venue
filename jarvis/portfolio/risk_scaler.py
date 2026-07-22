"""Portfolio Risk Scaling Layer (P2.2) — 배분 가중 → 리스크조정 노출 '제안'.

배분(P2.1 AllocationResult)의 정규화 가중을 vol-targeting · drawdown 스케일 ·
regime 배수로 조정해 gross exposure를 제안한다. **제안 전용 — 집행/리스크거버너 무수정.**

안전 기본값: 기본 무레버리지(max_leverage=1.0), vol 데이터 없으면 보수 폴백,
히스토리 부족하면 레버리지 금지. 결정적 · no-lookahead(as_of 이하만).
"""
from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field

_EPS = 1e-12


@dataclass(frozen=True)
class RiskScalingConfig:
    target_vol: float = 0.15          # 연율 목표 변동성
    max_leverage: float = 1.0         # gross 상한(기본 무레버리지 — 보수)
    ann_factor: int = 252             # 연율화 계수(periodic→annual)
    min_history: int = 20             # 미만 = 레버리지 금지(cap 1.0)
    conservative_vol_scalar: float = 0.5  # vol 데이터 결측 시 보수 스칼라
    # drawdown 사다리(오름차순 임계, 배수). dd<=임계면 해당 배수.
    dd_ladder: tuple = ((0.05, 1.0), (0.10, 0.75), (0.20, 0.5), (1.0, 0.25))
    # regime 라벨 → 배수(미지 라벨/None = 1.0)
    regime_multipliers: dict = field(default_factory=lambda: {
        "risk_on": 1.0, "bull": 1.0, "trending": 1.0,
        "neutral": 0.75, "range": 0.75, "chop": 0.75,
        "risk_off": 0.5, "bear": 0.5, "high_vol": 0.5, "crisis": 0.3,
    })


@dataclass(frozen=True)
class PortfolioState:
    equity: float
    peak: float


@dataclass(frozen=True)
class RiskAdjustedAllocation:
    strategy_weights: dict           # gross 반영된 배포 가중(합 ≈ gross_exposure)
    gross_exposure: float
    volatility_target: float
    current_volatility: float | None
    drawdown_adjustment: float
    regime_multiplier: float
    rationale: str
    timestamp: str
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else (hi if x > hi else x)


def _dd_ladder_factor(dd: float, ladder) -> float:
    for thr, mult in ladder:
        if dd <= thr:
            return mult
    return ladder[-1][1]


def _regime_multiplier(regime, table: dict) -> tuple[float, str]:
    if regime is None:
        return 1.0, "none"
    if isinstance(regime, (int, float)):
        return _clamp(float(regime), 0.0, 1.0), f"numeric:{regime}"
    label = regime
    if isinstance(regime, dict):
        label = regime.get("regime") or regime.get("state") or regime.get("label")
    label = str(label) if label is not None else None
    if label in table:
        return table[label], label
    return 1.0, f"unknown:{label}"  # 미지 라벨 = 무조정(1.0)


class PortfolioRiskScaler:
    def __init__(self, config: RiskScalingConfig | None = None) -> None:
        self.c = config or RiskScalingConfig()

    def _portfolio_returns(self, series: dict, weights: dict) -> list[float]:
        from jarvis.fusion.backtest import fused_returns
        return fused_returns(series, weights)

    def _current_drawdown(self, state, series, weights) -> float:
        if state is not None and state.peak > _EPS:
            return max(0.0, (state.peak - state.equity) / state.peak)
        if not series:
            return 0.0
        port = self._portfolio_returns(series, weights)
        eq, peak, cur = 1.0, 1.0, 1.0
        for r in port:
            cur *= (1.0 + r)
            peak = max(peak, cur)
        return max(0.0, (peak - cur) / peak) if peak > _EPS else 0.0

    def scale(self, allocation, matrix, as_of: str | None = None,
              state: PortfolioState | None = None, regime=None, ts: str = "") -> RiskAdjustedAllocation:
        weights = {p.strategy_id: p.target_weight for p in allocation.proposals}
        cal = [d for d in matrix.calendar() if as_of is None or d <= as_of]
        _, aligned = matrix.aligned(cal)
        series = {k: v for k, v in aligned.items() if k in weights}
        n_obs = len(next(iter(series.values()))) if series else 0

        # ── 변동성 타겟팅 ──
        current_vol = None
        vol_note = ""
        if n_obs >= 2 and series:
            per = statistics.pstdev(self._portfolio_returns(series, weights))
            if per > _EPS:
                current_vol = round(per * (self.c.ann_factor ** 0.5), 8)
        if current_vol is None:
            vol_scalar = self.c.conservative_vol_scalar
            vol_note = "missing_vol_data→conservative"
        else:
            vol_scalar = self.c.target_vol / current_vol

        # 히스토리 부족 → 레버리지 금지
        lev_cap = self.c.max_leverage if n_obs >= self.c.min_history else 1.0
        if n_obs < self.c.min_history:
            vol_note = (vol_note + "; " if vol_note else "") + "insufficient_history→no_leverage"

        # ── drawdown 스케일 ──
        dd = self._current_drawdown(state, series, weights)
        dd_adj = _dd_ladder_factor(dd, self.c.dd_ladder)

        # ── regime 배수 ──
        regime_mult, regime_label = _regime_multiplier(regime, self.c.regime_multipliers)

        gross = _clamp(vol_scalar * dd_adj * regime_mult, 0.0, lev_cap)
        scaled = {k: round(w * gross, 6) for k, w in weights.items()}

        rationale = (f"gross={round(gross,4)} = clamp(vol_scalar={round(vol_scalar,3)} × "
                     f"dd_adj={dd_adj}(dd={round(dd,4)}) × regime={regime_mult}({regime_label}), "
                     f"cap={lev_cap})")
        if vol_note:
            rationale += f" [{vol_note}]"
        return RiskAdjustedAllocation(
            strategy_weights=scaled, gross_exposure=round(gross, 6),
            volatility_target=self.c.target_vol, current_volatility=current_vol,
            drawdown_adjustment=dd_adj, regime_multiplier=regime_mult,
            rationale=rationale, timestamp=ts,
            diagnostics={"n_obs": n_obs, "leverage_cap": lev_cap,
                         "vol_scalar": round(vol_scalar, 6), "drawdown": round(dd, 6),
                         "regime_label": regime_label, "base_weights": weights})


def scale_allocation(allocation, matrix, config: RiskScalingConfig | None = None,
                     as_of: str | None = None, state: PortfolioState | None = None,
                     regime=None, ts: str = "") -> RiskAdjustedAllocation:
    """편의 진입점. 기록 안 함(제안 계산만)."""
    return PortfolioRiskScaler(config).scale(allocation, matrix, as_of, state, regime, ts)
