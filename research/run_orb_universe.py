"""ORB+RVOL+VWAP 유니버스 레벨 판정 (본판).

per-symbol winner 찾기 ❌ → universe-level aggregate ⭕.
질문: ORB가 전체 유니버스에서 비용 후 random distribution을 이기는가? 못 이기면 폐기.

⚠️ 튜닝 금지(고정 파라미터). TSLA 등 단일 종목은 의심 positive로만.

실행: PYTHONPATH=. python3 research/run_orb_universe.py
"""
from __future__ import annotations

import json
import os

from research.data.intraday_store import load_ohlc_lists, quality_report
from research.data.pull_intraday import DEFAULT_UNIVERSE
from research.strategies.orb_rvol_vwap import evaluate_ohlc, DEFAULTS
from research.validation.metrics import trade_metrics
from research.validation.baselines import random_same_frequency, empirical_p_value
from research.validation.multiple_testing import benjamini_hochberg, prob_at_least_one_fp
from research.reports.alpha_report import REPORT_DIR

TF = "15m"
COST_BPS = 5.0
N_RUNS = 500
SEED = 42
EXCEED_PCT = 95.0


def _slice(ohlc: dict, a: int, b: int) -> dict:
    return {k: v[a:b] for k, v in ohlc.items()}


def run(universe: list[str] | None = None) -> dict:
    syms = universe or DEFAULT_UNIVERSE
    per_symbol: list[dict] = []
    pooled_trades: list[dict] = []
    random_matrix: list[list[float]] = []   # [symbol][run]
    qa: list[dict] = []
    oos_first: list[dict] = []
    oos_second: list[dict] = []
    skipped: list[str] = []

    for sym in syms:
        ohlc = load_ohlc_lists(sym, TF)
        if not ohlc["close"]:
            skipped.append(sym)
            continue
        qa.append(quality_report(sym, TF))

        ev = evaluate_ohlc(ohlc, DEFAULTS, COST_BPS)
        strat = trade_metrics(ev["trades"])
        rnd = random_same_frequency(
            ohlc["close"], strat["num_trades"], ev["holds"],
            trade_size=DEFAULTS["trade_size"], cost_bps=COST_BPS,
            eligible_indices=ev["eligible"], n_runs=N_RUNS, seed=SEED,
        )
        pv = empirical_p_value(strat["total_pnl"], rnd)
        pooled_trades.extend(ev["trades"])
        random_matrix.append(rnd)
        per_symbol.append({
            "symbol": sym, "num_trades": strat["num_trades"],
            "total_pnl": strat["total_pnl"], "expectancy": strat["expectancy"],
            "profit_factor": strat["profit_factor"], "win_rate": strat["win_rate"],
            "percentile": pv["percentile"], "p_value": pv["p_value"],
            "underpowered": strat["underpowered"],
        })

        # OOS 안정성: 시간 2분할, 각 반 pooled에 기여
        n = len(ohlc["close"]); mid = n // 2
        fh = evaluate_ohlc(_slice(ohlc, 0, mid), DEFAULTS, COST_BPS)
        sh = evaluate_ohlc(_slice(ohlc, mid, n), DEFAULTS, COST_BPS)
        oos_first.extend(fh["trades"])
        oos_second.extend(sh["trades"])

    # ── 집계 ────────────────────────────────────────────────────────────
    pooled = trade_metrics(pooled_trades)
    # pooled random null = 런 인덱스별 종목합
    pooled_random = [sum(col) for col in zip(*random_matrix)] if random_matrix else []
    pooled_pv = empirical_p_value(pooled["total_pnl"], pooled_random)

    exceeders = [s for s in per_symbol if (s["percentile"] or 0) >= EXCEED_PCT]
    pvals = [s["p_value"] for s in per_symbol if s["p_value"] is not None]
    bh = benjamini_hochberg(pvals, alpha=0.1)

    m = len(per_symbol)
    fh_m = trade_metrics(oos_first)
    sh_m = trade_metrics(oos_second)

    verdict = _verdict(pooled, exceeders, m, bh, fh_m, sh_m)

    result = {
        "tf": TF, "cost_bps": COST_BPS, "n_runs": N_RUNS, "n_symbols": m,
        "skipped": skipped,
        "pooled": pooled_summary(pooled, pooled_pv),
        "exceeders_95pct": {"count": len(exceeders), "ratio": round(len(exceeders) / m, 3) if m else None,
                            "symbols": [s["symbol"] for s in exceeders],
                            "expected_by_chance_1plus": round(prob_at_least_one_fp(m, 0.05), 3)},
        "bh_fdr": {"n_survivors": bh["n_survivors"], "alpha": bh["alpha"]},
        "oos_stability": {
            "first_half": {"trades": fh_m["num_trades"], "total_pnl": fh_m["total_pnl"], "expectancy": fh_m["expectancy"]},
            "second_half": {"trades": sh_m["num_trades"], "total_pnl": sh_m["total_pnl"], "expectancy": sh_m["expectancy"]},
        },
        "per_symbol": sorted(per_symbol, key=lambda s: -(s["percentile"] or 0)),
        "verdict": verdict,
    }
    _write(result)
    return result


