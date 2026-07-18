"""
Alpaca Autopilot Router
Provides trading endpoints via alpaca-py + Finnhub news context.
"""

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
import asyncio
import datetime as dt
import httpx
import json
import os
import random
import re
import shutil
import socket
import subprocess
import urllib.request

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/alpaca", tags=["alpaca"])

ALPACA_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"
FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_key() -> None:
    if not ALPACA_KEY:
        raise HTTPException(status_code=503, detail="ALPACA_API_KEY not set in .env")


def _trading_client(paper: bool = ALPACA_PAPER) -> TradingClient:
    _require_key()
    return TradingClient(api_key=ALPACA_KEY, secret_key=ALPACA_SECRET, paper=paper)


def _data_client() -> StockHistoricalDataClient:
    _require_key()
    return StockHistoricalDataClient(api_key=ALPACA_KEY, secret_key=ALPACA_SECRET)


def _fmt_order(o) -> dict:
    return {
        "id": str(o.id),
        "symbol": o.symbol,
        "side": o.side.value,
        "qty": float(o.qty) if o.qty is not None else 0.0,
        "filled_qty": float(o.filled_qty) if o.filled_qty is not None else 0.0,
        "status": o.status.value,
        "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price is not None else None,
        "created_at": o.created_at.isoformat() if o.created_at else "",
    }


# ── Technical Indicators ──────────────────────────────────────────────────────

def calc_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas[-period:]]
    losses = [abs(min(d, 0)) for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def calc_ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    emas = [values[0]]
    for v in values[1:]:
        emas.append(v * k + emas[-1] * (1 - k))
    return emas


def calc_macd(closes: list[float]) -> tuple[float, float, float]:
    """Returns (macd, signal, histogram)."""
    if len(closes) < 26:
        return 0.0, 0.0, 0.0
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    macd_line = [ema12[i] - ema26[i] for i in range(len(closes))]
    signal_line = calc_ema(macd_line, 9) if len(macd_line) >= 9 else [macd_line[-1]]
    macd_val = round(macd_line[-1], 4)
    signal_val = round(signal_line[-1], 4)
    return macd_val, signal_val, round(macd_val - signal_val, 4)


# ── Pydantic models ───────────────────────────────────────────────────────────

class OrderRequest(BaseModel):
    symbol: str
    side: str           # "buy" | "sell"
    qty: float
    type: str = "market"        # "market" | "limit"
    limit_price: float | None = None
    paper: bool = True


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/account")
def get_account() -> dict:
    client = _trading_client()
    try:
        acc = client.get_account()
        return {
            "equity": float(acc.equity),
            "buying_power": float(acc.buying_power),
            "cash": float(acc.cash),
            "portfolio_value": float(acc.portfolio_value),
            "pattern_day_trader": bool(acc.pattern_day_trader),
            "paper": ALPACA_PAPER,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Alpaca account error: {e}") from e


@router.get("/positions")
def get_positions() -> list[dict]:
    client = _trading_client()
    try:
        positions = client.get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc),
                "market_value": float(p.market_value),
                "side": p.side.value,
            }
            for p in positions
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Alpaca positions error: {e}") from e


@router.get("/orders")
def get_orders() -> list[dict]:
    client = _trading_client()
    try:
        orders = client.get_orders(
            filter=GetOrdersRequest(limit=20, status=QueryOrderStatus.ALL)
        )
        return [_fmt_order(o) for o in orders]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Alpaca orders error: {e}") from e


@router.post("/order")
def place_order(req: OrderRequest) -> dict:
    if not ALPACA_KEY:
        raise HTTPException(status_code=503, detail="ALPACA_API_KEY not set in .env")
    side = OrderSide.BUY if req.side.lower() == "buy" else OrderSide.SELL
    client = TradingClient(api_key=ALPACA_KEY, secret_key=ALPACA_SECRET, paper=req.paper)
    try:
        if req.type == "limit" and req.limit_price:
            order_req = LimitOrderRequest(
                symbol=req.symbol.upper(),
                qty=req.qty,
                side=side,
                limit_price=req.limit_price,
                time_in_force=TimeInForce.GTC,
            )
        else:
            order_req = MarketOrderRequest(
                symbol=req.symbol.upper(),
                qty=req.qty,
                side=side,
                time_in_force=TimeInForce.DAY,
            )
        order = client.submit_order(order_req)
        return _fmt_order(order)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Alpaca order failed: {e}") from e


