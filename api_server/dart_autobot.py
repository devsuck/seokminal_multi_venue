"""서버측 DART 기업행위 자동매매 봇.

브라우저 탭과 무관하게 uvicorn 프로세스 안에서 주기적으로 돈다. 자사주 취득·
소각(호재) 신규 공시를 KIS 모의로 매수. 상태·로그는 파일에 남겨 프론트가 조회.
개인 내부자 매매는 5영업일 지연이라 대상 아님(기업행위만).
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/dart/auto", tags=["dart-autobot"])

_DATA = Path(os.environ.get("DART_BOT_DIR", "data"))
_CFG = _DATA / "dart_autobot.json"
_LOG = _DATA / "dart_autobot_log.jsonl"
_BUY_TYPES = {"BUYBACK", "CANCELLATION"}

_DEFAULT = {"enabled": False, "budget": 1000000.0, "interval_sec": 300, "acted": [], "last_run": None}


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


def _kr_market_open(now: _dt.datetime | None = None) -> bool:
    # 09:00–15:30 KST, 평일. KST = UTC+9.
    now = now or _dt.datetime.now(_dt.timezone.utc)
    kst = now + _dt.timedelta(hours=9)
    if kst.weekday() >= 5:
        return False
    mins = kst.hour * 60 + kst.minute
    return 9 * 60 <= mins <= 15 * 60 + 30


def _buy(code: str, krw: float) -> dict:
    """KIS 모의 시장가 매수 (원화예산÷현재가). tick 전용 헬퍼."""
    import yfinance as yf
    from backends.kis.order_client import KISOrderClient
    px = float(yf.Ticker(f"{code}.KS").history(period="1d")["Close"].iloc[-1])
    qty = int(krw // px)
    if qty < 1:
        raise ValueError(f"예산 부족 (현재가 ₩{px:,.0f})")
    kk, ks, kc = (os.environ.get("KIS_MOCK_APP_KEY", ""), os.environ.get("KIS_MOCK_APP_SECRET", ""), os.environ.get("KIS_MOCK_CANO", ""))
    kis = KISOrderClient(kk, ks, kc, os.environ.get("KIS_ACNT_PRDT_CD", "01"), mock=True)
    r = kis.place_order(code, "BUY", qty, "MARKET")
    return {"code": code, "qty": qty, "price": round(px, 0), "order_id": r.get("order_id")}


def tick() -> dict:
    """1회 실행: 신규 자사주 취득/소각 공시를 모의 매수. 장 마감 시 스킵."""
    cfg = _load()
    if not cfg["enabled"]:
        return {"skipped": "disabled"}
    if not _kr_market_open():
        cfg["last_run"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        _save(cfg)
        return {"skipped": "market_closed"}

    from insider.dart_client import get_recent_kr_corporate_actions
    try:
        rows = get_recent_kr_corporate_actions(days=7, max_items=40)
    except Exception as e:  # noqa: BLE001
        _log_event({"kind": "error", "msg": f"DART 조회 실패: {str(e)[:80]}"})
        return {"error": str(e)[:80]}

    acted = set(cfg.get("acted", []))
    bought = 0
    for r in rows:
        if r.get("trade_type") not in _BUY_TYPES:
            continue
        code = (r.get("ticker") or "").strip()
        if not code:
            continue
        key = f"{r.get('corp_name')}:{r.get('trade_type')}:{r.get('trade_date')}"
        if key in acted:
            continue
        try:
            res = _buy(code, float(cfg["budget"]))
            acted.add(key)
            _log_event({"kind": "buy", "corp": r.get("corp_name"), "code": code,
                        "action": r.get("trade_type"), **res})
            bought += 1
        except Exception as e:  # noqa: BLE001
            acted.add(key)  # 재시도 폭주 방지
            _log_event({"kind": "fail", "corp": r.get("corp_name"), "code": code, "msg": str(e)[:80]})
        if bought >= 5:
            break

    cfg["acted"] = list(acted)[-500:]
    cfg["last_run"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    _save(cfg)
    return {"bought": bought, "scanned": len(rows)}


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
    budget: float | None = None
    interval_sec: int | None = None


@router.get("/status")
def status() -> dict:
    cfg = _load()
    return {
        "enabled": cfg["enabled"], "budget": cfg["budget"], "interval_sec": cfg["interval_sec"],
        "last_run": cfg.get("last_run"), "market_open": _kr_market_open(),
        "acted_count": len(cfg.get("acted", [])), "log": _recent_log(40),
    }


@router.post("/config")
def set_config(body: BotConfig) -> dict:
    cfg = _load()
    if body.enabled is not None:
        cfg["enabled"] = body.enabled
    if body.budget is not None:
        cfg["budget"] = max(float(body.budget), 0.0)
    if body.interval_sec is not None:
        cfg["interval_sec"] = max(int(body.interval_sec), 60)
    _save(cfg)
    _log_event({"kind": "config", "enabled": cfg["enabled"], "budget": cfg["budget"]})
    return {"ok": True, **{k: cfg[k] for k in ("enabled", "budget", "interval_sec")}}


@router.post("/run-now")
def run_now() -> dict:
    """수동 1회 실행 (테스트용)."""
    return tick()