def pooled_summary(pooled: dict, pv: dict) -> dict:
    return {
        "num_trades": pooled["num_trades"], "total_pnl": pooled["total_pnl"],
        "expectancy": pooled["expectancy"], "profit_factor": pooled["profit_factor"],
        "win_rate": pooled["win_rate"], "per_trade_sharpe": pooled["per_trade_sharpe"],
        "percentile_vs_random": pv["percentile"], "empirical_p_value": pv["p_value"],
        "random_median": pv["random_median"],
    }


def _verdict(pooled, exceeders, m, bh, fh, sh) -> str:
    net = pooled["total_pnl"]
    nex = len(exceeders)
    oos_ok = (fh["expectancy"] > 0 and sh["expectancy"] > 0)
    if net <= 0 and nex <= 2:
        return "REJECT — 일반 ORB 엣지 없음(비용 후 pooled 음수, 95pct 초과 ≤2 = 노이즈)"
    if net > 0 and nex >= 5 and bh["n_survivors"] >= 1 and oos_ok:
        return "CONDITIONAL EDGE 후보 — pooled 양수 + 다수 종목 + BH 생존 + OOS 양쪽 양수"
    if net <= 0 and nex >= 1:
        return "REJECT 일반 — pooled 음수, 일부 종목만 양수 = 종목 과적합 의심"
    return "INCONCLUSIVE — 보류(기준 미충족, 추가 데이터/검토 필요)"


def _write(result: dict):
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(os.path.join(REPORT_DIR, "orb_universe.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)
    with open(os.path.join(REPORT_DIR, "orb_universe.md"), "w") as f:
        f.write(_md(result))


def _md(r: dict) -> str:
    p = r["pooled"]; ex = r["exceeders_95pct"]; oos = r["oos_stability"]
    lines = [
        "# ORB+RVOL+VWAP — Universe-Level Verdict",
        "",
        "> ⚠️ DORMANT hypothesis, fixed thresholds, NO optimization. Universe aggregate = 본판, per-symbol = 보조.",
        "",
        f"**심볼:** {r['n_symbols']}  |  tf: {r['tf']}  |  cost: {r['cost_bps']}bps  |  random runs: {r['n_runs']}",
        f"**skipped(데이터없음):** {', '.join(r['skipped']) or '없음'}",
        "",
        f"## 판정: {r['verdict']}",
        "",
        "## Pooled (전체 거래 풀 — 본판)",
        f"- trades: {p['num_trades']}  |  total PnL: {p['total_pnl']}  |  expectancy: {p['expectancy']}",
        f"- profit factor: {p['profit_factor']}  |  win rate: {p['win_rate']}  |  per-trade Sharpe: {p['per_trade_sharpe']}",
        f"- **vs random: percentile {p['percentile_vs_random']}, empirical p={p['empirical_p_value']}** (random median {p['random_median']})",
        "",
        "## 95pct 초과 종목",
        f"- count: {ex['count']}/{r['n_symbols']}  (ratio {ex['ratio']})  |  우연 기대(1+): {ex['expected_by_chance_1plus']}",
        f"- symbols: {', '.join(ex['symbols']) or '없음'}",
        f"- BH-FDR(α=0.1) 생존: {r['bh_fdr']['n_survivors']}",
        "",
        "## OOS 안정성 (시간 2분할 pooled)",
        f"- 전반: trades {oos['first_half']['trades']}, exp {oos['first_half']['expectancy']}",
        f"- 후반: trades {oos['second_half']['trades']}, exp {oos['second_half']['expectancy']}",
        "",
        "## Per-symbol (보조, percentile 내림차순)",
        "| symbol | trades | pnl | PF | win | pct | p |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in r["per_symbol"]:
        up = "⚠️" if s["underpowered"] else ""
        lines.append(f"| {s['symbol']}{up} | {s['num_trades']} | {s['total_pnl']} | "
                     f"{s['profit_factor']} | {s['win_rate']} | {s['percentile']} | {s['p_value']} |")
    return "\n".join(lines)


if __name__ == "__main__":
    r = run()
    p = r["pooled"]
    print("=" * 70)
    print(f"ORB UNIVERSE VERDICT ({r['n_symbols']} symbols, {r['tf']}, {r['cost_bps']}bps)")
    print("=" * 70)
    print(f"POOLED: trades={p['num_trades']} pnl={p['total_pnl']} exp={p['expectancy']} "
          f"PF={p['profit_factor']} win={p['win_rate']}")
    print(f"  vs random: percentile={p['percentile_vs_random']} p={p['empirical_p_value']} "
          f"(rand median={p['random_median']})")
    ex = r["exceeders_95pct"]
    print(f"95pct 초과: {ex['count']}/{r['n_symbols']} (우연기대 1+ = {ex['expected_by_chance_1plus']}) {ex['symbols']}")
    print(f"BH-FDR 생존: {r['bh_fdr']['n_survivors']}")
    o = r["oos_stability"]
    print(f"OOS: 전반 exp={o['first_half']['expectancy']} / 후반 exp={o['second_half']['expectancy']}")
    print(f"\nVERDICT: {r['verdict']}")
