"""LiveBotEngine — manages running bots and executes EMA cross strategy on live prices."""
import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

from live_engine.broker_interface import BotStatus, BrokerInterface, OrderResult, Position
from live_engine.risk_guard import RiskConfig, validate_order

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


def _today_realized_pnl(closed_trades: list[dict]) -> float:
    """Sum today's (UTC) closed-trade pnl for the daily-loss-limit check.
    exit_ts_ns may be None for malformed/legacy entries — skip those."""
    import datetime as _dt
    start_ns = int(
        _dt.datetime.now(_dt.UTC).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        * 1e9
    )
    return sum(
        t["pnl"] for t in closed_trades
        if t.get("exit_ts_ns") is not None and t["exit_ts_ns"] >= start_ns
    )


# ── Stop-and-reverse position sizing ──────────────────────────────────────────

def _target_units(*, fast: float, slow: float, current: int) -> int:
    """Desired position in units from the EMA cross: +1 long, -1 short.

    On an exact tie there is no signal, so the current position is held.
    """
    if fast > slow:
        return 1
    if fast < slow:
        return -1
    return current


def _order_for_target(
    *, current_units: int, target_units: int, trade_size: int
) -> tuple[str, int] | None:
    """Order needed to move from current to target position, or None if already there.

    Returns (side, quantity). A reversal (e.g. +1 → -1) trades the full
    distance (2 units) so the position actually flips instead of merely
    flattening — the fix for the engine/broker position desync.
    """
    delta = target_units - current_units
    if delta == 0:
        return None
    side = "BUY" if delta > 0 else "SELL"
    return side, abs(delta) * trade_size


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
    entry_ts_ns: int | None = None                           # timestamp when position was entered
    closed_trades: list[dict] = field(default_factory=list)  # last 200 closed trades
    signal_log: list[dict] = field(default_factory=list)     # last 100 signal changes


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
        await self._reconcile_position(state)
        state.task = asyncio.create_task(self._run(state), name=f"bot-{bot_id}")
        log.info("bot %s started", bot_id)

    async def _reconcile_position(self, state: _BotRunState) -> None:
        """Seed the tracked position from the broker so a restart doesn't assume flat.

        Best-effort: adapters that don't report positions return None and the
        bot starts flat, as before. A held position is mapped to the engine's
        unit model (±1) with the broker's average price as the entry.
        """
        try:
            pos: Position | None = await state.broker.get_position(state.instrument_id)
        except Exception as exc:
            log.warning("bot %s: position reconcile failed: %s", state.bot_id, exc)
            return
        if pos is not None and pos.side in ("LONG", "SHORT") and pos.qty:
            state.position = 1 if pos.side == "LONG" else -1
            state.entry_price = pos.avg_price
            log.info(
                "bot %s: reconciled to %s @ %.2f", state.bot_id, pos.side, pos.avg_price
            )

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

                    target = _target_units(fast=fast, slow=slow, current=state.position)
                    signal = "EMA_BUY" if target > 0 else "EMA_SELL" if target < 0 else "HOLD"
                    order = _order_for_target(
                        current_units=state.position,
                        target_units=target,
                        trade_size=state.trade_size,
                    )

                    if order is not None:
                        side, qty = order
                        try:
                            venue = "KR" if state.instrument_id.endswith(".XKRX") else "US_IB"
                            cfg = RiskConfig.from_env(venue=venue)
                            validate_order(
                                side=side, quantity=qty, price_estimate=tick.price,
                                current_position_qty=state.position * state.trade_size,
                                day_realized_pnl=_today_realized_pnl(state.closed_trades),
                                config=cfg,
                            )
                            result = await state.broker.place_order(
                                state.instrument_id, side, qty, "MARKET"
                            )
                            state.orders.append(result)
                            # Prefer the broker's actual fill price; fall back to the
                            # tick only when the adapter can't report a fill yet.
                            fill_price = (
                                result.avg_fill_price
                                if result.avg_fill_price is not None
                                else tick.price
                            )
                            # Realize PnL on the position being closed (if any).
                            if state.position != 0 and state.entry_price is not None:
                                sign = 1 if state.position > 0 else -1
                                pnl = (fill_price - state.entry_price) * state.trade_size * sign
                                state.closed_trades.append({
                                    "entry_ts_ns": state.entry_ts_ns,
                                    "exit_ts_ns": tick.ts_ns,
                                    "side": "LONG" if state.position > 0 else "SHORT",
                                    "entry_price": state.entry_price,
                                    "exit_price": fill_price,
                                    "qty": state.trade_size,
                                    "pnl": round(pnl, 6),
                                })
                                state.closed_trades = state.closed_trades[-200:]
                            # Adopt the new position at the fill price.
                            state.position = target
                            if target == 0:
                                state.entry_price = None
                                state.entry_ts_ns = None
                            else:
                                state.entry_price = fill_price
                                state.entry_ts_ns = tick.ts_ns
                            log.info(
                                "bot %s: %s %d %s @ %.2f",
                                state.bot_id, side, qty, state.instrument_id, fill_price,
                            )
                        except Exception as exc:
                            log.error("bot %s: order error: %s", state.bot_id, exc)
                            state.error = str(exc)

                    # Record signal change (not every tick — only on change)
                    if signal != state.last_signal:
                        state.signal_log.append({
                            "ts_ns": tick.ts_ns,
                            "signal": signal,
                            "price": tick.price,
                        })
                        state.signal_log = state.signal_log[-100:]

                    state.last_signal = signal
                else:
                    signal = "WARMING_UP"
                    if signal != state.last_signal:
                        state.signal_log.append({
                            "ts_ns": tick.ts_ns,
                            "signal": signal,
                            "price": tick.price,
                        })
                        state.signal_log = state.signal_log[-100:]
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
