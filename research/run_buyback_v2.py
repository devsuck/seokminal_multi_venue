"""buyback v2 shadow — 상승장 이벤트 제외 필터. v1(전체) vs v2(하락+중립만) 비교.

발견: 상승장 buyback = +0.1%·승률43%(무의미), 하락/중립 = +2.4%·승률>52%.
v2 = 경영진 자사주 매입이 신뢰성 있는 레짐(하락/중립)만. v1 동결·v2는 별도 shadow.
사전 경제가설(하락장 신호 강함)이 데이터로 확인 → 선택편향 낮음. 단 forward 검증 전 live 금지.
실행: PYTHONPATH=. python3 research/run_buyback_v2.py
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
COST_LEVELS = {"base_20bps": 40.0, "stress_50bps": 100.0}
REG_LOOKBACK = 60
N_RUNS = 500
SEED = 42


def _series():
    s = build_series("KOSDAQ", min_bars=90)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=90))
    return s


def _market_index(series):
    day_rets: dict = {}
    for b in series.values():
        if _st.mean(b["tval"][-20:]) < 1e9:
            continue
        for i in range(1, len(b["dates"])):
            if b["close"][i - 1] > 0:
                day_rets.setdefault(b["dates"][i], []).append(b["close"][i] / b["close"][i - 1] - 1)
    dates = sorted(day_rets); idx, cum = {}, 1.0
    for d in dates:
        cum *= (1 + _st.mean(day_rets[d])); idx[d] = cum
    return dates, idx


def _fwd(b, ed, rt):
    j = bisect.bisect_right(b["dates"], ed)
    if j >= len(b["dates"]):
        return None
    entry = b["open"][j]; xi = min(j + HOLD, len(b["dates"]) - 1)
    if entry <= 0 or xi <= j:
        return None
    return (b["close"][xi] / entry - 1) - rt / 10_000.0


def _regime(idx_dates, idx, ed):
    j = bisect.bisect_right(idx_dates, ed) - 1
    if j < REG_LOOKBACK:
        return None
    return idx[idx_dates[j]] / idx[idx_dates[j - REG_LOOKBACK]] - 1


def _wr(v):
    return sum(1 for x in v if x > 0) / len(v) if v else 0.0


def main():
    print("=" * 72)
    print("buyback v2 shadow — 상승장 제외 필터 (v1 동결, v2 별도)")
    print("=" * 72)
    series = _series()
    bb = load_events("buyback")
    idx_dates, idx = _market_index(series)

    rows = []  # (regime, net_base, date, stock)
    for e in bb:
        b = series.get(e["stock_code"])
        if b is None:
            continue
        reg = _regime(idx_dates, idx, e["date"])
        net = _fwd(b, e["date"], COST_LEVELS["base_20bps"])
        if reg is not None and net is not None:
            rows.append((reg, net, e["date"]))
    regs = sorted(r for r, _, _ in rows)
    bull_cut = regs[2 * len(regs) // 3]     # 상위 1/3 = 상승장

    v1 = [n for _, n, _ in rows]
    v2 = [n for r, n, _ in rows if r <= bull_cut]      # 하락+중립
    excluded = [n for r, n, _ in rows if r > bull_cut]  # 제외된 상승장
    print(f"\n상승장 경계: 60일 시장 {bull_cut:+.1%}")
    print(f"{'':14}{'n':>6}{'net':>10}{'승률':>8}")
    print(f"{'v1 (전체)':14}{len(v1):6}{_st.mean(v1):+10.4f}{_wr(v1):7.1%}")
    print(f"{'v2 (상승제외)':14}{len(v2):6}{_st.mean(v2):+10.4f}{_wr(v2):7.1%}")
    print(f"{'제외된 상승장':14}{len(excluded):6}{_st.mean(excluded):+10.4f}{_wr(excluded):7.1%}")
    print(f"\n개선: net {_st.mean(v1):+.4f}→{_st.mean(v2):+.4f} ({_st.mean(v2)-_st.mean(v1):+.4f}) "
          f"승률 {_wr(v1):.1%}→{_wr(v2):.1%}")

    # v2 vs 매칭 random(비-상승장 진입일) + WF + 비용 스트레스
    keep_dates = set(d for r, _, d in rows if r <= bull_cut)
    pool = [(b, i) for b in series.values() for i in range(len(b["dates"]) - HOLD - 1) if b["dates"][i] in keep_dates]
    stress = {}
    for name, rt in COST_LEVELS.items():
        v2c = []
        for e in bb:
            b = series.get(e["stock_code"])
            if b is None:
                continue
            reg = _regime(idx_dates, idx, e["date"])
            if reg is None or reg > bull_cut:
                continue
            n = _fwd(b, e["date"], rt)
            if n is not None:
                v2c.append(n)
        stress[name] = round(_st.mean(v2c), 6)
    print(f"\n비용 스트레스: base {stress['base_20bps']:+.4f} / stress50 {stress['stress_50bps']:+.4f}")

    rng = _random.Random(SEED); rmeans = []
    for _ in range(N_RUNS):
        s = 0.0
        for _ in range(len(v2)):
            b, i = pool[rng.randrange(len(pool))]
            e0 = b["open"][i + 1]; xi = min(i + 1 + HOLD, len(b["dates"]) - 1)
            s += ((b["close"][xi] / e0 - 1) - COST_LEVELS["base_20bps"] / 10_000.0) if e0 > 0 else 0.0
        rmeans.append(s / len(v2))
    pv = empirical_p_value(_st.mean(v2), rmeans)
    print(f"v2 vs 매칭 random(비상승장): pct={pv['percentile']} p={pv['p_value']} (med={pv['random_median']:+.4f})")

    v2sorted = sorted([(d, n) for r, n, d in rows if r <= bull_cut])
    mid = len(v2sorted) // 2
    fh = _st.mean([n for _, n in v2sorted[:mid]]); sh = _st.mean([n for _, n in v2sorted[mid:]])
    print(f"walk-forward: 전반 {fh:+.4f} / 후반 {sh:+.4f}")

    improved = _st.mean(v2) > _st.mean(v1) and _wr(v2) > _wr(v1)
    passed = improved and (pv["percentile"] or 0) >= 90 and fh > 0 and sh > 0 and stress["stress_50bps"] > 0
    verdict = ("V2 SHADOW 유망 — 상승장 제외로 개선(forward 검증 필요, live 금지)" if passed else
               "V2 개선 있으나 약함 — shadow 관찰" if improved else "V2 개선 없음 — 필터 채택 안 함")
    print(f"\nVERDICT: {verdict}")
    log_experiment({"hypothesis_id": "kr_buyback_v2_regime_shadow", "status": "v2_shadow" if improved else "no_effect",
                    "v1_net": round(_st.mean(v1), 6), "v2_net": round(_st.mean(v2), 6),
                    "v1_winrate": round(_wr(v1), 4), "v2_winrate": round(_wr(v2), 4),
                    "n_v2": len(v2), "n_excluded": len(excluded), "percentile": pv["percentile"], "p": pv["p_value"],
                    "wf_first": round(fh, 6), "wf_second": round(sh, 6), "cost_stress": stress,
                    "data_quality": "KRX PIT survivorship-free + EW 레짐", "verdict": verdict,
                    "note": "v1 동결. v2=상승장 제외 shadow. forward 검증 전 live 금지. 사전 경제가설 확인."})


if __name__ == "__main__":
    main()
