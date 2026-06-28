"""Hyperliquid public REST API client — no authentication required."""
import requests

HL_URL = "https://api.hyperliquid.xyz/info"


def get_all_mids() -> dict[str, str]:
    """Return current mid prices for all perpetual markets.

    Returns dict mapping coin name to mid price string, e.g. {"BTC": "94500.0"}.
    """
    resp = requests.post(HL_URL, json={"type": "allMids"}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_meta_and_ctxs() -> tuple[list[dict], list[dict]]:
    """Return (universe_list, asset_ctx_list) for all perpetual markets.

    universe_list: [{"name": "BTC", "szDecimals": 5, "maxLeverage": 50}, ...]
    asset_ctx_list: [{"funding": "0.0001", "openInterest": "5000.0",
                      "prevDayPx": "93000.0", "dayNtlVlm": "5e8",
                      "markPx": "94500.0", "midPx": "94500.0"}, ...]
    Lists are parallel — index i in universe corresponds to index i in ctxs.
    """
    resp = requests.post(HL_URL, json={"type": "metaAndAssetCtxs"}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list) or len(data) < 2 or "universe" not in data[0]:
        raise ValueError(f"Unexpected metaAndAssetCtxs response: {data!r:.100}")
    return data[0]["universe"], data[1]


def get_candles(coin: str, interval: str, start_ms: int, end_ms: int) -> list[dict]:
    """Return OHLCV candle snapshots for a coin over a time range.

    Args:
        coin: Market name e.g. "BTC"
        interval: One of "1d", "4h", "1h", "15m"
        start_ms: Start time in milliseconds (Unix epoch)
        end_ms: End time in milliseconds (Unix epoch)

    Each returned dict has keys: t (open time ms), T (close time ms), s (coin),
    i (interval), o, c, h, l (OHLC strings), v (volume string), n (trade count int).
    """
    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": coin,
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
        },
    }
    resp = requests.post(HL_URL, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_l2_book(coin: str) -> dict:
    """Return L2 order book for a coin.

    Returns dict with keys:
        coin (str), time (ms), levels (list of [bids, asks]):
            bids: list of {"px": str, "sz": str, "n": int} sorted best (highest) first
            asks: list of {"px": str, "sz": str, "n": int} sorted best (lowest) first
    """
    resp = requests.post(HL_URL, json={"type": "l2Book", "coin": coin}, timeout=10)
    resp.raise_for_status()
    return resp.json()
