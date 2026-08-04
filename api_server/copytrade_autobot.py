"""서버측 카피트레이딩 자동청산 봇.

브라우저 탭과 무관하게 uvicorn 프로세스 안에서 주기적으로 TP/SL 규칙을 페이퍼
포지션(Alpaca)에 적용해 청산한다. Alpaca 포지션이 유일한 진실 소스라 로컬
포지션 상태는 두지 않는다(dart_autobot과 다른 점).
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/copytrade/auto", tags=["copytrade-autobot"])

_DATA = Path(os.environ.get("DART_BOT_DIR", "data"))
_CFG = _DATA / "copytrade_autobot.json"
_LOG = _DATA / "copytrade_autobot_log.jsonl"

_DEFAULT = {
    "enabled": False, "interval_sec": 300,
    "tp_pct": 15.0, "sl_pct": 7.0, "last_run": None, "realized_pnl": 0.0,
}


def _load() -> dict:
    try:
        return {**_DEFAULT, **json.loads(_CFG.read_text())}
    except Exception:
        return dict(_DEFAULT)


def _save(cfg: dict) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    _CFG.write_text(json.dumps(cfg))


def _log_event(ev: dict) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    ev["ts"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    with _LOG.open("a") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def _recent_log(n: int = 40) -> list[dict]:
    try:
        lines = _LOG.read_text().strip().splitlines()
        return [json.loads(x) for x in lines[-n:]][::-1]
    except Exception:
        return []


def tick() -> dict:
    """1회 실행: TP/SL 임계 초과 페이퍼 포지션 전부 청산."""
    cfg = _load()
    if not cfg["enabled"]:
        return {"skipped": "disabled"}
    try:
        from api_server.risk_state import is_killed
        if is_killed():
            _log_event({"kind": "kill", "msg": "리스크 킬스위치 — 자동청산 중단"})
            return {"skipped": "kill_switch"}
    except Exception:
        pass

    key = os.environ.get("ALPACA_API_KEY", "")
    sec = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not sec:
        cfg["last_run"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        _save(cfg)
        return {"skipped": "no_alpaca_key"}

    tp = max(float(cfg.get("tp_pct", 15.0)), 0.1)
    sl = max(float(cfg.get("sl_pct", 7.0)), 0.1)
    from alpaca.trading.client import TradingClient
    client = TradingClient(api_key=key, secret_key=sec, paper=True)
    closed: list[dict] = []
    try:
        for p in client.get_all_positions():
            plpc = float(p.unrealized_plpc) * 100
            reason = None
            if plpc >= tp:
                reason = f"익절 +{plpc:.1f}%"
            elif plpc <= -sl:
                reason = f"손절 {plpc:.1f}%"
            if reason is None:
                continue
            try:
                pl_dollar = float(p.unrealized_pl)  # 청산 시점 Alpaca 평가손익 = 실현손익으로 확정
                client.close_position(p.symbol)
                cfg["realized_pnl"] = round(cfg.get("realized_pnl", 0.0) + pl_dollar, 4)
                closed.append({"ticker": p.symbol, "pl_pct": round(plpc, 2), "pl_dollar": round(pl_dollar, 2), "reason": reason})
                _log_event({"kind": "close", "ticker": p.symbol, "pl_pct": round(plpc, 2), "pl_dollar": round(pl_dollar, 2), "reason": reason})
            except Exception as e:  # noqa: BLE001 — 개별 실패는 다음 tick에서 재시도
                _log_event({"kind": "fail", "ticker": p.symbol, "msg": str(e)[:80]})
    except Exception as e:  # noqa: BLE001
        _log_event({"kind": "error", "msg": f"포지션 조회 실패: {str(e)[:80]}"})
        return {"error": str(e)[:80]}

    cfg["last_run"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    _save(cfg)
    return {"closed": closed, "count": len(closed)}


async def _loop() -> None:
    # uvicorn --reload 로 여러 번 뜰 수 있으니 예외는 삼키고 계속.
    while True:
        try:
            cfg = _load()
            interval = int(cfg.get("interval_sec", 300))
            if cfg.get("enabled"):
                await asyncio.to_thread(tick)
        except Exception:  # noqa: BLE001
            interval = 300
        await asyncio.sleep(max(interval, 60))


def start_loop() -> None:
    try:
        asyncio.get_event_loop().create_task(_loop())
    except RuntimeError:
        pass


# ── API ──────────────────────────────────────────────────────────────────────
class BotConfig(BaseModel):
    enabled: bool | None = None
    interval_sec: int | None = None
    tp_pct: float | None = None
    sl_pct: float | None = None


@router.get("/status")
def status() -> dict:
    cfg = _load()
    return {
        "enabled": cfg["enabled"], "interval_sec": cfg["interval_sec"],
        "tp_pct": cfg.get("tp_pct", 15.0), "sl_pct": cfg.get("sl_pct", 7.0),
        "last_run": cfg.get("last_run"), "realized_pnl": cfg.get("realized_pnl", 0.0),
        "log": _recent_log(40),
    }


@router.post("/config")
def set_config(body: BotConfig) -> dict:
    cfg = _load()
    if body.enabled is not None:
        cfg["enabled"] = body.enabled
    if body.interval_sec is not None:
        cfg["interval_sec"] = max(int(body.interval_sec), 60)
    if body.tp_pct is not None:
        cfg["tp_pct"] = max(float(body.tp_pct), 0.1)
    if body.sl_pct is not None:
        cfg["sl_pct"] = max(float(body.sl_pct), 0.1)
    _save(cfg)
    _log_event({"kind": "config", "enabled": cfg["enabled"], "tp_pct": cfg["tp_pct"], "sl_pct": cfg["sl_pct"]})
    return {"ok": True, **{k: cfg[k] for k in ("enabled", "interval_sec", "tp_pct", "sl_pct")}}


@router.post("/run-now")
def run_now() -> dict:
    """수동 1회 실행 (테스트용)."""
    return tick()
