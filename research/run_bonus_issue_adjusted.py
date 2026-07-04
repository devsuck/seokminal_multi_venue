"""무상증자 이벤트 스터디 — 수정주가(back-adjust) 적용. C 블로커 해결 검증.

raw에선 권리락 아티팩트로 -26%(가짜). 수정주가 적용 후 진짜 드리프트 보이는지.
전 종목 시계열에 무상증자 권리락 factor 적용 → 동일 백테스트(랜덤풀도 수정가).
실행: PYTHONPATH=. python3 research/run_bonus_issue_adjusted.py
"""
from __future__ import annotations

import bisect
import glob
import os
import random as _random
import statistics as _st

from research.agents.experiment_registry import log_experiment
from research.data.kr_adjustments import adjust_bars, load_factors
from research.data.kr_dart_events import load_events
from research.data.krx_api import build_series, market_dir
from research.validation.baselines import empirical_p_value

HOLD = 20
COST_LEVELS = {"base_20bps": 40.0, "stress_50bps": 100.0}
N_RUNS = 500
SEED = 42


def _series_adjusted():
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    fac = load_factors()
    n_adj = 0
    for code, b in s.items():
        if code in fac:
            s[code] = adjust_bars(b, fac[code]); n_adj += 1
    return s, n_adj, len(fac)


def _fwd(b, ed, rt):
    j = bisect.bisect_right(b["dates"], ed)
    if j >= len(b["dates"]):
        return None
    entry = b["open"][j]; xi = min(j + HOLD, len(b["dates"]) - 1)
    if entry <= 0 or xi <= j:
        return None
    return (b["close"][xi] / entry - 1) - rt / 10_000.0


def _eval(ev, series, rt):
    out = []
    for e in ev:
        b = series.get(e["stock_code"])
        if b is not None:
            r = _fwd(b, e["date"], rt)
            if r is not None:
                out.append((e["date"], r))
    return out


def main():
    print("=" * 74)
    print("무상증자 이벤트 — 수정주가(back-adjust) 적용")
    print("=" * 74)
    ev = load_events("bonus_issue")
    series, n_adj, n_fac = _series_adjusted()
    print(f"무상증자 {len(ev)} | KRX {len(series)}종목 | 권리락 조정 적용 {n_adj}종목 (factor {n_fac})")
    if n_fac == 0:
        print("조정계수 없음 — 배정비율 pull 먼저"); return
    pool = [(b, j) for b in series.values() for j in range(len(b["dates"]) - HOLD - 1)]

    results = {}
    for name, rt in COST_LEVELS.items():
        be = _eval(ev, series, rt)
        if not be:
            print("매칭 0"); return
        net = _st.mean([r for _, r in be])
        rng = _random.Random(SEED); rmeans = []
        for _ in range(N_RUNS):
            s = 0.0
            for _ in range(len(be)):
                b, j = pool[rng.randrange(len(pool))]
                e0 = b["open"][j + 1]; xi = min(j + 1 + HOLD, len(b["dates"]) - 1)
                s += ((b["close"][xi] / e0 - 1) - rt / 10_000.0) if e0 > 0 else 0.0
            rmeans.append(s / len(be))
        pv = empirical_p_value(net, rmeans)
        results[name] = {"n": len(be), "net": round(net, 6), "pct": pv["percentile"], "p": pv["p_value"], "med": pv["random_median"]}
        print(f"\n[{name}] 무상증자 n={len(be)} net={net:+.4f} vs random pct={pv['percentile']} p={pv['p_value']} (med={pv['random_median']:+.4f})")

    be = _eval(ev, series, COST_LEVELS["base_20bps"]); be.sort()
    mid = len(be) // 2
    fh = _st.mean([r for _, r in be[:mid]]); sh = _st.mean([r for _, r in be[mid:]])
    print(f"\nwalk-forward(base): 전반 {fh:+.4f} / 후반 {sh:+.4f}")

    base = results["base_20bps"]; pct = base["pct"] if base["pct"] is not None else 50.0
    passed = base["net"] > 0 and pct >= 95 and (base["p"] or 1) < 0.05 and fh > 0 and sh > 0 and results["stress_50bps"]["net"] > 0
    verdict = ("EDGE 후보 — 무상증자 양드리프트(수정주가·survivorship-free)" if passed else
               "WEAK — random 80~95pct" if base["net"] > 0 and pct >= 80 else
               "REJECT — 수정 후에도 엣지 없음(아티팩트였을 뿐)")
    print(f"\nVERDICT: {verdict}")
    print(f"(비교: raw는 -26% 아티팩트였음. 수정 후 net={base['net']:+.4f})")
    log_experiment({"hypothesis_id": "kr_bonus_issue_drift_v1_ADJ",
                    "status": "candidate" if passed else "weak" if (base["net"] > 0 and pct >= 80) else "rejected",
                    "trade_count": base["n"], "net_base": base["net"], "percentile": base["pct"], "p": base["p"],
                    "wf_first": round(fh, 6), "wf_second": round(sh, 6),
                    "cost_stress": {k: v["net"] for k, v in results.items()},
                    "data_quality": "KRX PIT + 무상증자 권리락 수정(back-adjust)", "verdict": verdict,
                    "note": "raw -26% 아티팩트 → 수정주가로 재검. 익일진입 20일보유"})


if __name__ == "__main__":
    main()
