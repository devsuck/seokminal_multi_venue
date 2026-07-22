"""Signal Fusion Layer — 검증전략 신호 → 설명가능 합성신호(자문). 주문 없음.

점진: v1 리스크조정 가중투표(구현) → v2 레짐 → v3 베이지안 → v4 메타러닝(pending).
설계: jarvis/fusion/DESIGN.md.
"""
from jarvis.fusion.fusion import FusionEngine  # noqa: F401
from jarvis.fusion.types import (  # noqa: F401
    Contribution,
    FusionSignal,
    StrategyPerf,
    StrategySignal,
)
from jarvis.fusion.weighting import DEFAULT_SCHEME, SCHEMES, get_scheme  # noqa: F401
