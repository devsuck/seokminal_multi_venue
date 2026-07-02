"""가설: ORB + RVOL + VWAP 추세지속 (롱온리, 인트라데이).

⚠️ DORMANT 모듈 — 검증된 알파 아님. 임계값 최적화 금지(고정). 일봉 실행 차단.
분봉 데이터가 오면 즉시 판정 가능하게 대기.

진입(모두 충족): 진입창(개장 30~90분) & OR고 돌파 & VWAP 위 & RVOL>1.5 & EMA 상승.
청산: ATR 1R 스탑 / 2R 타겟 / 8봉 타임스탑 / VWAP 이탈 (event_backtester).
random 베이스라인: 동일 opportunity set(eligible=진입창 봉)에서 같은 거래수·holding 분포.
"""
from __future__ import annotations

from xgb_strategy.labeling import atr_pct
from research.data.intraday_store import load_ohlc_lists
from research.features.session import session_ids, minutes_since_open
from research.features.opening_range import opening_range
from research.features.vwap import session_vwap
from research.features.rvol import rvol as compute_rvol
from research.backtest.event_backtester import run_event_backtest
from research.validation.metrics import trade_metrics
from research.validation.baselines import random_same_frequency, empirical_p_value
from research.reports.alpha_report import build_report

INTRADAY_TFS = {"1m", "5m", "15m"}

# 고정 파라미터 (최적화 금지 — 1차 생존 판정용)
DEFAULTS = {
    "or_minutes": 30.0,
    "entry_from": 30.0,   # 개장 후 진입 허용 시작(분)
    "entry_to": 90.0,     # 진입 허용 끝(분)
    "rvol_min": 1.5,
    "ema_period": 20,
    "atr_period": 14,
    "stop_atr": 1.0,
    "target_atr": 2.0,
    "time_stop_bars": 8,
    "trade_size": 10.0,
}


class IntradayDataRequiredError(Exception):
    """일봉 등 비인트라데이 tf로 실행 시도 → ORB는 인트라데이 전용."""


def _ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    e = sum(values[:period]) / period
    out[period - 1] = e
    k = 2 / (period + 1)
    for i in range(period, len(values)):
        e = values[i] * k + e * (1 - k)
        out[i] = e
    return out


def generate_signals(ohlc: dict, params: dict) -> dict:
    """봉별 entry_signals(bool) + eligible_indices(opportunity set) + 보조 시리즈."""
    p = {**DEFAULTS, **params}
    ts, o, h, l, c, v = (ohlc["ts"], ohlc["open"], ohlc["high"], ohlc["low"],
                         ohlc["close"], ohlc["volume"])
    n = len(c)
    sids = session_ids(ts)
    mso = minutes_since_open(ts, sids)
    orr = opening_range(h, l, sids, mso, p["or_minutes"])
    vwap = session_vwap(h, l, c, v, sids)
    rv = compute_rvol(v, sids, mso)
    ema = _ema(c, int(p["ema_period"]))
    ap = atr_pct(h, l, c, int(p["atr_period"]))
    atr_abs = [(ap[i] * c[i]) if ap[i] is not None else None for i in range(n)]

    eligible: list[int] = []
    entry: list[bool] = [False] * n
    for i in range(n):
        in_window = p["entry_from"] <= mso[i] <= p["entry_to"]
        ready = (orr["or_high"][i] is not None and vwap[i] is not None
                 and rv[i] is not None and atr_abs[i] is not None
                 and ema[i] is not None and i > 0 and ema[i - 1] is not None)
        if not (in_window and ready):
            continue
        eligible.append(i)  # opportunity set (진입 가능 시점)
        cond = (c[i] > orr["or_high"][i] and c[i] > vwap[i]
                and rv[i] > p["rvol_min"] and ema[i] > ema[i - 1])
        entry[i] = bool(cond)
    return {"entry": entry, "eligible": eligible, "vwap": vwap, "atr_abs": atr_abs}


