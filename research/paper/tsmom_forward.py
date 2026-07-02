"""TSMOM forward-test — shadow 원장 + 월간 리포트 (모니터링/리포팅 자동화만).

동결 config(tsmom_config) 사용. 실브로커 아닌 shadow: 저장 데이터로 동결전략 실행 →
가설 P&L. 월마다 최신 데이터 pull 후 실행 → 신규 월을 backtest envelope와 비교.
튜닝·config 변경 금지. Lv3 full 아님(모니터링/리포팅만).

CLI: PYTHONPATH=. python3 research/paper/tsmom_forward.py [--since YYYY-MM]
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import statistics as _st

from research.backtest.portfolio_backtester import run_portfolio, portfolio_metrics
from research.hypotheses.tsmom import build_panel, tsmom_weights, DEFAULTS
from research.data.futures_loader import ASSET_CLASS
from research.paper import tsmom_config as CFG

LEDGER = os.path.join(os.path.dirname(__file__), "tsmom_forward_ledger.jsonl")
REPORT = os.path.join(os.path.dirname(__file__), "tsmom_forward_report.md")


def panels():
    out = {}
    for s in CFG.UNIVERSE:
        p = build_panel(s)
        if len(p["dates"]) > CFG.PARAMS["lookback"] + CFG.PARAMS["vol_window"] + 30:
            out[s] = p
    return out


def trend_regime_score(pn: dict, date: str | None = None) -> dict:
    """레짐 점수: 시장별 |12mo momentum|/vol 평균 + 트렌딩 비율. 높을수록 TSMOM 유리.
    date=None → 각 시장 자기 최신봉(캘린더 불일치 방지)."""
    p = CFG.PARAMS
    scores = []
    for a, panel in pn.items():
        dates, close = panel["dates"], panel["close"]
        if date is None:
            j = len(dates) - 1
        else:
            j = bisect.bisect_right(dates, date) - 1
        if j < max(p["lookback"], p["vol_window"]):
            continue
        mom = close[dates[j]] / close[dates[j - p["lookback"]]] - 1.0
        rets = [close[dates[k]] / close[dates[k - 1]] - 1.0 for k in range(j - p["vol_window"] + 1, j + 1)]
        vol = _st.stdev(rets) * (252 ** 0.5) if len(rets) >= 2 else 0.0
        if vol > 1e-9:
            scores.append(abs(mom) / vol)
    if not scores:
        return {"regime_score": None, "trending_frac": None, "n": 0}
    return {"regime_score": round(_st.mean(scores), 3),
            "trending_frac": round(sum(1 for s in scores if s > 0.5) / len(scores), 3),
            "n": len(scores)}


def monthly_returns(daily, dates):
    by = {}
    for r, d in zip(daily, dates):
        by.setdefault(d[:7], []).append(r)
    out = {}
    for m, rs in by.items():
        t = 1.0
        for r in rs:
            t *= (1 + r)
        out[m] = round(t - 1, 6)
    return out


def backtest_envelope(pn: dict) -> dict:
    """검증 백테스트의 월수익 분포 = forward 비교용 봉투."""
    res = run_portfolio(pn, tsmom_weights, CFG.PARAMS, CFG.COST_BASE_BPS, CFG.REBALANCE_DAYS)
    mret = list(monthly_returns(res["daily_returns"], res["dates"]).values())
    srt = sorted(mret)
    return {
        "sharpe": res["metrics"]["sharpe"], "max_drawdown": res["metrics"]["max_drawdown"],
        "monthly_mean": round(_st.mean(mret), 6), "monthly_std": round(_st.stdev(mret), 6),
        "monthly_p10": round(srt[int(len(srt) * 0.1)], 6), "monthly_p90": round(srt[int(len(srt) * 0.9)], 6),
        "avg_turnover": res["avg_turnover"], "n_months": len(mret),
    }


def sleeve_contribution(pn: dict) -> dict:
    classes = {}
    for a in pn:
        classes.setdefault(ASSET_CLASS.get(a, "?"), []).append(a)
    out = {}
    for cls, syms in classes.items():
        m = run_portfolio({a: pn[a] for a in syms}, tsmom_weights, CFG.PARAMS,
                          CFG.COST_BASE_BPS, CFG.REBALANCE_DAYS)["metrics"]
        out[cls] = {"sharpe": m["sharpe"], "ann_return": m["ann_return"]}
    return out


def generate(since: str | None = None):
    pn = panels()
    last_date = max(max(p["dates"]) for p in pn.values())
    env = backtest_envelope(pn)
    regime = trend_regime_score(pn)  # 각 시장 자기 최신봉
    base = run_portfolio(pn, tsmom_weights, CFG.PARAMS, CFG.COST_BASE_BPS, CFG.REBALANCE_DAYS)
    stress = run_portfolio(pn, tsmom_weights, CFG.PARAMS, CFG.COST_STRESS_BPS, CFG.REBALANCE_DAYS)
    mret = monthly_returns(base["daily_returns"], base["dates"])
    sleeves = sleeve_contribution(pn)

    # forward 월(since 이후) = envelope 이탈 체크
    fwd = {m: v for m, v in mret.items() if since and m >= since}
    deviations = {m: ("BELOW_P10" if v < env["monthly_p10"] else "ABOVE_P90" if v > env["monthly_p90"] else "in_envelope")
                  for m, v in fwd.items()}

    report = {
        "version": CFG.VERSION, "status": CFG.STATUS, "as_of": last_date,
        "config_frozen": {"universe_n": len(pn), "params": CFG.PARAMS,
                          "rebalance_days": CFG.REBALANCE_DAYS,
                          "cost_base": CFG.COST_BASE_BPS, "cost_stress": CFG.COST_STRESS_BPS},
        "backtest_envelope": env,
        "cost": {"base_sharpe": base["metrics"]["sharpe"], "stress_sharpe": stress["metrics"]["sharpe"],
                 "avg_turnover": base["avg_turnover"], "cost_drag_base": base["cost_drag"],
                 "cost_drag_stress": stress["cost_drag"]},
        "trend_regime": regime,
        "sleeve_contribution": sleeves,
        "forward_months": fwd, "envelope_deviation": deviations,
        "baseline_ref": CFG.BASELINE,
    }
    _write_md(report)
    _append_ledger({"as_of": last_date, "regime_score": regime.get("regime_score"),
                    "trending_frac": regime.get("trending_frac"),
                    "base_sharpe": base["metrics"]["sharpe"], "forward_months": fwd})
    return report


def _append_ledger(entry: dict):
    with open(LEDGER, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _write_md(r: dict):
    env = r["backtest_envelope"]; c = r["cost"]; rg = r["trend_regime"]
    lines = [
        f"# TSMOM Forward-Test Report — {r['version']}",
        "",
        f"> **{r['status']}** · as of {r['as_of']} · ⚠️ PAPER ONLY, NO LIVE CAPITAL.",
        f"> config 동결(튜닝 금지): {r['config_frozen']['universe_n']}시장, {r['config_frozen']['params']}, "
        f"rebal {r['config_frozen']['rebalance_days']}d, cost {r['config_frozen']['cost_base']}/{r['config_frozen']['cost_stress']}bps",
        "",
        "## Backtest Envelope (forward 비교 기준)",
        f"- Sharpe {env['sharpe']} · maxDD {env['max_drawdown']} · 월수익 평균 {env['monthly_mean']} "
        f"std {env['monthly_std']} · P10 {env['monthly_p10']} / P90 {env['monthly_p90']}",
        "",
        "## 비용 / 턴오버",
        f"- base Sharpe {c['base_sharpe']} / 20bps stress {c['stress_sharpe']} · "
        f"avg turnover {c['avg_turnover']} · cost drag base {c['cost_drag_base']} / stress {c['cost_drag_stress']}",
        "",
        "## Trend Regime Score (높을수록 TSMOM 유리)",
        f"- regime_score {rg.get('regime_score')} · trending_frac {rg.get('trending_frac')} (n={rg.get('n')})",
        "",
        "## Sleeve Contribution",
        "| sleeve | sharpe | ann_ret |", "|---|---|---|",
    ]
    for cls, v in sorted(r["sleeve_contribution"].items(), key=lambda x: -(x[1]["sharpe"] or 0)):
        lines.append(f"| {cls} | {v['sharpe']} | {v['ann_return']} |")
    lines += ["", "## Forward Months (envelope 이탈)"]
    if r["forward_months"]:
        for m, v in sorted(r["forward_months"].items()):
            lines.append(f"- {m}: {v:+.4f} → {r['envelope_deviation'][m]}")
    else:
        lines.append("- (아직 forward 월 없음 — 월마다 최신 데이터 pull 후 재실행)")
    lines += ["", "## 운영 원칙", "- live capital 금지. sleeve/레짐필터/파라미터 변경 금지. 결과 후 튜닝 금지.",
              "- 레짐 의존은 reject 사유 아님(TSMOM 본질) — forward에서 관찰."]
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="forward 월 시작 YYYY-MM (envelope 이탈 체크)")
    args = ap.parse_args()
    r = generate(args.since)
    print(f"report → {REPORT}")
    print(f"as_of {r['as_of']} | envelope Sharpe {r['backtest_envelope']['sharpe']} "
          f"| regime {r['trend_regime'].get('regime_score')} | turnover {r['cost']['avg_turnover']}")


if __name__ == "__main__":
    main()
