"""XAU Session Confluence 백테스트 러너 — TradingView Strategy Tester 대조용.

저장된 XAU 인트라데이(15m 베이스)로 전략 상태머신(`research.xau_session.strategy.run`)을
돌려 트레이드를 얻고, equity 복리로 순차 sizing(riskPercent%)·비용(commission/slippage)을
적용해 통계(트레이드수/승률/Profit Factor/총손익)를 낸다. 이 수치를 유저의 TradingView
백테스트와 대조해 포팅 충실도를 검증(스펙 §6).

no-lookahead 리샘플: 60m 아시안레인지는 전략이 베이스 바에서 세션 중 hi/lo를 추적하므로
(60m highest==15m highest, 봉경계 무관) 별도 리샘플 불필요. 240m HTF 바이어스 필터(기본 OFF)만
`_resample_ohlc`로 만들고, 각 상위봉 바이어스는 봉 종료 ts에 태깅해 확정 후에만 참조.
"""
from __future__ import annotations

from research.xau_session.strategy import Config, Trade, run

INITIAL_EQUITY = 100_000.0
POINT_VALUE = 1.0            # XAU 스팟: 1 유닛 = $1/이동
COMMISSION_PER_CONTRACT = 2.5
SLIPPAGE_TICKS = 2.0
TICK_SIZE = 0.01            # ⚠️ 심볼별 mintick에 맞춰야 정밀 대조 (데이터소스 의존)


