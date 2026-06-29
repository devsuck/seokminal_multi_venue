"""XGBoost strategy runner — integrates with backtest pipeline."""
from __future__ import annotations
from xgb_strategy.features import compute_features
from xgb_strategy.model import train_model, predict_signals


def generate_xgb_signals(bars: list, params: dict) -> list[str]:
    """
    Train XGBoost on first train_ratio of bars, generate BUY/SELL/HOLD for all bars.
    Training window returns HOLD (no look-ahead bias).
    """
    train_ratio = float(params.get("train_ratio", 0.7))
    n_estimators = int(params.get("n_estimators", 100))
    max_depth = int(params.get("max_depth", 4))
    learning_rate = float(params.get("learning_rate", 0.1))

    closes = [float(b.close) for b in bars]
    train_n = int(len(closes) * train_ratio)

    model = train_model(closes, train_ratio, n_estimators, max_depth, learning_rate)
    feats = compute_features(closes)

    # Only predict on test portion; training window → HOLD
    test_feats: list[list[float] | None] = [None] * train_n + feats[train_n:]
    signals = predict_signals(model, test_feats)
    return signals
