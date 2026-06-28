"""LiveBotEngine — manages running bots and executes EMA cross strategy on live prices."""
import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

from live_engine.broker_interface import BotStatus, BrokerInterface, OrderResult

log = logging.getLogger(__name__)

# ── EMA helper ────────────────────────────────────────────────────────────────

def _ema(prices: list[float], period: int) -> float:
    if len(prices) < period:
        raise ValueError(f"need {period} prices, got {len(prices)}")
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return ema


# ── Per-bot running state ─────────────────────────────────────────────────────

@dataclass
class _BotRunState:
    bot_id: str
    instrument_id: str
    fast_ema: int
    slow_ema: int
    trade_size: int
    broker: BrokerInterface
    task: asyncio.Task | None = None
    prices: list[float] = field(default_factory=list)
    position: int = 0           # 0=flat, 1=long, -1=short
    last_price: float | None = None
    last_signal: str | None = None
    orders: list[OrderResult] = field(default_factory=list)
    error: str | None = None
    subscribers: set = field(default_factory=set)  # WebSocket connections
    entry_price: float | None = None  # price when position was entered


# ── Engine ────────────────────────────────────────────────────────────────────

class LiveBotEngine:
    """Singleton engine. One instance shared by the FastAPI app."""

    def __init__(self) -> None:
        self._running: dict[str, _BotRunState] = {}

    def is_running(self, bot_id: str) -> bool:
        return bot_id in self._running

    async def start(
        self,
        bot_id: str,
        instrument_id: str,
        fast_ema: int,
        slow_ema: int,
        trade_size: int,
        broker: BrokerInterface,
    ) -> None:
        if bot_id in self._running:
            return
        state = _BotRunState(
            bot_id=bot_id,
            instrument_id=instrument_id,
            fast_ema=fast_ema,
            slow_ema=slow_ema,
            trade_size=trade_size,
            broker=broker,
        )
        self._running[bot_id] = state
        state.task = asyncio.create_task(self._run(state), name=f"bot-{bot_id}")
        log.info("bot %s started", bot_id)

    async def stop(self, bot_id: str) -> None:
        state = self._running.pop(bot_id, None)
        if state is None:
            return
        if state.task and not state.task.done():
            state.task.cancel()
            try:
                await state.task
            except asyncio.CancelledError:
                pass
        await state.broker.close()
        log.info("bot %s stopped", bot_id)

    def get_status(self, bot_id: str) -> BotStatus | None:
        state = self._running.get(bot_id)
        if state is None:
            return None
        return BotStatus(
            bot_id=bot_id,
            instrument_id=state.instrument_id,
            running=True,
            position="LONG" if state.position > 0 else "SHORT" if state.position < 0 else "FLAT",
            qty=abs(state.position * state.trade_size),
            last_price=state.last_price,
            last_signal=state.last_signal,
            orders=list(state.orders[-20:]),  # last 20
            error=state.error,
            entry_price=state.entry_price,
        )

    def get_all_statuses(self) -> dict[str, BotStatus]:
        return {bid: self.get_status(bid) for bid in self._running}

    async def subscribe(self, bot_id: str, websocket) -> None:
        """Add a WebSocket to the subscriber set for this bot."""
        state = self._running.get(bot_id)
        if state:
            state.subscribers.add(websocket)

    async def unsubscribe(self, bot_id: str, websocket) -> None:
        state = self._running.get(bot_id)
        if state:
            state.subscribers.discard(websocket)

    # ── Strategy loop ─────────────────────────────────────────────────────────

    async def _run(self, state: _BotRunState) -> None:
        try:
            async for tick in state.broker.stream_prices(state.instrument_id):
                state.last_price = tick.price
                state.prices.append(tick.price)

                # Keep a rolling window (max 500 prices)
                if len(state.prices) > 500:
                    state.prices = state.prices[-500:]

                # Compute signal once we have enough history
                if len(state.prices) >= state.slow_ema:
                    fast = _ema(state.prices, state.fast_ema)
                    slow = _ema(state.prices, state.slow_ema)

                    if fast > slow:
                        signal = "EMA_BUY"
                        if state.position <= 0:
                            try:
                                result = await state.broker.place_order(
                                    state.instrument_id, "BUY", state.trade_size, "MARKET"
                                )
                                state.orders.append(result)
                                state.entry_price = tick.price  # record entry
                                state.position = 1
                                log.info("bot %s: BUY %s @ %.2f", state.bot_id, state.instrument_id, tick.price)
                            except Exception as exc:
                                log.error("bot %s: order error: %s", state.bot_id, exc)
                                state.error = str(exc)
                    elif fast < slow:
                        signal = "EMA_SELL"
                        if state.position >= 0:
                            try:
                                result = await state.broker.place_order(
                                    state.instrument_id, "SELL", state.trade_size, "MARKET"
                                )
                                state.orders.append(result)
                                state.entry_price = tick.price  # record entry
                                state.position = -1
                                log.info("bot %s: SELL %s @ %.2f", state.bot_id, state.instrument_id, tick.price)
                            except Exception as exc:
                                log.error("bot %s: order error: %s", state.bot_id, exc)
                                state.error = str(exc)
                    else:
                        signal = "HOLD"

                    state.last_signal = signal
                else:
                    signal = "WARMING_UP"
                    state.last_signal = signal

                # Push to WebSocket subscribers
                if state.subscribers:
                    payload = {
                        "price": tick.price,
                        "ts_ns": tick.ts_ns,
                        "signal": state.last_signal,
                        "position": state.position,
                    }
                    dead = set()
                    for ws in state.subscribers:
                        try:
                            await ws.send_json(payload)
                        except Exception:
                            dead.add(ws)
                    state.subscribers -= dead

        except asyncio.CancelledError:
            log.info("bot %s: task cancelled", state.bot_id)
            raise
        except Exception as exc:
            log.error("bot %s: fatal error: %s", state.bot_id, exc)
            state.error = str(exc)


# ── Factory: choose broker from instrument_id ─────────────────────────────────

def make_broker(instrument_id: str) -> BrokerInterface:
    venue = instrument_id.split(".")[-1] if "." in instrument_id else ""

    if venue == "XKRX":
        from live_engine.kis_broker import KISBroker
        return KISBroker(
            app_key=os.environ["KIS_APP_KEY"],
            app_secret=os.environ["KIS_APP_SECRET"],
            cano=os.environ["KIS_CANO"],
            acnt_prdt_cd=os.environ["KIS_ACNT_PRDT_CD"],
            mock=os.environ.get("KIS_MOCK", "true").lower() == "true",
        )
    else:
        from live_engine.ib_broker import IBBroker
        return IBBroker(
            host=os.environ.get("IB_HOST", "127.0.0.1"),
            port=int(os.environ.get("IB_PORT", "7497")),
        )


# Singleton
engine = LiveBotEngine()
