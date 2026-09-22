"""Venue별 킬스위치 상태 저장/조회 + 조회용 API.

평가(드로다운 계산 → 자동킬 트리거)는 api_server/venue_risk.py가 담당 — 이
파일은 상태 저장(risk_kill.json, venue-keyed)과 순수 조회만 한다. 주문/봇
경로는 is_killed(venue)를 확인해서 신규 진입을 막는다(매도/청산은 안 막음).
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


def _load() -> dict:
    try:
        return json.loads(_KILL.read_text())
    except Exception:
        return {}


def _venue_meta(state: dict, venue: str) -> dict:
    v = state.get(venue)
    return v if isinstance(v, dict) else {"engaged": False, "reason": "", "ts": None}


def set_kill(venue: str, engaged: bool, reason: str = "") -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    state = _load()
    state[venue] = {
        "engaged": engaged, "reason": reason,
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
    tmp = _KILL.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(_KILL)


def venue_engaged(venue: str) -> bool:
    """자기 venue 킬 상태만 — _AGGREGATE OR 없음. 드로다운 자동판정의 sticky
    체크용(venue_risk.py가 씀) — 이미 killed면 재호출 안 하려고 raw 상태가 필요."""
    return bool(_venue_meta(_load(), venue).get("engaged"))


def is_killed(venue: str) -> bool:
    """게이팅용 — 자기 venue 킬 OR 전체(_AGGREGATE) 킬. 봇/주문 경로가 이걸 호출."""
    return venue_engaged(venue) or venue_engaged("_AGGREGATE")


class VenueRiskStatus(BaseModel):
    kill_engaged: bool
    kill_reason: str
    kill_ts: str | None = None
    current_equity_usd: float | None = None
    current_drawdown_pct: float | None = None
    max_drawdown_limit_pct: float


class RiskStatus(BaseModel):
    venues: dict[str, VenueRiskStatus]
    limits: dict
    # --- back-compat top-level mirror for the pre-per-venue dashboard widget.
    # Real fix is a dashboard update (separate follow-up, different repo) — this
    # keeps the existing emergency-stop control honest in the meantime. ---
    kill_engaged: bool = False
    kill_reason: str = ""
    current_drawdown_pct: float | None = None
    max_drawdown_limit_pct: float | None = None
    drawdown_breached: bool = False


class KillRequest(BaseModel):
    engaged: bool
    reason: str = "manual"
    venue: str = "_AGGREGATE"


@router.get("/status", response_model=RiskStatus)
def risk_status() -> RiskStatus:
    from live_engine.risk_guard import RiskConfig
    from api_server import venue_risk
    cfg = RiskConfig.from_env()
    state = _load()
    venues = {}
    for v in (*venue_risk.VENUES, "_AGGREGATE"):
        meta = _venue_meta(state, v)
        hist = venue_risk.history(v)
        dd = venue_risk.drawdown_pct(v, hist[-1]) if hist else None
        venues[v] = VenueRiskStatus(
            kill_engaged=venue_engaged(v), kill_reason=meta.get("reason", ""), kill_ts=meta.get("ts"),
            current_equity_usd=hist[-1] if hist else None,
            current_drawdown_pct=dd,
            max_drawdown_limit_pct=venue_risk.max_dd_limit(v),
        )
    any_killed = any(v.kill_engaged for v in venues.values())
    kill_reason = next((v.kill_reason for v in venues.values() if v.kill_engaged), "")
    worst = min(venues.values(), key=lambda v: v.current_drawdown_pct if v.current_drawdown_pct is not None else 0.0)
    return RiskStatus(
        venues=venues,
        limits={
            "max_order_qty": cfg.max_order_qty,
            "max_order_notional": cfg.max_order_notional,
            "max_position_qty": cfg.max_position_qty,
            "daily_loss_limit": cfg.daily_loss_limit,
        },
        kill_engaged=any_killed,
        kill_reason=kill_reason,
        current_drawdown_pct=worst.current_drawdown_pct,
        max_drawdown_limit_pct=worst.max_drawdown_limit_pct,
        drawdown_breached=any_killed,
    )


@router.post("/kill")
def risk_kill(body: KillRequest) -> dict:
    set_kill(body.venue, body.engaged, body.reason)
    return {"venue": body.venue, "kill_engaged": body.engaged, "reason": body.reason}
