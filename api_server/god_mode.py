"""God Mode 승급 3조건 심사 — Lv3(자가학습) 에이전트가 최근 실적 기준
paper→live 전환 자격을 갖췄는지 판정한다.

3조건 (전부 통과해야 eligible=True):
①최근 window_days일 순수익 > 벤치마크(SPY.ARCA/KOSPI.XKRX buy&hold)
②MDD ≤ 15%
③반으로 쪼갠 미니 워크포워드 — 후반 실현손익이 전반보다 안 나쁨

agent_store.read_cycles + agent_perf.compute_performance의 실현손익
이벤트만으로 재구성한다(별도 mark-to-market 데이터 없음). 데이터가
부족하면(윈도우 내 체결 없음, 벤치마크 조회 실패 등) 해당 조건은
fail-safe로 실패 처리한다 — 애매하면 승급 안 시킨다.
"""
from __future__ import annotations

import datetime as dt

from api_server import agent_store
from api_server.agent_perf import compute_performance

WINDOW_DAYS = 30
MDD_LIMIT_PCT = 15.0
_BENCHMARK_BY_MARKET = {"US": "SPY", "KR": "^KS11"}  # yfinance 심볼 (KOSPI 지수)


def _cycle_ts(cycle: dict) -> dt.datetime | None:
    raw = cycle.get("ts")
    if not raw:
        return None
    try:
        ts = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)


def _benchmark_return_pct(market: str, start: dt.date, end: dt.date) -> float | None:
    symbol = _BENCHMARK_BY_MARKET.get(market, "SPY")
    try:
        import yfinance as yf
        hist = yf.Ticker(symbol).history(
            start=start.isoformat(),
            end=(end + dt.timedelta(days=1)).isoformat(),
            auto_adjust=True,
        )["Close"].dropna()
    except Exception:  # noqa: BLE001
        return None
    if len(hist) < 2:
        return None
    base = float(hist.iloc[0])
    if not base:
        return None
    return (float(hist.iloc[-1]) - base) / base * 100


def _equity_curve(alloc: float, trades: list[dict]) -> list[float]:
    curve = [alloc]
    cum = alloc
    for t in trades:
        cum += t["realized_pnl"]
        curve.append(cum)
    return curve


def _mdd_pct(equity_curve: list[float]) -> float | None:
    if len(equity_curve) < 2:
        return None
    peak = equity_curve[0]
    mdd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            mdd = min(mdd, (e - peak) / peak * 100)
    return abs(mdd)


def evaluate(agent_id: str, window_days: int = WINDOW_DAYS) -> dict:
    """3조건을 심사해 eligibility 리포트를 반환한다. 승급 자체는 하지 않는다."""
    agent = agent_store.get_agent(agent_id)
    if agent is None:
        raise ValueError(f"agent not found: {agent_id!r}")

    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=window_days)

    cycles = [c for c in agent_store.read_cycles(agent_id, limit=100000)
              if (ts := _cycle_ts(c)) is not None and ts >= cutoff]
    perf = compute_performance(cycles)
    trades = [t for t in perf.trades if t["realized_pnl"] is not None]
    alloc = float(agent.get("account_alloc") or 0)

    conditions = []

    # ① 순수익 > 벤치마크 buy&hold
    net_pct = (perf.realized_pnl / alloc * 100) if alloc else None
    bench_pct = None
    if trades:
        start_ts = min(_cycle_ts(c) for c in cycles if _cycle_ts(c) is not None)
        bench_pct = _benchmark_return_pct(agent.get("market", "US"), start_ts.date(), now.date())
    c1_passed = net_pct is not None and bench_pct is not None and net_pct > bench_pct
    conditions.append({
        "key": "beats_benchmark",
        "label": f"최근 {window_days}일 순수익 > 벤치마크 매수보유",
        "passed": bool(c1_passed),
        "detail": (f"{net_pct:+.2f}% vs {bench_pct:+.2f}%"
                   if net_pct is not None and bench_pct is not None else "데이터 부족"),
    })

    # ② MDD ≤ 15%
    mdd = _mdd_pct(_equity_curve(alloc, trades)) if alloc else None
    c2_passed = mdd is not None and mdd <= MDD_LIMIT_PCT
    conditions.append({
        "key": "mdd_within_limit",
        "label": f"MDD ≤ {MDD_LIMIT_PCT:.0f}%",
        "passed": bool(c2_passed),
        "detail": (f"{mdd:.2f}%" if mdd is not None else "데이터 부족"),
    })

    # ③ 미니 워크포워드 — 반으로 쪼갠 후반이 전반보다 안 나쁨
    half_passed = None
    first_half_pnl = second_half_pnl = None
    if len(trades) >= 2:
        mid = len(trades) // 2
        first_half_pnl = round(sum(t["realized_pnl"] for t in trades[:mid]), 4)
        second_half_pnl = round(sum(t["realized_pnl"] for t in trades[mid:]), 4)
        half_passed = second_half_pnl >= first_half_pnl
    conditions.append({
        "key": "walk_forward_stable",
        "label": "미니 워크포워드 — 후반이 전반보다 안 나쁨",
        "passed": bool(half_passed),
        "detail": (f"전반 {first_half_pnl:+.2f} → 후반 {second_half_pnl:+.2f}"
                   if half_passed is not None else "데이터 부족 (윈도우 내 체결 2건 미만)"),
    })

    return {
        "agent_id": agent_id,
        "eligible": all(c["passed"] for c in conditions),
        "conditions": conditions,
        "window_days": window_days,
        "as_of": now.isoformat(),
    }
