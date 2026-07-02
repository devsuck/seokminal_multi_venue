"""Pure KR Momentum — VQFM 첫 실험 (가격·시총 PIT만, survivorship-free).

월 리밸런스, 12-1 모멘텀(252d 룩백, 최근 21d 스킵) 상위 decile 롱, 1개월 보유,
매칭 random(같은 리밸일·같은 종목수·시점 universe) 분포. 고정 파라미터·미최적화.
실행: PYTHONPATH=. python3 research/run_kr_momentum.py
"""
from __future__ import annotations

import bisect
import random as _random
import statistics as _st
import glob, os

from research.data.krx_api import build_series, market_dir
from research.validation.baselines import empirical_p_value

LOOKBACK = 252
SKIP = 21
TOP_PCT = 0.10
MIN_TVAL = 1e9        # 20d 평균 거래대금 >= 10억 (유동성)
MIN_MCAP = 5e10       # 시총 >= 500억
COST_RT_BPS = 40.0    # 리밸런스 왕복(턴오버 100% 가정 근사)
N_RUNS = 500
SEED = 42


def _series():
    s = build_series("KOSDAQ", min_bars=LOOKBACK + 40)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=LOOKBACK + 40))
    return s


def _at(bars, date):
    """code 시계열에서 date의 인덱스(≤). 없으면 None."""
    j = bisect.bisect_right(bars["dates"], date) - 1
    return j if j >= 0 else None


def main():
    print("=" * 70)
    print("PURE KR MOMENTUM (12-1, 월리밸, top decile, PIT survivorship-free)")
    print("=" * 70)
    series = _series()
    all_dates = sorted(set().union(*[set(s["dates"]) for s in series.values()])) if series else []
    if len(all_dates) < LOOKBACK + 60:
        print(f"데이터 부족: {len(all_dates)}일 (5년 pull 필요)"); return
    print(f"종목 {len(series)} | 거래일 {len(all_dates)} ({all_dates[0]}~{all_dates[-1]})")

    # 월 첫 거래일 = 리밸런스일
    rebal = []
    seen = set()
    for d in all_dates:
        ym = d[:7]
        if ym not in seen:
            seen.add(ym); rebal.append(d)
    rebal = [d for d in rebal if all_dates.index(d) >= LOOKBACK + 5]  # 룩백 확보 후
    print(f"리밸런스 {len(rebal)}회 ({rebal[0]}~{rebal[-1]})")

    # 시점별 universe + 모멘텀
    def universe_and_mom(t):
        out = []
        for c, b in series.items():
            k = _at(b, t)
            if k is None or k < LOOKBACK or b["dates"][k] != t and (all_dates.index(t) - all_dates.index(b["dates"][k]) > 3):
                # t에 거래 없으면(정지 등) 3일 이내만 허용
                pass
            if k is None or k < LOOKBACK:
                continue
            # 유동성·시총·관리 게이트
            tv = _st.mean(b["tval"][k - 20:k]) if k >= 20 else 0
            mc = b["marcap"][k]
            if tv < MIN_TVAL or mc < MIN_MCAP or "관리" in b["sect"][k]:
                continue
            p0, ps, pl = b["close"][k], b["close"][k - SKIP], b["close"][k - LOOKBACK]
            if pl <= 0 or p0 <= 0:
                continue
            mom = ps / pl - 1  # 12-1: (t-21)/(t-252)
            out.append((c, mom, k))
        return out

    port_rets = []
    strat_dates = []
    for ri in range(len(rebal) - 1):
        t, tn = rebal[ri], rebal[ri + 1]
        uni = universe_and_mom(t)
        if len(uni) < 30:
            continue
        uni.sort(key=lambda x: -x[1])
        n_top = max(5, int(len(uni) * TOP_PCT))
        longs = uni[:n_top]
        rets = []
        for c, _, k in longs:
            b = series[c]
            kn = _at(b, tn)
            if kn is None or kn <= k:
                rets.append(-COST_RT_BPS / 10_000.0); continue  # 상장폐지 등 → 비용만(보수)
            rets.append(b["close"][kn] / b["close"][k] - 1 - COST_RT_BPS / 10_000.0)
        if rets:
            port_rets.append(_st.mean(rets)); strat_dates.append(t)

    if len(port_rets) < 6:
        print(f"리밸 성사 {len(port_rets)}회 — 데이터 부족"); return
    ann = _st.mean(port_rets) * 12
    vol = _st.stdev(port_rets) * (12 ** 0.5) if len(port_rets) >= 2 else 0
    sharpe = ann / vol if vol > 1e-9 else None
    total = 1.0
    for r in port_rets:
        total *= (1 + r)
    print(f"\n전략: 월평균 {_st.mean(port_rets):+.4f} | 연율 {ann:+.4f} | vol {vol:.4f} | Sharpe {sharpe} | 총 {total-1:+.4f} | 리밸 {len(port_rets)}")

    # 매칭 random: 같은 리밸일·같은 종목수, 랜덤 종목
    rng = _random.Random(SEED)
    rand_ann = []
    for _ in range(N_RUNS):
        prs = []
        for ri in range(len(rebal) - 1):
            t, tn = rebal[ri], rebal[ri + 1]
            uni = universe_and_mom(t)
            if len(uni) < 30:
                continue
            n_top = max(5, int(len(uni) * TOP_PCT))
            picks = rng.sample(uni, n_top)
            rr = []
            for c, _, k in picks:
                b = series[c]; kn = _at(b, tn)
                rr.append((b["close"][kn] / b["close"][k] - 1 - COST_RT_BPS / 10_000.0) if (kn and kn > k) else -COST_RT_BPS / 10_000.0)
            if rr:
                prs.append(_st.mean(rr))
        rand_ann.append(_st.mean(prs) * 12 if prs else 0)
    pv = empirical_p_value(ann, rand_ann)
    print(f"vs random(연율): pct={pv['percentile']} p={pv['p_value']} (rand_med={pv['random_median']:+.4f})")

    # walk-forward 2분할
    mid = len(port_rets) // 2
    fh = _st.mean(port_rets[:mid]) * 12; sh = _st.mean(port_rets[mid:]) * 12
    print(f"walk-forward(연율): 전반 {fh:+.4f} / 후반 {sh:+.4f}")

    powered = len(port_rets) >= 24
    passed = (ann > 0 and (pv["percentile"] or 0) >= 95 and (pv["p_value"] or 1) < 0.05 and fh > 0 and sh > 0)
    verdict = ("UNDERPOWERED — 리밸 부족(더 긴 데이터)" if not powered else
               "WATCHLIST 후보 — random·비용후 통과" if passed else
               "WEAK — random 80~95pct" if (ann > 0 and (pv["percentile"] or 0) >= 80) else
               "REJECT — 매칭 random·비용 못 넘음")
    print(f"\nVERDICT: {verdict}")

    from research.agents.experiment_registry import log_experiment
    log_experiment({"hypothesis_id": "kr_pure_momentum_v1", "status": "underpowered" if not powered else "watchlist" if passed else "rejected",
                    "n_rebal": len(port_rets), "ann_return": round(ann, 4), "sharpe": round(sharpe, 3) if sharpe else None,
                    "random_pct": pv["percentile"], "p": pv["p_value"], "wf_first": round(fh, 4), "wf_second": round(sh, 4),
                    "data_quality": "PIT + survivorship-free (KRX)", "verdict": verdict, "note": "12-1 모멘텀 월리밸 top decile, 고정파라미터"})


if __name__ == "__main__":
    main()
