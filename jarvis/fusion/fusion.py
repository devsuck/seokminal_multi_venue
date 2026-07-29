"""FusionEngine — 전략 신호 + 성과 → 계기별 합성신호(설명가능).

주문 없음. FusionSignal(자문)만. 계기별로 신호 낸 전략만 정규화 대상.
"""
from __future__ import annotations

from collections import defaultdict

from jarvis.fusion.types import Contribution, FusionSignal, StrategyPerf, StrategySignal
from jarvis.fusion.weighting import DEFAULT_SCHEME, get_scheme

_EPS = 1e-9


def _sign(x: float) -> int:
    if x > _EPS:
        return 1
    if x < -_EPS:
        return -1
    return 0


class FusionEngine:
    def __init__(self, scheme: str = DEFAULT_SCHEME) -> None:
        self.scheme = get_scheme(scheme)

    def fuse(self, signals: list[StrategySignal], perfs: dict[str, StrategyPerf],
             as_of: str = "") -> list[FusionSignal]:
        """계기별 리스크조정 가중투표 → FusionSignal 목록."""
        weights = self.scheme.weights(perfs)

        by_instrument: dict[str, list[StrategySignal]] = defaultdict(list)
        for s in signals:
            by_instrument[s.instrument].append(s)

        out: list[FusionSignal] = []
        for instrument in sorted(by_instrument):
            sigs = by_instrument[instrument]
            contribs: list[Contribution] = []
            net = 0.0
            wsum = 0.0
            for s in sigs:
                w = weights.get(s.strategy_id, 0.0)
                p = perfs.get(s.strategy_id)
                signed = w * s.direction * s.strength
                net += signed
                wsum += w
                contribs.append(Contribution(
                    strategy_id=s.strategy_id, direction=s.direction, strength=s.strength,
                    weight=round(w, 6), signed_contribution=round(signed, 6),
                    perf_score=round(p.score, 6) if p else 0.0,
                    underpowered=bool(p.underpowered) if p else True,
                    reason="" if w > 0 else "zero_weight(무엣지/미배선/손실)"))
            confidence = (abs(net) / wsum) if wsum > _EPS else 0.0
            out.append(FusionSignal(
                instrument=instrument, direction=_sign(net),
                confidence=round(min(1.0, confidence), 6), score=round(net, 6),
                scheme=self.scheme.name, as_of=as_of, n_strategies=len(sigs),
                contributions=sorted(contribs, key=lambda c: -abs(c.signed_contribution)),
                meta={"weight_sum": round(wsum, 6)}))
        return out
