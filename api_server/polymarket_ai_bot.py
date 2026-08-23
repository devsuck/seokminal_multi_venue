"""Polymarket AI 판단 봇(side="ai") — Tavily 검색 grounding + Groq 판단 기반 진입, paper 전용.

polymarket_bot.py(가격구조 기반 favorite/underdog/random)와 완전히 독립된 셋째
sibling 봇. 같은 마켓 유니버스를 보되 판단 신호축이 다르다 — 후보 필터는
polymarket_bot.py의 _scan_and_enter와 동일 기준 재사용, 진입 여부/방향만
AI 판단값(research/polymarket_ai_judgment/judge.py)의 yes_prob vs 시장가
괴리(edge)로 결정한다. 예산·포지션 전부 독립 — 다른 두 봇과 자본 공유 없음.

설계: docs/superpowers/specs/2026-08-23-polymarket-ai-judgment-bot-design.md"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from polymarket.client import get_market, get_markets
from research.polymarket_ai_judgment import judge as _judge

router = APIRouter(prefix="/polymarket-ai-bot", tags=["polymarket-ai-bot"])

_DATA = Path(os.environ.get("POLYMARKET_AI_BOT_DIR", "data"))
_CFG = _DATA / "polymarket_ai_bot.json"
_LOG = _DATA / "polymarket_ai_bot_log.jsonl"

_DEFAULT = {
    "enabled": False, "interval_sec": 3600,
    "budget": 2000.0, "per_market_usd": 40.0, "max_positions": 50,
    "min_liquidity": 3000.0, "min_price": 0.10, "max_price": 0.90,
    "min_days_to_resolution": 3, "max_days_to_resolution": 21,
    "min_edge": 0.05, "max_new_calls_per_tick": 5, "max_new_calls_per_day": 30,
    "spent": 0.0, "realized_pnl": 0.0,
    "positions": [],  # [{condition_id, question, event_id, side, entry_price, usd, shares, end_date, entry_ts, ai_yes_prob, edge}]
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
            keep.append(pos)
            continue
        if not m["closed"]:
            keep.append(pos)
            continue
        final_price = m["yes_price"] if pos["side"] == "YES" else m["no_price"]
        payout = round(final_price)
        pnl = round((payout - pos["entry_price"]) * pos["shares"], 2)
        cfg["spent"] = round(max(float(cfg.get("spent", 0.0)) - pos["usd"], 0.0), 2)
        cfg["realized_pnl"] = round(float(cfg.get("realized_pnl", 0.0)) + pnl, 2)
        _log_event({"kind": "resolve", "question": pos["question"], "side": pos["side"],
                    "entry_price": pos["entry_price"], "payout": payout, "pnl": pnl})
        resolved += 1
    cfg["positions"] = keep
    return resolved


def _scan_candidates(cfg: dict) -> list[dict]:
    """polymarket_bot.py의 _scan_and_enter와 동일 필터 기준(활성/유동성/가격대/
    잔여만기), 사이드 선택 없이 후보 목록만 반환 — 사이드는 AI 판단 후 결정."""
    held_conditions = {p["condition_id"] for p in cfg.get("positions", [])}
    held_events = {p["event_id"] for p in cfg.get("positions", [])}

    try:
        markets = get_markets(limit=500)
    except Exception as e:  # noqa: BLE001
        _log_event({"kind": "scan_fail", "msg": str(e)[:100]})
        return []

    today = _dt.date.today()
    candidates = []
    for m in markets:
        if not m["active"] or m["closed"] or not m["accepting_orders"]:
            continue
        if m["condition_id"] in held_conditions or m["event_id"] in held_events:
            continue
        if m["liquidity"] < cfg["min_liquidity"]:
            continue
        if not (cfg["min_price"] <= m["yes_price"] <= cfg["max_price"]):
            continue
        try:
            end = _dt.date.fromisoformat(m["end_date"])
        except ValueError:
            continue
        days_left = (end - today).days
        if days_left < cfg["min_days_to_resolution"] or days_left > cfg["max_days_to_resolution"]:
            continue
        candidates.append(m)
    return candidates


def _judge_and_enter(cfg: dict) -> int:
    remaining_slots = cfg["max_positions"] - len(cfg.get("positions", []))
    if remaining_slots <= 0:
        return 0
    remaining_budget = cfg["budget"] - cfg.get("spent", 0.0)
    if remaining_budget < cfg["per_market_usd"]:
        return 0

    candidates = _scan_candidates(cfg)
    if not candidates:
        return 0

    cache = _judge.load_cache()
    daily_state = _judge.load_daily_state()
    judged, cache, daily_state, _calls_used = _judge.judge_markets(
        candidates, cache, daily_state,
        max_new_calls_per_tick=cfg["max_new_calls_per_tick"],
        max_new_calls_per_day=cfg["max_new_calls_per_day"],
    )
    _judge.save_cache(cache)
    _judge.save_daily_state(daily_state)

    held_events = {p["event_id"] for p in cfg.get("positions", [])}
    entered = 0
    for m in judged:
        if entered >= remaining_slots or remaining_budget < cfg["per_market_usd"]:
            break
        if m["event_id"] in held_events:
            continue
        judgment = m.get("judgment")
        if judgment is None:
            continue
        edge = judgment["yes_prob"] - m["yes_price"]
        if abs(edge) < cfg["min_edge"]:
            continue
        side, price = ("YES", m["yes_price"]) if edge > 0 else ("NO", m["no_price"])
        if price <= 0:
            continue

        usd = min(cfg["per_market_usd"], remaining_budget)
        shares = round(usd / price, 4)
        pos = {
            "condition_id": m["condition_id"], "question": m["question"],
            "event_id": m["event_id"], "side": side, "entry_price": price,
            "usd": usd, "shares": shares, "end_date": m["end_date"],
            "entry_ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "ai_yes_prob": judgment["yes_prob"], "edge": round(edge, 4),
        }
        cfg.setdefault("positions", []).append(pos)
        cfg["spent"] = round(float(cfg.get("spent", 0.0)) + usd, 2)
        remaining_budget -= usd
        held_events.add(m["event_id"])
        _log_event({"kind": "entry", **pos, "reasoning": judgment.get("reasoning", "")})
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
    entered = _judge_and_enter(cfg)
    cfg["last_run"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    _save(cfg)
    return {"entered": entered, "resolved": resolved, "positions": len(cfg.get("positions", [])),
            "spent": cfg["spent"], "realized_pnl": cfg["realized_pnl"]}


async def _loop() -> None:
    while True:
        interval = 3600
        try:
            cfg = _load()
            interval = int(cfg.get("interval_sec", 3600))
            if cfg.get("enabled"):
                await asyncio.to_thread(tick)
        except Exception:  # noqa: BLE001
            pass
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
    min_edge: float | None = None
    max_new_calls_per_tick: int | None = None
    max_new_calls_per_day: int | None = None
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
        "max_days_to_resolution": cfg["max_days_to_resolution"],
        "min_edge": cfg["min_edge"], "max_new_calls_per_tick": cfg["max_new_calls_per_tick"],
        "max_new_calls_per_day": cfg["max_new_calls_per_day"],
        "spent": cfg.get("spent", 0.0), "realized_pnl": cfg.get("realized_pnl", 0.0),
        "remaining": max(cfg["budget"] - cfg.get("spent", 0.0), 0.0),
        "positions": cfg.get("positions", []), "last_run": cfg.get("last_run"),
        "log": _recent_log(40),
        "note": "Tavily 검색 grounding + Groq 판단(yes_prob) vs 시장가 괴리(edge)가 "
                "min_edge 넘을 때만 진입 — 가격구조 기반 다각화 배스킷/sharp_wallet 봇과 "
                "완전 독립 예산·포지션. v1 paper 전용, N=20~30건 정산 전까지 결론 안 냄.",
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
    if body.min_edge is not None:
        cfg["min_edge"] = min(max(float(body.min_edge), 0.0), 0.99)
    if body.max_new_calls_per_tick is not None:
        cfg["max_new_calls_per_tick"] = max(int(body.max_new_calls_per_tick), 0)
    if body.max_new_calls_per_day is not None:
        cfg["max_new_calls_per_day"] = max(int(body.max_new_calls_per_day), 0)
    if body.reset_spent:
        cfg["spent"] = 0.0
    _save(cfg)
    _log_event({"kind": "config", "enabled": cfg["enabled"], "budget": cfg["budget"]})
    return {"ok": True, **{k: cfg[k] for k in (
        "enabled", "interval_sec", "budget", "per_market_usd", "max_positions",
        "min_liquidity", "min_price", "max_price", "min_days_to_resolution",
        "max_days_to_resolution", "min_edge", "max_new_calls_per_tick", "max_new_calls_per_day")}}


@router.post("/run-now")
def run_now() -> dict:
    return tick()
