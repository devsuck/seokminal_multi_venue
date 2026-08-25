"""Pre-trade risk guard shared by every order path (manual US/KR, bots, HL).

A single chokepoint so no order — whether typed in the UI, fired by a bot, or
POSTed directly to the API — can bypass the firm-wide limits. Limits are read
from the environment so paper and live deployments can differ without code
changes. All checks are pure functions over explicit inputs to keep them
trivially testable.
"""
from __future__ import annotations

import datetime as _dt
import os
from dataclasses import dataclass


class RiskViolation(Exception):
    """Raised when an order would breach a configured risk limit."""


class DailyLossLimitBreached(RiskViolation):
    """Raised specifically for the daily realized-loss breach, so callers can
    distinguish it from other risk violations (e.g. to fire an alert)."""


@dataclass(frozen=True)
class RiskConfig:
    max_order_qty: int
    max_order_notional: float
    max_position_qty: int
    daily_loss_limit: float          # absolute value of the worst allowed realized loss
    kill_switch: bool
    min_option_dte: int = 0          # block option orders expiring sooner than this (0 = off)

    @classmethod
    def from_env(cls) -> "RiskConfig":
        return cls(
            max_order_qty=int(os.environ.get("MAX_ORDER_QTY", "10000")),
            max_order_notional=float(os.environ.get("MAX_ORDER_NOTIONAL", "1000000")),
            max_position_qty=int(os.environ.get("MAX_POSITION_QTY", "50000")),
            daily_loss_limit=float(os.environ.get("DAILY_LOSS_LIMIT", "100000")),
            kill_switch=os.environ.get("TRADING_KILL_SWITCH", "false").lower() == "true",
            min_option_dte=int(os.environ.get("MIN_OPTION_DTE", "0")),
        )


def validate_order(
    *,
    side: str,
    quantity: float,
    price_estimate: float | None,
    current_position_qty: float,
    day_realized_pnl: float,
    config: RiskConfig,
) -> None:
    """Validate one order against the risk limits; raise RiskViolation if blocked.

    ``quantity`` may be fractional (crypto). ``current_position_qty`` is signed
    (positive long, negative short). ``day_realized_pnl`` is signed (negative =
    loss). ``price_estimate`` may be None for a MARKET order with no recent
    price; notional is skipped then. Reducing an existing position is always
    allowed past the position cap so a breached book can still be unwound.
    """
    if config.kill_switch:
        raise RiskViolation("trading kill switch is engaged — all orders blocked")

    if quantity <= 0:
        raise RiskViolation(f"quantity must be positive, got {quantity}")

    if quantity > config.max_order_qty:
        raise RiskViolation(
            f"order quantity {quantity} exceeds max order qty {config.max_order_qty}"
        )

    if price_estimate is not None:
        notional = quantity * price_estimate
        if notional > config.max_order_notional:
            raise RiskViolation(
                f"order notional {notional:.2f} exceeds max notional "
                f"{config.max_order_notional:.2f}"
            )

    # Daily loss: block opening risk once the day's realized loss breaches the limit.
    if day_realized_pnl <= -abs(config.daily_loss_limit):
        raise DailyLossLimitBreached(
            f"daily loss limit reached (realized {day_realized_pnl:.2f}, "
            f"limit {-abs(config.daily_loss_limit):.2f})"
        )

    # Position cap: only enforce when the order *increases* absolute exposure.
    signed = quantity if side.upper() == "BUY" else -quantity
    projected = current_position_qty + signed
    increases_exposure = abs(projected) > abs(current_position_qty)
    if increases_exposure and abs(projected) > config.max_position_qty:
        raise RiskViolation(
            f"resulting position {projected} exceeds max position qty "
            f"{config.max_position_qty}"
        )


def validate_option_expiry(expiry: str, config: RiskConfig, *, today: _dt.date | None = None) -> None:
    """Block option orders expiring within ``config.min_option_dte`` days.

    Near-expiry (esp. 0DTE) contracts carry outsized pin/assignment/gamma
    risk relative to premium — worth a dedicated gate distinct from the
    generic notional/qty checks above. ``min_option_dte=0`` (default) disables
    this check so it never blocks anyone who hasn't opted in via env.
    """
    if config.min_option_dte <= 0:
        return
    exp_date = _dt.datetime.strptime(expiry, "%Y%m%d").date()
    dte = (exp_date - (today or _dt.date.today())).days
    if dte < config.min_option_dte:
        raise RiskViolation(
            f"option expiry {expiry} is {dte}d out, below min DTE {config.min_option_dte}"
        )


def validate_defined_risk_spread(*, max_loss: float, config: RiskConfig) -> None:
    """Gate for defined-risk multi-leg option positions (e.g. iron condors).

    A short option's premium-at-entry notional badly understates its real risk
    (unbounded for a naked short). For a defined-risk spread the *actual* worst
    case is the wing width minus credit received — gate on that instead of the
    generic notional check in ``validate_order``.
    """
    if config.kill_switch:
        raise RiskViolation("trading kill switch is engaged — all orders blocked")
    if max_loss > config.max_order_notional:
        raise RiskViolation(
            f"defined-risk max loss {max_loss:.2f} exceeds max order notional "
            f"{config.max_order_notional:.2f}"
        )


class DailyPnLTracker:
    """Accumulates realized PnL per calendar day (UTC) for the loss-limit check."""

    def __init__(self) -> None:
        self._by_day: dict[str, float] = {}

    @staticmethod
    def _today() -> str:
        return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d")

    def add(self, pnl: float, day: str | None = None) -> None:
        key = day or self._today()
        self._by_day[key] = self._by_day.get(key, 0.0) + pnl

    def realized(self, day: str | None = None) -> float:
        key = day or self._today()
        return self._by_day.get(key, 0.0)
