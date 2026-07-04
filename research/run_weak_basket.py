"""B — 약신호 분산 바스켓. 개별 WEAK(turn-of-month·gap-fill·crypto momentum)을 묶으면?

각 약신호 월수익 시계열 → 상관 → 등가중 바스켓 → 개별 vs 바스켓 Sharpe.
가설: 개별론 못써도 무상관이면 분산으로 쓸만해질까? (개별 기준 안 낮춤, 바스켓 전체 검증)
실행: PYTHONPATH=. python3 research/run_weak_basket.py
"""
from __future__ import annotations

import bisect
import datetime as _dt
import glob
import os
import statistics as _st

from research.data.intraday_store import load_df


def _date(ts):
    return _dt.datetime.fromtimestamp(int(ts), tz=_dt.timezone.utc).strftime("%Y-%m-%d")


def _ann_sharpe(m):
    v = list(m.values()) if isinstance(m, dict) else m
    return (_st.mean(v) * (12 ** 0.5) / _st.stdev(v)) if len(v) >= 2 and _st.stdev(v) > 1e-12 else 0.0


def _max_dd(v):
    eq, peak, worst = 1.0, 1.0, 0.0
    for r in v:
        eq *= (1 + r); peak = max(peak, eq); worst = min(worst, eq / peak - 1)
    return worst


def _corr(a, b):
    n = len(a)
    if n < 3:
        return 0.0
    ma, mb = _st.mean(a), _st.mean(b)
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (n - 1)
    sa, sb = _st.stdev(a), _st.stdev(b)
    return cov / (sa * sb) if sa > 1e-12 and sb > 1e-12 else 0.0


# ── 1. crypto momentum 월수익 ──
def crypto_mom_monthly():
    FUT = {"ES", "NQ", "YM", "RTY", "CL", "GC", "SI", "HG", "NG", "ZB", "ZN", "ZF", "ZT",
           "ZC", "ZS", "ZW", "ZL", "ZM", "ZQ", "UB", "HE", "LE", "PA", "PL", "KC", "SB",
           "CC", "CT", "HO", "RB", "EMD", "NKD"}
    coins = {}
    for p in sorted(glob.glob("data/intraday/*_1d.parquet")):
        s = os.path.basename(p).replace("_1d.parquet", "")
        if s in FUT:
            continue
        df = load_df(s, "1d")
        if len(df) >= 200:
            coins[s] = (df["close"].tolist(), df["ts_utc"].tolist())
    maxlen = max(len(c) for c, _ in coins.values())
    by_month = {}
    for t in range(31, maxlen - 7, 7):
        u = []
        for s, (c, ts) in coins.items():
            if t >= len(c) or t + 7 >= len(c) or c[t - 30] <= 0 or c[t] <= 0:
                continue
            u.append((c, t, c[t] / c[t - 30] - 1))
        if len(u) < 8:
            continue
        u.sort(key=lambda x: -x[2]); n_top = max(2, len(u) // 5)
        r = _st.mean([c[t + 7] / c[t] - 1 - 10 / 1e4 for c, t, _ in u[:n_top]])
        ym = _date(coins[list(coins)[0]][1][t])[:7]
        by_month.setdefault(ym, []).append(r)
    return {m: _st.mean(rs) for m, rs in by_month.items()}


# ── 2. US gap-fill 월수익 ──
def gap_fill_monthly():
    by_month = {}
    for p in sorted(glob.glob("data/intraday/*_15m.parquet")):
        df = load_df(os.path.basename(p).replace("_15m.parquet", ""), "15m")
        if len(df) < 2000:
            continue
        days = {}
        for ts, o, c in zip(df["ts_utc"].tolist(), df["open"].tolist(), df["close"].tolist()):
            d = _date(ts)
            if d not in days:
                days[d] = [o, c]
            days[d][1] = c
        ds = sorted(days)
        for i in range(1, len(ds)):
            o, c = days[ds[i]]; pc = days[ds[i - 1]][1]
            if o > 0 and pc > 0 and o / pc - 1 <= -0.005:
                by_month.setdefault(ds[i][:7], []).append(c / o - 1 - 5 / 1e4)
    return {m: _st.mean(rs) for m, rs in by_month.items()}


# ── 3. KR turn-of-month 월수익 ──
def kr_tom_monthly():
    from research.data.krx_api import build_series, market_dir
    s = build_series("KOSDAQ", min_bars=300)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=300))
    liquid = [b for b in s.values() if len(b["close"]) >= 300
              and _st.mean(b["tval"][-20:]) >= 1e9 and b["marcap"][-1] >= 5e10]
    all_dates = sorted(set().union(*[set(b["dates"]) for b in liquid]))
    tom = [all_dates[i] for i in range(len(all_dates) - 1) if all_dates[i][:7] != all_dates[i + 1][:7]]
    out = {}
    for d in tom:
        rs = []
        for b in liquid:
            k = bisect.bisect_right(b["dates"], d) - 1
            if k < 10 or k + 4 >= len(b["close"]) or b["close"][k] <= 0:
                continue
            rs.append(b["close"][k + 4] / b["close"][k] - 1 - 40 / 1e4)
        if rs:
            out[d[:7]] = _st.mean(rs)
    return out


def main():
    print("=" * 70)
    print("B — 약신호 분산 바스켓 (turn-of-month · gap-fill · crypto momentum)")
    print("=" * 70)
    sigs = {"kr_tom": kr_tom_monthly(), "gap_fill": gap_fill_monthly(), "crypto_mom": crypto_mom_monthly()}
    print("\n개별(전체):")
    for name, m in sigs.items():
        v = list(m.values())
        print(f"  {name:12} n={len(v):3} 연율 {_st.mean(v)*12:+.2%} Sharpe {_ann_sharpe(v):+.2f} MDD {_max_dd(v):+.1%}")

    common = sorted(set(sigs["kr_tom"]) & set(sigs["gap_fill"]) & set(sigs["crypto_mom"]))
    if len(common) < 6:
        print(f"\n공통월 {len(common)} — 바스켓 불가"); return
    aligned = {n: [sigs[n][m] for m in common] for n in sigs}
    print(f"\n공통 {len(common)}개월 ({common[0]}~{common[-1]}) 상관행렬:")
    ns = list(sigs)
    for i in range(len(ns)):
        for j in range(i + 1, len(ns)):
            print(f"  {ns[i]:10} vs {ns[j]:10} {_corr(aligned[ns[i]], aligned[ns[j]]):+.2f}")

    basket = [_st.mean([aligned[n][i] for n in ns]) for i in range(len(common))]
    print(f"\n등가중 바스켓: 연율 {_st.mean(basket)*12:+.2%} Sharpe {_ann_sharpe(basket):+.2f} MDD {_max_dd(basket):+.1%}")
    best = max(_ann_sharpe(aligned[n]) for n in ns)
    print(f"최고 개별(공통구간) Sharpe {best:+.2f} → 바스켓 {_ann_sharpe(basket):+.2f} "
          f"({'분산이득 O' if _ann_sharpe(basket) > best else '분산이득 미미/약신호는 약신호'})")


if __name__ == "__main__":
    main()
