"""전략 리스크조정 성과 → 투표 가중치 근거.

v1 정책: 손실전략(음 Sharpe)은 0표, 소표본은 수축(MIN_OBS=30). 순수 함수 위주라
테스트 용이. 실원장 조립은 `assemble_returns`(부분 커버리지, 정직하게 빈값 반환).
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path
from jarvis.fusion.types import StrategyPerf

# 소표본 수축 기준 — research.validation의 MIN_TRADES(30) 관례와 정합.
MIN_OBS = 30

_BUYBACK_LEDGER = "buyback_bot_positions.jsonl"


def risk_adjusted_score(returns: list[float]) -> dict:
    """순수 함수. 반환: {score, sharpe, volatility, observation_count, underpowered}.

    score = max(0, Sharpe) * min(1, n/MIN_OBS). 손실/무엣지 = ~0표.
    """
    n = len(returns)
    if n < 2:
        return {"score": 0.0, "sharpe": None, "volatility": None,
                "observation_count": n, "underpowered": True}
    from risk_analysis.metrics import compute_risk_metrics
    m = compute_risk_metrics(returns)
    sharpe = m.get("sharpe_ratio")
    vol = m.get("volatility")
    sharpe_eff = max(0.0, sharpe if sharpe is not None else 0.0)
    shrink = min(1.0, n / MIN_OBS)
    return {"score": round(sharpe_eff * shrink, 6), "sharpe": sharpe,
            "volatility": vol, "observation_count": n, "underpowered": n < MIN_OBS}


def perf_from_returns(strategy_id: str, returns: list[float], source: str) -> StrategyPerf:
    r = risk_adjusted_score(returns)
    return StrategyPerf(
        strategy_id=strategy_id, score=r["score"], sharpe=r["sharpe"],
        volatility=r["volatility"], observation_count=r["observation_count"],
        underpowered=r["underpowered"], source=source,
        detail={"min_obs": MIN_OBS})


def _read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def returns_from_buyback() -> list[float]:
    """buyback 페이퍼 원장 closed 포지션의 pnl_pct 시퀀스(입장일 순)."""
    rows = [r for r in _read_jsonl(state_path(_BUYBACK_LEDGER)) if r.get("status") == "closed"]
    rows.sort(key=lambda r: r.get("entry_date", ""))
    return [float(r["pnl_pct"]) for r in rows if r.get("pnl_pct") is not None]


def assemble_returns(strategy_id: str) -> tuple[list[float], str]:
    """전략 → (수익률 시퀀스, 출처). v1 부분 커버리지 — 미배선은 ([], 'no_returns')."""
    sid = strategy_id.lower()
    if "buyback" in sid:
        r = returns_from_buyback()
        if r:
            return r, "buyback_bot_positions"
    return [], "no_returns"


def perf_for(strategy_id: str) -> StrategyPerf:
    """실원장에서 성과 조립 → StrategyPerf. 수익률 없으면 0표(정직)."""
    returns, source = assemble_returns(strategy_id)
    return perf_from_returns(strategy_id, returns, source)
