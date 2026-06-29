"""
Hyperliquid trading client.
The local `hyperliquid/` package shadows the SDK, so we temporarily
reorder sys.path so site-packages wins during import, then restore it.
"""
import os
import sys
from pathlib import Path
from typing import Any


def _sdk_imports():
    """Import SDK classes with local package shadow temporarily removed."""
    local_pkg_parent = str(Path(__file__).parent.parent.resolve())

    # Remove paths whose `hyperliquid/` would resolve to our local dir
    filtered = [p for p in sys.path if Path(p).resolve() != Path(local_pkg_parent).resolve()]

    # Clear any already-cached local hyperliquid modules
    stale = [k for k in sys.modules if k == "hyperliquid" or k.startswith("hyperliquid.")]
    for k in stale:
        del sys.modules[k]

    orig_path = sys.path[:]
    sys.path = filtered
    try:
        from hyperliquid.exchange import Exchange       # type: ignore
        from hyperliquid.info import Info               # type: ignore
        from hyperliquid.utils.constants import MAINNET_API_URL  # type: ignore
        return Exchange, Info, MAINNET_API_URL
    finally:
        sys.path = orig_path
        # Remove SDK modules from cache so next call re-imports cleanly
        to_purge = [k for k in sys.modules if k == "hyperliquid" or k.startswith("hyperliquid.")]
        for k in to_purge:
            del sys.modules[k]


def _private_key() -> str:
    key = os.getenv("HL_PRIVATE_KEY", "").strip()
    if not key:
        raise ValueError("HL_PRIVATE_KEY env var not set")
    return key


def _account_address() -> str:
    addr = os.getenv("HL_ACCOUNT_ADDRESS", "").strip()
    if not addr:
        raise ValueError("HL_ACCOUNT_ADDRESS env var not set")
    return addr


def _wallet():
    from eth_account import Account  # type: ignore
    return Account.from_key(_private_key())


def get_positions() -> dict[str, Any]:
    Exchange, Info, MAINNET_API_URL = _sdk_imports()
    info = Info(MAINNET_API_URL, skip_ws=True)
    account = _account_address()
    state = info.user_state(account)
    spot_state = info.spot_user_state(account)
    open_orders = info.open_orders(account)

    # Unified account: account value = perp margin + spot USDC
    usdc_spot = next(
        (float(b["total"]) for b in spot_state.get("balances", []) if b["coin"] == "USDC"),
        0.0,
    )
    margin_summary = state.get("marginSummary", {})
    perp_value = float(margin_summary.get("accountValue", 0))
    combined_value = perp_value + usdc_spot
    margin_summary = dict(margin_summary)
    margin_summary["accountValue"] = str(combined_value)
    margin_summary["spotUsdcBalance"] = str(usdc_spot)

    return {
        "address": account,
        "margin_summary": margin_summary,
        "cross_margin_summary": state.get("crossMarginSummary", {}),
        "asset_positions": state.get("assetPositions", []),
        "open_orders": open_orders,
    }


def place_order(
    coin: str,
    is_buy: bool,
    size: float,
    order_type: str = "market",
    limit_px: float | None = None,
    reduce_only: bool = False,
    slippage: float = 0.05,
) -> dict[str, Any]:
    Exchange, _, MAINNET_API_URL = _sdk_imports()
    wallet = _wallet()
    exchange = Exchange(wallet, MAINNET_API_URL)

    if order_type == "market":
        return exchange.market_open(coin.upper(), is_buy, size,
                                    slippage=slippage, reduce_only=reduce_only)
    elif order_type == "limit":
        if limit_px is None:
            raise ValueError("limit_px required for limit orders")
        return exchange.order(coin.upper(), is_buy, size, limit_px,
                              {"limit": {"tif": "Gtc"}}, reduce_only=reduce_only)
    else:
        raise ValueError(f"Unknown order_type: {order_type}")


def cancel_order(coin: str, oid: int) -> dict[str, Any]:
    Exchange, _, MAINNET_API_URL = _sdk_imports()
    wallet = _wallet()
    exchange = Exchange(wallet, MAINNET_API_URL)
    return exchange.cancel(coin.upper(), oid)


def close_position(coin: str, size: float | None = None, slippage: float = 0.05) -> dict[str, Any]:
    Exchange, _, MAINNET_API_URL = _sdk_imports()
    wallet = _wallet()
    exchange = Exchange(wallet, MAINNET_API_URL)
    return exchange.market_close(coin.upper(), sz=size, slippage=slippage)