def _resample_ohlc(bars: dict, tf_seconds: int) -> dict:
    """베이스 바 → tf_seconds 버킷(UTC 경계 정렬). open=버킷 첫 시가, high/low=집계,
    close=마지막 종가, ts=버킷 종료(=start+tf_seconds, no-lookahead 참조용)."""
    ts_, o_, h_, l_, c_ = bars["ts"], bars["o"], bars["h"], bars["l"], bars["c"]
    out_ts, out_o, out_h, out_l, out_c = [], [], [], [], []
    cur_bucket = None
    for i in range(len(ts_)):
        b = (int(ts_[i]) // tf_seconds) * tf_seconds
        if b != cur_bucket:
            cur_bucket = b
            out_ts.append(b + tf_seconds)
            out_o.append(o_[i]); out_h.append(h_[i]); out_l.append(l_[i]); out_c.append(c_[i])
        else:
            out_h[-1] = max(out_h[-1], h_[i])
            out_l[-1] = min(out_l[-1], l_[i])
            out_c[-1] = c_[i]
    return {"ts": out_ts, "o": out_o, "h": out_h, "l": out_l, "c": out_c}


def _ema(values: list[float], length: int) -> list[float]:
    if not values:
        return []
    k = 2.0 / (length + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def build_htf_bias(bars: dict, tf_seconds: int = 240 * 60, ema_len: int = 50) -> dict:
    """240m 리샘플 → close vs EMA(ema_len) → bias(+1 bullish/-1 bearish), 봉 종료 ts 태깅."""
    htf = _resample_ohlc(bars, tf_seconds)
    ema = _ema(htf["c"], ema_len)
    bias = [1 if c > e else -1 for c, e in zip(htf["c"], ema)]
    return {"ts": htf["ts"], "bias": bias}


def _size_and_cost(
    t: Trade, equity: float, risk_percent: float, point_value: float,
    commission_per_contract: float, slippage_ticks: float, tick_size: float,
) -> tuple[float, float]:
    """트레이드 → (net_pnl, qty). qty=equity·risk%/100/(risk·point_value).
    slippage: 진입·청산 각 불리하게 → 유닛당 2·slip 차감. commission: 양방향 계약당."""
    risk = t.risk_per_unit
    qty = equity * risk_percent / 100.0 / (risk * point_value)
    slip = slippage_ticks * tick_size
    gross = t.direction * (t.exit_price - t.entry_price) * point_value
    gross -= 2.0 * slip * point_value                    # 진입+청산 슬리피지
    commission = commission_per_contract * qty * 2.0
    return gross * qty - commission, qty


def backtest(
    bars: dict, cfg: Config | None = None, *,
    initial_equity: float = INITIAL_EQUITY,
    point_value: float = POINT_VALUE,
    commission_per_contract: float = COMMISSION_PER_CONTRACT,
    slippage_ticks: float = SLIPPAGE_TICKS,
    tick_size: float = TICK_SIZE,
) -> dict:
    """전략 실행 → 복리 순차 sizing/비용 → 통계. 트레이드 리스트 포함."""
    cfg = cfg or Config()
    htf = build_htf_bias(bars) if cfg.filter_htf_bias else None
    trades = run(bars, cfg, htf)
    equity = initial_equity
    gross_win = gross_loss = 0.0
    wins = 0
    rows = []
    for t in trades:
        pnl, qty = _size_and_cost(t, equity, cfg.risk_percent, point_value,
                                  commission_per_contract, slippage_ticks, tick_size)
        equity += pnl
        if pnl > 0:
            wins += 1
            gross_win += pnl
        else:
            gross_loss += -pnl
        rows.append({"entry_ts": t.entry_ts, "exit_ts": t.exit_ts, "dir": t.direction,
                     "entry": t.entry_price, "exit": t.exit_price, "reason": t.exit_reason,
                     "qty": round(qty, 4), "pnl": round(pnl, 2)})
    n = len(trades)
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
    return {
        "n_trades": n,
        "wins": wins,
        "win_rate": round(wins / n, 4) if n else 0.0,
        "profit_factor": round(pf, 4) if pf != float("inf") else pf,
        "gross_win": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
        "net": round(equity - initial_equity, 2),
        "final_equity": round(equity, 2),
        "trades": rows,
    }


def load(symbol: str, base_tf: str = "15m") -> dict:
    """intraday_store에서 베이스 바 로드 → strategy 입력 dict(ts,o,h,l,c)."""
    from research.data.intraday_store import load_ohlc_lists
    d = load_ohlc_lists(symbol, base_tf)
    return {"ts": d["ts"], "o": d["open"], "h": d["high"], "l": d["low"], "c": d["close"]}


def main() -> None:
    """사용: python -m research.run_xau_session_backtest [SYMBOL] [TICK_SIZE]
    SYMBOL 미지정 시 xyz:GOLD/PAXG/GC/XAUUSD 순 자동탐색. TradingView가 OANDA:XAUUSD
    스팟이면 xyz:GOLD(24/7 연속)가 가장 가까운 대체, GC(6개월)는 교차대조용."""
    import sys
    from research.data.intraday_store import load_df
    candidates = ["xyz:GOLD", "PAXG", "GC", "XAUUSD", "GOLD"]
    argv = sys.argv[1:]
    symbol = argv[0] if argv else next((s for s in candidates if not load_df(s, "15m").empty), None)
    tick = float(argv[1]) if len(argv) > 1 else TICK_SIZE
    if symbol is None or load_df(symbol, "15m").empty:
        print("XAU 15m 데이터 없음. intraday_store에 xyz:GOLD/PAXG/GC 등 저장 후 재실행(맥).")
        print(f"  탐색 심볼: {candidates}  (직접 지정: python -m research.run_xau_session_backtest GC)")
        return
    rep = backtest(load(symbol), tick_size=tick)
    df = load_df(symbol, "15m")
    print(f"=== XAU Session Confluence 백테스트 ({symbol}, 15m, {len(df)}봉, tick={tick}) ===")
    for k in ("n_trades", "wins", "win_rate", "profit_factor", "gross_win", "gross_loss", "net", "final_equity"):
        print(f"  {k:14s}: {rep[k]}")
    print("  → TradingView Strategy Tester 결과와 대조(트레이드수/승률/PF/총손익).")
    print("  ⚠️ OANDA:XAUUSD 스팟과 데이터소스가 달라 트레이드 1:1 불일치 정상 — 통계적 근사가 목표.")


if __name__ == "__main__":
    main()
