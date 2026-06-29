"""Price-based feature engineering for XGBoost strategy."""
from __future__ import annotations
import math


def _ema(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    ema = sum(values[:period]) / period
    result[period - 1] = ema
    k = 2 / (period + 1)
    for i in range(period, len(values)):
        ema = values[i] * k + ema * (1 - k)
        result[i] = ema
    return result


def _rsi(closes: list[float], period: int = 14) -> list[float | None]:
    result: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return result
    gains, losses = [], []
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    if avg_l == 0.0:
        result[period] = 100.0
    else:
        rs = avg_g / avg_l
        result[period] = 100.0 - 100.0 / (1 + rs)
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0.0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0.0)) / period
        if avg_l == 0.0:
            result[i] = 100.0
        else:
            result[i] = 100.0 - 100.0 / (1 + avg_g / avg_l)
    return result


def compute_features(closes: list[float]) -> list[list[float] | None]:
    """
    Compute feature vectors for each bar. Returns None for warmup bars.
    Features: [rsi14, macd_diff, ema12_ratio, ema26_ratio, mom5, mom10]
    """
    n = len(closes)
    rsi14 = _rsi(closes, 14)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)

    # MACD line
    macd: list[float | None] = [
        (ema12[i] - ema26[i]) if (ema12[i] is not None and ema26[i] is not None) else None
        for i in range(n)
    ]
    # MACD signal (9-period EMA of macd)
    valid_macd = [v for v in macd if v is not None]
    macd_sig_raw = _ema(valid_macd, 9)
    macd_sig: list[float | None] = [None] * n
    j = 0
    for i in range(n):
        if macd[i] is not None:
            macd_sig[i] = macd_sig_raw[j]
            j += 1

    result: list[list[float] | None] = []
    for i in range(n):
        if (
            rsi14[i] is None
            or macd[i] is None
            or macd_sig[i] is None
            or ema12[i] is None
            or ema26[i] is None
            or i < 10
        ):
            result.append(None)
            continue
        rsi_val = rsi14[i]
        macd_diff = macd[i] - macd_sig[i]  # type: ignore[operator]
        ema12_ratio = closes[i] / ema12[i] - 1.0  # type: ignore[operator]
        ema26_ratio = closes[i] / ema26[i] - 1.0  # type: ignore[operator]
        mom5 = (closes[i] / closes[i - 5] - 1.0) if i >= 5 else 0.0
        mom10 = (closes[i] / closes[i - 10] - 1.0) if i >= 10 else 0.0
        row = [rsi_val, macd_diff, ema12_ratio, ema26_ratio, mom5, mom10]
        if any(math.isnan(v) or math.isinf(v) for v in row):
            result.append(None)
        else:
            result.append(row)
    return result
