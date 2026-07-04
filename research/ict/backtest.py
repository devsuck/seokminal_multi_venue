"""ICT 전략 백테스트 — 실 15분봉. 매칭 random(같은 킬존 eligible·같은 거래수·보유) 대비.

진입 = model_a_entries의 i → i+1 시가 진입 근사(여기선 c[i]→c[i+H] 종가기반, 보수).
random baseline = 킬존 eligible에서 랜덤 진입 동일수·동일 보유. empirical p-value.
"""
from __future__ import annotations

import statistics as _st

from research.ict.strategy import model_a_entries
from research.validation.baselines import empirical_p_value, random_same_frequency

HOLD = 8            # 15m*8 = 2시간 보유
COST_BPS = 5.0      # US 대형주 편도 근사
TRADE_SIZE = 1.0
N_RUNS = 500
SEED = 42


def _net(closes: list[float], entries: list[int], hold: int) -> tuple[float, int]:
    from research.validation.engine import simulate_fixed_hold_longs
    trades = simulate_fixed_hold_longs(closes, entries, [hold] * len(entries), TRADE_SIZE, COST_BPS)
    return sum(t["pnl"] for t in trades), len(trades)


def backtest_symbol(bars: dict, hold: int = HOLD) -> dict:
    c = bars["c"]
    sig = model_a_entries(bars)
    entries = [i for i in sig["entries"] if i + hold < len(c)]
    if len(entries) < 5:
        return {"n_entries": len(entries), "verdict": "UNDERPOWERED", "net": None,
                "percentile": None, "p": None, **{k: sig[k] for k in ("n_fvg", "n_sweep", "n_kz")}}

    strat_net, n = _net(c, entries, hold)
    eligible = [i for i in sig["eligible"] if i + hold < len(c)]
    rand = random_same_frequency(c, n_trades=len(entries), holding_periods=[hold],
                                 trade_size=TRADE_SIZE, cost_bps=COST_BPS,
                                 eligible_indices=eligible, n_runs=N_RUNS, seed=SEED)
    ev = empirical_p_value(strat_net, rand)
    mid = len(entries) // 2
    wf1 = _net(c, entries[:mid], hold)[0] if mid else 0.0
    wf2 = _net(c, entries[mid:], hold)[0] if len(entries) - mid else 0.0
    return {"n_entries": len(entries), "net": round(strat_net, 4),
            "percentile": ev["percentile"], "p": ev["p_value"], "rand_med": ev["random_median"],
            "wf_first": round(wf1, 4), "wf_second": round(wf2, 4),
            "n_fvg": sig["n_fvg"], "n_sweep": sig["n_sweep"], "n_kz": sig["n_kz"]}
