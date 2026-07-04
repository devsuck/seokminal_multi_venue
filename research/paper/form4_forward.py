"""미국 내부자 오픈마켓 매수 drift 포워드 테스트 (OpenInsider 데이터).

가설: 임원/이사/10% 주주 오픈마켓 매수 공시(Form 4 P코드) →
      D+1 진입 → 20일 보유 → 양의 drift.
공시일(disclosure_date) 기준 — 시장이 정보를 아는 시점.
CLI: PYTHONPATH=. python3 research/paper/form4_forward.py
"""
from __future__ import annotations

import argparse
import bisect
import os
import statistics as _st
from datetime import datetime

HOLD_DAYS = 20
COST_BASE_BPS = 5
LEDGER = os.path.join(os.path.dirname(__file__), "form4_forward_ledger.jsonl")
REPORT = os.path.join(os.path.dirname(__file__), "form4_forward_report.md")


def _price_series(ticker: str) -> dict | None:
    try:
        import yfinance as yf
        df = yf.download(ticker, start="2020-01-01", auto_adjust=True, progress=False)
        if df.empty or len(df) < 20:
            return None
        # yfinance 1.4+ MultiIndex: columns = (field, ticker)
        cols = df.columns
        if hasattr(cols, "levels"):
            opens = df[("Open", ticker)].values
            closes = df[("Close", ticker)].values
        else:
            opens = df["Open"].values
            closes = df["Close"].values
        return {
            "dates": [d.strftime("%Y-%m-%d") for d in df.index],
            "open": [float(x) for x in opens],
            "close": [float(x) for x in closes],
        }
    except Exception:
        return None


def _ret(bars: dict, event_date: str) -> float | None:
    j0 = bisect.bisect_right(bars["dates"], event_date) - 1
    i = j0 + 1
    if j0 < 0 or i >= len(bars["dates"]):
        return None
    entry = bars["open"][i]
    xi = min(i + HOLD_DAYS, len(bars["dates"]) - 1)
    if entry <= 0 or xi <= i or xi < i + HOLD_DAYS:
        return None
    return (bars["close"][xi] / entry - 1) - COST_BASE_BPS / 10_000.0


def generate(since: str | None = None, write: bool = True) -> dict:
    from research.data.openinsider import load_events
    events = load_events(min_date="2022-01-01")

    _price_cache: dict[str, dict | None] = {}
    rows = []

    for e in events:
        ticker = e["ticker"]
        if ticker not in _price_cache:
            _price_cache[ticker] = _price_series(ticker)
        bars = _price_cache[ticker]
        if bars is None:
            continue
        r = _ret(bars, e["disclosure_date"])
        if r is not None:
            rows.append((e["disclosure_date"], r, ticker))

    by_month: dict = {}
    for d, r, _ in rows:
        by_month.setdefault(d[:7], []).append(r)

    cohorts = {m: {"n": len(rs), "median": round(_st.median(rs), 6), "mean": round(_st.mean(rs), 6)}
               for m, rs in sorted(by_month.items())}
    med_list = [c["median"] for c in cohorts.values() if c["n"] >= 5]
    srt = sorted(med_list)
    envelope = {
        "n_months": len(med_list),
        "cohort_median_p10": round(srt[int(len(srt) * 0.1)], 6) if srt else None,
        "cohort_median_p90": round(srt[int(len(srt) * 0.9)], 6) if srt else None,
        "cohort_median_avg": round(_st.mean(med_list), 6) if med_list else None,
    }
    all_r = [r for _, r, _ in rows]
    overall = {
        "n": len(all_r),
        "mean": round(_st.mean(all_r), 6) if all_r else None,
        "median": round(_st.median(all_r), 6) if all_r else None,
        "win_rate": round(sum(1 for x in all_r if x > 0) / len(all_r), 4) if all_r else None,
    }

    fwd = {m: cohorts[m] for m in cohorts if since and m >= since}
    result = {
        "version": "us_insider_buy_drift_v1",
        "status": "research",
        "data_source": "openinsider.com (Form 4 P-purchase, $10k+)",
        "config_frozen": {"entry": "D+1_open", "hold": HOLD_DAYS, "cost_base": COST_BASE_BPS},
        "overall": overall, "envelope": envelope, "cohorts": cohorts,
        "forward_cohorts": fwd, "rows": [(d, r) for d, r, _ in rows],
    }

    if write:
        import json
        os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
        with open(LEDGER, "a") as f:
            f.write(json.dumps({"ts": datetime.utcnow().isoformat(), "result": result}) + "\n")

    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="이후 코호트만 표시 (YYYY-MM)")
    args = ap.parse_args()
    r = generate(since=args.since, write=False)
    ov = r["overall"]
    print(f"n={ov['n']}  median={ov['median']}  mean={ov['mean']}  win_rate={ov['win_rate']}")
    env = r["envelope"]
    if env["n_months"] > 0:
        print(f"envelope n_months={env['n_months']} p10={env['cohort_median_p10']} p90={env['cohort_median_p90']} avg={env['cohort_median_avg']}")
    if r["cohorts"]:
        print("\n월별 코호트 (최근 12개월):")
        for m, c in list(r["cohorts"].items())[-12:]:
            print(f"  {m}: n={c['n']} median={c['median']:+.4f}")