@router.delete("/order/{order_id}")
def cancel_order(order_id: str) -> dict:
    client = _trading_client()
    try:
        client.cancel_order_by_id(order_id)
        return {"status": "cancelled", "order_id": order_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Alpaca cancel failed: {e}") from e


@router.get("/context/{symbol}")
def get_context(symbol: str) -> dict:
    """
    Returns rich context (bars, technicals, news, position, account)
    suitable for an LLM to make a trading decision.
    """
    _require_key()
    symbol = symbol.upper()

    # ── 1. Fetch 5-min bars (enough for MACD+RSI) ────────────────────────────
    data_client = _data_client()
    now = dt.datetime.now(dt.timezone.utc)
    start_time = now - dt.timedelta(days=7)  # back 7 days to get ~60+ bars across sessions

    tf5 = TimeFrame(5, TimeFrameUnit.Minute)
    bars_raw: list = []
    try:
        bars_req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf5,
            start=start_time,
            limit=60,
        )
        bars_resp = data_client.get_stock_bars(bars_req)
        if symbol in bars_resp:
            bars_raw = list(bars_resp[symbol])
    except Exception:
        bars_raw = []

    closes = [float(b.close) for b in bars_raw]
    opens = [float(b.open) for b in bars_raw]
    highs = [float(b.high) for b in bars_raw]
    lows = [float(b.low) for b in bars_raw]
    volumes = [float(b.volume) for b in bars_raw]

    # RSI & MACD on all available closes
    rsi = calc_rsi(closes)
    macd_val, macd_signal, macd_hist = calc_macd(closes)

    # Volume ratio: last bar volume vs 20-bar avg
    vol_ratio = 1.0
    if len(volumes) >= 2:
        avg_vol = sum(volumes[:-1][-20:]) / min(len(volumes) - 1, 20)
        if avg_vol > 0:
            vol_ratio = round(volumes[-1] / avg_vol, 2)

    # Current price info
    current_price = closes[-1] if closes else 0.0
    open_price = opens[-1] if opens else 0.0
    high_price = max(highs[-20:]) if highs else 0.0
    low_price = min(lows[-20:]) if lows else 0.0

    # Return only last 20 bars for the response
    bars_out = [
        {
            "t": b.timestamp.isoformat() if hasattr(b, "timestamp") else str(b.timestamp),
            "o": float(b.open),
            "h": float(b.high),
            "l": float(b.low),
            "c": float(b.close),
            "v": float(b.volume),
        }
        for b in bars_raw[-20:]
    ]

    # ── 2. Fetch Finnhub news ─────────────────────────────────────────────────
    news_items: list[dict] = []
    if FINNHUB_KEY:
        try:
            today = dt.date.today()
            yesterday = today - dt.timedelta(days=1)
            resp = httpx.get(
                "https://finnhub.io/api/v1/company-news",
                params={
                    "symbol": symbol,
                    "from": yesterday.isoformat(),
                    "to": today.isoformat(),
                    "token": FINNHUB_KEY,
                },
                timeout=5.0,
            )
            if resp.status_code == 200:
                raw_news = resp.json()
                for item in raw_news[:5]:
                    news_items.append({
                        "headline": item.get("headline", ""),
                        "summary": item.get("summary", ""),
                        "datetime": str(item.get("datetime", "")),
                        "source": item.get("source", ""),
                    })
        except Exception:
            pass

    # ── 3. Current position ───────────────────────────────────────────────────
    position_out = None
    try:
        trading_client = _trading_client()
        pos = trading_client.get_open_position(symbol)
        position_out = {
            "qty": float(pos.qty),
            "avg_price": float(pos.avg_entry_price),
            "unrealized_pl": float(pos.unrealized_pl),
            "unrealized_plpc": round(float(pos.unrealized_plpc) * 100, 2),
        }
    except Exception:
        position_out = None  # no position

    # ── 4. Account summary ────────────────────────────────────────────────────
    account_out = {"equity": 0.0, "buying_power": 0.0, "cash": 0.0}
    try:
        trading_client = _trading_client()
        acc = trading_client.get_account()
        account_out = {
            "equity": float(acc.equity),
            "buying_power": float(acc.buying_power),
            "cash": float(acc.cash),
        }
    except Exception:
        pass

    return {
        "symbol": symbol,
        "timestamp": now.isoformat(),
        "price": {
            "current": round(current_price, 4),
            "open": round(open_price, 4),
            "high": round(high_price, 4),
            "low": round(low_price, 4),
        },
        "technicals": {
            "rsi_14": rsi,
            "macd": macd_val,
            "macd_signal": macd_signal,
            "macd_hist": macd_hist,
            "volume_ratio": vol_ratio,
        },
        "bars_5min": bars_out,
        "news": news_items,
        "position": position_out,
        "account": account_out,
    }


