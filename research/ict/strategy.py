"""ICT 조합 전략 — 프리미티브를 객관 규칙으로 엮는다.

모델 A (long): NY 킬존 안에서 **매도측 유동성 사냥(bullish sweep)** +
               상방 변위(bullish FVG 근처) → 다음 봉 시가 진입, 고정 H봉 보유.
= 고전 ICT "sweep → displacement → FVG 되돌림" 롱. 파라미터 고정, 미최적화.
"""
from __future__ import annotations

from research.ict.primitives import (
    fair_value_gaps,
    has_bullish_fvg_near,
    killzone_indices,
    liquidity_sweeps,
)


def model_a_entries(bars: dict, lookback: int = 10, kz: tuple[float, float] = (13.5, 15.0)) -> dict:
    """반환: {entries:[진입 인덱스], eligible:[킬존 인덱스(랜덤 baseline용)]}.

    entries = 킬존 & bullish sweep[i] & bullish FVG(i-1..i) → i+1 진입 대상은 백테스트가 처리."""
    h, l, c, ts = bars["h"], bars["l"], bars["c"], bars["ts"]
    fvgs = fair_value_gaps(h, l)
    sweeps = liquidity_sweeps(h, l, c, lookback=lookback)
    kz_idx = set(killzone_indices(ts, kz[0], kz[1]))
    sweep_bull = {s["idx"] for s in sweeps if s["type"] == "bullish"}

    entries = []
    for i in range(len(c) - 1):
        if i in kz_idx and i in sweep_bull and has_bullish_fvg_near(fvgs, i, window=1):
            entries.append(i)
    eligible = sorted(kz_idx & set(range(len(c) - 1)))
    return {"entries": entries, "eligible": eligible,
            "n_fvg": len(fvgs), "n_sweep": len(sweep_bull), "n_kz": len(kz_idx)}
