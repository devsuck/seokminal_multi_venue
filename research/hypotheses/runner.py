"""제네릭 유니버스 러너 — 가설(signal 생성 함수)을 받아 검증.

모든 가설 공통: 롱온리, 이벤트 백테스트(ATR스탑/R타겟/타임스탑/VWAP이탈),
동일 opportunity set random 분포, pooled 집계, BH-FDR, OOS 2분할.
튜닝 금지·고정 파라미터. 판정 = pooled가 비용 후 random 분포를 이기는가.
"""
from __future__ import annotations

import json
import os
from typing import Callable

from xgb_strategy.labeling import atr_pct
from research.data.intraday_store import load_ohlc_lists, quality_report
from research.data.pull_intraday import DEFAULT_UNIVERSE
from research.features.session import session_ids, minutes_since_open
from research.features.vwap import session_vwap
from research.backtest.event_backtester import run_event_backtest
from research.validation.metrics import trade_metrics
from research.validation.baselines import random_same_frequency, empirical_p_value
from research.validation.multiple_testing import benjamini_hochberg, prob_at_least_one_fp
from research.reports.alpha_report import REPORT_DIR

TF = "15m"
COST_BPS = 5.0
N_RUNS = 500
SEED = 42
EXCEED_PCT = 95.0

# 공통 청산 파라미터(고정)
STOP_ATR = 1.0
TARGET_ATR = 2.0
TIME_STOP = 8
TRADE_SIZE = 10.0

# signal 함수 시그니처: (ohlc, feat, aux, params) -> {"entry": bool[], "eligible": int[]}
SignalFn = Callable[[dict, dict, dict, dict], dict]
AuxFn = Callable[[str, dict], dict]  # (symbol, ohlc) -> {name: aligned list}


def common_features(ohlc: dict, atr_period: int = 14) -> dict:
    h, l, c, v = ohlc["high"], ohlc["low"], ohlc["close"], ohlc["volume"]
    sids = session_ids(ohlc["ts"])
    mso = minutes_since_open(ohlc["ts"], sids)
    vwap = session_vwap(h, l, c, v, sids)
    ap = atr_pct(h, l, c, atr_period)
    atr_abs = [(ap[i] * c[i]) if ap[i] is not None else None for i in range(len(c))]
    return {"sids": sids, "mso": mso, "vwap": vwap, "atr_abs": atr_abs}


def _slice(d: dict, a: int, b: int) -> dict:
    return {k: (v[a:b] if isinstance(v, list) else v) for k, v in d.items()}


def _evaluate(ohlc: dict, aux: dict, signals_fn: SignalFn, params: dict, cost_bps: float = COST_BPS) -> dict:
    feat = common_features(ohlc)
    sig = signals_fn(ohlc, feat, aux, params)
    trades = run_event_backtest(
        ohlc["high"], ohlc["low"], ohlc["close"],
        sig["entry"], feat["atr_abs"], trade_size=TRADE_SIZE, cost_bps=cost_bps,
        stop_atr=STOP_ATR, target_atr=TARGET_ATR, time_stop_bars=TIME_STOP, vwap=feat["vwap"],
    )
    holds = [max(1, t["exit_idx"] - t["entry_idx"]) for t in trades] or [TIME_STOP]
    return {"trades": trades, "eligible": sig["eligible"], "holds": holds}


