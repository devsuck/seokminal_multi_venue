"""Simple regime detector: rolling vol + SMA direction.

Regimes:
  bull_low_vol   — price > SMA, vol <= vol_threshold
  bull_high_vol  — price > SMA, vol >  vol_threshold
  bear_low_vol   — price < SMA, vol <= vol_threshold
  bear_high_vol  — price < SMA, vol >  vol_threshold
"""
import math
import statistics


def detect_regime(
    closes: list[float],
    sma_period: int = 50,
    vol_period: int = 20,
    vol_threshold: float | None = None,
) -> dict:
    """
    Detect market regime from price series.

    Args:
        closes: Closing prices (oldest first).
        sma_period: Period for simple moving average (trend direction).
        vol_period: Period for rolling annualised volatility.
        vol_threshold: Ann. vol cutoff for 'high/low'. Default = historical median.

    Returns dict with:
        regimes: list of {"date_index": int, "regime": str, "vol": float, "sma": float}
        current_regime: str
        current_vol: float
        vol_threshold: float
        bull_low_vol_pct: fraction of time in each regime
        bear_high_vol_pct: ...
    """
    n = len(closes)
    if n < sma_period + 1:
        raise ValueError(f"need >= {sma_period + 1} closes, got {n}")

    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, n)]

    regimes: list[dict] = []
    vols: list[float] = []

    for i in range(len(returns)):
        if i < vol_period - 1:
            regimes.append(None)  # not enough history yet
            continue

        window_ret = returns[i - vol_period + 1 : i + 1]
        vol_daily = statistics.stdev(window_ret)
        ann_vol = vol_daily * math.sqrt(252)
        vols.append(ann_vol)

        # SMA uses close prices (aligned to returns index i → price index i+1)
        price_idx = i + 1
        if price_idx < sma_period:
            regimes.append(None)
            continue

        sma = sum(closes[price_idx - sma_period + 1 : price_idx + 1]) / sma_period
        price = closes[price_idx]
        regimes.append({
            "date_index": price_idx,
            "vol": round(ann_vol, 4),
            "sma": round(sma, 4),
            "price": round(price, 4),
        })

    if vol_threshold is None:
        vol_threshold = statistics.median(vols) if vols else 0.2

    result_regimes = []
    for r in regimes:
        if r is None:
            continue
        trend = "bull" if r["price"] >= r["sma"] else "bear"
        vol_state = "low_vol" if r["vol"] <= vol_threshold else "high_vol"
        r["regime"] = f"{trend}_{vol_state}"
        result_regimes.append(r)

    regime_counts: dict[str, int] = {}
    for r in result_regimes:
        regime_counts[r["regime"]] = regime_counts.get(r["regime"], 0) + 1
    total = len(result_regimes) or 1

    return {
        "regimes": result_regimes,
        "current_regime": result_regimes[-1]["regime"] if result_regimes else "unknown",
        "current_vol": result_regimes[-1]["vol"] if result_regimes else None,
        "current_sma": result_regimes[-1]["sma"] if result_regimes else None,
        "vol_threshold": round(vol_threshold, 4),
        "sma_period": sma_period,
        "vol_period": vol_period,
        "regime_distribution": {k: round(v / total, 4) for k, v in regime_counts.items()},
    }
