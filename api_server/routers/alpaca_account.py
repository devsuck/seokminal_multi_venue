"""Alpaca 계좌/시세/주문 라우트 — 페이퍼 배스킷 봇(api_server/polymarket_bot.py는 아니고
daytrade/swing 에이전트)이 쓰는 계좌 조회·주문·컨텍스트·인트라데이 스코어링 엔드포인트.
공유 헬퍼(_fetch_intraday_bars 등)는 alpaca_shared 모듈 경유로 호출 — 테스트가
`monkeypatch.setattr(alpaca_shared, ...)`로 패치하면 여기와 agents.py 양쪽에 반영된다."""
from __future__ import annotations

import datetime as dt

import httpx
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
from fastapi import APIRouter, HTTPException

from api_server.routers import alpaca_shared as shared
from api_server.routers.alpaca_shared import OrderRequest

router = APIRouter(prefix="/alpaca", tags=["alpaca"])


@router.get("/account")
def get_account() -> dict:
    client = shared._trading_client()
    try:
        acc = client.get_account()
        return {
            "equity": float(acc.equity),
            "buying_power": float(acc.buying_power),
            "cash": float(acc.cash),
            "portfolio_value": float(acc.portfolio_value),
            "pattern_day_trader": bool(acc.pattern_day_trader),
            "paper": shared.ALPACA_PAPER,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Alpaca account error: {e}") from e


@router.get("/positions")
def get_positions() -> list[dict]:
    client = shared._trading_client()
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
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus
    client = shared._trading_client()
    try:
        orders = client.get_orders(
            filter=GetOrdersRequest(limit=20, status=QueryOrderStatus.ALL)
        )
        return [shared._fmt_order(o) for o in orders]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Alpaca orders error: {e}") from e


@router.post("/order")
def place_order(req: OrderRequest) -> dict:
    if not shared.ALPACA_KEY:
        raise HTTPException(status_code=503, detail="ALPACA_API_KEY not set in .env")
    from alpaca.trading.client import TradingClient
    side = OrderSide.BUY if req.side.lower() == "buy" else OrderSide.SELL
    client = TradingClient(api_key=shared.ALPACA_KEY, secret_key=shared.ALPACA_SECRET, paper=req.paper)
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
        return shared._fmt_order(order)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Alpaca order failed: {e}") from e


@router.delete("/order/{order_id}")
def cancel_order(order_id: str) -> dict:
    client = shared._trading_client()
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
    shared._require_key()
    symbol = symbol.upper()

    # ── 1. Fetch 5-min bars (enough for MACD+RSI) ────────────────────────────
    data_client = shared._data_client()
    now = dt.datetime.now(dt.timezone.utc)
    start_time = now - dt.timedelta(days=7)  # back 7 days to get ~60+ bars across sessions

    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
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
    rsi = shared.calc_rsi(closes)
    macd_val, macd_signal, macd_hist = shared.calc_macd(closes)

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
    if shared.FINNHUB_KEY:
        try:
            today = dt.date.today()
            yesterday = today - dt.timedelta(days=1)
            resp = httpx.get(
                "https://finnhub.io/api/v1/company-news",
                params={
                    "symbol": symbol,
                    "from": yesterday.isoformat(),
                    "to": today.isoformat(),
                    "token": shared.FINNHUB_KEY,
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
        trading_client = shared._trading_client()
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
        trading_client = shared._trading_client()
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


@router.get("/intraday/score/{symbol}")
def intraday_score_symbol(symbol: str) -> dict:
    """Professional intraday signal (VWAP/ORB/RVOL/EMA/ATR) for one symbol."""
    from api_server import intraday_score as _intraday
    shared._require_key()
    try:
        bars = shared._fetch_intraday_bars(symbol)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"intraday bars error: {e}") from e
    result = _intraday.score_intraday(bars)
    result["symbol"] = symbol.upper()
    return result


@router.get("/intraday/scores")
def intraday_scores(symbols: str) -> dict:
    """Batch intraday scoring. ``symbols`` = comma-separated tickers."""
    from api_server import intraday_score as _intraday
    shared._require_key()
    out = {}
    for sym in [s.strip().upper() for s in symbols.split(",") if s.strip()]:
        try:
            bars = shared._fetch_intraday_bars(sym)
            res = _intraday.score_intraday(bars)
        except Exception as e:
            res = {"direction": "FLAT", "score": 0, "signal": "AVOID", "error": str(e)}
        res["symbol"] = sym
        out[sym] = res
    return {"scores": out}
