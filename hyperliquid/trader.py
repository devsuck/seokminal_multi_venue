"""
Hyperliquid trading client.
Uses hyperliquid-python-sdk (installed in site-packages).
Local `hyperliquid/` package shadows the SDK, so we import via importlib.
"""
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

# Load SDK modules from site-packages, bypassing local package shadow
def _load_sdk_module(name: str):
    for p in sys.path:
        candidate = Path(p) / "hyperliquid" / (name.replace(".", "/") + ".py")
        if not candidate.exists():
            candidate = Path(p) / "hyperliquid" / name.replace(".", "/") / "__init__.py"
        if candidate.exists():
            # Make sure it's site-packages, not our local dir
            local_dir = Path(__file__).parent
            if candidate.parent.resolve() == local_dir.resolve():
                continue
            spec = importlib.util.spec_from_file_location(f"_hl_sdk.{name}", candidate)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                return mod
    raise ImportError(f"hyperliquid SDK module '{name}' not found in site-packages")


def _get_sdk():
    try:
        exchange_mod  = _load_sdk_module("exchange")
        info_mod      = _load_sdk_module("info")
        utils_mod     = _load_sdk_module("utils.constants")
        return exchange_mod, info_mod, utils_mod
    except ImportError as e:
        raise RuntimeError(f"hyperliquid-python-sdk not installed: {e}") from e


def _private_key() -> str:
    key = os.getenv("HL_PRIVATE_KEY", "").strip()
    if not key:
        raise ValueError("HL_PRIVATE_KEY env var not set")
    return key


def _wallet():
    from eth_account import Account  # type: ignore
    return Account.from_key(_private_key())


def get_positions() -> dict[str, Any]:
    """Return open positions + account summary for the configured wallet."""
    _, info_mod, constants_mod = _get_sdk()
    info = info_mod.Info(constants_mod.MAINNET_API_URL, skip_ws=True)
    wallet = _wallet()
    state = info.user_state(wallet.address)
    open_orders = info.open_orders(wallet.address)
    return {
        "address": wallet.address,
        "margin_summary": state.get("marginSummary", {}),
        "cross_margin_summary": state.get("crossMarginSummary", {}),
        "asset_positions": state.get("assetPositions", []),
        "open_orders": open_orders,
    }


def place_order(
    coin: str,
    is_buy: bool,
    size: float,
    order_type: str = "market",     # "market" | "limit"
    limit_px: float | None = None,
    reduce_only: bool = False,
    slippage: float = 0.05,
) -> dict[str, Any]:
    """Place a market or limit order. Returns SDK response."""
    exchange_mod, _, constants_mod = _get_sdk()
    wallet = _wallet()
    exchange = exchange_mod.Exchange(wallet, constants_mod.MAINNET_API_URL)

    if order_type == "market":
        result = exchange.market_open(
            coin.upper(),
            is_buy,
            size,
            slippage=slippage,
            reduce_only=reduce_only,
        )
    elif order_type == "limit":
        if limit_px is None:
            raise ValueError("limit_px required for limit orders")
        result = exchange.order(
            coin.upper(),
            is_buy,
            size,
            limit_px,
            {"limit": {"tif": "Gtc"}},
            reduce_only=reduce_only,
        )
    else:
        raise ValueError(f"Unknown order_type: {order_type}")

    return result


def cancel_order(coin: str, oid: int) -> dict[str, Any]:
    """Cancel an open order by order ID."""
    exchange_mod, _, constants_mod = _get_sdk()
    wallet = _wallet()
    exchange = exchange_mod.Exchange(wallet, constants_mod.MAINNET_API_URL)
    return exchange.cancel(coin.upper(), oid)


def close_position(coin: str, size: float | None = None, slippage: float = 0.05) -> dict[str, Any]:
    """Market-close a position. size=None closes entire position."""
    exchange_mod, _, constants_mod = _get_sdk()
    wallet = _wallet()
    exchange = exchange_mod.Exchange(wallet, constants_mod.MAINNET_API_URL)
    return exchange.market_close(coin.upper(), sz=size, slippage=slippage)
