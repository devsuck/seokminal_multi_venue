"""통합 리스크 상태 — 킬스위치(파일 영속) + drawdown 자동 차단.

RiskConfig(주문 한도)는 그대로. 여기선 런타임 킬스위치(재시작·브라우저 무관)와
최대낙폭(MDD) 초과 시 자동 킬을 담당. 봇/주문 경로가 is_killed()를 확인.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/risk", tags=["risk"])

_DATA = Path(os.environ.get("DART_BOT_DIR", "data"))
_KILL = _DATA / "risk_kill.json"


def _max_dd_limit() -> float:
    return float(os.environ.get("MAX_DRAWDOWN_PCT", "15"))  # peak 대비 -15%면 차단


def is_killed() -> bool:
    try:
        return bool(json.loads(_KILL.read_text()).get("engaged"))
    except Exception:
        return False


def set_kill(engaged: bool, reason: str = "") -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    _KILL.write_text(json.dumps({
        "engaged": engaged, "reason": reason,
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }))


def _kill_meta() -> dict:
    try:
        return json.loads(_KILL.read_text())
    except Exception:
        return {"engaged": False, "reason": "", "ts": None}


def _current_drawdown_pct() -> float | None:
    """Alpaca 페이퍼 equity의 peak 대비 현재 낙폭(%)."""
    key = os.environ.get("ALPACA_API_KEY", ""); sec = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not sec:
        return None
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetPortfolioHistoryRequest
        c = TradingClient(key, sec, paper=True)
        h = c.get_portfolio_history(GetPortfolioHistoryRequest(period="3M", timeframe="1D"))
        eq = [float(e) for e in (h.equity or []) if e and e > 0]
        if len(eq) < 2:
            return None
        peak = eq[0]; dd = 0.0
        for e in eq:
            peak = max(peak, e)
            dd = min(dd, (e - peak) / peak * 100)
        return round(dd, 2)
    except Exception:
        return None


class RiskStatus(BaseModel):
    kill_engaged: bool
    kill_reason: str
    kill_ts: str | None = None
    current_drawdown_pct: float | None = None
    max_drawdown_limit_pct: float
    drawdown_breached: bool
    limits: dict


class KillRequest(BaseModel):
    engaged: bool
    reason: str = "manual"


@router.get("/status", response_model=RiskStatus)
def risk_status() -> RiskStatus:
    from live_engine.risk_guard import RiskConfig
    cfg = RiskConfig.from_env()
    dd = _current_drawdown_pct()
    limit = _max_dd_limit()
    breached = dd is not None and dd <= -limit
    # 자동 킬: MDD 한도 초과면 즉시 차단
    if breached and not is_killed():
        set_kill(True, f"MDD {dd}% ≤ -{limit}% 자동 차단")
    meta = _kill_meta()
    return RiskStatus(
        kill_engaged=is_killed(), kill_reason=meta.get("reason", ""), kill_ts=meta.get("ts"),
        current_drawdown_pct=dd, max_drawdown_limit_pct=limit, drawdown_breached=breached,
        limits={
            "max_order_qty": cfg.max_order_qty,
            "max_order_notional": cfg.max_order_notional,
            "max_position_qty": cfg.max_position_qty,
            "daily_loss_limit": cfg.daily_loss_limit,
        },
    )


@router.post("/kill")
def risk_kill(body: KillRequest) -> dict:
    set_kill(body.engaged, body.reason)
    return {"kill_engaged": body.engaged, "reason": body.reason}
