"""Variance Risk Premium (VRP) 옵션 매도 봇 — 정의된 리스크(아이언 콘도어)만.

발상: 내재변동성(IV)이 실현변동성(RV)보다 구조적으로 비싼 프리미엄(VRP)을
아이언 콘도어(숏 스트랭글 + 보호 날개)로 수취. 네이키드 숏은 절대 안 함 —
IB 계정 마진/포지션별 증거금 조회 API가 없어 무한손실 포지션의 실제 리스크를
정확히 게이트할 수 없기 때문. 콘도어는 진입 시점에 최대손실이 확정되므로
`risk_guard.validate_defined_risk_spread`로 안전하게 게이트 가능.

dart_autobot.py와 동일한 파일 저장 패턴(JSON 설정 + JSONL 로그). paper 전용
(IB paper 7497) — 실집행 없음.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
import random
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from live_engine.risk_guard import RiskConfig, RiskViolation, validate_defined_risk_spread
from options.pricer import vrp_spread

router = APIRouter(prefix="/vrp", tags=["vrp-bot"])

_DATA = Path(os.environ.get("VRP_BOT_DIR", "data"))
_CFG = _DATA / "vrp_bot.json"
_LOG = _DATA / "vrp_bot_log.jsonl"

_DEFAULT = {
    "enabled": False, "interval_sec": 3600,
    "symbols": ["SPY"],
    "contracts": 1,
    "target_dte_min": 25, "target_dte_max": 45,
    "short_delta": 0.16,          # 숏 콜/풋 목표 델타 (풋은 -0.16)
    "wing_width_pct": 0.03,       # 보호 날개까지 거리 (스팟 대비 %)
    "min_spread_pct": 0.15,       # 진입 최소 VRP: (IV-RV)/RV
    "profit_target_pct": 0.5,     # 수취 크레딧의 50% 확보 시 청산
    "stop_multiple": 2.0,         # 손실이 크레딧의 2배면 청산
    "exit_dte": 7,                # 만기 7일 전엔 무조건 청산 (핀 리스크 회피)
    "max_positions": 3,
    "spent": 0.0,                 # 오픈 포지션들의 max_loss 합 (증거금 예약액 개념)
    "realized_pnl": 0.0,
    "positions": [],              # [{symbol, expiry, legs:[...], credit_received, max_loss, entry_ts, entry_vrp_pct}]
    "last_run": None,
}


def _load() -> dict:
    try:
        cfg = {**_DEFAULT, **json.loads(_CFG.read_text())}
    except Exception:
        return dict(_DEFAULT)
    return cfg


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


def _ib_host() -> str:
    return os.environ.get("IB_HOST", "127.0.0.1")


def _data_client():
    from backends.ib.client import IBClient
    return IBClient(host=_ib_host(), client_id=random.randint(700, 799))


def _order_client():
    from backends.ib.order_client import IBOrderClient
    return IBOrderClient(host=_ib_host(), port=7497,
                          client_id=int(os.environ.get("IB_VRP_ORDER_CLIENT_ID", "77")))


async def _place_leg(order_client, symbol: str, expiry: str, strike: float, right: str,
                      side: str, contracts: int) -> dict:
    r = await order_client.place_option_order(symbol, expiry, strike, right, side,
                                               contracts, "MARKET", None, wait_fill=True)
    return {"strike": strike, "right": right, "side": side, "contracts": contracts,
            "fill": r.get("avg_fill_price")}


async def _unwind_legs(order_client, symbol: str, expiry: str, filled_legs: list[dict]) -> None:
    """진입 도중 일부 레그만 체결됐을 때 되돌리기 (실패 시 로그만, 최선 노력)."""
    for leg in filled_legs:
        try:
            reverse = "SELL" if leg["side"] == "BUY" else "BUY"
            await order_client.place_option_order(
                symbol, expiry, leg["strike"], leg["right"], reverse,
                leg["contracts"], "MARKET", None, wait_fill=True,
            )
        except Exception as e:  # noqa: BLE001
            _log_event({"kind": "unwind_fail", "symbol": symbol, "leg": leg, "msg": str(e)[:80]})


def _pick_expiry(chain: dict, dte_min: int, dte_max: int) -> tuple[str, list[dict]] | None:
    today = _dt.date.today()
    mid = (dte_min + dte_max) / 2
    best: tuple[int, str, list] | None = None
    for expiry, rows in chain.items():
        try:
            exp_date = _dt.datetime.strptime(expiry, "%Y%m%d").date()
        except ValueError:
            continue
        dte = (exp_date - today).days
        if not (dte_min <= dte <= dte_max):
            continue
        if best is None or abs(dte - mid) < abs(best[0] - mid):
            best = (dte, expiry, rows)
    return (best[1], best[2]) if best else None


def _pick_wing(rows: list[dict], right: str, short_strike: float, wing: float, outward: bool) -> dict | None:
    """short_strike에서 wing만큼(스팟 기준 달러폭) 떨어진 방향의 다음 행사가 옵션."""
    if outward:  # 콜: short보다 높은 행사가
        cands = sorted((r for r in rows if r["right"] == right and r["strike"] > short_strike),
                        key=lambda r: r["strike"])
    else:  # 풋: short보다 낮은 행사가
        cands = sorted((r for r in rows if r["right"] == right and r["strike"] < short_strike),
                        key=lambda r: -r["strike"])
    if not cands:
        return None
    for r in cands:
        if abs(r["strike"] - short_strike) >= wing:
            return r
    return cands[-1]  # 원하는 폭 못 채우면 가장 먼 것으로 (그래도 defined-risk 유지)


async def _scan_and_enter(cfg: dict) -> int:
    open_symbols = {p["symbol"] for p in cfg.get("positions", [])}
    entered = 0
    for symbol in cfg.get("symbols", []):
        if len(cfg.get("positions", [])) >= cfg["max_positions"]:
            break
        if symbol in open_symbols:
            continue
        try:
            data = _data_client()
            end = ""
            bars = await data.get_daily_bars(symbol, end, "90 D")
            closes = [float(b.close) for b in bars]
            chain = await data.get_option_chain(symbol, max_expiries=6)
        except Exception as e:  # noqa: BLE001
            _log_event({"kind": "scan_fail", "symbol": symbol, "msg": str(e)[:100]})
            continue
        if not chain or len(closes) < 21:
            continue
        picked = _pick_expiry(chain, cfg["target_dte_min"], cfg["target_dte_max"])
        if picked is None:
            continue
        expiry, rows = picked
        spot = closes[-1]
        atm_rows = sorted(rows, key=lambda r: abs(r["strike"] - spot))[:4]
        iv_vals = [r["iv"] for r in atm_rows if r.get("iv")]
        if not iv_vals:
            continue
        atm_iv = sum(iv_vals) / len(iv_vals)
        spread = vrp_spread(atm_iv, closes, window=20)
        if spread is None or spread["spread_pct"] < cfg["min_spread_pct"]:
            continue

        calls = [r for r in rows if r["right"] == "C" and r.get("delta") is not None]
        puts = [r for r in rows if r["right"] == "P" and r.get("delta") is not None]
        if not calls or not puts:
            continue
        short_call = min(calls, key=lambda r: abs(r["delta"] - cfg["short_delta"]))
        short_put = min(puts, key=lambda r: abs(r["delta"] + cfg["short_delta"]))
        wing = spot * cfg["wing_width_pct"]
        long_call = _pick_wing(rows, "C", short_call["strike"], wing, outward=True)
        long_put = _pick_wing(rows, "P", short_put["strike"], wing, outward=False)
        if not long_call or not long_put:
            continue

        short_call_bid, short_put_bid = short_call.get("bid"), short_put.get("bid")
        long_call_ask, long_put_ask = long_call.get("ask"), long_put.get("ask")
        if None in (short_call_bid, short_put_bid, long_call_ask, long_put_ask):
            continue  # 호가 없음 — 유동성 부족, 스킵
        credit_est = (short_call_bid + short_put_bid) - (long_call_ask + long_put_ask)
        if credit_est <= 0:
            continue

        contracts = int(cfg["contracts"])
        call_wing_width = long_call["strike"] - short_call["strike"]
        put_wing_width = short_put["strike"] - long_put["strike"]
        max_loss_est = max(call_wing_width, put_wing_width) * 100 * contracts - credit_est * 100 * contracts
        if max_loss_est <= 0:
            continue

        try:
            validate_defined_risk_spread(max_loss=max_loss_est, config=RiskConfig.from_env())
        except RiskViolation as e:
            _log_event({"kind": "risk_block", "symbol": symbol, "msg": str(e)[:120]})
            continue

        order_client = _order_client()
        filled: list[dict] = []
        try:
            # 보호 날개 먼저 매수 (실패해도 네이키드 숏 상태가 되지 않도록) → 숏 나중.
            filled.append(await _place_leg(order_client, symbol, expiry, long_put["strike"], "P", "BUY", contracts))
            filled.append(await _place_leg(order_client, symbol, expiry, long_call["strike"], "C", "BUY", contracts))
            filled.append(await _place_leg(order_client, symbol, expiry, short_put["strike"], "P", "SELL", contracts))
            filled.append(await _place_leg(order_client, symbol, expiry, short_call["strike"], "C", "SELL", contracts))
        except Exception as e:  # noqa: BLE001
            await _unwind_legs(order_client, symbol, expiry, [f for f in filled if f.get("fill") is not None])
            await order_client.close()
            _log_event({"kind": "entry_fail", "symbol": symbol, "msg": str(e)[:100], "filled": filled})
            continue
        await order_client.close()

        if any(f.get("fill") is None for f in filled):
            to_unwind = [f for f in filled if f.get("fill") is not None]
            oc2 = _order_client()
            await _unwind_legs(oc2, symbol, expiry, to_unwind)
            await oc2.close()
            _log_event({"kind": "entry_fail", "symbol": symbol, "msg": "일부 레그 미체결", "filled": filled})
            continue

        long_put_fill, long_call_fill, short_put_fill, short_call_fill = (f["fill"] for f in filled)
        credit_received = round((short_call_fill + short_put_fill - long_call_fill - long_put_fill) * 100 * contracts, 2)
        max_loss = round(max(call_wing_width, put_wing_width) * 100 * contracts - credit_received, 2)

        pos = {
            "symbol": symbol, "expiry": expiry,
            "legs": [
                {"strike": long_put["strike"], "right": "P", "side": "BUY", "contracts": contracts},
                {"strike": long_call["strike"], "right": "C", "side": "BUY", "contracts": contracts},
                {"strike": short_put["strike"], "right": "P", "side": "SELL", "contracts": contracts},
                {"strike": short_call["strike"], "right": "C", "side": "SELL", "contracts": contracts},
            ],
            "credit_received": credit_received,
            "max_loss": max(max_loss, 0.01),
            "entry_ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "entry_vrp_pct": round(spread["spread_pct"] * 100, 1),
        }
        cfg.setdefault("positions", []).append(pos)
        cfg["spent"] = round(float(cfg.get("spent", 0.0)) + pos["max_loss"], 2)
        _log_event({"kind": "entry", **pos})
        entered += 1
        open_symbols.add(symbol)
    return entered


async def _mark_position(data_client, pos: dict) -> float | None:
    """현재 레그 시세로 되사는(청산) 비용(달러, 순 지불액) 추정. None = 시세 조회 실패."""
    try:
        chain = await data_client.get_option_chain(pos["symbol"], max_expiries=8)
    except Exception:
        return None
    rows = chain.get(pos["expiry"])
    if not rows:
        return None
    by_key = {(r["strike"], r["right"]): r for r in rows}
    cost = 0.0
    for leg in pos["legs"]:
        row = by_key.get((leg["strike"], leg["right"]))
        if row is None:
            return None
        contracts = leg["contracts"]
        if leg["side"] == "SELL":  # 되사야 함 (ask)
            px = row.get("ask")
            if px is None:
                return None
            cost += px * 100 * contracts
        else:  # 되팔아야 함 (bid)
            px = row.get("bid")
            if px is None:
                return None
            cost -= px * 100 * contracts
    return cost


async def _close_position(order_client, pos: dict) -> float | None:
    """전 레그 반대매매로 청산. 실제 체결가 기준 순 지불액(양수=비용) 반환, 실패 시 None."""
    total = 0.0
    for leg in pos["legs"]:
        reverse = "SELL" if leg["side"] == "BUY" else "BUY"
        try:
            r = await order_client.place_option_order(
                pos["symbol"], pos["expiry"], leg["strike"], leg["right"], reverse,
                leg["contracts"], "MARKET", None, wait_fill=True,
            )
        except Exception:
            return None
        fill = r.get("avg_fill_price")
        if fill is None:
            return None
        # reverse=SELL 원래 BUY레그 청산 → 수령(음수 비용); reverse=BUY 원래 SELL레그 청산 → 지불(양수 비용)
        sign = -1 if reverse == "SELL" else 1
        total += sign * fill * 100 * leg["contracts"]
    return total


async def _process_exits(cfg: dict) -> int:
    keep: list[dict] = []
    closed = 0
    if not cfg.get("positions"):
        return 0
    data_client = _data_client()
    today = _dt.date.today()
    for pos in cfg.get("positions", []):
        cost_to_close = await _mark_position(data_client, pos)
        exp_date = _dt.datetime.strptime(pos["expiry"], "%Y%m%d").date()
        dte = (exp_date - today).days
        reason = None
        if cost_to_close is not None:
            pnl = pos["credit_received"] - cost_to_close
            if pnl >= cfg["profit_target_pct"] * pos["credit_received"]:
                reason = f"익절 (크레딧의 {pnl/pos['credit_received']*100:.0f}% 확보)"
            elif pnl <= -cfg["stop_multiple"] * pos["credit_received"]:
                reason = f"손절 (크레딧의 {cfg['stop_multiple']:.1f}배 손실)"
        if reason is None and dte <= cfg["exit_dte"]:
            reason = f"만기 {dte}일 전 강제 청산 (핀 리스크 회피)"
        if reason is None:
            keep.append(pos)
            continue
        order_client = _order_client()
        net_cost = await _close_position(order_client, pos)
        await order_client.close()
        if net_cost is None:
            keep.append(pos)  # 청산 실패 — 다음 tick 재시도
            _log_event({"kind": "exit_fail", "symbol": pos["symbol"], "expiry": pos["expiry"]})
            continue
        realized = round(pos["credit_received"] - net_cost, 2)
        cfg["spent"] = round(max(float(cfg.get("spent", 0.0)) - pos["max_loss"], 0.0), 2)
        cfg["realized_pnl"] = round(float(cfg.get("realized_pnl", 0.0)) + realized, 2)
        _log_event({"kind": "exit", "symbol": pos["symbol"], "expiry": pos["expiry"],
                    "reason": reason, "realized_pnl": realized, "credit_received": pos["credit_received"]})
        closed += 1
    cfg["positions"] = keep
    return closed


async def tick() -> dict:
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

    closed = await _process_exits(cfg)
    _save(cfg)
    entered = await _scan_and_enter(cfg)
    cfg["last_run"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    _save(cfg)
    return {"entered": entered, "closed": closed, "positions": len(cfg.get("positions", [])),
            "spent": cfg["spent"], "realized_pnl": cfg["realized_pnl"]}


async def _loop() -> None:
    while True:
        try:
            cfg = _load()
            interval = int(cfg.get("interval_sec", 3600))
            if cfg.get("enabled"):
                await tick()
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
    symbols: list[str] | None = None
    contracts: int | None = None
    target_dte_min: int | None = None
    target_dte_max: int | None = None
    short_delta: float | None = None
    wing_width_pct: float | None = None
    min_spread_pct: float | None = None
    profit_target_pct: float | None = None
    stop_multiple: float | None = None
    exit_dte: int | None = None
    max_positions: int | None = None


@router.get("/status")
def status() -> dict:
    cfg = _load()
    return {
        "enabled": cfg["enabled"], "interval_sec": cfg["interval_sec"],
        "symbols": cfg["symbols"], "contracts": cfg["contracts"],
        "target_dte_min": cfg["target_dte_min"], "target_dte_max": cfg["target_dte_max"],
        "short_delta": cfg["short_delta"], "wing_width_pct": cfg["wing_width_pct"],
        "min_spread_pct": cfg["min_spread_pct"], "profit_target_pct": cfg["profit_target_pct"],
        "stop_multiple": cfg["stop_multiple"], "exit_dte": cfg["exit_dte"],
        "max_positions": cfg["max_positions"],
        "spent": cfg.get("spent", 0.0), "realized_pnl": cfg.get("realized_pnl", 0.0),
        "positions": cfg.get("positions", []), "last_run": cfg.get("last_run"),
        "log": _recent_log(40),
    }


@router.post("/config")
def set_config(body: BotConfig) -> dict:
    cfg = _load()
    if body.enabled is not None:
        cfg["enabled"] = body.enabled
    if body.interval_sec is not None:
        cfg["interval_sec"] = max(int(body.interval_sec), 300)
    if body.symbols is not None:
        cfg["symbols"] = [s.strip().upper() for s in body.symbols if s.strip()]
    if body.contracts is not None:
        cfg["contracts"] = max(int(body.contracts), 1)
    if body.target_dte_min is not None:
        cfg["target_dte_min"] = max(int(body.target_dte_min), 1)
    if body.target_dte_max is not None:
        cfg["target_dte_max"] = max(int(body.target_dte_max), cfg["target_dte_min"])
    if body.short_delta is not None:
        cfg["short_delta"] = min(max(float(body.short_delta), 0.01), 0.49)
    if body.wing_width_pct is not None:
        cfg["wing_width_pct"] = min(max(float(body.wing_width_pct), 0.005), 0.5)
    if body.min_spread_pct is not None:
        cfg["min_spread_pct"] = max(float(body.min_spread_pct), 0.0)
    if body.profit_target_pct is not None:
        cfg["profit_target_pct"] = min(max(float(body.profit_target_pct), 0.05), 0.95)
    if body.stop_multiple is not None:
        cfg["stop_multiple"] = max(float(body.stop_multiple), 0.5)
    if body.exit_dte is not None:
        cfg["exit_dte"] = max(int(body.exit_dte), 1)
    if body.max_positions is not None:
        cfg["max_positions"] = max(int(body.max_positions), 1)
    _save(cfg)
    _log_event({"kind": "config", "enabled": cfg["enabled"], "symbols": cfg["symbols"]})
    return {"ok": True, **{k: cfg[k] for k in (
        "enabled", "interval_sec", "symbols", "contracts", "target_dte_min", "target_dte_max",
        "short_delta", "wing_width_pct", "min_spread_pct",
        "profit_target_pct", "stop_multiple", "exit_dte", "max_positions")}}


@router.post("/run-now")
async def run_now() -> dict:
    return await tick()
