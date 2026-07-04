"""위시리스트 4개 실데이터 검증 — 연속루프가 찾은 "실배선 가능" 후보.

1. crypto_weekend : 주말 저유동성 → 월요일 진입 반전 (HL 일봉)
2. us_turn_of_month: 월말 진입 4일 보유 (US 15m→일봉 집계)
3. kr_turn_of_month: 월말 진입 4일 보유 (KRX PIT)
4. kr_low_vol      : 저변동성 하위decile 롱 월리밸 (KRX PIT)
매칭 random + walk-forward. 4개 p값 BH-FDR(다중검정). 실행: PYTHONPATH=. python3 research/run_wishlist_real.py
"""
from __future__ import annotations

import datetime as _dt
import glob
import os
import random as _random
import statistics as _st

from research.agents.experiment_registry import log_experiment
from research.data.intraday_store import load_df
from research.validation.baselines import empirical_p_value
from research.validation.multiple_testing import benjamini_hochberg

N_RUNS = 500
SEED = 42


def _date(ts: int) -> str:
    return _dt.datetime.fromtimestamp(int(ts), tz=_dt.timezone.utc).strftime("%Y-%m-%d")


def _weekday(ts: int) -> int:
    return _dt.datetime.fromtimestamp(int(ts), tz=_dt.timezone.utc).weekday()


# ── 이벤트 풀링 검정(진입 인덱스 리스트 → 수익, 매칭 random) ──
def _pooled(assets: list[dict], entry_fn, hold: int, cost_rt: float, seed: int = SEED) -> dict:
    """assets: [{closes:[...], ts:[...]}]. entry_fn(asset)->진입 인덱스 리스트."""
    strat, per_asset = [], []
    for a in assets:
        c = a["closes"]
        ents = [i for i in entry_fn(a) if i + hold < len(c)]
        elig = [i for i in range(len(c) - hold)]
        rets = [c[i + hold] / c[i] - 1 - cost_rt for i in ents if c[i] > 0]
        strat += rets
        per_asset.append((c, len(ents), elig))
    if len(strat) < 30:
        return {"n": len(strat), "net": None, "pct": None, "p": None, "wf1": None, "wf2": None}
    smean = _st.mean(strat)
    rng = _random.Random(seed); rmeans = []
    for _ in range(N_RUNS):
        pool = []
        for c, k, elig in per_asset:
            if k == 0 or not elig:
                continue
            for i in rng.sample(elig, min(k, len(elig))):
                if c[i] > 0:
                    pool.append(c[i + hold] / c[i] - 1 - cost_rt)
        rmeans.append(_st.mean(pool) if pool else 0.0)
    ev = empirical_p_value(smean, rmeans)
    mid = len(strat) // 2
    return {"n": len(strat), "net": round(smean, 6), "pct": ev["percentile"], "p": ev["p_value"],
            "wf1": round(_st.mean(strat[:mid]), 6), "wf2": round(_st.mean(strat[mid:]), 6)}


def _last_tom_entries(a: dict) -> list[int]:
    """월 마지막 거래일 인덱스(다음날이 다른 달)."""
    ds = a["dates"]
    return [i for i in range(len(ds) - 1) if ds[i][:7] != ds[i + 1][:7]]


def _monday_entries(a: dict) -> list[int]:
    return [i for i, t in enumerate(a["ts"]) if _weekday(t) == 0]


# ── 데이터 로더 ──
def _crypto(n_coins: int = 18) -> list[dict]:
    out = []
    for p in sorted(glob.glob("data/intraday/*_1d.parquet")):
        sym = os.path.basename(p).replace("_1d.parquet", "")
        if sym in ("ES", "NQ", "YM", "RTY", "CL", "GC", "SI", "HG", "NG", "ZB", "ZN", "ZF", "ZT",
                   "ZC", "ZS", "ZW", "ZL", "ZM", "ZQ", "UB", "HE", "LE", "PA", "PL", "KC", "SB",
                   "CC", "CT", "HO", "RB", "EMD", "NKD"):  # 선물 제외 = 크립토만
            continue
        df = load_df(sym, "1d")
        if len(df) < 300:
            continue
        out.append({"closes": df["close"].tolist(), "ts": df["ts_utc"].tolist(),
                    "dates": [_date(t) for t in df["ts_utc"].tolist()]})
        if len(out) >= n_coins:
            break
    return out


def _us_daily() -> list[dict]:
    """US 15m → 일봉 집계(UTC date 종가)."""
    out = []
    for p in sorted(glob.glob("data/intraday/*_15m.parquet")):
        sym = os.path.basename(p).replace("_15m.parquet", "")
        df = load_df(sym, "15m")
        if len(df) < 2000:
            continue
        by_day: dict = {}
        for ts, cl in zip(df["ts_utc"].tolist(), df["close"].tolist()):
            by_day[_date(ts)] = cl   # 마지막 종가 = 일 종가
        days = sorted(by_day)
        out.append({"closes": [by_day[d] for d in days], "dates": days,
                    "ts": [int(_dt.datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=_dt.timezone.utc).timestamp()) for d in days]})
    return out


def _kr_assets():
    from research.data.krx_api import build_series, market_dir
    s = build_series("KOSDAQ", min_bars=300)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=300))
    return s


def _kr_liquid(series, min_tval=1e9, min_mcap=5e10) -> list[dict]:
    out = []
    for b in series.values():
        if len(b["close"]) < 300:
            continue
        # 유동성·시총 최근값 게이트
        if _st.mean(b["tval"][-20:]) < min_tval or b["marcap"][-1] < min_mcap:
            continue
        out.append({"closes": b["close"], "dates": b["dates"], "ts": []})
    return out


