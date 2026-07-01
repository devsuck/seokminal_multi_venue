"""
Hyperliquid trading client.
The local `hyperliquid/` package shadows the SDK, so we temporarily
reorder sys.path so site-packages wins during import, then restore it.
"""
import os
import sys
from pathlib import Path
from typing import Any

MAINNET_URL = "https://api.hyperliquid.xyz"
TESTNET_URL = "https://api.hyperliquid-testnet.xyz"


def _api_url(paper: bool) -> str:
    return TESTNET_URL if paper else MAINNET_URL


def _dex_of(name: str) -> str:
    """Builder perp-DEX prefix from a market name ('xyz:TSLA' → 'xyz'), else ''
    for the standard USDC crypto DEX ('BTC' → '')."""
    return name.split(":")[0] if ":" in name else ""


def _perp_dexs(name: str):
    dex = _dex_of(name)
    return [dex] if dex else None


def _sdk_imports():
    """Import SDK classes with local package shadow temporarily removed."""
    local_pkg_parent = str(Path(__file__).parent.parent.resolve())
    filtered = [p for p in sys.path if Path(p).resolve() != Path(local_pkg_parent).resolve()]

    stale = [k for k in sys.modules if k == "hyperliquid" or k.startswith("hyperliquid.")]
    for k in stale:
        del sys.modules[k]

    orig_path = sys.path[:]
    sys.path = filtered
    try:
        from hyperliquid.exchange import Exchange  # type: ignore
        from hyperliquid.info import Info          # type: ignore
        return Exchange, Info
    finally:
        sys.path = orig_path
        for k in [k for k in sys.modules if k == "hyperliquid" or k.startswith("hyperliquid.")]:
            del sys.modules[k]


def _private_key(paper: bool = False) -> str:
    """Signing key. HL API/agent wallets are per-network, so paper (testnet)
    uses HL_TESTNET_PRIVATE_KEY when set, falling back to HL_PRIVATE_KEY."""
    if paper:
        tk = os.getenv("HL_TESTNET_PRIVATE_KEY", "").strip()
        if tk:
            return tk
    key = os.getenv("HL_PRIVATE_KEY", "").strip()
    if not key:
        raise ValueError("HL_PRIVATE_KEY env var not set")
    return key


def _account_address(paper: bool = False) -> str:
    if paper:
        ta = os.getenv("HL_TESTNET_ACCOUNT_ADDRESS", "").strip()
        if ta:
            return ta
    addr = os.getenv("HL_ACCOUNT_ADDRESS", "").strip()
    if not addr:
        raise ValueError("HL_ACCOUNT_ADDRESS env var not set")
    return addr


def _wallet(paper: bool = False):
    from eth_account import Account  # type: ignore
    return Account.from_key(_private_key(paper))


def get_positions(paper: bool = False) -> dict[str, Any]:
    Exchange, Info = _sdk_imports()
    url = _api_url(paper)
    info = Info(url, skip_ws=True)
    account = _account_address(paper)
    state = info.user_state(account)
    open_orders = info.open_orders(account)

    usdc_spot = 0.0
    if not paper:
        spot_state = info.spot_user_state(account)
        usdc_spot = next(
            (float(b["total"]) for b in spot_state.get("balances", []) if b["coin"] == "USDC"),
            0.0,
        )

    margin_summary = dict(state.get("marginSummary", {}))
    perp_value = float(margin_summary.get("accountValue", 0))
    margin_summary["accountValue"] = str(perp_value + usdc_spot)
    margin_summary["spotUsdcBalance"] = str(usdc_spot)

    return {
        "address": account,
        "paper": paper,
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
    paper: bool = False,
) -> dict[str, Any]:
    Exchange, _ = _sdk_imports()
    wallet = _wallet(paper)
    # Builder-DEX markets (e.g. 'xyz:TSLA') need the DEX meta loaded; plain
    # crypto ('BTC') uses the standard USDC DEX. Preserve the dex-prefixed name.
    name = coin if ":" in coin else coin.upper()
    exchange = Exchange(wallet, _api_url(paper), perp_dexs=_perp_dexs(coin))

    if order_type == "market":
        # market_open does not accept reduce_only in this SDK; reducing/closing
        # an existing position is done via close_position() (market_close).
        return exchange.market_open(name, is_buy, size, slippage=slippage)
    elif order_type == "limit":
        if limit_px is None:
            raise ValueError("limit_px required for limit orders")
        return exchange.order(name, is_buy, size, limit_px,
                              {"limit": {"tif": "Gtc"}}, reduce_only=reduce_only)
    else:
        raise ValueError(f"Unknown order_type: {order_type}")


def cancel_order(coin: str, oid: int, paper: bool = False) -> dict[str, Any]:
    Exchange, _ = _sdk_imports()
    wallet = _wallet(paper)
    exchange = Exchange(wallet, _api_url(paper))
    return exchange.cancel(coin.upper(), oid)


def close_position(coin: str, size: float | None = None,
                   slippage: float = 0.05, paper: bool = False) -> dict[str, Any]:
    Exchange, _ = _sdk_imports()
    wallet = _wallet(paper)
    name = coin if ":" in coin else coin.upper()
    exchange = Exchange(wallet, _api_url(paper), perp_dexs=_perp_dexs(coin))
    return exchange.market_close(name, sz=size, slippage=slippage)


def set_leverage(coin: str, leverage: int, is_cross: bool = True,
                 paper: bool = False) -> dict[str, Any]:
    """Set leverage for a coin (cross by default). Day-trading uses this before
    sizing a leveraged position. leverage is an integer multiplier (e.g. 5)."""
    Exchange, _ = _sdk_imports()
    wallet = _wallet(paper)
    name = coin if ":" in coin else coin.upper()
    exchange = Exchange(wallet, _api_url(paper), perp_dexs=_perp_dexs(coin))
    return exchange.update_leverage(int(leverage), name, is_cross)


def get_candles(coin: str, interval: str = "5m", lookback_min: int = 1440,
                paper: bool = False) -> list[dict[str, Any]]:
    """Fetch recent OHLCV candles → intraday_score bar dicts {t,o,h,l,c,v}.

    ``lookback_min`` is how far back to pull (default 24h). HL returns candle
    objects with ms open-time ``t`` and string OHLCV; we normalise to floats and
    a tz-aware datetime so the intraday engine can consume them directly.
    """
    import datetime as _dt

    _, Info = _sdk_imports()
    info = Info(_api_url(paper), skip_ws=True, perp_dexs=_perp_dexs(coin))
    name = coin if ":" in coin else coin.upper()
    now_ms = int(_dt.datetime.now(_dt.timezone.utc).timestamp() * 1000)
    start_ms = now_ms - lookback_min * 60 * 1000
    raw = info.candles_snapshot(name, interval, start_ms, now_ms)
    bars = []
    for c in raw or []:
        bars.append({
            "t": _dt.datetime.fromtimestamp(int(c["t"]) / 1000, tz=_dt.timezone.utc),
            "o": float(c["o"]), "h": float(c["h"]), "l": float(c["l"]),
            "c": float(c["c"]), "v": float(c["v"]),
        })
    return bars
