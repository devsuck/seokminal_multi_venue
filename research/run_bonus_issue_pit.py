"""KR 무상증자 이벤트 스터디 — PIT/survivorship-free (KRX 공식). C: 새 이벤트 연못.

가설: 무상증자 공시 = 주주친화 신호 → 발표후 양의 드리프트(buyback과 같은 호재 family).
공시 익일 시가 진입 · 20일 보유 · 매칭 random · 비용 스트레스 · buyback 대조.
실행: PYTHONPATH=. python3 research/run_bonus_issue_pit.py
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
N_RUNS = 500
SEED = 42


def _series():
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    return s


def _fwd(b, ed, rt):
    j = bisect.bisect_right(b["dates"], ed)
    if j >= len(b["dates"]):
        return None
    entry = b["open"][j]; xi = min(j + HOLD, len(b["dates"]) - 1)
    if entry <= 0 or xi <= j:
        return None
    return (b["close"][xi] / entry - 1) - rt / 10_000.0


def _eval(events, series, rt):
    out = []
    for e in events:
        b = series.get(e["stock_code"])
        if b is not None:
            r = _fwd(b, e["date"], rt)
            if r is not None:
                out.append((e["date"], r))
    return out


def main():
    print("=" * 74)
    print("KR 무상증자 이벤트 스터디 — PIT/survivorship-free (KRX 공식)")
    print("=" * 74)
    ev = load_events("bonus_issue")
    if not ev:
        print("bonus_issue 이벤트 없음 — pull 필요"); return
    series = _series()
    bb = load_events("buyback")
    pool = [(b, j) for b in series.values() for j in range(len(b["dates"]) - HOLD - 1)]
    print(f"무상증자 {len(ev)} / buyback(대조) {len(bb)} | KRX {len(series)}종목 | pool {len(pool)}")

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
        bbe = _eval(bb, series, rt); bnet = _st.mean([r for _, r in bbe]) if bbe else None
        results[name] = {"n": len(be), "net": round(net, 6), "pct": pv["percentile"], "p": pv["p_value"], "bb": round(bnet, 6) if bnet else None}
        print(f"\n[{name}] 무상증자 n={len(be)} net={net:+.4f} vs random pct={pv['percentile']} p={pv['p_value']} (med={pv['random_median']:+.4f}) | buyback ref {bnet:+.4f}" if bnet else "")

    be = _eval(ev, series, COST_LEVELS["base_20bps"]); be.sort()
    mid = len(be) // 2
    fh = _st.mean([r for _, r in be[:mid]]); sh = _st.mean([r for _, r in be[mid:]])
    print(f"\nwalk-forward(base): 전반 {fh:+.4f} / 후반 {sh:+.4f}")

    base = results["base_20bps"]; pct = base["pct"] if base["pct"] is not None else 50.0
    passed = base["net"] > 0 and pct >= 95 and (base["p"] or 1) < 0.05 and fh > 0 and sh > 0 and results["stress_50bps"]["net"] > 0
    verdict = ("EDGE 후보 — 무상증자 양드리프트 통과(PIT survivorship-free)" if passed else
               "WEAK — random 80~95pct" if base["net"] > 0 and pct >= 80 else
               "REJECT — 매칭 random·비용 못 넘음")
    print(f"\nVERDICT: {verdict}")
    log_experiment({"hypothesis_id": "kr_bonus_issue_drift_v1_PIT",
                    "status": "candidate" if passed else "weak" if (base["net"] > 0 and pct >= 80) else "rejected",
                    "hold_days": HOLD, "trade_count": base["n"], "net_base": base["net"], "percentile": base["pct"], "p": base["p"],
                    "buyback_ref": base["bb"], "wf_first": round(fh, 6), "wf_second": round(sh, 6),
                    "cost_stress": {k: v["net"] for k, v in results.items()},
                    "data_quality": "PIT + survivorship-free (KRX 스냅샷)", "verdict": verdict,
                    "note": "무상증자 익일진입 20일보유, 고정파라미터"})


if __name__ == "__main__":
    main()
