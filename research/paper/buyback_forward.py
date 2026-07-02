"""KR buyback forward-test (모니터링/리포팅). 이벤트 코호트 월별 추적.

동결 config(buyback_config) 사용. 매월 신규 자사주 공시 → 20일 후 포워드수익 완료 →
월 코호트 중앙값/평균을 backtest envelope와 비교. 팻테일이라 중앙값이 주 지표.
CLI: PYTHONPATH=. python3 research/paper/buyback_forward.py [--since YYYY-MM]
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import statistics as _st

from research.data.krx_api import build_series, market_dir
from research.data.kr_dart_events import load_events
from research.paper import buyback_config as CFG
import glob

LEDGER = os.path.join(os.path.dirname(__file__), "buyback_forward_ledger.jsonl")
REPORT = os.path.join(os.path.dirname(__file__), "buyback_forward_report.md")


def _series():
    s = build_series("KOSDAQ", min_bars=30)
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=30))
    return s


def _ret(bars, event_date):
    j0 = bisect.bisect_right(bars["dates"], event_date) - 1
    i = j0 + 1
    if j0 < 0 or i >= len(bars["dates"]):
        return None
    entry = bars["open"][i]; xi = min(i + CFG.HOLD_DAYS, len(bars["dates"]) - 1)
    if entry <= 0 or xi <= i or xi < i + CFG.HOLD_DAYS:  # 완결된(20일 채운) 것만
        return None
    return (bars["close"][xi] / entry - 1) - CFG.COST_BASE_BPS / 10_000.0


def generate(since: str | None = None, write: bool = True) -> dict:
    series = _series()
    bb = load_events("buyback")
    # (event_month, net) — 20일 완결된 것만
    rows = []
    for e in bb:
        b = series.get(e["stock_code"])
        if b is None:
            continue
        r = _ret(b, e["date"])
        if r is not None:
            rows.append((e["date"][:7], r))
    by_month: dict = {}
    for m, r in rows:
        by_month.setdefault(m, []).append(r)

    # 월 코호트 중앙값/평균
    cohorts = {m: {"n": len(rs), "median": round(_st.median(rs), 6), "mean": round(_st.mean(rs), 6)}
               for m, rs in sorted(by_month.items())}
    med_list = [c["median"] for c in cohorts.values() if c["n"] >= 10]
    srt = sorted(med_list)
    envelope = {
        "n_months": len(med_list),
        "cohort_median_p10": round(srt[int(len(srt) * 0.1)], 6) if srt else None,
        "cohort_median_p90": round(srt[int(len(srt) * 0.9)], 6) if srt else None,
        "cohort_median_avg": round(_st.mean(med_list), 6) if med_list else None,
    }
    all_r = [r for _, r in rows]
    overall = {"n": len(all_r), "mean": round(_st.mean(all_r), 6) if all_r else None,
               "median": round(_st.median(all_r), 6) if all_r else None,
               "win_rate": round(sum(1 for x in all_r if x > 0) / len(all_r), 4) if all_r else None}

    fwd = {m: cohorts[m] for m in cohorts if since and m >= since}
    result = {"version": CFG.VERSION, "status": CFG.STATUS,
              "config_frozen": {"entry": CFG.ENTRY, "hold": CFG.HOLD_DAYS, "cost_base": CFG.COST_BASE_BPS},
              "overall": overall, "envelope": envelope, "cohorts": cohorts,
              "forward_cohorts": fwd, "baseline_ref": CFG.BASELINE}
    if write:
        _write_md(result)
        with open(LEDGER, "a") as f:
            f.write(json.dumps({"overall": overall, "envelope": envelope, "n_forward": len(fwd)}, default=str) + "\n")
    return result


def _write_md(r: dict):
    o = r["overall"]; e = r["envelope"]
    lines = [
        f"# KR Buyback Forward-Test — {r['version']}", "",
        f"> **{r['status']}** · ⚠️ PAPER ONLY, NO LIVE. config 동결(entry={r['config_frozen']['entry']}, hold={r['config_frozen']['hold']}d, cost={r['config_frozen']['cost_base']}bps)",
        "> ⚠️ 팻테일 — 중앙값이 주 지표(평균은 상위5%에 흔들림).", "",
        "## Overall (완결 코호트)",
        f"- n={o['n']} · 평균 {o['mean']} · **중앙값 {o['median']}** · 승률 {o['win_rate']}", "",
        "## Envelope (월 코호트 중앙값 분포)",
        f"- 월수 {e['n_months']} · 중앙값 P10 {e['cohort_median_p10']} / P90 {e['cohort_median_p90']} · 평균 {e['cohort_median_avg']}", "",
        "## Forward 월 코호트 (envelope 비교)",
    ]
    if r["forward_cohorts"]:
        for m, c in sorted(r["forward_cohorts"].items()):
            dev = ("BELOW_P10" if e["cohort_median_p10"] is not None and c["median"] < e["cohort_median_p10"]
                   else "ABOVE_P90" if e["cohort_median_p90"] is not None and c["median"] > e["cohort_median_p90"]
                   else "in_envelope")
            lines.append(f"- {m}: n={c['n']} median={c['median']} mean={c['mean']} → {dev}")
    else:
        lines.append("- (--since 지정 필요, 매월 신규 데이터 pull 후 재실행)")
    lines += ["", "## 운영 원칙", "- live 금지. entry/hold/cost/필터 변경 금지. 분해결과로 튜닝 금지.",
              "- 팻테일 → 분산 필수(한 종목 몰빵 금지), 충분한 거래수로 테일 실현.",
              "- 핵심 리스크 = timing sensitivity(다음날 시가 즉시 진입 가능한지 관찰, delayed면 엣지 소멸)."]
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    open(REPORT, "w").write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="forward 월 시작 YYYY-MM")
    args = ap.parse_args()
    r = generate(args.since)
    o = r["overall"]
    print(f"report → {REPORT}")
    print(f"overall n={o['n']} 중앙값={o['median']} 평균={o['mean']} 승률={o['win_rate']} | envelope 월수 {r['envelope']['n_months']}")


if __name__ == "__main__":
    main()
