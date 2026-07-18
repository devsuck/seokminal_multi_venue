"""Polymarket 페이퍼 다각화 배스킷 봇.

주의: 이건 알파(초과수익) 전략이 아니다. 이벤트 예측시장은 주식/크립토와
상관관계가 낮아 "분산" 목적으로만 쓴다 — 방향성 엣지를 주장하지 않고,
유동성 있고 극단(롱샷/헤비페이버릿)이 아닌 이진 시장에 균등 배분한 뒤
만기까지 보유(hold-to-resolution)한다. house 규율(TSMOM 등과 동일하게
"검증 전엔 paper")에 따라 이 봇도 실집행 없이 paper 전용으로 시작한다.

dart_autobot.py와 동일한 파일 저장 패턴 — JSON 설정 + JSONL 로그.
Gamma API는 공개·무인증이라 IB/KIS와 달리 동기 requests만으로 충분.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from polymarket.client import get_market, get_markets

router = APIRouter(prefix="/polymarket", tags=["polymarket-bot"])

_DATA = Path(os.environ.get("POLYMARKET_BOT_DIR", "data"))
_CFG = _DATA / "polymarket_bot.json"
_LOG = _DATA / "polymarket_bot_log.jsonl"

_DEFAULT = {
    "enabled": False, "interval_sec": 3600,
    "budget": 500.0, "per_market_usd": 20.0, "max_positions": 15,
    "min_liquidity": 5000.0, "min_price": 0.10, "max_price": 0.90,
    "min_days_to_resolution": 3, "max_days_to_resolution": 30,
    "side": "favorite",  # "favorite" | "underdog" | "random" — 무엣지, 다각화 전용
    "spent": 0.0, "realized_pnl": 0.0,
    "positions": [],  # [{condition_id, question, event_id, side, entry_price, usd, shares, end_date, entry_ts}]
    "last_run": None,
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


def _process_resolutions(cfg: dict) -> int:
    """만기 지난/청산된 포지션 정산. 반환: 정산 건수."""
    keep: list[dict] = []
    resolved = 0
    for pos in cfg.get("positions", []):
        m = get_market(pos["condition_id"])
        if m is None:
            keep.append(pos)  # 조회 실패 — 다음 tick 재시도
            continue
        if not m["closed"]:
            keep.append(pos)  # 아직 진행중
            continue
        final_price = m["yes_price"] if pos["side"] == "YES" else m["no_price"]
        payout = round(final_price)  # 정산 후 가격은 1.0/0.0에 수렴 — 반올림으로 확정 승패 판정
        pnl = round((payout - pos["entry_price"]) * pos["shares"], 2)
        cfg["spent"] = round(max(float(cfg.get("spent", 0.0)) - pos["usd"], 0.0), 2)
        cfg["realized_pnl"] = round(float(cfg.get("realized_pnl", 0.0)) + pnl, 2)
        _log_event({"kind": "resolve", "question": pos["question"], "side": pos["side"],
                    "entry_price": pos["entry_price"], "payout": payout, "pnl": pnl})
        resolved += 1
    cfg["positions"] = keep
    return resolved


def _scan_and_enter(cfg: dict) -> int:
    held_conditions = {p["condition_id"] for p in cfg.get("positions", [])}
    held_events = {p["event_id"] for p in cfg.get("positions", [])}
    remaining_slots = cfg["max_positions"] - len(cfg.get("positions", []))
    if remaining_slots <= 0:
        return 0
    remaining_budget = cfg["budget"] - cfg.get("spent", 0.0)
    if remaining_budget < cfg["per_market_usd"]:
        return 0

    try:
        markets = get_markets(limit=500)
    except Exception as e:  # noqa: BLE001
        _log_event({"kind": "scan_fail", "msg": str(e)[:100]})
        return 0

    today = _dt.date.today()
    entered = 0
    for m in markets:
        if entered >= remaining_slots or remaining_budget < cfg["per_market_usd"]:
            break
        if not m["active"] or m["closed"] or not m["accepting_orders"]:
            continue
        if m["condition_id"] in held_conditions or m["event_id"] in held_events:
            continue  # 같은 이벤트 중복 배팅 방지 — 다각화 취지
        if m["liquidity"] < cfg["min_liquidity"]:
            continue
        if not (cfg["min_price"] <= m["yes_price"] <= cfg["max_price"]):
            continue
        try:
            end = _dt.date.fromisoformat(m["end_date"])
        except ValueError:
            continue
        days_left = (end - today).days
        if days_left < cfg["min_days_to_resolution"]:
            continue
        if days_left > cfg["max_days_to_resolution"]:
            continue  # 만기 너무 먼 시장 제외 — 자본 오래 묶이는 것 방지

        side_pref = cfg.get("side", "favorite")
        if side_pref == "underdog":
            side, price = ("YES", m["yes_price"]) if m["yes_price"] < m["no_price"] else ("NO", m["no_price"])
        elif side_pref == "random":
            import random as _r
            side, price = _r.choice([("YES", m["yes_price"]), ("NO", m["no_price"])])
        else:  # favorite (기본)
            side, price = ("YES", m["yes_price"]) if m["yes_price"] >= m["no_price"] else ("NO", m["no_price"])
        if price <= 0:
            continue

        usd = min(cfg["per_market_usd"], remaining_budget)
        shares = round(usd / price, 4)
        pos = {
            "condition_id": m["condition_id"], "question": m["question"],
            "event_id": m["event_id"], "side": side, "entry_price": price,
            "usd": usd, "shares": shares, "end_date": m["end_date"],
            "entry_ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        cfg.setdefault("positions", []).append(pos)
        cfg["spent"] = round(float(cfg.get("spent", 0.0)) + usd, 2)
        remaining_budget -= usd
        held_conditions.add(m["condition_id"])
        held_events.add(m["event_id"])
        _log_event({"kind": "entry", **pos})
        entered += 1
    return entered


def tick() -> dict:
    cfg = _load()
    if not cfg["enabled"]:
        return {"skipped": "disabled"}
    try:
        from api_server.risk_state import is_killed
        if is_killed():
            _log_event({"kind": "kill", "msg": "리스크 킬스위치 — 매매 중단"})
            return {"skipped": "kill_switch"}
    except Exception:
        pass

    resolved = _process_resolutions(cfg)
    _save(cfg)
    entered = _scan_and_enter(cfg)
    cfg["last_run"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    _save(cfg)
    return {"entered": entered, "resolved": resolved, "positions": len(cfg.get("positions", [])),
            "spent": cfg["spent"], "realized_pnl": cfg["realized_pnl"]}


async def _loop() -> None:
    while True:
        try:
            cfg = _load()
            interval = int(cfg.get("interval_sec", 3600))
            if cfg.get("enabled"):
                await asyncio.to_thread(tick)
        except Exception:  # noqa: BLE001
            interval = 3600
        await asyncio.sleep(max(interval, 300))


def start_loop() -> None:
    try:
        asyncio.get_event_loop().create_task(_loop())
    except RuntimeError:
        pass


# ── API ──────────────────────────────────────────────────────────────────────
class BotConfig(BaseModel):
    enabled: bool | None = None
    interval_sec: int | None = None
    budget: float | None = None
    per_market_usd: float | None = None
    max_positions: int | None = None
    min_liquidity: float | None = None
    min_price: float | None = None
    max_price: float | None = None
    min_days_to_resolution: int | None = None
    max_days_to_resolution: int | None = None
    side: str | None = None
    reset_spent: bool | None = None


@router.get("/status")
def status() -> dict:
    cfg = _load()
    return {
        "enabled": cfg["enabled"], "interval_sec": cfg["interval_sec"],
        "budget": cfg["budget"], "per_market_usd": cfg["per_market_usd"],
        "max_positions": cfg["max_positions"], "min_liquidity": cfg["min_liquidity"],
        "min_price": cfg["min_price"], "max_price": cfg["max_price"],
        "min_days_to_resolution": cfg["min_days_to_resolution"],
        "max_days_to_resolution": cfg["max_days_to_resolution"], "side": cfg["side"],
        "spent": cfg.get("spent", 0.0), "realized_pnl": cfg.get("realized_pnl", 0.0),
        "remaining": max(cfg["budget"] - cfg.get("spent", 0.0), 0.0),
        "positions": cfg.get("positions", []), "last_run": cfg.get("last_run"),
        "log": _recent_log(40),
        "note": "무방향 다각화 배스킷 — 엣지 주장 없음, 상관관계 낮은 이벤트 리스크 분산용. paper 전용.",
    }


@router.post("/config")
def set_config(body: BotConfig) -> dict:
    cfg = _load()
    if body.enabled is not None:
        cfg["enabled"] = body.enabled
    if body.interval_sec is not None:
        cfg["interval_sec"] = max(int(body.interval_sec), 300)
    if body.budget is not None:
        cfg["budget"] = max(float(body.budget), 0.0)
    if body.per_market_usd is not None:
        cfg["per_market_usd"] = max(float(body.per_market_usd), 1.0)
    if body.max_positions is not None:
        cfg["max_positions"] = max(int(body.max_positions), 1)
    if body.min_liquidity is not None:
        cfg["min_liquidity"] = max(float(body.min_liquidity), 0.0)
    if body.min_price is not None:
        cfg["min_price"] = min(max(float(body.min_price), 0.01), 0.49)
    if body.max_price is not None:
        cfg["max_price"] = min(max(float(body.max_price), 0.51), 0.99)
    if body.min_days_to_resolution is not None:
        cfg["min_days_to_resolution"] = max(int(body.min_days_to_resolution), 0)
    if body.max_days_to_resolution is not None:
        cfg["max_days_to_resolution"] = max(int(body.max_days_to_resolution), 1)
    if body.side is not None and body.side in ("favorite", "underdog", "random"):
        cfg["side"] = body.side
    if body.reset_spent:
        cfg["spent"] = 0.0
    _save(cfg)
    _log_event({"kind": "config", "enabled": cfg["enabled"], "budget": cfg["budget"]})
    return {"ok": True, **{k: cfg[k] for k in (
        "enabled", "interval_sec", "budget", "per_market_usd", "max_positions",
        "min_liquidity", "min_price", "max_price", "min_days_to_resolution",
        "max_days_to_resolution", "side")}}


@router.post("/run-now")
def run_now() -> dict:
    return tick()
