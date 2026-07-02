"""실패 원인 분해 — 신규 전략 전에 이것만. gross vs net + exit 비중.

핵심 구분:
  gross positive + net negative → 비용/실행 문제(다른 처방: 지정가·롱홀드·저비용)
  gross negative              → 신호 자체 사망(타임프레임/자산군 전환)
결과를 registry에 rejected로 고정. 튜닝 금지.
"""
from __future__ import annotations

from research.data.pull_intraday import DEFAULT_UNIVERSE, LIQUID
from research.hypotheses.runner import _evaluate
from research.hypotheses import strategies as S
from research.strategies.orb_rvol_vwap import generate_signals as _orb_gen, DEFAULTS as _ORB_DEF
from research.data.intraday_store import load_ohlc_lists
from research.validation.metrics import trade_metrics
from research.agents.experiment_registry import log_experiment

GROSS_BPS = 0.0
NET_BPS = 5.0


def _orb_signal(ohlc, feat, aux, params):
    sig = _orb_gen(ohlc, {**_ORB_DEF, **params})
    return {"entry": sig["entry"], "eligible": sig["eligible"]}


HYPOTHESES = [
    ("orb_rvol_vwap", _orb_signal, None, DEFAULT_UNIVERSE),
    ("vwap_mean_reversion", S.vwap_mean_reversion, None, DEFAULT_UNIVERSE),
    ("orb_failed_reversal", S.orb_failed_reversal, None, DEFAULT_UNIVERSE),
    ("gap_continuation", S.gap_continuation, None, DEFAULT_UNIVERSE),
    ("atr_compression", S.atr_compression, None, DEFAULT_UNIVERSE),
    ("sector_relative_momentum", S.sector_relative_momentum, S.sector_aux, LIQUID),
]


def decompose(name, signals_fn, aux_fn, universe):
    gross_t, net_t, reasons = [], [], {}
    for sym in universe:
        ohlc = load_ohlc_lists(sym, "15m")
        if not ohlc["close"]:
            continue
        aux = aux_fn(sym, ohlc) if aux_fn else {}
        g = _evaluate(ohlc, aux, signals_fn, {}, cost_bps=GROSS_BPS)
        n = _evaluate(ohlc, aux, signals_fn, {}, cost_bps=NET_BPS)
        gross_t += g["trades"]; net_t += n["trades"]
        for t in g["trades"]:
            r = t.get("exit_reason", "?")
            reasons[r] = reasons.get(r, 0) + 1
    gm, nm = trade_metrics(gross_t), trade_metrics(net_t)
    total = sum(reasons.values()) or 1
    reason_pct = {k: round(v / total * 100, 1) for k, v in sorted(reasons.items(), key=lambda x: -x[1])}
    diag = ("SIGNAL DEAD (gross도 음수)" if gm["total_pnl"] <= 0
            else "COST/EXECUTION (gross 양수, net 음수)" if nm["total_pnl"] <= 0
            else "gross·net 양수(재검토)")
    return {"name": name, "trades": nm["num_trades"],
            "gross_pnl": gm["total_pnl"], "gross_exp": gm["expectancy"], "gross_pf": gm["profit_factor"],
            "net_pnl": nm["total_pnl"], "net_exp": nm["expectancy"],
            "exit_mix_pct": reason_pct, "diagnosis": diag}


def main():
    print("=" * 78)
    print("FAILURE DECOMPOSITION — gross vs net + exit mix (튜닝 금지, registry 고정)")
    print("=" * 78)
    for name, fn, aux, uni in HYPOTHESES:
        d = decompose(name, fn, aux, uni)
        print(f"\n### {name}  (trades={d['trades']})")
        print(f"  GROSS pnl={d['gross_pnl']:>12}  exp={d['gross_exp']:>8}  PF={d['gross_pf']}")
        print(f"  NET   pnl={d['net_pnl']:>12}  exp={d['net_exp']:>8}")
        print(f"  exit mix: {d['exit_mix_pct']}")
        print(f"  → {d['diagnosis']}")
        log_experiment({
            "hypothesis_id": name, "tf": "15m", "status": "rejected",
            "gross_pnl": d["gross_pnl"], "net_pnl": d["net_pnl"], "trade_count": d["trades"],
            "exit_mix_pct": d["exit_mix_pct"], "diagnosis": d["diagnosis"],
            "reason": "negative_after_costs / BH-FDR 0 / indistinguishable_from_random",
            "note": "fixed params, no tuning. 15m US large-cap long-only.",
        })
    print("\n→ registry 기록 완료: research/agents/experiment_registry.jsonl")


if __name__ == "__main__":
    main()