def evaluate_ohlc(ohlc: dict, params: dict | None = None, cost_bps: float = 5.0) -> dict:
    """ohlc dict 직접 평가(OOS 슬라이스 재사용용). 반환: {trades, eligible, closes, holds}."""
    p = {**DEFAULTS, **(params or {})}
    sig = generate_signals(ohlc, p)
    trades = run_event_backtest(
        ohlc["high"], ohlc["low"], ohlc["close"],
        sig["entry"], sig["atr_abs"],
        trade_size=p["trade_size"], cost_bps=cost_bps,
        stop_atr=p["stop_atr"], target_atr=p["target_atr"],
        time_stop_bars=int(p["time_stop_bars"]), vwap=sig["vwap"],
    )
    holds = [max(1, t["exit_idx"] - t["entry_idx"]) for t in trades] or [int(p["time_stop_bars"])]
    return {"trades": trades, "eligible": sig["eligible"], "closes": ohlc["close"], "holds": holds}


def run_hypothesis(
    symbol: str,
    tf: str = "15m",
    params: dict | None = None,
    n_runs: int = 500,
    seed: int = 42,
    cost_bps: float = 5.0,
    write_report: bool = True,
    keep_random: bool = False,
) -> dict:
    """ORB 가설 검증 실행. tf 비인트라데이 → raise. 데이터 없음 → BLOCKED 리포트."""
    if tf not in INTRADAY_TFS:
        raise IntradayDataRequiredError(
            f"ORB requires intraday tf {sorted(INTRADAY_TFS)}, got {tf!r}"
        )
    p = {**DEFAULTS, **(params or {})}
    ohlc = load_ohlc_lists(symbol, tf)
    if not ohlc["close"]:
        return _blocked(symbol, tf, "no intraday OHLCV — pull data first", write_report)

    ev = evaluate_ohlc(ohlc, p, cost_bps)
    trades, holds = ev["trades"], ev["holds"]
    strat = trade_metrics(trades)

    # random: 동일 opportunity set(eligible) / 같은 거래수 / holding 분포 / 비용
    rnd = random_same_frequency(
        ohlc["close"], n_trades=strat["num_trades"], holding_periods=holds,
        trade_size=p["trade_size"], cost_bps=cost_bps,
        eligible_indices=ev["eligible"], n_runs=n_runs, seed=seed,
    )
    pval = empirical_p_value(strat["total_pnl"], rnd)

    result = {
        "symbol": symbol, "tf": tf, "blocked": False,
        "strategy": strat, "random": pval,
        "eligible_count": len(ev["eligible"]),
        "exit_reasons": _reason_counts(trades),
    }
    if keep_random:
        result["random_stats"] = rnd
    if write_report:
        rep = build_report(
            name=f"orb_rvol_vwap_{symbol}_{tf}",
            hypothesis="ORB고 돌파 + RVOL>1.5 + VWAP위 + EMA상승 → 추세지속 (롱온리, 고정임계·미최적화)",
            universe=[symbol], timeframe=tf,
            cost={"cost_bps": cost_bps, "slippage_bps": 0, "spread_bps": 0, "effective_bps": cost_bps},
            strategy=strat, random_pval=pval,
            naive={"total_pnl": None, "note": "ORB는 buy&hold 비교 부적합 → random 분포가 주판정"},
            walk_forward_result={"summary": {}},
            is_harness_dryrun=False,
            extra={"eligible_count": len(sig["eligible"]), "exit_reasons": _reason_counts(trades),
                   "note": "DORMANT hypothesis. NOT validated alpha. fixed thresholds, no optimization."},
        )
        result["report"] = rep
    return result


def _reason_counts(trades: list[dict]) -> dict:
    out: dict[str, int] = {}
    for t in trades:
        out[t.get("exit_reason", "?")] = out.get(t.get("exit_reason", "?"), 0) + 1
    return out


def _blocked(symbol: str, tf: str, msg: str, write_report: bool) -> dict:
    res = {"symbol": symbol, "tf": tf, "blocked": True, "reason": msg,
           "verdict": "BLOCKED: requires intraday OHLCV"}
    if write_report:
        import json, os
        from research.reports.alpha_report import REPORT_DIR
        os.makedirs(REPORT_DIR, exist_ok=True)
        base = os.path.join(REPORT_DIR, f"orb_rvol_vwap_{symbol}_{tf}")
        with open(base + ".json", "w") as f:
            json.dump(res, f, indent=2)
        with open(base + ".md", "w") as f:
            f.write(f"# ORB — {symbol} {tf}\n\n**BLOCKED: requires intraday OHLCV.** {msg}\n")
    return res
