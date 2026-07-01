"""VWAP and TWAP computation from OHLCV bars."""
import numpy as np


def compute_vwap_twap(bars: list[dict]) -> dict:
    """bars: list of {open, high, low, close, volume, ts_event}"""
    if not bars:
        return {}
    typical = np.array([(b["high"] + b["low"] + b["close"]) / 3 for b in bars])
    volume = np.array([b["volume"] for b in bars])
    close = np.array([b["close"] for b in bars])

    total_vol = volume.sum()
    vwap = float((typical * volume).sum() / total_vol) if total_vol > 0 else float(typical.mean())
    twap = float(typical.mean())
    current = float(close[-1])

    daily = []
    for b, tp in zip(bars, typical):
        daily.append({
            "date": str(b.get("date", "")),
            "typical_price": round(float(tp), 4),
            "close": round(float(b["close"]), 4),
            "volume": int(b["volume"]),
        })

    return {
        "vwap": round(vwap, 4),
        "twap": round(twap, 4),
        "current_price": round(current, 4),
        "vwap_deviation_pct": round((current - vwap) / vwap * 100, 4) if vwap else 0,
        "twap_deviation_pct": round((current - twap) / twap * 100, 4) if twap else 0,
        "total_volume": int(total_vol),
        "n_bars": len(bars),
    }
