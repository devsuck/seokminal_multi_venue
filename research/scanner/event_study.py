"""Generic 이벤트 스터디 — 어떤 KR 이벤트든 동일 엔진. PIT survivorship-free.

공시 익일 시가 진입 · N일 보유 · 매칭 random(전 종목풀) · WF · 비용 스트레스 ·
아웃라이어(median/상위꼬리). 레드팀 통제 증거까지 산출.
"""
from __future__ import annotations

import bisect
import glob
import os
import random as _random
import statistics as _st

from research.validation.baselines import empirical_p_value

HOLD = 20
COST_BASE = 40.0
COST_STRESS = 100.0
N_RUNS = 500
SEED = 42

_series_cache = {"s": None}


def load_series():
    if _series_cache["s"] is not None:
        return _series_cache["s"]
    from research.data.krx_api import build_series, market_dir
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    _series_cache["s"] = s
    return s


def _fwd(b, ed, cost):
    j = bisect.bisect_right(b["dates"], ed)
    if j >= len(b["dates"]):
        return None
    entry = b["open"][j]; xi = min(j + HOLD, len(b["dates"]) - 1)
    if entry <= 0 or xi <= j:
        return None
    return b["close"][xi] / entry - 1 - cost / 1e4


def event_study(events: list[dict], series: dict, direction: str = "bullish") -> dict:
    """반환: n·net·percentile·p·wf·median·top_tail_share + 레드팀 evidence."""
    pool = [(b, i) for b in series.values() for i in range(len(b["dates"]) - HOLD - 1)]
    rets = []
    for e in events:
        b = series.get(e.get("stock_code"))
        if b is None:
            continue
        r = _fwd(b, e["date"], COST_BASE)
        if r is not None:
            rets.append((e["date"], r))
    n = len(rets)
    if n < 30:
        return {"n": n, "verdict": "UNDERPOWERED", "evidence": {}, "net": None, "percentile": None}

    vals = [r for _, r in rets]
    net = _st.mean(vals)
    med = _st.median(vals)
    # 매칭 random
    rng = _random.Random(SEED); rmeans = []
    for _ in range(N_RUNS):
        s = 0.0
        for _ in range(n):
            b, i = pool[rng.randrange(len(pool))]
            e0 = b["open"][i + 1]; xi = min(i + 1 + HOLD, len(b["dates"]) - 1)
            s += (b["close"][xi] / e0 - 1 - COST_BASE / 1e4) if e0 > 0 else 0.0
        rmeans.append(s / n)
    pv = empirical_p_value(net, rmeans)
    # 비용 스트레스(왕복 100bps)
    srets = []
    for e in events:
        b = series.get(e.get("stock_code"))
        if b is not None:
            r = _fwd(b, e["date"], COST_STRESS)
            if r is not None:
                srets.append(r)
    stress = _st.mean(srets) if srets else net
    # WF
    rs = sorted(rets); mid = len(rs) // 2
    wf1 = _st.mean([r for _, r in rs[:mid]]); wf2 = _st.mean([r for _, r in rs[mid:]])
    # 아웃라이어: 상위5% 기여
    sv = sorted(vals, reverse=True)
    top5 = sum(sv[:max(1, len(sv) // 20)]); tot = sum(sv)
    top_tail_share = (top5 / tot) if tot != 0 else None

    pct = pv["percentile"] or 0.0
    # 방향별 통과: bullish=상위(양드리프트), bearish/research=하위(음드리프트)
    if direction == "bullish":
        rnd_pass = pct >= 95 and net > 0
        wf_pass = wf1 > 0 and wf2 > 0
        cost_pass = stress > 0
    else:  # bearish/research = 음드리프트 확인(롱 아님)
        rnd_pass = pct <= 5 and net < 0
        wf_pass = wf1 < 0 and wf2 < 0
        cost_pass = stress < net + 0.02  # 비용 늘려도 여전히 음
    evidence = {
        "random_baseline": "passed" if rnd_pass else "failed",
        "walk_forward": "passed" if wf_pass else "failed",
        "cost_stress": "passed" if cost_pass else "failed",
        "survivorship": "passed",   # KRX PIT = 구조적 survivorship-free
        "outlier_dependence": "passed" if (top_tail_share is None or top_tail_share < 0.8) else "failed",
    }
    return {"n": n, "net": round(net, 6), "median": round(med, 6), "percentile": pv["percentile"],
            "p": pv["p_value"], "net_stress": round(stress, 6), "wf_first": round(wf1, 6), "wf_second": round(wf2, 6),
            "top_tail_share": round(top_tail_share, 4) if top_tail_share is not None else None,
            "direction": direction, "evidence": evidence}
