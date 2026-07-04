"""buyback × 시장 레짐 복합 — 말 되는 조합만.

경제 논리: 경영진이 하락장(공포)에 자사주 매입 = 저평가 신호 더 신뢰성↑ → 드리프트 더 셀 것.
EW 시장지수 60일 수익으로 레짐 분류 → buyback net을 레짐별 비교 + 레짐내 매칭 random.
v2 shadow(v1 동결). 실행: PYTHONPATH=. python3 research/run_buyback_regime.py
"""
from __future__ import annotations

import bisect
import glob
import os
import random as _random
import statistics as _st

from research.agents.experiment_registry import log_experiment
from research.data.kr_dart_events import load_events
from research.data.krx_api import build_series, market_dir
from research.validation.baselines import empirical_p_value

HOLD = 20
COST_RT = 40.0
N_RUNS = 500
SEED = 42
REG_LOOKBACK = 60


def _series():
    s = build_series("KOSDAQ", min_bars=90)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=90))
    return s


def _market_index(series):
    """EW 시장지수: 날짜별 유동종목 일수익 평균 → 누적."""
    day_rets: dict = {}
    for b in series.values():
        if _st.mean(b["tval"][-20:]) < 1e9:
            continue
        for i in range(1, len(b["dates"])):
            if b["close"][i - 1] > 0:
                day_rets.setdefault(b["dates"][i], []).append(b["close"][i] / b["close"][i - 1] - 1)
    dates = sorted(day_rets)
    idx, cum = {}, 1.0
    for d in dates:
        cum *= (1 + _st.mean(day_rets[d]))
        idx[d] = cum
    return dates, idx


def _fwd(b, ed, rt=COST_RT):
    j = bisect.bisect_right(b["dates"], ed)
    if j >= len(b["dates"]):
        return None
    entry = b["open"][j]; xi = min(j + HOLD, len(b["dates"]) - 1)
    if entry <= 0 or xi <= j:
        return None
    return (b["close"][xi] / entry - 1) - rt / 10_000.0


def _regime(idx_dates, idx, ed):
    """이벤트일 시장 60일 수익. 없으면 None."""
    j = bisect.bisect_right(idx_dates, ed) - 1
    if j < REG_LOOKBACK:
        return None
    return idx[idx_dates[j]] / idx[idx_dates[j - REG_LOOKBACK]] - 1


def main():
    print("=" * 70)
    print("buyback × 시장 레짐 (하락장 buyback이 더 센가?) — v2 shadow")
    print("=" * 70)
    series = _series()
    bb = load_events("buyback")
    idx_dates, idx = _market_index(series)
    print(f"buyback {len(bb)} | 시장지수 {len(idx_dates)}일")

    # 이벤트별 (레짐, net)
    rows = []
    for e in bb:
        b = series.get(e["stock_code"])
        if b is None:
            continue
        reg = _regime(idx_dates, idx, e["date"])
        net = _fwd(b, e["date"])
        if reg is not None and net is not None:
            rows.append((reg, net, e["date"]))
    if len(rows) < 100:
        print("표본 부족"); return

    # 레짐 3분위(하락/중립/상승)
    regs = sorted(r for r, _, _ in rows)
    q1, q2 = regs[len(regs) // 3], regs[2 * len(regs) // 3]
    buckets = {"하락장": [], "중립": [], "상승장": []}
    for reg, net, d in rows:
        k = "하락장" if reg <= q1 else "상승장" if reg > q2 else "중립"
        buckets[k].append(net)
    print(f"\n레짐 경계: 60일 시장수익 {q1:+.1%} / {q2:+.1%}")
    print(f"{'레짐':8} {'n':>5} {'buyback net':>12} {'승률':>7}")
    for k, v in buckets.items():
        wr = sum(1 for x in v if x > 0) / len(v) if v else 0
        print(f"{k:8} {len(v):5} {_st.mean(v):+11.4f} {wr:6.1%}")

    # 하락장 buyback이 상승장보다 유의하게 센가? + 하락장 내 매칭 random
    bear, bull = buckets["하락장"], buckets["상승장"]
    print(f"\n하락장 {_st.mean(bear):+.4f} vs 상승장 {_st.mean(bull):+.4f} = 차이 {_st.mean(bear)-_st.mean(bull):+.4f}")

    # 하락장 buyback vs 하락장 랜덤(같은 레짐 진입일 랜덤 종목)
    bear_dates = set(d for reg, _, d in rows if reg <= q1)
    pool = []
    for b in series.values():
        for i in range(len(b["dates"]) - HOLD - 1):
            if b["dates"][i] in bear_dates:
                pool.append((b, i))
    if pool:
        rng = _random.Random(SEED); rmeans = []
        for _ in range(N_RUNS):
            s = 0.0
            for _ in range(len(bear)):
                b, i = pool[rng.randrange(len(pool))]
                e0 = b["open"][i + 1]; xi = min(i + 1 + HOLD, len(b["dates"]) - 1)
                s += ((b["close"][xi] / e0 - 1) - COST_RT / 10_000.0) if e0 > 0 else 0.0
            rmeans.append(s / len(bear))
        pv = empirical_p_value(_st.mean(bear), rmeans)
        print(f"하락장 buyback vs 하락장 random: pct={pv['percentile']} p={pv['p_value']} (med={pv['random_median']:+.4f})")

    stronger = _st.mean(bear) > _st.mean(bull) * 1.3
    verdict = ("레짐 신호 O — 하락장 buyback 유의하게 셈(v2 필터 후보)" if stronger else
               "레짐 무관 — buyback은 레짐 상관없이 작동(필터 불필요, 억지 안 함)")
    print(f"\nVERDICT: {verdict}")
    log_experiment({"hypothesis_id": "kr_buyback_x_regime_v2shadow",
                    "status": "watchlist" if stronger else "no_effect",
                    "bear_net": round(_st.mean(bear), 6), "bull_net": round(_st.mean(bull), 6),
                    "neutral_net": round(_st.mean(buckets["중립"]), 6),
                    "data_quality": "KRX PIT + EW 레짐", "verdict": verdict,
                    "note": "buyback×레짐 복합, v1 동결·v2 shadow. 억지필터 금지 원칙"})


if __name__ == "__main__":
    main()
