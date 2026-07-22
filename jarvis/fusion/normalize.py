"""Signal Normalization Layer — 전략-상대 정규화로 strength 비교가능화.

문제: 전략마다 raw_strength 스케일이 다름(tsmom |w|/cap 분포 vs buyback 상수 1.0 등).
직접 합치면 왜곡. 해법: 각 전략의 자기 신호 분포 기준으로 [0,1] 재척도.
raw_strength → strategy-relative normalization → normalized_strength.

FusionEngine는 불변(정규화는 그 앞단 별도 레이어). raw는 meta에 보존(설명가능).
정규화는 전략 '내부' 확신 순위만 바꾼다 — 전략 간 표 크기는 fusion의 perf 가중이 담당.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict

from jarvis.fusion.types import StrategySignal

METHODS = ("rank", "minmax", "zscore")


def _rank_scale(vals: list[float]) -> list[float]:
    """평균순위 백분위 [0,1]. 이상치에 강건. 단일/전부동일 → 1.0."""
    n = len(vals)
    if n == 1 or max(vals) == min(vals):
        return [1.0] * n
    order = sorted(range(n), key=lambda i: vals[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return [r / (n - 1) for r in ranks]


def _minmax_scale(vals: list[float]) -> list[float]:
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return [1.0] * len(vals)
    return [(v - lo) / (hi - lo) for v in vals]


def _zscore_scale(vals: list[float]) -> list[float]:
    """z-score → 로지스틱 [0,1]. 단일/무분산 → 1.0."""
    if len(vals) < 2:
        return [1.0] * len(vals)
    m = statistics.mean(vals)
    s = statistics.pstdev(vals)
    if s <= 1e-12:
        return [1.0] * len(vals)
    return [1.0 / (1.0 + math.exp(-(v - m) / s)) for v in vals]


_SCALERS = {"rank": _rank_scale, "minmax": _minmax_scale, "zscore": _zscore_scale}


def normalize_signals(signals: list[StrategySignal], method: str = "rank") -> list[StrategySignal]:
    """전략별로 raw_strength를 [0,1] 정규화한 새 StrategySignal 목록. raw는 meta에 보존."""
    if method not in _SCALERS:
        raise KeyError(f"unknown method '{method}'. available: {METHODS}")
    scale = _SCALERS[method]

    by_strat: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(signals):
        by_strat[s.strategy_id].append(i)

    norm: list[float] = [1.0] * len(signals)
    for _, idxs in by_strat.items():
        raws = [signals[i].strength for i in idxs]
        for i, v in zip(idxs, scale(raws)):
            norm[i] = round(float(v), 6)

    out = []
    for s, v in zip(signals, norm):
        meta = {**s.meta, "raw_strength": s.strength, "norm_method": method}
        out.append(StrategySignal(
            strategy_id=s.strategy_id, instrument=s.instrument, direction=s.direction,
            strength=v, as_of=s.as_of, source=s.source, meta=meta))
    return out