def run_universe(name: str, desc: str, signals_fn: SignalFn,
                 aux_fn: AuxFn | None = None, params: dict | None = None,
                 universe: list[str] | None = None) -> dict:
    syms = universe or DEFAULT_UNIVERSE
    params = params or {}
    per_symbol, pooled_trades, random_matrix, skipped = [], [], [], []
    oos_first, oos_second = [], []

    for sym in syms:
        ohlc = load_ohlc_lists(sym, TF)
        if not ohlc["close"]:
            skipped.append(sym)
            continue
        aux = aux_fn(sym, ohlc) if aux_fn else {}
        ev = _evaluate(ohlc, aux, signals_fn, params)
        strat = trade_metrics(ev["trades"])
        rnd = random_same_frequency(
            ohlc["close"], strat["num_trades"], ev["holds"],
            trade_size=TRADE_SIZE, cost_bps=COST_BPS,
            eligible_indices=ev["eligible"], n_runs=N_RUNS, seed=SEED,
        )
        pv = empirical_p_value(strat["total_pnl"], rnd)
        pooled_trades.extend(ev["trades"]); random_matrix.append(rnd)
        per_symbol.append({"symbol": sym, "num_trades": strat["num_trades"],
                           "total_pnl": strat["total_pnl"], "expectancy": strat["expectancy"],
                           "profit_factor": strat["profit_factor"], "win_rate": strat["win_rate"],
                           "percentile": pv["percentile"], "p_value": pv["p_value"],
                           "underpowered": strat["underpowered"]})
        n = len(ohlc["close"]); mid = n // 2
        oos_first.extend(_evaluate(_slice(ohlc, 0, mid), _slice(aux, 0, mid), signals_fn, params)["trades"])
        oos_second.extend(_evaluate(_slice(ohlc, mid, n), _slice(aux, mid, n), signals_fn, params)["trades"])

    pooled = trade_metrics(pooled_trades)
    pooled_random = [sum(col) for col in zip(*random_matrix)] if random_matrix else []
    ppv = empirical_p_value(pooled["total_pnl"], pooled_random)
    exceeders = [s for s in per_symbol if (s["percentile"] or 0) >= EXCEED_PCT]
    pvals = [s["p_value"] for s in per_symbol if s["p_value"] is not None]
    bh = benjamini_hochberg(pvals, alpha=0.1)
    m = len(per_symbol)
    fh, sh = trade_metrics(oos_first), trade_metrics(oos_second)
    verdict = _verdict(pooled, exceeders, bh, fh, sh)

    result = {
        "name": name, "hypothesis": desc, "tf": TF, "cost_bps": COST_BPS,
        "n_symbols": m, "skipped": skipped,
        "pooled": {"num_trades": pooled["num_trades"], "total_pnl": pooled["total_pnl"],
                   "expectancy": pooled["expectancy"], "profit_factor": pooled["profit_factor"],
                   "win_rate": pooled["win_rate"],
                   "percentile_vs_random": ppv["percentile"], "empirical_p_value": ppv["p_value"],
                   "random_median": ppv["random_median"]},
        "exceeders_95pct": {"count": len(exceeders), "symbols": [s["symbol"] for s in exceeders],
                            "expected_by_chance_1plus": round(prob_at_least_one_fp(m, 0.05), 3) if m else None},
        "bh_fdr_survivors": bh["n_survivors"],
        "oos": {"first_exp": fh["expectancy"], "second_exp": sh["expectancy"],
                "first_trades": fh["num_trades"], "second_trades": sh["num_trades"]},
        "per_symbol": sorted(per_symbol, key=lambda s: -(s["percentile"] or 0)),
        "verdict": verdict,
    }
    _write(name, result)
    return result


def _verdict(pooled, exceeders, bh, fh, sh) -> str:
    net = pooled["total_pnl"]; nex = len(exceeders)
    oos_ok = fh["expectancy"] > 0 and sh["expectancy"] > 0
    if net <= 0 and nex <= 2:
        return "REJECT — 엣지 없음(pooled 음수, 95pct 초과 ≤2 = 노이즈)"
    if net > 0 and nex >= 5 and bh["n_survivors"] >= 1 and oos_ok:
        return "CONDITIONAL EDGE 후보 — pooled 양수 + 다수 종목 + BH 생존 + OOS 양쪽 양수"
    if net <= 0 and nex >= 1:
        return "REJECT 일반 — pooled 음수, 일부만 양수 = 종목 과적합 의심"
    return "INCONCLUSIVE — 보류"


def _write(name: str, result: dict):
    os.makedirs(REPORT_DIR, exist_ok=True)
    safe = name.replace(" ", "_")
    with open(os.path.join(REPORT_DIR, f"{safe}.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)


def print_result(r: dict):
    p = r["pooled"]; ex = r["exceeders_95pct"]; o = r["oos"]
    print(f"\n### {r['name']} ({r['n_symbols']} syms)")
    print(f"  POOLED trades={p['num_trades']} pnl={p['total_pnl']} exp={p['expectancy']} "
          f"PF={p['profit_factor']} win={p['win_rate']}")
    print(f"  vs random pct={p['percentile_vs_random']} p={p['empirical_p_value']} (rand_med={p['random_median']})")
    print(f"  95pct: {ex['count']}/{r['n_symbols']} {ex['symbols']} (chance1+={ex['expected_by_chance_1plus']}) | BH={r['bh_fdr_survivors']}")
    print(f"  OOS first_exp={o['first_exp']} second_exp={o['second_exp']}")
    print(f"  VERDICT: {r['verdict']}")