# ── Terminal management ───────────────────────────────────────────────────────

TTYD_PORT = 7681
TMUX_SESSION = "autopilot"


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def _tmux_session_exists() -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", TMUX_SESSION],
        capture_output=True,
    )
    return result.returncode == 0


@router.post("/terminal/start")
def start_terminal() -> dict:
    """Start tmux+claude session and ttyd if not already running."""
    if shutil.which("tmux") is None:
        raise HTTPException(status_code=503, detail="tmux not installed — run: brew install tmux")
    if shutil.which("ttyd") is None:
        raise HTTPException(status_code=503, detail="ttyd not installed — run: brew install ttyd")
    if shutil.which("claude") is None:
        raise HTTPException(status_code=503, detail="claude not found in PATH")

    agent_loop = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "..", "autopilot", "agent_loop.sh",
    )
    agent_loop = os.path.normpath(agent_loop)

    # Start tmux session with autonomous agent loop
    if not _tmux_session_exists():
        subprocess.Popen(
            ["tmux", "new-session", "-d", "-s", TMUX_SESSION, agent_loop],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # Start ttyd pointing at tmux session if port not in use
    if not _port_in_use(TTYD_PORT):
        subprocess.Popen(
            ["ttyd", "-p", str(TTYD_PORT), "-W", "tmux", "attach-session", "-t", TMUX_SESSION],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    return {"status": "ok", "tmux_session": TMUX_SESSION, "ttyd_port": TTYD_PORT}


@router.get("/terminal/status")
def terminal_status() -> dict:
    return {
        "ttyd_running": _port_in_use(TTYD_PORT),
        "tmux_session": _tmux_session_exists(),
    }


# ── tmux pane capture (used by shutdown status) ───────────────────────────────

_ANSI_RE = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;]*[ -/]*[@-~])')


def _tmux_capture(n: int = 500) -> list[str]:
    try:
        if not _tmux_session_exists():
            return []
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", TMUX_SESSION, "-p", "-S", f"-{n}"],
            capture_output=True, text=True, timeout=3,
        )
        raw = _ANSI_RE.sub("", result.stdout)
        return [l.rstrip() for l in raw.split("\n") if l.strip()]
    except Exception:
        return []


# ── Shutdown ──────────────────────────────────────────────────────────────────

import os as _os
import signal as _signal
import threading as _threading

AUTOPILOT_DIR = _os.path.normpath(_os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "..", "autopilot"
))
KILL_FILE = _os.path.join(AUTOPILOT_DIR, "KILL")

HANDOFF_PROMPT = """
지금 즉시 현재 작업을 중단하고 다음 인수인계 작업을 수행해.

1. 현재 포트폴리오 상태 확인: bash tools/portfolio.sh
2. 오늘 분석/매매 요약을 memory.py에 기록:
   python3 tools/memory.py reflect '종료 전 인수인계: [현재 상태 요약, 보유 종목, 다음 사이클 주목 사항]'
3. 인수인계 완료 후 반드시 마지막 줄에 다음 텍스트만 출력:
   HANDOFF_COMPLETE

지금 바로 시작해.
"""