def _kr_low_vol(series, lookback=60, hold_months=1, cost_rt=40 / 1e4) -> dict:
    """월리밸: 저변동(하위decile) 롱 vs random decile."""
    all_dates = sorted(set().union(*[set(b["dates"]) for b in series.values()]))
    rebal, seen = [], set()
    for d in all_dates:
        if d[:7] not in seen:
            seen.add(d[:7]); rebal.append(d)
    import bisect
    def at(b, d):
        j = bisect.bisect_right(b["dates"], d) - 1
        return j if j >= 0 else None
    def universe(t):
        u = []
        for b in series.values():
            k = at(b, t)
            if k is None or k < lookback:
                continue
            if _st.mean(b["tval"][k - 20:k]) < 1e9 or b["marcap"][k] < 5e10:
                continue
            rets = [b["close"][j] / b["close"][j - 1] - 1 for j in range(k - lookback + 1, k + 1) if b["close"][j - 1] > 0]
            if len(rets) < lookback - 5:
                continue
            u.append((b, k, _st.stdev(rets)))
        return u
    port, rng = [], _random.Random(SEED)
    rand_series = [[] for _ in range(N_RUNS)]
    for ri in range(len(rebal) - 1):
        t, tn = rebal[ri], rebal[ri + 1]
        u = universe(t)
        if len(u) < 30:
            continue
        u.sort(key=lambda x: x[2])              # vol 오름차순
        n_top = max(5, len(u) // 10)
        def fwd(sub):
            rs = []
            for b, k, _ in sub:
                kn = at(b, tn)
                rs.append((b["close"][kn] / b["close"][k] - 1 - cost_rt) if (kn and kn > k) else -cost_rt)
            return _st.mean(rs) if rs else 0.0
        port.append(fwd(u[:n_top]))
        for run in range(N_RUNS):
            rand_series[run].append(fwd(rng.sample(u, n_top)))
    if len(port) < 12:
        return {"n": len(port), "net": None, "pct": None, "p": None, "wf1": None, "wf2": None}
    ann = _st.mean(port) * 12
    rand_ann = [_st.mean(r) * 12 for r in rand_series]
    ev = empirical_p_value(ann, rand_ann)
    mid = len(port) // 2
    return {"n": len(port), "net": round(ann, 6), "pct": ev["percentile"], "p": ev["p_value"],
            "wf1": round(_st.mean(port[:mid]) * 12, 6), "wf2": round(_st.mean(port[mid:]) * 12, 6)}


def _verdict(r: dict) -> str:
    if r["net"] is None:
        return "UNDERPOWERED"
    pct = r["pct"] or 0.0
    if r["net"] > 0 and pct >= 95 and (r["p"] or 1) < 0.05 and (r["wf1"] or 0) > 0 and (r["wf2"] or 0) > 0:
        return "EDGE 후보"
    if r["net"] > 0 and pct >= 80:
        return "WEAK"
    return "REJECT"


def main():
    print("=" * 74)
    print("위시리스트 4개 실데이터 검증 (매칭 random + BH-FDR)")
    print("=" * 74)
    results = {}

    cr = _crypto()
    print(f"\n[1] crypto_weekend — 코인 {len(cr)} (월요일 진입 2일 보유)")
    results["crypto_weekend_reversion_v1"] = _pooled(cr, _monday_entries, hold=2, cost_rt=10 / 1e4)

    us = _us_daily()
    print(f"[2] us_turn_of_month — 종목 {len(us)} (월말 진입 4일 보유)")
    results["us_turn_of_month_v1"] = _pooled(us, _last_tom_entries, hold=4, cost_rt=5 / 1e4)

    print("[3][4] KRX 로딩...")
    series = _kr_assets()
    krl = _kr_liquid(series)
    print(f"    KR 유동종목 {len(krl)} / 전체 {len(series)}")
    results["kr_turn_of_month_v1"] = _pooled(krl, _last_tom_entries, hold=4, cost_rt=40 / 1e4)
    results["kr_low_vol_anomaly_v1"] = _kr_low_vol(series)

    print("\n" + "-" * 74)
    pvals, ids = [], []
    for hid, r in results.items():
        v = _verdict(r)
        net = f"{r['net']:+.4%}" if r["net"] is not None else "—"
        print(f"{hid:28} n={r['n']:5} net={net:>9} pct={r['pct']} p={r['p']} wf={r['wf1']}/{r['wf2']} → {v}")
        if r["p"] is not None:
            pvals.append(r["p"]); ids.append(hid)
        log_experiment({"hypothesis_id": hid + "_REAL", "status": "candidate" if v == "EDGE 후보" else "weak" if v == "WEAK" else "rejected" if v == "REJECT" else "underpowered",
                        "n": r["n"], "net": r["net"], "percentile": r["pct"], "p": r["p"],
                        "wf_first": r["wf1"], "wf_second": r["wf2"], "verdict": v,
                        "data_quality": "real (HL/US15m/KRX PIT)", "note": "위시리스트 실배선 검증, 고정파라미터"})

    if pvals:
        bh = benjamini_hochberg(pvals, alpha=0.1)
        print("\nBH-FDR(다중검정, α=0.1):")
        for i, hid in enumerate(ids):
            print(f"  {hid:28} p={pvals[i]} survivor={bh['survivors'][i]}")
        print(f"  → 생존 {bh['n_survivors']}/{len(pvals)} (threshold {bh['threshold']})")


if __name__ == "__main__":
    main()
