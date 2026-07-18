"""KR turn-of-month 포트폴리오 forward-test (모니터링/리포팅). 월별 EW 코호트 추적.

동결 config(tom_config) 사용. 매월 마지막 거래일 진입 → 4일 보유 완료 →
월 코호트 수익을 backtest envelope(월별 분포)와 비교.
CLI: PYTHONPATH=. python3 research/paper/tom_forward.py [--since YYYY-MM]
"""
from __future__ import annotations

import argparse
import bisect
import glob
import json
import os
import statistics as _st

from research.data.krx_api import build_series, market_dir
from research.paper import tom_config as CFG

LEDGER = os.path.join(os.path.dirname(__file__), "tom_forward_ledger.jsonl")
REPORT = os.path.join(os.path.dirname(__file__), "tom_forward_report.md")


def _liquid_universe():
    s = build_series("KOSDAQ", min_bars=CFG.LIQUID_FILTER["min_bars"])
    if glob.glob(os.path.join(market_dir("KOSPI"), "*.parquet")):
        s.update(build_series("KOSPI", min_bars=CFG.LIQUID_FILTER["min_bars"]))
    return [b for b in s.values() if len(b["close"]) >= CFG.LIQUID_FILTER["min_bars"]
            and _st.mean(b["tval"][-20:]) >= CFG.LIQUID_FILTER["min_tval_20d"]
            and b["marcap"][-1] >= CFG.LIQUID_FILTER["min_marcap"]]


def _month_end_days(liquid):
    all_dates = sorted(set().union(*[set(b["dates"]) for b in liquid])) if liquid else []
    return [d for i, d in enumerate(all_dates[:-1]) if d[:7] != all_dates[i + 1][:7]]


def _at(b, d):
    j = bisect.bisect_right(b["dates"], d) - 1
    return j if j >= 0 else None


def generate(since: str | None = None, write: bool = True) -> dict:
    liquid = _liquid_universe()
    tom_days = _month_end_days(liquid)
    cost_rt = CFG.COST_BASE_BPS / 1e4

    cohorts: dict[str, dict] = {}
    for d in tom_days:
        rs = []
        for b in liquid:
            k = _at(b, d)
            if k is None or k < 10 or k + CFG.HOLD_DAYS >= len(b["close"]):
                continue
            if b["close"][k] <= 0:
                continue
            rs.append(b["close"][k + CFG.HOLD_DAYS] / b["close"][k] - 1 - cost_rt)
        if rs:
            cohorts[d[:7]] = {"n": len(rs), "mean": round(_st.mean(rs), 6),
                              "median": round(_st.median(rs), 6)}

    means = [c["mean"] for c in cohorts.values()]
    srt = sorted(means)
    envelope = {
        "n_months": len(means),
        "mean_p10": round(srt[int(len(srt) * 0.1)], 6) if srt else None,
        "mean_p90": round(srt[int(len(srt) * 0.9)], 6) if srt else None,
        "mean_avg": round(_st.mean(means), 6) if means else None,
    }
    overall = {"n_months": len(means), "mean": round(_st.mean(means), 6) if means else None,
               "win_rate": round(sum(1 for x in means if x > 0) / len(means), 4) if means else None}

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
        f"# KR Turn-of-Month Portfolio Forward-Test — {r['version']}", "",
        f"> **{r['status']}** · ⚠️ PAPER ONLY, NO LIVE. config 동결(entry={r['config_frozen']['entry']}, hold={r['config_frozen']['hold']}d, cost={r['config_frozen']['cost_base']}bps)",
        "> ⚠️ backtest WF 후반이 전반보다 16배 약함(감쇠 의심) — forward가 진짜 시금석.", "",
        "## Overall (완결 월코호트)",
        f"- 월수={o['n_months']} · 평균 {o['mean']} · 승률 {o['win_rate']}", "",
        "## Envelope (월 코호트 평균 분포)",
        f"- 월수 {e['n_months']} · 평균 P10 {e['mean_p10']} / P90 {e['mean_p90']} · 평균 {e['mean_avg']}", "",
        "## Forward 월 코호트 (envelope 비교)",
    ]
    if r["forward_cohorts"]:
        for m, c in sorted(r["forward_cohorts"].items()):
            dev = ("BELOW_P10" if e["mean_p10"] is not None and c["mean"] < e["mean_p10"]
                   else "ABOVE_P90" if e["mean_p90"] is not None and c["mean"] > e["mean_p90"]
                   else "in_envelope")
            lines.append(f"- {m}: n={c['n']} mean={c['mean']} median={c['median']} → {dev}")
    else:
        lines.append("- (--since 지정 필요, 매월 신규 데이터 pull 후 재실행)")
    lines += ["", "## 운영 원칙", "- live 금지. entry/hold/cost/유동성필터 변경 금지. 분해결과로 튜닝 금지.",
              "- WF 감쇠 의심 → forward에서도 약화 지속되면 KILL 후보."]
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    open(REPORT, "w").write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="forward 월 시작 YYYY-MM")
    args = ap.parse_args()
    r = generate(args.since)
    o = r["overall"]
    print(f"report → {REPORT}")
    print(f"overall 월수={o['n_months']} 평균={o['mean']} 승률={o['win_rate']} | envelope 월수 {r['envelope']['n_months']}")


if __name__ == "__main__":
    main()
