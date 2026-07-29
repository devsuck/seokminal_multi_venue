"""가중 스킴 — 점진 구현. v1만 구현, v2~v4는 pending(가짜결과 금지).

WeightingScheme.weights(perfs) → {strategy_id: weight}. 가중치 합 1, 음수 없음.
전략의 '표 크기'만 정한다(방향/강도는 StrategySignal에서).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from jarvis.fusion.types import StrategyPerf


class WeightingScheme(ABC):
    name: str = "base"
    implemented: bool = False

    @abstractmethod
    def weights(self, perfs: dict[str, StrategyPerf]) -> dict[str, float]:
        ...


class RiskAdjustedVoting(WeightingScheme):
    """v1 — 리스크조정 가중투표. weight_i = score_i / Σ score (score = max(0,Sharpe)*수축)."""
    name = "v1_risk_adjusted"
    implemented = True

    def weights(self, perfs: dict[str, StrategyPerf]) -> dict[str, float]:
        raw = {sid: max(0.0, p.score) for sid, p in perfs.items()}
        total = sum(raw.values())
        if total <= 0:
            return {sid: 0.0 for sid in perfs}
        return {sid: raw[sid] / total for sid in perfs}


class _PendingScheme(WeightingScheme):
    """미구현 스킴 — 호출 시 정직하게 실패(합성 가짜결과 금지)."""
    implemented = False

    def __init__(self, name: str, note: str) -> None:
        self.name = name
        self.note = note

    def weights(self, perfs: dict[str, StrategyPerf]) -> dict[str, float]:
        raise NotImplementedError(f"{self.name} 미구현: {self.note}")


SCHEMES: dict[str, WeightingScheme] = {
    "v1_risk_adjusted": RiskAdjustedVoting(),
    "v2_regime_aware": _PendingScheme("v2_regime_aware", "레짐 조건부 가중 — v1 validation 통과 후 착수"),
    "v3_bayesian": _PendingScheme("v3_bayesian", "베이지안 갱신 — v2 이후"),
    "v4_meta_learning": _PendingScheme("v4_meta_learning", "메타러닝 — v3 이후"),
}

DEFAULT_SCHEME = "v1_risk_adjusted"


def get_scheme(name: str) -> WeightingScheme:
    if name not in SCHEMES:
        raise KeyError(f"unknown scheme '{name}'. available: {sorted(SCHEMES)}")
    return SCHEMES[name]
