"""Polymarket sharp_wallet 컨버전스 신호 paper 라이브 집행 봇.

검증 통과(BH-FDR+walk-forward) 그룹 중 라이브 실행 가능한 것만 진입 —
bucket1(30/120/300s), bucket3(300s). score-tercile(mid/high)은 score의
liquidity 컴포넌트가 미래 300s 윈도우라 라이브 진입판정이 청산시점보다
늦게 확정되는 순서모순이라 v1 제외. 청산은 hold-to-resolution이 아니라
entry_ts+horizon_s 시점 마크아웃. 비용은 검증 당시 고정 200bps 대신 CLOB
실측 스프레드로 대체(진입 게이트는 안 건드림).

api_server/polymarket_bot.py(다각화 봇)와 동일한 JSON 설정 + JSONL 로그 패턴.
docs/superpowers/specs/2026-08-02-polymarket-sharp-wallet-execution-design.md
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
import time as _time
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from polymarket.client import get_market
from polymarket.clob_client import get_order_book, spread_bps_from_book
from research.hypotheses.polymarket_sharp_wallet import build_convergence_count, load_sharp_wallet_trades
from research.polymarket_sharp_wallet.positions import fetch_wallet_positions
from research.validation.cost_model import polymarket_effective_cost_bps

router = APIRouter(prefix="/polymarket-sharp-wallet-bot", tags=["polymarket-sharp-wallet-bot"])

_DATA = Path(os.environ.get("POLYMARKET_SHARP_WALLET_BOT_DIR", "data"))
_CFG = _DATA / "polymarket_sharp_wallet_bot.json"
_LOG = _DATA / "polymarket_sharp_wallet_bot_log.jsonl"

# v1 라이브 실행 허용 그룹 — bucket2/score-tercile(low/mid/high) 전부 제외
# (스펙 §진입신호 — score의 liquidity 컴포넌트가 미래 300s 윈도우라 순서모순).
_HORIZONS_BY_BUCKET = {1: (30, 120, 300), 3: (300,)}

_DEFAULT = {
    "enabled": False, "interval_sec": 15,
    "budget": 300.0, "trade_size_usd": 15.0, "max_concurrent_positions": 30,
    "spent": 0.0, "realized_pnl": 0.0,
    "positions": [],  # [{condition_id, convergence_bucket, horizon_s, direction, entry_price,
                       #   entry_ts, exit_at, usd, shares, entry_spread_bps, wallet_positions_snapshot}]
    "last_anchor_ts": 0.0,
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


def _spread_bps_for_market(m: dict) -> float | None:
    token_ids = m.get("clob_token_ids")
    if not token_ids or not token_ids[0]:
        return None
    book = get_order_book(token_ids[0])
    return spread_bps_from_book(book) if book else None


def _wallet_snapshot_safe(wallet: str | None) -> list[dict]:
    if not wallet:
        return []
    return fetch_wallet_positions(wallet)


def _scan_and_enter(cfg: dict) -> int:
    remaining_slots = cfg["max_concurrent_positions"] - len(cfg.get("positions", []))
    remaining_budget = cfg["budget"] - cfg.get("spent", 0.0)
    if remaining_slots <= 0 or remaining_budget < cfg["trade_size_usd"]:
        return 0

    today = _dt.datetime.now(_dt.timezone.utc).date()
    yesterday = today - _dt.timedelta(days=1)
    try:
        trades = load_sharp_wallet_trades([yesterday.isoformat(), today.isoformat()])
        anchors = build_convergence_count(trades)
    except Exception as e:  # noqa: BLE001
        _log_event({"kind": "scan_fail", "msg": str(e)[:100]})
        return 0
    if anchors.empty:
        return 0

    last_ts = cfg.get("last_anchor_ts", 0.0)
    new_anchors = anchors[anchors["ts"] > last_ts].sort_values("ts")
    if new_anchors.empty:
        return 0

    entered = 0
    max_ts_seen = last_ts
    for _, row in new_anchors.iterrows():
        max_ts_seen = max(max_ts_seen, float(row["ts"]))
        if entered >= remaining_slots or remaining_budget < cfg["trade_size_usd"]:
            continue  # 슬롯/예산 소진 — 그래도 last_anchor_ts는 갱신해 재처리 방지
        horizons = _HORIZONS_BY_BUCKET.get(int(row["convergence_bucket"]))
        if not horizons:
            continue  # bucket2/미분류 — v1 진입 금지 그룹

        try:
            # get_market()은 3회 재시도 후 실패시 raise(None 아님) — 한 anchor의
            # fetch 실패가 전체 스캔을 abort시키지 않도록 anchor 단위로 격리.
            m = get_market(row["condition_id"])
            if m is None or not m["active"] or m["closed"]:
                continue
            entry_price = m["yes_price"]
            if entry_price <= 0:
                continue

            # anchor당 1회만 조회(3개 horizon이 같은 순간·같은 마켓이라 공유) — 저장공간/RAM 제약.
            entry_spread_bps = _spread_bps_for_market(m)
            wallet_snapshot = _wallet_snapshot_safe(row["proxy_wallet"])
        except Exception as e:  # noqa: BLE001
            _log_event({"kind": "entry_fail", "condition_id": row["condition_id"], "msg": str(e)[:100]})
            continue

        for h in horizons:
            if entered >= remaining_slots or remaining_budget < cfg["trade_size_usd"]:
                break
            usd = min(cfg["trade_size_usd"], remaining_budget)
            shares = round(usd / entry_price, 4)
            pos = {
                "condition_id": row["condition_id"],
                "convergence_bucket": int(row["convergence_bucket"]),
                "horizon_s": h, "direction": float(row["direction"]),
                "entry_price": entry_price, "entry_ts": float(row["ts"]),
                "exit_at": float(row["ts"]) + h,
                "usd": usd, "shares": shares,
                "entry_spread_bps": entry_spread_bps,
                "wallet_positions_snapshot": wallet_snapshot,
            }
            cfg.setdefault("positions", []).append(pos)
            cfg["spent"] = round(cfg.get("spent", 0.0) + usd, 2)
            remaining_budget -= usd
            _log_event({"kind": "entry", **pos})
            entered += 1

    cfg["last_anchor_ts"] = max_ts_seen
    return entered


def _process_exits(cfg: dict) -> int:
    """entry_ts + horizon_s 지난 포지션을 그 순간 시장가로 강제청산."""
    now = _time.time()
    keep: list[dict] = []
    closed = 0
    for pos in cfg.get("positions", []):
        if now < pos["exit_at"]:
            keep.append(pos)
            continue

        # try/except: fetch 단계만 격리(Task 3 패턴). state mutation(cfg 갱신)은 밖에서.
        try:
            m = get_market(pos["condition_id"])
            exit_spread_bps = _spread_bps_for_market(m) if m else None
        except Exception as e:  # noqa: BLE001
            _log_event({"kind": "exit_fail", "condition_id": pos["condition_id"], "msg": str(e)[:100]})
            keep.append(pos)  # 다음 tick 재시도
            continue

        # m이 None이면 재시도
        if m is None:
            keep.append(pos)
            continue

        # 계산 및 state mutation (try/except 밖)
        exit_price = m["yes_price"]
        spreads = [s for s in (pos.get("entry_spread_bps"), exit_spread_bps) if s is not None]
        cost_bps = (polymarket_effective_cost_bps(spread_bps=sum(spreads) / len(spreads))
                    if spreads else polymarket_effective_cost_bps())
        cost_usd = (pos["entry_price"] + exit_price) * pos["shares"] * cost_bps / 10_000.0
        pnl = round(pos["direction"] * (exit_price - pos["entry_price"]) * pos["shares"] - cost_usd, 2)
        cfg["spent"] = round(max(cfg.get("spent", 0.0) - pos["usd"], 0.0), 2)
        cfg["realized_pnl"] = round(cfg.get("realized_pnl", 0.0) + pnl, 2)
        _log_event({"kind": "exit", "condition_id": pos["condition_id"],
                     "convergence_bucket": pos["convergence_bucket"], "horizon_s": pos["horizon_s"],
                     "entry_price": pos["entry_price"], "exit_price": exit_price,
                     "cost_bps": round(cost_bps, 2), "pnl": pnl})
        closed += 1
    cfg["positions"] = keep
    return closed
