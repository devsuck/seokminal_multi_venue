"""멀티-에이전트(스윙/데이트레이드/HL) CRUD + 틱 실행 + 성과/God-Mode/전략증류 라우트.
Alpaca 계좌 헬퍼는 alpaca_shared(shared.X)로, AUTOPILOT_DIR/agent_loop.sh 경로는
terminal 모듈에서 가져온다 — 둘 다 원래 router_autopilot.py 한 파일에 있던 것을
그대로 옮긴 것뿐, 로직 변경 없음."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import os as _os
import random
import shutil
import subprocess
import threading as _threading
import urllib.request

from alpaca.common.enums import Sort
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api_server import agent_store
from api_server.routers import alpaca_shared as shared
from api_server.routers.terminal import AUTOPILOT_DIR

agents_router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str
    type: str            # "swing" | "daytrade" | "hl_daytrade"
    account_alloc: float = 100000.0
    paper: bool = True   # False = live (real money / mainnet)
    autonomy: int = 2    # 1=조건식(Lv1, 백테스트 승격 전용) / 2=AI 전략가(구Lv2·3·4 통합) / 3=자가학습(구Lv5)
    market: str = "US"   # US | KR | MIXED (swing scope)
    condition: dict | None = None       # Lv1 전용: 백테스트에서 검증한 rule 1개 (buildSpawnRules 포맷)
    instrument_id: str | None = None    # Lv1 전용: condition과 함께 지정 (예: "005930.XKRX")
    option: dict | None = None          # option_lv1 전용: {expiry, strike, right, contracts}


class CyclePayload(BaseModel):
    cycle: int
    decision: str        # WATCH | BUY | SELL | SKIP | HOLD
    symbol: str | None = None
    score: float | None = None
    max_score: float | None = None
    action: str | None = None
    next_trigger: str | None = None
    cash_pct: float | None = None
    note: str | None = None
    markets: dict | None = None
    fill: dict | None = None  # {side, qty, price} when an order executed this cycle


def _agent_tmux(agent_id: str) -> str:
    return f"seokminal-agent-{agent_id}"


def _session_exists(name: str) -> bool:
    return subprocess.run(["tmux", "has-session", "-t", name], capture_output=True).returncode == 0


@agents_router.get("")
def list_agents() -> dict:
    agents = agent_store.list_agents()
    from jarvis.execution.agent_gate import validation_of
    # Reflect real tmux liveness so a crashed session doesn't read as running.
    for a in agents:
        a["session_live"] = _session_exists(_agent_tmux(a["id"]))
        v = validation_of(a)
        a["validated"] = v["validated"]
        a["validation_reason"] = v["reason"]
    return {"agents": agents, "profiles": agent_store.AGENT_PROFILES}


@agents_router.post("")
def create_agent(body: AgentCreate) -> dict:
    try:
        return agent_store.create_agent(body.name, body.type, body.account_alloc, body.paper, body.autonomy,
                                         body.market, body.condition, body.instrument_id, body.option)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@agents_router.get("/{agent_id}")
def get_agent(agent_id: str) -> dict:
    agent = agent_store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    agent["session_live"] = _session_exists(_agent_tmux(agent_id))
    return agent


@agents_router.delete("/{agent_id}")
def delete_agent(agent_id: str, confirm: str | None = None) -> dict:
    ag = agent_store.get_agent(agent_id)
    if ag is None:
        raise HTTPException(status_code=404, detail="agent not found")
    # 잠금(protected) 에이전트는 이름 확인 없이 삭제 불가 (실수 방지)
    if ag.get("protected") and confirm != ag.get("name"):
        raise HTTPException(status_code=403, detail=f"잠긴 에이전트 — 삭제하려면 이름('{ag.get('name')}') 확인 필요")
    name = _agent_tmux(agent_id)
    if _session_exists(name):
        subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)
    if not agent_store.delete_agent(agent_id):
        raise HTTPException(status_code=404, detail="agent not found")
    return {"status": "deleted", "agent_id": agent_id}


@agents_router.post("/{agent_id}/protect")
def protect_agent(agent_id: str, protected: bool = True) -> dict:
    ag = agent_store.set_protected(agent_id, protected)
    if ag is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return {"agent_id": agent_id, "protected": ag.get("protected", False)}


@agents_router.post("/{agent_id}/start")
def start_agent(agent_id: str) -> dict:
    agent = agent_store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    if shutil.which("tmux") is None:
        raise HTTPException(status_code=503, detail="tmux not installed")
    agent_loop = _os.path.normpath(_os.path.join(AUTOPILOT_DIR, "agent_loop.sh"))
    name = _agent_tmux(agent_id)
    if not _session_exists(name):
        subprocess.Popen(
            ["tmux", "new-session", "-d", "-s", name,
             agent_loop, agent_id, agent["type"], str(agent.get("autonomy", 2)),
             agent.get("market", "US"), str(agent.get("account_alloc", 100000))],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    agent_store.set_status(agent_id, "running")
    return {"status": "running", "agent_id": agent_id, "tmux_session": name}


@agents_router.post("/{agent_id}/stop")
def stop_agent(agent_id: str) -> dict:
    if agent_store.get_agent(agent_id) is None:
        raise HTTPException(status_code=404, detail="agent not found")
    name = _agent_tmux(agent_id)
    if _session_exists(name):
        subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)
    agent_store.set_status(agent_id, "stopped")
    return {"status": "stopped", "agent_id": agent_id}


@agents_router.get("/{agent_id}/cycles")
def get_agent_cycles(agent_id: str, limit: int = 50) -> dict:
    if agent_store.get_agent(agent_id) is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return {"cycles": agent_store.read_cycles(agent_id, limit=limit)}


@agents_router.post("/{agent_id}/cycles")
def post_agent_cycle(agent_id: str, body: CyclePayload) -> dict:
    agent = agent_store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    try:
        result = agent_store.record_cycle(agent_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if body.fill and body.symbol:
        try:
            from api_server.lv6_notify import notify_live_trade
            notify_live_trade(
                agent_id=agent_id,
                venue=agent.get("market", "?"),
                symbol=body.symbol,
                side=str(body.fill.get("side", "?")),
                size=float(body.fill.get("qty", 0)),
                price=float(body.fill.get("price", 0)),
                paper=bool(agent.get("paper", True)),
            )
        except Exception:
            pass  # 알림 실패는 조용히 — cycle 기록 자체는 이미 성공

    return result


# ── Per-agent performance dashboard ───────────────────────────────────────────

from api_server import agent_perf


def _latest_price(symbol: str) -> float | None:
    """Best-effort latest close for unrealized-PnL enrichment (None on failure)."""
    try:
        data_client = shared._data_client()
        now = dt.datetime.now(dt.timezone.utc)
        req = StockBarsRequest(
            symbol_or_symbols=symbol.upper(),
            timeframe=TimeFrame(5, TimeFrameUnit.Minute),
            start=now - dt.timedelta(days=5),
            sort=Sort.DESC,
            limit=1,
        )
        resp = data_client.get_stock_bars(req)
        bars = resp.data.get(symbol.upper()) or []
        return float(bars[-1].close) if bars else None
    except Exception:
        return None


def _ib_latest_prices(symbols: list[str]) -> dict[str, float | None]:
    """Live IB prices for open positions — Alpaca has no fill data for IB-executed
    symbols, so /performance always showed unrealized_pnl=0 for live IB agents.
    Reuses the same connect+get_intraday_bars+score_intraday path as the IB
    day-trade tick (agents.py _daytrade_tick_locked) — no order placed."""
    from backends.ib.order_client import IBOrderClient

    async def _fetch() -> dict[str, float | None]:
        ib = IBOrderClient(host=os.environ.get("IB_HOST", "127.0.0.1"), port=7496,
                            client_id=random.randint(600, 699))
        out: dict[str, float | None] = {}
        try:
            for sym in symbols:
                try:
                    bars = await ib.get_intraday_bars(sym)
                    out[sym] = _intraday.score_intraday(bars).get("price")
                except Exception:
                    out[sym] = None
        finally:
            await ib.close()
        return out

    try:
        return asyncio.run(_fetch())
    except Exception:
        return dict.fromkeys(symbols)


def _hl_latest_prices(symbols: list[str]) -> dict[str, float | None]:
    _, _, _, _, get_candles = _hl_funcs()
    out: dict[str, float | None] = {}
    for sym in symbols:
        try:
            bars = get_candles(sym)
            out[sym] = float(bars[-1]["c"]) if bars else None
        except Exception:
            out[sym] = None
    return out


@agents_router.get("/{agent_id}/performance")
def agent_performance(agent_id: str) -> dict:
    """Portfolio + trade log + realized/unrealized PnL for one agent.

    Derived from the agent's own recorded cycle fills (FIFO ledger), so it is
    isolated per agent even though Alpaca paper is a single shared account.
    """
    agent = agent_store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")

    cycles = agent_store.read_cycles(agent_id, limit=100000)
    perf = agent_perf.compute_performance(cycles)

    # Current price must come from the venue the agent actually trades on —
    # Alpaca never has data for IB/HL fills, so those always priced at None
    # and unrealized_pnl silently stayed 0 (agents.py, fixed 2026-08-02).
    symbols = [pos["symbol"] for pos in perf.open_positions]
    profile = agent.get("profile", {})
    venue = profile.get("venue") or ("KR" if agent.get("market") == "KR" else "US")
    from jarvis.execution.agent_gate import enforce_paper
    paper, _gate_note = enforce_paper(agent)
    if venue == "HL":
        prices = _hl_latest_prices(symbols)
    elif venue == "US" and not paper:
        prices = _ib_latest_prices(symbols)
    else:
        prices = {s: _latest_price(s) for s in symbols}

    # Enrich open positions with current price → unrealized PnL.
    unrealized = 0.0
    positions_out = []
    for pos in perf.open_positions:
        cur = prices.get(pos["symbol"])
        upl = (cur - pos["avg_price"]) * pos["qty"] if cur is not None else None
        if upl is not None:
            unrealized += upl
        positions_out.append({
            **pos,
            "current_price": cur,
            "unrealized_pnl": round(upl, 4) if upl is not None else None,
        })

    alloc = float(agent["account_alloc"])
    total_pnl = round(perf.realized_pnl + unrealized, 4)
    return {
        "agent_id": agent_id,
        "alloc": alloc,
        "cash": round(alloc + perf.realized_pnl - perf.invested, 4),
        "invested": perf.invested,
        "realized_pnl": perf.realized_pnl,
        "unrealized_pnl": round(unrealized, 4),
        "total_pnl": total_pnl,
        "return_pct": round(total_pnl / alloc * 100, 4) if alloc else 0.0,
        "open_positions": positions_out,
        "trades": list(reversed(perf.trades)),  # newest first for the log
    }


# ── God Mode 승급 (Lv3 자가학습 → live, 3조건 심사 + 사람 확인) ──────────────

from api_server import god_mode as _god_mode


@agents_router.get("/{agent_id}/god-mode/eligibility")
def god_mode_eligibility(agent_id: str) -> dict:
    """3조건 심사 결과 조회 — 버튼 활성화 여부 판단용. 승급은 아직 하지 않음."""
    try:
        return _god_mode.evaluate(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@agents_router.post("/{agent_id}/god-mode/promote")
def god_mode_promote(agent_id: str) -> dict:
    """God Mode 승급 실행 — 서버가 3조건을 재검증한 뒤에만 paper→live 전환.

    프론트에서 이미 eligibility로 확인했더라도 여기서 다시 검증한다(클라이언트를
    신뢰하지 않음). 이 호출 자체가 "사람의 최종 확인 클릭"이다 — 자동 승급 없음.
    """
    try:
        check = _god_mode.evaluate(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not check["eligible"]:
        raise HTTPException(status_code=403, detail={"message": "3조건 미충족 — 승급 불가", **check})
    try:
        agent = agent_store.promote_to_god_mode(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return agent


# ── Intraday (day-trading) scoring ────────────────────────────────────────────

from api_server import intraday_score as _intraday


# ── Deterministic day-trade tick (no LLM) ─────────────────────────────────────

from api_server import daytrade_logic
from api_server.lv5_learner import compute_lv5_params

_DAYTRADE_UNIVERSE = {
    "US": ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "AMD", "META", "AMZN", "MSFT", "GOOGL"],
    # KR (yfinance .KS symbols; KIS orders use the 6-digit code = strip .KS)
    "KR": ["005930.KS", "000660.KS", "373220.KS", "005380.KS", "000270.KS",
           "035420.KS", "035720.KS", "005490.KS", "068270.KS", "207940.KS"],
    # HL (all USDC-settled): crypto on the standard DEX (plain names) + TradFi on
    # the xyz builder DEX ('xyz:' prefix) — stocks, indices, commodities, forex.
    # Built from the user's watchlist plus liquid xyz markets. Crypto is limited
    # to the user's chosen names (not all perps).
    "HL": [
        # crypto (standard USDC DEX) — user's list only
        "BTC", "ETH", "SOL", "HYPE", "DOGE",
        # xyz TradFi (USDC) — user watchlist
        "xyz:SKHX", "xyz:XYZ100", "xyz:SP500", "xyz:SPCX", "xyz:SILVER",
        "xyz:CL", "xyz:BRENTOIL", "xyz:GOLD", "xyz:NVDA", "xyz:SMSN",
        "xyz:TSLA", "xyz:MSFT", "xyz:GOOGL", "xyz:JPY", "xyz:ORCL",
        "xyz:AAPL", "xyz:NATGAS", "xyz:META", "xyz:HOOD", "xyz:EUR", "xyz:NFLX",
        # xyz liquid additions (not in watchlist)
        "xyz:MU", "xyz:SNDK", "xyz:DRAM", "xyz:CRCL", "xyz:INTC", "xyz:MSTR",
        "xyz:AMD", "xyz:EWY", "xyz:AMZN", "xyz:COIN", "xyz:PLTR", "xyz:TSM",
        "xyz:COPPER", "xyz:PLATINUM", "xyz:AVGO", "xyz:LLY", "xyz:ASML",
        "xyz:JP225", "xyz:KR200", "xyz:BABA", "xyz:ARM",
    ],
}


def _hl_funcs():
    from hyperliquid.trader import (
        get_positions, place_order, close_position, set_leverage, get_candles,
    )
    return get_positions, place_order, close_position, set_leverage, get_candles


# One tick per agent at a time. Without this, an overlapping trigger (external
# scheduler retry, slow HL round-trip) reads the same stale position snapshot
# twice and fires duplicate entry orders before either one's fill shows up in
# get_positions().
_tick_locks: dict[str, _threading.Lock] = {}
_tick_locks_guard = _threading.Lock()


def _lock_for_tick(agent_id: str) -> _threading.Lock:
    with _tick_locks_guard:
        lock = _tick_locks.get(agent_id)
        if lock is None:
            lock = _threading.Lock()
            _tick_locks[agent_id] = lock
        return lock


@agents_router.post("/{agent_id}/daytrade-tick")
def daytrade_tick(agent_id: str, cycle: int = 0) -> dict:
    """Run one deterministic day-trade cycle for an agent — no LLM.

    Scores the universe with the intraday engine, closes positions whose signal
    flipped/degraded, opens the single best actionable signal (ATR-sized), and
    records a structured cycle. The agent loop just calls this on a timer, so a
    quiet market costs zero tokens.
    """
    lock = _lock_for_tick(agent_id)
    if not lock.acquire(blocking=False):
        return {"agent_id": agent_id, "venue": None, "decision": "SKIP",
                "actions": ["이전 tick 진행 중 — 중복 실행 방지"], "scores_summary": {}}
    try:
        return _daytrade_tick_locked(agent_id, cycle)
    finally:
        lock.release()


def _daytrade_tick_locked(agent_id: str, cycle: int) -> dict:
    agent = agent_store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    profile = agent.get("profile", {})
    # 데이트레이딩 타입은 profile.venue로 고정(kr_daytrade=KR, hl_daytrade=HL).
    # 스윙/장투는 profile.venue가 없으니 에이전트의 market으로 라우팅 →
    # KR봇이 US(Alpaca)로 새던 통화·시장 오라우팅 버그 수정.
    venue = profile.get("venue") or ("KR" if agent.get("market") == "KR" else "US")
    threshold = float(profile.get("buy_score_threshold", 55))
    leverage = float(profile.get("leverage", 1))
    position_pct = float(profile.get("position_pct", 0.10))
    autonomy_lv = int(agent.get("autonomy", 2))
    universe = _DAYTRADE_UNIVERSE.get(venue, _DAYTRADE_UNIVERSE["US"])
    # registry 게이트: 미검증 전략은 live 불가(페이퍼 강제) — 연구 트랙과 같은 기준
    from jarvis.execution.agent_gate import enforce_paper
    paper, _gate_note = enforce_paper(agent)
    # TradFi (xyz builder DEX) has no usable testnet liquidity → paper agents
    # trade crypto only; live agents get the full multi-asset universe.
    if venue == "HL" and paper:
        universe = [c for c in universe if ":" not in c]

    # Per-agent capital: size against this agent's allocated budget minus what
    # it already has deployed (its own ledger), NOT the shared account equity —
    # so multiple agents on one Alpaca/HL account each stay within their slice.
    alloc = float(agent["account_alloc"])
    _cycles = agent_store.read_cycles(agent_id, limit=100000)
    _perf = agent_perf.compute_performance(_cycles)
    budget = max(alloc + _perf.realized_pnl - _perf.invested, 0.0)
    # 브로커 계좌(Alpaca/HL/KIS)는 여러 봇이 공유(다른 US 데이트레이드 에이전트,
    # DART 오토파일럿 등) — 계좌 전체 보유를 내 포지션으로 착각해 남의 종목까지
    # 청산하는 사고 방지(2026-08-14, DART봇 보유 7종목이 KR 거시전략 에이전트에게
    # 조용히 청산됨). 이 에이전트가 자기 사이클 원장에 기록한 종목만 own_codes로 스코프.
    own_codes = {p["symbol"] for p in _perf.open_positions}

    # 드로다운 서킷브레이커: 배정 자본의 max_drawdown_pct(기본 50%) 이상 실현손실 시
    # 신규진입만 정지(청산/마킹은 계속) — lv5 가상화폐가 -78%까지 계속 진입한 사고 재발 방지.
    max_dd_pct = float(profile.get("max_drawdown_pct", 0.5))
    dd_pause = alloc > 0 and _perf.realized_pnl <= -alloc * max_dd_pct

    # Lv3(구Lv5) 자가학습: 이력 분석 → threshold/position_pct 자동 조정
    lv5_state: dict = {}
    lv5_agent_note: str = ""
    _market_ctx: dict = {}
    if autonomy_lv >= 3:
        lv5_state = compute_lv5_params(_cycles, threshold, position_pct)
        threshold = lv5_state["threshold"]
        position_pct = lv5_state["position_pct"]
        # 에이전틱 오버레이: 캐시된 Claude 분석 적용 → universe 재구성 포함
        from api_server.lv5_agent import trigger_review_if_needed, apply_cached_strategy
        from api_server.lv5_context import get_cached_context
        threshold, position_pct, universe, _agent_pause, lv5_agent_note = apply_cached_strategy(
            agent_id, threshold, position_pct, universe,
        )
        # 시장 컨텍스트 (VIX/어닝/뉴스) — 30분 캐시, 빠름
        _market_ctx = get_cached_context(venue, universe)
        # 10사이클마다 백그라운드 3-Phase 에이전틱 리뷰 트리거 (tick 블로킹 없음)
        trigger_review_if_needed(
            agent_id, venue, threshold, position_pct, universe, _cycles, cycle,
        )
        if _agent_pause:
            lv5_state["pause"] = True

    actions: list[str] = []
    if _gate_note:
        actions.append(_gate_note)
    if dd_pause:
        actions.append(f"드로다운 서킷브레이커: 실현손실 {_perf.realized_pnl:.2f}"
                        f"(배정 {alloc:.2f}의 {max_dd_pct*100:.0f}% 이상) — 신규진입 정지")
    if lv5_state.get("lv5_note"):
        actions.append(lv5_state["lv5_note"])
    if lv5_agent_note:
        actions.append(lv5_agent_note)
    # 한 사이클에 exit+entry가 동시에 일어날 수 있어(청산 후 다른 종목 진입) 단일
    # fill이 아니라 리스트로 기록 — 예전엔 exit가 fill을 아예 안 남겨서 원장에
    # 반영 안 되고, entry가 나중에 같은 변수를 덮어써 exit가 통째로 유실됐음
    # (2026-08-15, 491d9679 lv5 가상화폐 -94% 사고 원인).
    fills: list[dict] = []

    # Lv5 pause: 연속 손절 감지 시 entry skip (청산만 수행)
    lv5_pause = lv5_state.get("pause", False) or dd_pause

    if venue == "HL":
        get_positions, _, _, _, get_candles = _hl_funcs()
        # scores
        scores = {}
        for coin in universe:
            try:
                bars = get_candles(coin, "5m", 1440, paper)
                scores[coin] = _intraday.score_intraday(bars, crypto=True)
            except Exception as e:
                scores[coin] = {"error": str(e), "signal": "AVOID", "score": 0}
        # positions + equity
        pos_raw = get_positions(paper=paper)
        equity = float(pos_raw.get("margin_summary", {}).get("accountValue", 0) or 0)
        held = []
        qty_by_symbol: dict[str, float] = {}
        for p in pos_raw.get("asset_positions", []):
            szi = float(p["position"]["szi"])
            coin = p["position"]["coin"]
            if szi != 0 and coin in own_codes:
                cur = scores.get(coin, {}).get("price")
                held.append({"symbol": coin, "side": "long" if szi > 0 else "short",
                             "entry": float(p["position"].get("entryPx", 0) or 0), "current": cur})
                qty_by_symbol[coin] = abs(szi)
        # exits: hard TP/SL first, then signal flip/degrade
        tp_pct = float(profile.get("tp_pct", 0.05)); sl_pct = float(profile.get("sl_pct", 0.03))
        exits = daytrade_logic.stop_exits(held, tp_pct, sl_pct) + daytrade_logic.decide_exits(held, scores)
        from jarvis.execution.broker_bridge import BrokerOrderRejected, route_close, route_order, route_set_leverage
        for ex in {e["symbol"]: e for e in exits}.values():
            try:
                route_close(venue="HL", symbol=ex["symbol"], paper=paper)
                actions.append(f"close {ex['symbol']} ({ex['reason']})")
                q, px = qty_by_symbol.get(ex["symbol"]), scores.get(ex["symbol"], {}).get("price")
                if q and px:
                    fills.append({"symbol": ex["symbol"], "side": "sell" if ex["side"] == "long" else "buy",
                                  "qty": q, "price": px})
            except Exception as e:
                actions.append(f"close {ex['symbol']} FAILED: {e}")
        held_syms = {h["symbol"] for h in held}
        # entry
        entry = daytrade_logic.decide_entry(scores, threshold, allow_short=True)
        if entry and autonomy_lv >= 3:
            from api_server.lv5_dsl import apply_dsl, get_cached_dsl
            import datetime as _dt_dsl
            _thr_dsl, _pct_dsl, _skip_dsl, _reason_dsl = apply_dsl(
                get_cached_dsl(agent_id), entry["symbol"], threshold, position_pct,
                hour=_dt_dsl.datetime.now().hour, vix=_market_ctx.get("vix"),
                days_to_earnings=_market_ctx.get("earnings_days", {}).get(entry["symbol"]),
            )
            if _skip_dsl:
                actions.append(_reason_dsl); entry = None
            else:
                position_pct = _pct_dsl
        if entry and entry["symbol"] not in held_syms and budget > 0 and not lv5_pause:
            size = daytrade_logic.position_size(budget, position_pct, leverage, entry["entry"] or 0)
            size = round(size, 4)
            if size > 0:
                try:
                    route_set_leverage(coin=entry["symbol"], leverage=int(leverage), is_cross=True, paper=paper)
                    route_order({"venue": "HL", "symbol": entry["symbol"], "side": entry["side"],
                                 "quantity": size, "order_type": "market", "price": entry["entry"], "paper": paper})
                    fills.append({"symbol": entry["symbol"], "side": entry["side"], "qty": size, "price": entry["entry"]})
                    actions.append(f"{entry['side']} {entry['symbol']} {size} @ {entry['entry']} (x{int(leverage)})")
                except Exception as e:
                    actions.append(f"entry {entry['symbol']} FAILED: {e}")
    elif venue == "KR":
        # KR intraday: yfinance 5-min bars (KST session) + KIS execution (mock/real).
        from backends.kis.order_client import KISOrderClient
        if paper:
            kk, ks, kc = (os.environ.get("KIS_MOCK_APP_KEY", ""), os.environ.get("KIS_MOCK_APP_SECRET", ""), os.environ.get("KIS_MOCK_CANO", ""))
        else:
            kk, ks, kc = (os.environ.get("KIS_APP_KEY", ""), os.environ.get("KIS_APP_SECRET", ""), os.environ.get("KIS_CANO", ""))
        kis = KISOrderClient(kk, ks, kc, os.environ.get("KIS_ACNT_PRDT_CD", "01"), mock=paper)
        scores = {}
        for sym in universe:
            code = sym.split(".")[0]  # 005930.KS → 005930 (key + KIS order code)
            try:
                bars = shared._fetch_kr_intraday_bars(sym)
                scores[code] = _intraday.score_intraday(bars, market="KR")
            except Exception as e:
                scores[code] = {"error": str(e), "signal": "AVOID", "score": 0}
        # holdings (entry/current from KIS balance) + equity
        try:
            equity = float(kis.get_balance().get("net_asset", 0) or 0)
            held = [{"symbol": h["code"], "side": "long", "entry": h["avg_price"], "current": h["current"]}
                    for h in kis.get_holdings() if h["code"] in own_codes]
        except Exception as e:
            equity = 0.0; held = []
            actions.append(f"KIS 조회 실패: {str(e)[:60]}")
        tp_pct = float(profile.get("tp_pct", 0.03)); sl_pct = float(profile.get("sl_pct", 0.02))
        exits = daytrade_logic.stop_exits(held, tp_pct, sl_pct) + daytrade_logic.decide_exits(held, scores)
        for ex in {e["symbol"]: e for e in exits}.values():
            try:
                qtyh = next((h["qty"] for h in kis.get_holdings() if h["code"] == ex["symbol"]), 0)
                if qtyh > 0:
                    from jarvis.execution.broker_bridge import route_order
                    px_ex = next((h["current"] for h in held if h["symbol"] == ex["symbol"]), None)
                    route_order({"venue": "KR", "symbol": ex["symbol"], "side": "SELL", "quantity": int(qtyh),
                                 "order_type": "MARKET", "price": px_ex, "paper": paper})
                    actions.append(f"청산 {ex['symbol']} ({ex['reason']})")
                    px = next((h["current"] for h in held if h["symbol"] == ex["symbol"]), None)
                    if px:
                        fills.append({"symbol": ex["symbol"], "side": "sell", "qty": qtyh, "price": px})
            except Exception as e:
                actions.append(f"청산 {ex['symbol']} FAILED: {str(e)[:50]}")
        held_syms = {h["symbol"] for h in held}
        entry = daytrade_logic.decide_entry(scores, threshold, allow_short=False)  # KR 롱 온리
        if entry and autonomy_lv >= 3:
            from api_server.lv5_dsl import apply_dsl, get_cached_dsl
            import datetime as _dt_dsl
            _thr_dsl, _pct_dsl, _skip_dsl, _reason_dsl = apply_dsl(
                get_cached_dsl(agent_id), entry["symbol"], threshold, position_pct,
                hour=_dt_dsl.datetime.now().hour, vix=_market_ctx.get("vix"),
                days_to_earnings=_market_ctx.get("earnings_days", {}).get(entry["symbol"]),
            )
            if _skip_dsl:
                actions.append(_reason_dsl); entry = None
            else:
                position_pct = _pct_dsl
        if entry and entry["symbol"] not in held_syms and budget > 0 and not lv5_pause:
            qty = int(daytrade_logic.position_size(budget, position_pct, 1.0, entry["entry"] or 0))
            if qty > 0:
                try:
                    from jarvis.execution.broker_bridge import route_order
                    route_order({"venue": "KR", "symbol": entry["symbol"], "side": "BUY", "quantity": qty,
                                 "order_type": "MARKET", "price": entry["entry"], "paper": paper})
                    fills.append({"symbol": entry["symbol"], "side": "buy", "qty": qty, "price": entry["entry"]})
                    actions.append(f"매수 {entry['symbol']} {qty}주 @ {entry['entry']}")
                except Exception as e:
                    actions.append(f"매수 {entry['symbol']} FAILED: {str(e)[:50]}")
    else:  # US equities. paper→Alpaca(data+exec, free) / live→IB(data+exec, 구독).
        scores = {}
        tp_pct = float(profile.get("tp_pct", 0.04)); sl_pct = float(profile.get("sl_pct", 0.02))

        if paper:
            # Alpaca paper: 5분봉 데이터(무료 IEX) + Alpaca 페이퍼 실행. TWS 불필요.
            for sym in universe:
                try:
                    bars = shared._fetch_intraday_bars(sym)
                    scores[sym] = _intraday.score_intraday(bars)
                except Exception as e:
                    scores[sym] = {"error": str(e), "signal": "AVOID", "score": 0}
            client = shared._trading_client()
            held = []
            qty_by_symbol: dict[str, float] = {}
            for p in client.get_all_positions():
                q = float(p.qty)
                if q != 0 and p.symbol in own_codes:
                    held.append({"symbol": p.symbol, "side": "long" if q > 0 else "short",
                                 "entry": float(p.avg_entry_price), "current": float(p.current_price)})
                    qty_by_symbol[p.symbol] = abs(q)
            exits = daytrade_logic.stop_exits(held, tp_pct, sl_pct) + daytrade_logic.decide_exits(held, scores)
            from jarvis.execution.broker_bridge import route_close, route_order
            for ex in {e["symbol"]: e for e in exits}.values():
                try:
                    route_close(venue="US_ALPACA", symbol=ex["symbol"], paper=paper)
                    actions.append(f"close {ex['symbol']} ({ex['reason']})")
                    q, px = qty_by_symbol.get(ex["symbol"]), next((h["current"] for h in held if h["symbol"] == ex["symbol"]), None)
                    if q and px:
                        fills.append({"symbol": ex["symbol"], "side": "sell" if ex["side"] == "long" else "buy",
                                      "qty": q, "price": px})
                except Exception as e:
                    actions.append(f"close {ex['symbol']} FAILED: {e}")
            held_syms = {h["symbol"] for h in held}
            entry = daytrade_logic.decide_entry(scores, threshold, allow_short=False)
            if entry and autonomy_lv >= 3:
                from api_server.lv5_dsl import apply_dsl, get_cached_dsl
                import datetime as _dt_dsl
                _thr_dsl, _pct_dsl, _skip_dsl, _reason_dsl = apply_dsl(
                    get_cached_dsl(agent_id), entry["symbol"], threshold, position_pct,
                    hour=_dt_dsl.datetime.now().hour, vix=_market_ctx.get("vix"),
                    days_to_earnings=_market_ctx.get("earnings_days", {}).get(entry["symbol"]),
                )
                if _skip_dsl:
                    actions.append(_reason_dsl); entry = None
                else:
                    position_pct = _pct_dsl
            if entry and entry["symbol"] not in held_syms and budget > 0 and not lv5_pause:
                qty = int(daytrade_logic.position_size(budget, position_pct, 1.0, entry["entry"] or 0))
                if qty > 0:
                    try:
                        route_order({"venue": "US_ALPACA", "symbol": entry["symbol"], "side": "BUY",
                                     "quantity": qty, "order_type": "market", "price": entry["entry"], "paper": paper})
                        fills.append({"symbol": entry["symbol"], "side": "buy", "qty": qty, "price": entry["entry"]})
                        actions.append(f"buy {entry['symbol']} {qty} @ {entry['entry']}")
                    except Exception as e:
                        actions.append(f"entry {entry['symbol']} FAILED: {e}")
        else:
            # Live: IB via TWS (7496). 데이터(5분봉)+실행+실체결가를 한 세션에서
            # → 판단 소스와 체결 브로커 일치(괴리 없음), 실 avg_fill_price로 P&L 정확.
            from backends.ib.order_client import IBOrderClient
            from jarvis.execution.broker_bridge import route_order_ib

            async def _ib_us():
                ib = IBOrderClient(host=os.environ.get("IB_HOST", "127.0.0.1"), port=7496,
                                   client_id=random.randint(600, 699))
                acts, fls, sc = [], [], {}
                try:
                    # scores from IB 5-min bars (same broker as execution)
                    for sym in universe:
                        try:
                            bars = await ib.get_intraday_bars(sym)
                            sc[sym] = _intraday.score_intraday(bars)
                        except Exception as e:
                            sc[sym] = {"error": str(e), "signal": "AVOID", "score": 0}
                    raw = [p for p in await ib.get_positions() if p["symbol"] in own_codes]
                    held = [{"symbol": p["symbol"], "side": "long" if p["qty"] > 0 else "short",
                             "entry": p["avg_price"], "current": sc.get(p["symbol"], {}).get("price")}
                            for p in raw]
                    ex_all = daytrade_logic.stop_exits(held, tp_pct, sl_pct) + daytrade_logic.decide_exits(held, sc)
                    for e in {x["symbol"]: x for x in ex_all}.values():
                        pos = next((p for p in raw if p["symbol"] == e["symbol"]), None)
                        if pos:
                            close_side = "SELL" if pos["qty"] > 0 else "BUY"
                            px = next((h["current"] for h in held if h["symbol"] == e["symbol"]), None)
                            await route_order_ib({"symbol": e["symbol"], "side": close_side,
                                                   "quantity": int(abs(pos["qty"])), "order_type": "MARKET",
                                                   "price": px, "paper": False, "wait_fill": True}, ib)
                            acts.append(f"close {e['symbol']} ({e['reason']})")
                            if px:
                                fls.append({"symbol": e["symbol"], "side": "sell" if pos["qty"] > 0 else "buy",
                                           "qty": abs(pos["qty"]), "price": px})
                    hs = {p["symbol"] for p in raw}
                    en = daytrade_logic.decide_entry(sc, threshold, allow_short=False)
                    if en and en["symbol"] not in hs and budget > 0:
                        q = int(daytrade_logic.position_size(budget, position_pct, 1.0, en["entry"] or 0))
                        if q > 0:
                            r = await route_order_ib({"symbol": en["symbol"], "side": "BUY", "quantity": q,
                                                       "order_type": "MARKET", "price": en["entry"],
                                                       "paper": False, "wait_fill": True}, ib)
                            # 실 체결가 우선, 없으면(미체결/지연) 신호가로 폴백 표시
                            px = r.get("avg_fill_price") or en["entry"]
                            tag = "IB" if r.get("avg_fill_price") else "IB est"
                            fls.append({"symbol": en["symbol"], "side": "buy", "qty": q, "price": px})
                            acts.append(f"buy {en['symbol']} {q} @ {px} ({tag})")
                finally:
                    await ib.close()
                return acts, fls, sc

            try:
                a, ib_fills, scores = asyncio.run(_ib_us())
                actions.extend(a)
                fills.extend(ib_fills)
            except Exception as e:
                actions.append(f"IB(TWS) 실행 실패: {str(e)[:80]}")

    # Build + record the structured cycle (deterministic, no LLM).
    best = daytrade_logic.decide_entry(scores, 0, allow_short=(venue == "HL"))  # top candidate for display
    last_fill = fills[-1] if fills else None
    decision = "BUY" if (last_fill and last_fill["side"] == "buy") else "SELL" if last_fill else "SKIP"
    top_sym = (last_fill["symbol"] if last_fill else (best["symbol"] if best else "NONE"))
    top_score = (best["score"] if best else 0)
    note_bits = actions if actions else ["실행 없음 — 조건 미충족"]
    payload = {
        "cycle": cycle, "decision": decision, "symbol": top_sym,
        "score": top_score, "max_score": 100, "best_score": top_score,
        "action": "; ".join(actions) if actions else "none",
        "next_trigger": f"conviction ≥ {threshold:.0f} 신호",
        "cash_pct": None, "note": " | ".join(note_bits)[:400],
        "fills": fills, "markets": {"US": None, "KR": None},
        "lv5_threshold": threshold if autonomy_lv >= 3 else None,
        "lv5_note": lv5_state.get("lv5_note"),
        "lv5_agent_note": lv5_agent_note or None,
        "lv5_win_rate": lv5_state.get("win_rate"),
        "lv5_n_trades": lv5_state.get("n_trades"),
    }
    agent_store.record_cycle(agent_id, payload)
    return {"agent_id": agent_id, "venue": venue, "decision": decision,
            "actions": actions, "scores_summary": {k: v.get("signal") for k, v in scores.items()}}


# ── Lv1 조건식 페이퍼 tick (백테스트 승격 전용, daily bar) ────────────────────

from api_server import condition_tick as _condition_tick


@agents_router.post("/{agent_id}/condition-tick")
def condition_tick_endpoint(agent_id: str, cycle: int = 0) -> dict:
    """Lv1 에이전트 1틱 — 백테스트에서 검증한 조건식을 daily bar로 그대로 평가.

    daytrade_tick과 별도 경로: score-threshold가 아니라 condition_engine으로 게이트를
    걸고, 게이트 통과 후엔 EMA fast/slow 크로스로 진입/청산한다(EMACrossFlat과 동일 의미론).
    Lv1은 항상 paper — 실집행 없음.
    """
    agent = agent_store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    if int(agent.get("autonomy", 0)) != 1:
        raise HTTPException(status_code=400, detail="condition-tick은 Lv1(autonomy=1) 전용")

    result = _condition_tick.evaluate_agent(agent)
    action = result["action"]
    instrument_id = agent["instrument_id"]
    profile = agent.get("profile", {})
    position_pct = float(profile.get("position_pct", 0.10))

    fill = None
    note_bits = [result["note"]]

    # 드로다운 서킷브레이커: 배정 자본의 max_drawdown_pct(기본 50%) 이상 실현손실 시 신규진입 정지.
    alloc = float(agent["account_alloc"])
    _cycles = agent_store.read_cycles(agent_id, limit=100000)
    _perf = agent_perf.compute_performance(_cycles)
    budget = max(alloc + _perf.realized_pnl - _perf.invested, 0.0)
    max_dd_pct = float(profile.get("max_drawdown_pct", 0.5))
    dd_pause = alloc > 0 and _perf.realized_pnl <= -alloc * max_dd_pct
    if dd_pause and action == "BUY":
        note_bits.append(f"드로다운 서킷브레이커: 실현손실 {_perf.realized_pnl:.2f}"
                          f"(배정 {alloc:.2f}의 {max_dd_pct*100:.0f}% 이상) — 신규진입 정지")

    if action in ("BUY", "SELL"):
        is_kr = instrument_id.endswith(".XKRX")
        from jarvis.execution.broker_bridge import route_order
        try:
            if is_kr:
                from backends.kis.order_client import KISOrderClient
                kk = os.environ.get("KIS_MOCK_APP_KEY", "")
                ks = os.environ.get("KIS_MOCK_APP_SECRET", "")
                kc = os.environ.get("KIS_MOCK_CANO", "")
                kis = KISOrderClient(kk, ks, kc, os.environ.get("KIS_ACNT_PRDT_CD", "01"), mock=True)
                code = instrument_id.split(".")[0]
                if action == "BUY":
                    qty = int(daytrade_logic.position_size(budget, position_pct, 1.0, result["price"]))
                    if qty > 0 and not dd_pause:
                        route_order({"venue": "KR", "symbol": code, "side": "BUY", "quantity": qty,
                                     "order_type": "MARKET", "price": result["price"], "paper": True})
                        fill = {"side": "buy", "qty": qty, "price": result["price"]}
                        note_bits.append(f"매수 {code} {qty}주 @ {result['price']}")
                else:
                    # KIS 모의계좌는 다른 봇과 공유 — 브로커 전체 보유가 아니라
                    # 이 에이전트 원장에 기록된 수량만큼만 매도(own_codes 필터와 동일 취지).
                    own_qty = int(next((p["qty"] for p in _perf.open_positions
                                        if p["symbol"] == instrument_id), 0))
                    broker_qty = int(next((h["qty"] for h in kis.get_holdings() if h["code"] == code), 0))
                    qtyh = min(own_qty, broker_qty)
                    if qtyh > 0:
                        route_order({"venue": "KR", "symbol": code, "side": "SELL", "quantity": qtyh,
                                     "order_type": "MARKET", "price": result["price"], "paper": True})
                        fill = {"side": "sell", "qty": qtyh, "price": result["price"]}
                        note_bits.append(f"청산 {code} {qtyh}주 @ {result['price']}")
            else:
                symbol = instrument_id.split(".")[0]
                if action == "BUY":
                    qty = int(daytrade_logic.position_size(budget, position_pct, 1.0, result["price"]))
                    if qty > 0 and not dd_pause:
                        route_order({"venue": "US_ALPACA", "symbol": symbol, "side": "BUY", "quantity": qty,
                                     "order_type": "market", "price": result["price"], "paper": True})
                        fill = {"side": "buy", "qty": qty, "price": result["price"]}
                        note_bits.append(f"buy {symbol} {qty} @ {result['price']}")
                else:
                    # Alpaca 페이퍼도 다른 봇과 공유 계좌 — close_position은 그 심볼
                    # 보유 전체를 닫으므로 남의 몫까지 팔 수 있다. 내 원장 수량만 매도.
                    own_qty = int(next((p["qty"] for p in _perf.open_positions
                                        if p["symbol"] == instrument_id), 0))
                    if own_qty > 0:
                        route_order({"venue": "US_ALPACA", "symbol": symbol, "side": "SELL", "quantity": own_qty,
                                     "order_type": "market", "price": result["price"], "paper": True})
                        fill = {"side": "sell", "qty": own_qty, "price": result["price"]}
                        note_bits.append(f"close {symbol} {own_qty}")
        except Exception as e:
            note_bits.append(f"{action} 실패: {str(e)[:80]}")
            fill = None

    agent_store.set_condition_state(agent_id, spawned=result["spawned"], position_state=result["position_state"])

    # BUY/SELL은 실제 체결(fill)이 있어야 기록 — 주문 실패 시 SKIP으로 정직하게 남김.
    decision = result["action"] if result["action"] not in ("BUY", "SELL") or fill else "SKIP"
    payload = {
        "cycle": cycle, "decision": decision, "symbol": instrument_id,
        "score": None, "max_score": None, "best_score": None,
        "action": "; ".join(note_bits), "next_trigger": "조건식 게이트 + EMA 크로스",
        "cash_pct": None, "note": " | ".join(note_bits)[:400],
        "fill": fill, "fill_symbol": instrument_id if fill else None,
    }
    agent_store.record_cycle(agent_id, payload)
    return {"agent_id": agent_id, "decision": decision, "note": result["note"],
            "spawned": result["spawned"], "position_state": result["position_state"]}


@agents_router.post("/{agent_id}/option-condition-tick")
async def option_condition_tick_endpoint(agent_id: str, cycle: int = 0) -> dict:
    """option_lv1 에이전트 1틱 — condition_tick과 동일한 게이트+EMA 판단을 기초자산 daily
    bar로 계산하되, 체결은 옵션 계약(콜/풋)으로 나간다. 항상 IB paper(7497) — 실집행 없음."""
    agent = agent_store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    if agent.get("type") != "option_lv1":
        raise HTTPException(status_code=400, detail="option-condition-tick은 option_lv1 전용")
    if int(agent.get("autonomy", 0)) != 1:
        raise HTTPException(status_code=400, detail="option-condition-tick은 Lv1(autonomy=1) 전용")

    result = _condition_tick.evaluate_agent(agent)
    action = result["action"]
    instrument_id = agent["instrument_id"]
    symbol = instrument_id.split(".")[0]
    expiry = agent["option_expiry"]
    strike = float(agent["option_strike"])
    right = agent["option_right"]
    contracts = int(agent["option_contracts"])

    fill = None
    note_bits = [result["note"]]

    if action in ("BUY", "SELL"):
        from api_server.main import _check_risk
        from backends.ib.order_client import IBOrderClient

        ib = IBOrderClient(host=os.environ.get("IB_HOST", "127.0.0.1"), port=7497,
                            client_id=int(os.environ.get("IB_OPTION_ORDER_CLIENT_ID", "12")))
        try:
            _check_risk(side=action, quantity=contracts, price_estimate=None, option_expiry=expiry)
            order_result = await ib.place_option_order(symbol, expiry, strike, right, action, contracts, "MARKET", None)
            fill = {"side": action.lower(), "qty": contracts, "price": order_result.get("filled") or None}
            note_bits.append(
                f"{'매수' if action == 'BUY' else '청산'} {symbol} {expiry} {strike}{right} x{contracts}계약"
            )
        except HTTPException:
            raise
        except (ConnectionRefusedError, OSError) as exc:
            note_bits.append(f"{action} 실패: IB TWS 연결 안됨 ({str(exc)[:60]})")
        except Exception as e:
            note_bits.append(f"{action} 실패: {str(e)[:80]}")
        finally:
            await ib.close()

    agent_store.set_condition_state(agent_id, spawned=result["spawned"], position_state=result["position_state"])

    decision = result["action"] if result["action"] not in ("BUY", "SELL") or fill else "SKIP"
    option_label = f"{symbol} {expiry} {strike}{right}"
    payload = {
        "cycle": cycle, "decision": decision, "symbol": option_label,
        "score": None, "max_score": None, "best_score": None,
        "action": "; ".join(note_bits), "next_trigger": "조건식 게이트 + EMA 크로스 (옵션 체결)",
        "cash_pct": None, "note": " | ".join(note_bits)[:400],
        "fill": fill, "fill_symbol": option_label if fill else None,
    }
    agent_store.record_cycle(agent_id, payload)
    return {"agent_id": agent_id, "decision": decision, "note": result["note"],
            "spawned": result["spawned"], "position_state": result["position_state"]}


# ── Strategy distillation (Lv3 자유탐색 → 검증된 규칙 전략) ────────────────────

import shutil as _shutil


def _claude_bin() -> str | None:
    return _shutil.which("claude") or (
        _os.path.expanduser("~/.local/bin/claude")
        if _os.path.exists(_os.path.expanduser("~/.local/bin/claude")) else None
    )


@agents_router.post("/{agent_id}/distill")
def distill_strategy(agent_id: str) -> dict:
    """Distil an agent's realized trades into a *backtestable* rule strategy.

    Turns Lv3 discretionary trading (no fixed strategy) into a concrete
    macd/rsi/ema_cross spec, then validates it on history via /backtest — the
    bridge from 'AI vibes that worked' to a reproducible, deployable edge.
    """
    agent = agent_store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")

    cycles = agent_store.read_cycles(agent_id, limit=100000)
    perf = agent_perf.compute_performance(cycles)
    trades = perf.trades
    if len(trades) < 3:
        raise HTTPException(status_code=422, detail="거래 이력 부족 — 증류하려면 체결 3건 이상 필요")

    claude = _claude_bin()
    if claude is None:
        raise HTTPException(status_code=503, detail="claude CLI 없음")

    # Compact trade log for the LLM.
    log_lines = [
        f"{t.get('ts','')} {t['side']} {t['symbol']} {t['qty']}@{t['price']} "
        f"pnl={t.get('realized_pnl')} 이유:{t.get('reason','')}"
        for t in trades[-40:]
    ]
    prompt = (
        "다음은 자율 트레이딩 에이전트의 실제 체결 로그다. 반복되는 진입/청산 로직을 "
        "백테스트 가능한 단일 전략으로 증류하라. macd/rsi/ema_cross 중 가장 근접한 것과 "
        "파라미터를 골라라.\n\n" + "\n".join(log_lines) +
        "\n\n마지막 줄에 JSON 한 줄만 출력(설명 금지):\n"
        '{"instrument_id":"AAPL.NASDAQ","strategy":"macd|rsi|ema_cross",'
        '"params":{"fast":12,"slow":26,"signal_period":9},"rationale":"한 줄 근거"}'
    )
    try:
        proc = subprocess.run(
            [claude, "--dangerously-skip-permissions", "--permission-mode",
             "bypassPermissions", "--print", prompt],
            capture_output=True, text=True, timeout=150,
        )
        raw = proc.stdout
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"distill LLM 실패: {e}") from e

    m = re.findall(r"\{.*\}", raw)
    if not m:
        raise HTTPException(status_code=502, detail="증류 결과 파싱 실패 (JSON 없음)")
    try:
        spec = json.loads(m[-1])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"증류 JSON 파싱 실패: {e}") from e

    instrument = spec.get("instrument_id", "")
    strategy = spec.get("strategy", "")
    params = spec.get("params", {}) or {}
    if strategy not in ("macd", "rsi", "ema_cross"):
        raise HTTPException(status_code=422, detail=f"증류 전략 미지원: {strategy!r}")

    # Validate on ~1y history via the backtest endpoint.
    end = dt.date.today()
    start = end - dt.timedelta(days=365)
    q = {"instrument_id": instrument, "start": start.isoformat(),
         "end": end.isoformat(), "strategy": strategy}
    for k in ("fast", "slow", "signal_period", "period"):
        if k in params:
            q[k] = params[k]
    qs = "&".join(f"{k}={v}" for k, v in q.items())
    metrics = {}
    try:
        with urllib.request.urlopen(
            f"http://localhost:8000/backtest?{qs}", timeout=30
        ) as r:
            bt = json.loads(r.read())
        metrics = {k: bt.get(k) for k in ("sharpe_ratio", "total_pnl_pct", "win_rate")}
    except Exception as e:
        metrics = {"error": str(e)}

    sharpe = metrics.get("sharpe_ratio")
    validated = isinstance(sharpe, (int, float)) and sharpe >= 1.0
    return {
        "agent_id": agent_id,
        "proposal": {"instrument_id": instrument, "strategy": strategy,
                     "params": params, "rationale": spec.get("rationale", "")},
        "backtest": metrics,
        "validated": validated,
        "verdict": ("검증 통과 (Sharpe≥1) — 라이브 배포 후보" if validated
                    else "검증 미달 — 라이브 부적합, 재탐색 권장"),
        "trades_analyzed": len(trades),
    }


@agents_router.get("/overview/all")
def agents_overview() -> dict:
    """Portfolio-level summary across ALL agents (realized PnL, fast — no price
    fetches). For the multi-agent overview dashboard + graphs."""
    rows = []
    tot_alloc = tot_realized = 0.0
    for a in agent_store.list_agents():
        perf = agent_perf.compute_performance(agent_store.read_cycles(a["id"], limit=100000))
        alloc = float(a["account_alloc"])
        realized = perf.realized_pnl
        tot_alloc += alloc
        tot_realized += realized
        rows.append({
            "id": a["id"], "name": a["name"], "type": a["type"],
            "paper": a["paper"], "status": a["status"], "autonomy": a.get("autonomy"),
            "alloc": alloc, "realized_pnl": realized,
            "return_pct": round(realized / alloc * 100, 3) if alloc else 0.0,
            "invested": perf.invested, "cash": round(alloc + realized - perf.invested, 2),
            "open_positions": len(perf.open_positions), "trades": len(perf.trades),
        })
    return {
        "agents": rows,
        "totals": {
            "count": len(rows),
            "alloc": round(tot_alloc, 2),
            "realized_pnl": round(tot_realized, 2),
            "return_pct": round(tot_realized / tot_alloc * 100, 3) if tot_alloc else 0.0,
            "running": sum(1 for r in rows if r["status"] == "running"),
        },
    }


@agents_router.get("/accounts/balances")
def account_balances() -> dict:
    """Real account balances per venue + how much is already allocated to agents.
    Fault-tolerant: each source is independent so one failure doesn't hide the
    rest. Lets the user size allocations even with zero agents."""
    out: dict = {"venues": {}, "allocated": {}}

    # Alpaca (paper by env)
    try:
        client = shared._trading_client()
        acc = client.get_account()
        out["venues"]["alpaca"] = {
            "mode": "paper" if shared.ALPACA_PAPER else "live",
            "equity": float(acc.equity), "cash": float(acc.cash),
            "buying_power": float(acc.buying_power),
        }
    except Exception as e:
        out["venues"]["alpaca"] = {"error": str(e)[:120]}

    # KIS 모의 + 실계좌. KIS 모의서버가 간헐적으로 rt_cd=2 / RemoteDisconnected를
    # 뱉어 → 실패 시 1회 재시도. 모의·실전 독립 처리(하나 실패가 다른 하나 숨기지 않게).
    from backends.kis.order_client import KISOrderClient
    import time as _t

    def _kis_balance(app_key, secret, cano, mock):
        # KIS 서버가 rt_cd=2 (빈 msg) / RemoteDisconnected를 자주 던져 최대 4회 재시도.
        last = None
        for attempt in range(4):
            try:
                c = KISOrderClient(app_key, secret, cano, os.environ.get("KIS_ACNT_PRDT_CD", "01"), mock=mock)
                b = c.get_balance()
                return {"mode": "paper" if mock else "live", "net_asset": b["net_asset"],
                        "deposit": b["deposit"], "total_eval": b["total_eval"]}
            except Exception as e:  # noqa: BLE001
                last = e
                if attempt < 3:
                    _t.sleep(0.5)
        return {"error": str(last)[:120]}

    mk, ms, mc = (os.environ.get("KIS_MOCK_APP_KEY", ""), os.environ.get("KIS_MOCK_APP_SECRET", ""), os.environ.get("KIS_MOCK_CANO", ""))
    out["venues"]["kis_mock"] = _kis_balance(mk, ms, mc, True) if (mk and ms and mc) else {"error": "KIS_MOCK 키 없음"}
    rk, rs, rc = (os.environ.get("KIS_APP_KEY", ""), os.environ.get("KIS_APP_SECRET", ""), os.environ.get("KIS_CANO", ""))
    out["venues"]["kis_live"] = _kis_balance(rk, rs, rc, False) if (rk and rs and rc) else {"error": "KIS 실계좌 키 없음"}

    # IB live only (US paper is Alpaca; IB paper dropped). Requires TWS.
    try:
        from backends.ib.client import IBClient
        try:
            # Hard timeout: IB summary can hang (flaky TWS / account-update push)
            # and this endpoint feeds the balance panel — never let it block.
            async def _ib_summary():
                return await asyncio.wait_for(
                    IBClient(port=7496, client_id=random.randint(700, 799)).get_account_summary(),
                    timeout=6.0,
                )
            summ = asyncio.run(_ib_summary())
            out["venues"]["ib_live"] = {"mode": "live", "net_liquidation": summ["net_liquidation"],
                                        "cash": summ["total_cash"], "currency": summ.get("currency", "USD")}
        except (TimeoutError, asyncio.TimeoutError):
            out["venues"]["ib_live"] = {"error": "IB 응답 시간 초과 (TWS 확인)"}
        except Exception as e:
            out["venues"]["ib_live"] = {"error": str(e)[:80] or "IB 연결 실패"}
    except Exception as e:
        out["venues"]["ib_live"] = {"error": str(e)[:120]}

    # Hyperliquid testnet + mainnet
    try:
        from hyperliquid.trader import get_positions as _hlpos
        for label, paper in (("hl_testnet", True), ("hl_mainnet", False)):
            try:
                p = _hlpos(paper=paper)
                out["venues"][label] = {
                    "mode": "paper" if paper else "live",
                    "account_value": float(p.get("margin_summary", {}).get("accountValue", 0) or 0),
                }
            except Exception as e:
                out["venues"][label] = {"error": str(e)[:120]}
    except Exception as e:
        out["venues"]["hl"] = {"error": str(e)[:120]}

    # Allocated to agents, split by venue (type/market → venue).
    us = kr = hl_paper = hl_live = 0.0
    for a in agent_store.list_agents():
        alloc = float(a["account_alloc"])
        if a["type"] == "hl_daytrade":
            if a["paper"]:
                hl_paper += alloc
            else:
                hl_live += alloc
        elif a.get("market") == "KR":
            kr += alloc  # kr_macro → KIS, not Alpaca
        else:  # swing / autonomous → Alpaca (US)
            us += alloc
    out["allocated"] = {
        "us_alpaca": round(us, 2),
        "kr_kis": round(kr, 2),
        "hl_testnet": round(hl_paper, 2),
        "hl_mainnet": round(hl_live, 2),
    }

    # Normalized list for the frontend (one primary balance + currency + how much
    # is already allocated to agents on that venue).
    def _num(v: dict, *keys):
        for k in keys:
            if isinstance(v, dict) and k in v and not v.get("error"):
                return v[k]
        return None
    ven = out["venues"]
    out["accounts"] = [
        {"venue": "alpaca", "label": "Alpaca · 미국주식", "ccy": "USD",
         "mode": ven.get("alpaca", {}).get("mode"),
         "balance": _num(ven.get("alpaca", {}), "equity"),
         "allocated": round(us, 2), "error": ven.get("alpaca", {}).get("error")},
        {"venue": "kis_mock", "label": "한투 · 모의(한국주식)", "ccy": "KRW",
         "mode": "paper", "balance": _num(ven.get("kis_mock", {}), "net_asset"),
         "allocated": round(kr, 2), "error": ven.get("kis_mock", {}).get("error")},
        {"venue": "kis_live", "label": "한투 · 실계좌(한국주식)", "ccy": "KRW",
         "mode": "live", "balance": _num(ven.get("kis_live", {}), "net_asset"),
         "allocated": 0.0, "error": ven.get("kis_live", {}).get("error")},
        {"venue": "ib_live", "label": "IB · 실계좌(미국)", "ccy": ven.get("ib_live", {}).get("currency", "USD"),
         "mode": "live", "balance": _num(ven.get("ib_live", {}), "net_liquidation"),
         "allocated": 0.0, "error": ven.get("ib_live", {}).get("error")},
        {"venue": "hl_testnet", "label": "HL · 테스트넷(크립토)", "ccy": "USDC",
         "mode": "paper", "balance": _num(ven.get("hl_testnet", {}), "account_value"),
         "allocated": round(hl_paper, 2), "error": ven.get("hl_testnet", {}).get("error")},
        {"venue": "hl_mainnet", "label": "HL · 메인넷(실USDC)", "ccy": "USDC",
         "mode": "live", "balance": _num(ven.get("hl_mainnet", {}), "account_value"),
         "allocated": round(hl_live, 2), "error": ven.get("hl_mainnet", {}).get("error")},
    ]
    return out


@agents_router.get("/accounts/kis-holdings")
def kis_holdings(mock: bool = True) -> dict:
    """한투(KIS) 모의/실계좌 보유 종목. mock=false면 실계좌."""
    from backends.kis.order_client import KISOrderClient
    from api_server.kr_names import name_for

    if mock:
        kk, ks, kc = (os.environ.get("KIS_MOCK_APP_KEY", ""), os.environ.get("KIS_MOCK_APP_SECRET", ""),
                      os.environ.get("KIS_MOCK_CANO", ""))
    else:
        kk, ks, kc = (os.environ.get("KIS_APP_KEY", ""), os.environ.get("KIS_APP_SECRET", ""),
                      os.environ.get("KIS_CANO", ""))
    if not (kk and ks and kc):
        return {"holdings": [], "error": "KIS 키 없음"}

    try:
        c = KISOrderClient(kk, ks, kc, os.environ.get("KIS_ACNT_PRDT_CD", "01"), mock=mock)
        out = []
        for h in c.get_holdings():
            entry = float(h.get("avg_price", 0) or 0)
            cur = float(h.get("current", 0) or 0)
            code = h.get("code")
            out.append({
                "code": code, "name": name_for(code) or code,
                "qty": h.get("qty"), "avg_price": entry, "current": cur,
                "return_pct": round((cur - entry) / entry * 100, 2) if entry else None,
            })
        return {"holdings": out, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"holdings": [], "error": str(exc)[:120]}