@router.post("/shutdown/initiate")
def shutdown_initiate() -> dict:
    """Stop agent loop, run handoff, signal ready."""
    # Touch KILL file → prevents next cycle
    with open(KILL_FILE, "w") as f:
        f.write("shutdown\n")

    # Interrupt current tmux process (Ctrl+C)
    subprocess.run(["tmux", "send-keys", "-t", TMUX_SESSION, "C-c", ""], capture_output=True)
    import time; time.sleep(1)
    subprocess.run(["tmux", "send-keys", "-t", TMUX_SESSION, "C-c", ""], capture_output=True)
    import time; time.sleep(1)

    # Run handoff claude in tmux
    handoff_cmd = (
        f"cd {AUTOPILOT_DIR} && "
        f"claude --print \"{HANDOFF_PROMPT.strip()}\" 2>&1; "
        f"echo HANDOFF_COMPLETE"
    )
    subprocess.run(
        ["tmux", "send-keys", "-t", TMUX_SESSION, handoff_cmd, "Enter"],
        capture_output=True,
    )
    return {"status": "initiated"}


@router.get("/shutdown/status")
def shutdown_status() -> dict:
    """Check if handoff is complete."""
    lines = _tmux_capture(200)
    content = "\n".join(lines)
    done = "HANDOFF_COMPLETE" in content
    # Return last 20 lines for display
    recent = lines[-20:] if len(lines) > 20 else lines
    return {"done": done, "recent_lines": recent}


def _kill_all() -> None:
    import time
    time.sleep(2)
    # Kill tmux (agent + everything inside)
    subprocess.run(["tmux", "kill-server"], capture_output=True)
    # Kill ttyd
    subprocess.run(["bash", "-c", "lsof -ti:7681 | xargs kill -9 2>/dev/null; true"],
                   shell=False, capture_output=True)
    # Kill npm dev (port 3000)
    subprocess.run(["bash", "-c", "lsof -ti:3000 | xargs kill -9 2>/dev/null; true"],
                   shell=False, capture_output=True)
    time.sleep(0.5)
    # Kill self (uvicorn)
    _os.kill(_os.getpid(), _signal.SIGTERM)


@router.post("/shutdown/execute")
def shutdown_execute() -> dict:
    """Kill all servers (2s delay to allow response to reach client)."""
    # Remove KILL file so next startup is clean
    try:
        _os.remove(KILL_FILE)
    except FileNotFoundError:
        pass
    _threading.Thread(target=_kill_all, daemon=True).start()
    return {"status": "shutting_down"}


# ── Multi-agent management ────────────────────────────────────────────────────

from fastapi import APIRouter as _APIRouter
from api_server import agent_store

agents_router = _APIRouter(prefix="/agents", tags=["agents"])


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
    if agent_store.get_agent(agent_id) is None:
        raise HTTPException(status_code=404, detail="agent not found")
    try:
        return agent_store.record_cycle(agent_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Per-agent performance dashboard ───────────────────────────────────────────

from api_server import agent_perf


def _latest_price(symbol: str) -> float | None:
    """Best-effort latest close for unrealized-PnL enrichment (None on failure)."""
    try:
        data_client = _data_client()
        now = dt.datetime.now(dt.timezone.utc)
        req = StockBarsRequest(
            symbol_or_symbols=symbol.upper(),
            timeframe=TimeFrame(5, TimeFrameUnit.Minute),
            start=now - dt.timedelta(days=5),
            limit=1,
        )
        resp = data_client.get_stock_bars(req)
        bars = list(resp[symbol.upper()]) if symbol.upper() in resp else []
        return float(bars[-1].close) if bars else None
    except Exception:
        return None


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

    # Enrich open positions with current price → unrealized PnL.
    unrealized = 0.0
    positions_out = []
    for pos in perf.open_positions:
        cur = _latest_price(pos["symbol"])
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


def _fetch_intraday_bars(symbol: str, days: int = 2) -> list[dict]:
    """Fetch recent 5-min bars for ``symbol`` as intraday_score-shaped dicts."""
    data_client = _data_client()
    now = dt.datetime.now(dt.timezone.utc)
    req = StockBarsRequest(
        symbol_or_symbols=symbol.upper(),
        timeframe=TimeFrame(5, TimeFrameUnit.Minute),
        start=now - dt.timedelta(days=days),
        limit=200,
    )
    resp = data_client.get_stock_bars(req)
    bars = list(resp[symbol.upper()]) if symbol.upper() in resp else []
    return [
        {"t": b.timestamp, "o": float(b.open), "h": float(b.high),
         "l": float(b.low), "c": float(b.close), "v": float(b.volume)}
        for b in bars
    ]


def _fetch_kr_intraday_bars(symbol: str) -> list[dict]:
    """KR 5-min bars via yfinance (.KS/.KQ) → intraday_score bar dicts."""
    import yfinance as yf
    h = yf.Ticker(symbol).history(period="5d", interval="5m")
    out = []
    for ts, row in h.iterrows():
        out.append({
            "t": ts.to_pydatetime(), "o": float(row["Open"]), "h": float(row["High"]),
            "l": float(row["Low"]), "c": float(row["Close"]), "v": float(row["Volume"]),
        })
    return out


@router.get("/intraday/score/{symbol}")
def intraday_score_symbol(symbol: str) -> dict:
    """Professional intraday signal (VWAP/ORB/RVOL/EMA/ATR) for one symbol."""
    _require_key()
    try:
        bars = _fetch_intraday_bars(symbol)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"intraday bars error: {e}") from e
    result = _intraday.score_intraday(bars)
    result["symbol"] = symbol.upper()
    return result


