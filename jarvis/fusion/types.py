"""Signal Fusion 자료형 — 불변 dataclass. 방향/강도 검증 포함."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else float(x))


@dataclass(frozen=True)
class StrategySignal:
    """한 전략이 한 계기(instrument)에 대해 내는 원자 신호.

    direction: -1 short / 0 flat / +1 long. strength: 0..1 전략 자체 확신도.
    """
    strategy_id: str
    instrument: str
    direction: int
    strength: float = 1.0
    as_of: str = ""
    source: str = ""
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.direction not in (-1, 0, 1):
            raise ValueError(f"direction must be -1/0/+1, got {self.direction}")
        object.__setattr__(self, "strength", _clamp01(self.strength))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StrategyPerf:
    """전략의 리스크조정 성과 = 투표 가중치의 근거. score>=0(음수 성과=0표)."""
    strategy_id: str
    score: float
    sharpe: float | None
    volatility: float | None
    observation_count: int
    underpowered: bool
    source: str
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Contribution:
    """계기별 합성에 대한 전략별 기여 — 설명가능성의 핵심."""
    strategy_id: str
    direction: int
    strength: float
    weight: float
    signed_contribution: float
    perf_score: float
    underpowered: bool
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FusionSignal:
    """합성신호(자문). 주문 아님. contributions로 완전 설명가능."""
    instrument: str
    direction: int
    confidence: float
    score: float
    scheme: str
    as_of: str
    n_strategies: int
    contributions: list[Contribution] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d
