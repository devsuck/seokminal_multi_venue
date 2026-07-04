"""buyback v2(레짐 필터) forward 모니터 — in-sample vs forward(OOS) 분리.

v2 = 상승장 이벤트 제외(하락+중립만). v1 동결, v2는 shadow.
등록일(FROZEN_DATE) 이후 이벤트 = 진짜 forward(OOS). 그것만 v2 검증. 이전 = in-sample(발견, 증거 아님).
forward가 in-sample 개선(v2>v1)을 재현하면 승격 후보. 실행: PYTHONPATH=. python3 research/paper/buyback_v2_forward.py
"""
from __future__ import annotations

import bisect
import glob
import os
import statistics as _st

FROZEN_DATE = "2026-07-03"   # v2 레짐필터 사전등록일
HOLD = 20
COST = 40.0
REG_LOOKBACK = 60


def _series():
    from research.data.krx_api import build_series, market_dir
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


def _fwd(b, ed):
    j = bisect.bisect_right(b["dates"], ed)
    if j >= len(b["dates"]):
        return None
    entry = b["open"][j]; xi = min(j + HOLD, len(b["dates"]) - 1)
    if entry <= 0 or xi <= j:
        return None
    return (b["close"][xi] / entry - 1) - COST / 10_000.0


def _regime(idx_dates, idx, ed):
    j = bisect.bisect_right(idx_dates, ed) - 1
    if j < REG_LOOKBACK:
        return None
    return idx[idx_dates[j]] / idx[idx_dates[j - REG_LOOKBACK]] - 1


def _seg(rows, bull_cut):
    """세그먼트 요약: v1(전체)·v2(비상승장) net·승률·n."""
    v1 = [n for _, _, n in rows]
    v2 = [n for _, r, n in rows if r <= bull_cut]
    def wr(v):
        return round(sum(1 for x in v if x > 0) / len(v), 4) if v else None
    return {"n_v1": len(v1), "n_v2": len(v2),
            "v1_net": round(_st.mean(v1), 6) if v1 else None, "v2_net": round(_st.mean(v2), 6) if v2 else None,
            "v1_winrate": wr(v1), "v2_winrate": wr(v2),
            "v2_improves": (bool(v1 and v2 and _st.mean(v2) > _st.mean(v1) and (wr(v2) or 0) > (wr(v1) or 0)))}


def generate(write: bool = False) -> dict:
    from research.data.kr_dart_events import load_events
    series = _series()
    bb = load_events("buyback")
    idx_dates, idx = _market_index(series)

    rows = []  # (date, regime, net)
    for e in bb:
        b = series.get(e["stock_code"])
        if b is None:
            continue
        reg = _regime(idx_dates, idx, e["date"])
        net = _fwd(b, e["date"])
        if reg is not None and net is not None:
            rows.append((e["date"], reg, net))
    regs = sorted(r for _, r, _ in rows)
    bull_cut = regs[2 * len(regs) // 3] if regs else 0.0

    insample = [r for r in rows if r[0] < FROZEN_DATE]
    forward = [r for r in rows if r[0] >= FROZEN_DATE]

    result = {
        "hypothesis_id": "kr_buyback_v2_regime_shadow", "status": "v2_shadow",
        "frozen_date": FROZEN_DATE, "bull_cutoff_60d_mktret": round(bull_cut, 4),
        "rule": "이벤트일 시장 60일수익 상위1/3(상승장) 제외 → 하락+중립만",
        "in_sample": _seg(insample, bull_cut),
        "forward": _seg(forward, bull_cut),
        "forward_note": ("forward 이벤트 0 — 등록 직후. 새 buyback 공시 쌓이면 채워짐."
                         if not forward else f"forward {len(forward)}건 누적 중"),
        "discipline": "v1 동결. forward가 in-sample 개선 재현해야 승격. 그 전 live/paper 금지.",
    }
    if write:
        import json
        p = os.path.join(os.path.dirname(__file__), "buyback_v2_forward_ledger.jsonl")
        with open(p, "a") as f:
            f.write(json.dumps({"in_sample": result["in_sample"], "forward": result["forward"]}, default=str) + "\n")
    return result


def main():
    import json
    print(json.dumps(generate(write=False), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