@router.get("/intraday/scores")
def intraday_scores(symbols: str) -> dict:
    """Batch intraday scoring. ``symbols`` = comma-separated tickers."""
    _require_key()
    out = {}
    for sym in [s.strip().upper() for s in symbols.split(",") if s.strip()]:
        try:
            bars = _fetch_intraday_bars(sym)
            res = _intraday.score_intraday(bars)
        except Exception as e:
            res = {"direction": "FLAT", "score": 0, "signal": "AVOID", "error": str(e)}
        res["symbol"] = sym
        out[sym] = res
    return {"scores": out}


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
    budget = max(alloc - agent_perf.compute_performance(_cycles).invested, 0.0)

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
    if lv5_state.get("lv5_note"):
        actions.append(lv5_state["lv5_note"])
    if lv5_agent_note:
        actions.append(lv5_agent_note)
    fill = None
    fill_symbol = None

    # Lv5 pause: 연속 손절 감지 시 entry skip (청산만 수행)
    lv5_pause = lv5_state.get("pause", False)

    if venue == "HL":
        get_positions, place_order, close_position, set_leverage, get_candles = _hl_funcs()
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
        for p in pos_raw.get("asset_positions", []):
            szi = float(p["position"]["szi"])
            if szi != 0:
                coin = p["position"]["coin"]
                cur = scores.get(coin, {}).get("price")
                held.append({"symbol": coin, "side": "long" if szi > 0 else "short",
                             "entry": float(p["position"].get("entryPx", 0) or 0), "current": cur})
        # exits: hard TP/SL first, then signal flip/degrade
        tp_pct = float(profile.get("tp_pct", 0.05)); sl_pct = float(profile.get("sl_pct", 0.03))
        exits = daytrade_logic.stop_exits(held, tp_pct, sl_pct) + daytrade_logic.decide_exits(held, scores)
        for ex in {e["symbol"]: e for e in exits}.values():
            try:
                close_position(coin=ex["symbol"], paper=paper)
                actions.append(f"close {ex['symbol']} ({ex['reason']})")
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
                    set_leverage(entry["symbol"], int(leverage), True, paper)
                    place_order(entry["symbol"], entry["side"] == "buy", size, "market", paper=paper)
                    fill = {"side": entry["side"], "qty": size, "price": entry["entry"]}
                    fill_symbol = entry["symbol"]
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
                bars = _fetch_kr_intraday_bars(sym)
                scores[code] = _intraday.score_intraday(bars, market="KR")
            except Exception as e:
                scores[code] = {"error": str(e), "signal": "AVOID", "score": 0}
        # holdings (entry/current from KIS balance) + equity
        try:
            equity = float(kis.get_balance().get("net_asset", 0) or 0)
            held = [{"symbol": h["code"], "side": "long", "entry": h["avg_price"], "current": h["current"]}
                    for h in kis.get_holdings()]
        except Exception as e:
            equity = 0.0; held = []
            actions.append(f"KIS 조회 실패: {str(e)[:60]}")
        tp_pct = float(profile.get("tp_pct", 0.03)); sl_pct = float(profile.get("sl_pct", 0.02))
        exits = daytrade_logic.stop_exits(held, tp_pct, sl_pct) + daytrade_logic.decide_exits(held, scores)
        for ex in {e["symbol"]: e for e in exits}.values():
            try:
                qtyh = next((h["qty"] for h in kis.get_holdings() if h["code"] == ex["symbol"]), 0)
                if qtyh > 0:
                    kis.place_order(ex["symbol"], "SELL", int(qtyh), "MARKET")
                    actions.append(f"청산 {ex['symbol']} ({ex['reason']})")
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
                    kis.place_order(entry["symbol"], "BUY", qty, "MARKET")
                    fill = {"side": "buy", "qty": qty, "price": entry["entry"]}
                    fill_symbol = entry["symbol"]
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
                    bars = _fetch_intraday_bars(sym)
                    scores[sym] = _intraday.score_intraday(bars)
                except Exception as e:
                    scores[sym] = {"error": str(e), "signal": "AVOID", "score": 0}
            client = _trading_client()
            held = []
            for p in client.get_all_positions():
                q = float(p.qty)
                if q != 0:
                    held.append({"symbol": p.symbol, "side": "long" if q > 0 else "short",
                                 "entry": float(p.avg_entry_price), "current": float(p.current_price)})
            exits = daytrade_logic.stop_exits(held, tp_pct, sl_pct) + daytrade_logic.decide_exits(held, scores)
            for ex in {e["symbol"]: e for e in exits}.values():
                try:
                    client.close_position(ex["symbol"]); actions.append(f"close {ex['symbol']} ({ex['reason']})")
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
                        from alpaca.trading.requests import MarketOrderRequest
                        from alpaca.trading.enums import OrderSide, TimeInForce
                        client.submit_order(MarketOrderRequest(symbol=entry["symbol"], qty=qty,
                            side=OrderSide.BUY, time_in_force=TimeInForce.DAY))
                        fill = {"side": "buy", "qty": qty, "price": entry["entry"]}
                        fill_symbol = entry["symbol"]
                        actions.append(f"buy {entry['symbol']} {qty} @ {entry['entry']}")
                    except Exception as e:
                        actions.append(f"entry {entry['symbol']} FAILED: {e}")
        else:
            # Live: IB via TWS (7496). 데이터(5분봉)+실행+실체결가를 한 세션에서
            # → 판단 소스와 체결 브로커 일치(괴리 없음), 실 avg_fill_price로 P&L 정확.
            from backends.ib.order_client import IBOrderClient

            async def _ib_us():
                ib = IBOrderClient(host=os.environ.get("IB_HOST", "127.0.0.1"), port=7496,
                                   client_id=random.randint(600, 699))
                acts, fl, fs, sc = [], None, None, {}
                try:
                    # scores from IB 5-min bars (same broker as execution)
                    for sym in universe:
                        try:
                            bars = await ib.get_intraday_bars(sym)
                            sc[sym] = _intraday.score_intraday(bars)
                        except Exception as e:
                            sc[sym] = {"error": str(e), "signal": "AVOID", "score": 0}
                    raw = await ib.get_positions()
                    held = [{"symbol": p["symbol"], "side": "long" if p["qty"] > 0 else "short",
                             "entry": p["avg_price"], "current": sc.get(p["symbol"], {}).get("price")}
                            for p in raw]
                    ex_all = daytrade_logic.stop_exits(held, tp_pct, sl_pct) + daytrade_logic.decide_exits(held, sc)
                    for e in {x["symbol"]: x for x in ex_all}.values():
                        pos = next((p for p in raw if p["symbol"] == e["symbol"]), None)
                        if pos:
                            await ib.place_order(e["symbol"], "SELL" if pos["qty"] > 0 else "BUY",
                                                 int(abs(pos["qty"])), "MARKET", wait_fill=True)
                            acts.append(f"close {e['symbol']} ({e['reason']})")
                    hs = {p["symbol"] for p in raw}
                    en = daytrade_logic.decide_entry(sc, threshold, allow_short=False)
                    if en and en["symbol"] not in hs and budget > 0:
                        q = int(daytrade_logic.position_size(budget, position_pct, 1.0, en["entry"] or 0))
                        if q > 0:
                            r = await ib.place_order(en["symbol"], "BUY", q, "MARKET", wait_fill=True)
                            # 실 체결가 우선, 없으면(미체결/지연) 신호가로 폴백 표시
                            px = r.get("avg_fill_price") or en["entry"]
                            tag = "IB" if r.get("avg_fill_price") else "IB est"
                            fl = {"side": "buy", "qty": q, "price": px}; fs = en["symbol"]
                            acts.append(f"buy {en['symbol']} {q} @ {px} ({tag})")
                finally:
                    await ib.close()
                return acts, fl, fs, sc

            try:
                a, fill, fill_symbol, scores = asyncio.run(_ib_us())
                actions.extend(a)
            except Exception as e:
                actions.append(f"IB(TWS) 실행 실패: {str(e)[:80]}")

    # Build + record the structured cycle (deterministic, no LLM).
    best = daytrade_logic.decide_entry(scores, 0, allow_short=(venue == "HL"))  # top candidate for display
    decision = "BUY" if (fill and fill["side"] == "buy") else "SELL" if fill else "SKIP"
    top_sym = fill_symbol or (best["symbol"] if best else "NONE")
    top_score = (best["score"] if best else 0)
    note_bits = actions if actions else ["실행 없음 — 조건 미충족"]
    payload = {
        "cycle": cycle, "decision": decision, "symbol": top_sym,
        "score": top_score, "max_score": 100, "best_score": top_score,
        "action": "; ".join(actions) if actions else "none",
        "next_trigger": f"conviction ≥ {threshold:.0f} 신호",
        "cash_pct": None, "note": " | ".join(note_bits)[:400],
        "fill": fill, "fill_symbol": fill_symbol, "markets": {"US": None, "KR": None},
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

    if action in ("BUY", "SELL"):
        is_kr = instrument_id.endswith(".XKRX")
        try:
            if is_kr:
                from backends.kis.order_client import KISOrderClient
                kk = os.environ.get("KIS_MOCK_APP_KEY", "")
                ks = os.environ.get("KIS_MOCK_APP_SECRET", "")
                kc = os.environ.get("KIS_MOCK_CANO", "")
                kis = KISOrderClient(kk, ks, kc, os.environ.get("KIS_ACNT_PRDT_CD", "01"), mock=True)
                code = instrument_id.split(".")[0]
                if action == "BUY":
                    alloc = float(agent["account_alloc"])
                    _cycles = agent_store.read_cycles(agent_id, limit=100000)
                    budget = max(alloc - agent_perf.compute_performance(_cycles).invested, 0.0)
                    qty = int(daytrade_logic.position_size(budget, position_pct, 1.0, result["price"]))
                    if qty > 0:
                        kis.place_order(code, "BUY", qty, "MARKET")
                        fill = {"side": "buy", "qty": qty, "price": result["price"]}
                        note_bits.append(f"매수 {code} {qty}주 @ {result['price']}")
                else:
                    qtyh = next((h["qty"] for h in kis.get_holdings() if h["code"] == code), 0)
                    if qtyh > 0:
                        kis.place_order(code, "SELL", int(qtyh), "MARKET")
                        fill = {"side": "sell", "qty": qtyh, "price": result["price"]}
                        note_bits.append(f"청산 {code} {qtyh}주 @ {result['price']}")
            else:
                from alpaca.trading.requests import MarketOrderRequest
                from alpaca.trading.enums import OrderSide, TimeInForce
                symbol = instrument_id.split(".")[0]
                client = _trading_client(paper=True)
                if action == "BUY":
                    alloc = float(agent["account_alloc"])
                    _cycles = agent_store.read_cycles(agent_id, limit=100000)
                    budget = max(alloc - agent_perf.compute_performance(_cycles).invested, 0.0)
                    qty = int(daytrade_logic.position_size(budget, position_pct, 1.0, result["price"]))
                    if qty > 0:
                        client.submit_order(MarketOrderRequest(symbol=symbol, qty=qty,
                            side=OrderSide.BUY, time_in_force=TimeInForce.DAY))
                        fill = {"side": "buy", "qty": qty, "price": result["price"]}
                        note_bits.append(f"buy {symbol} {qty} @ {result['price']}")
                else:
                    client.close_position(symbol)
                    fill = {"side": "sell", "qty": None, "price": result["price"]}
                    note_bits.append(f"close {symbol}")
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
        client = _trading_client()
        acc = client.get_account()
        out["venues"]["alpaca"] = {
            "mode": "paper" if ALPACA_PAPER else "live",
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
