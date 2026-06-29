from __future__ import annotations
import math
from unittest.mock import MagicMock
from xgb_strategy.features import compute_features
from xgb_strategy.model import train_model, predict_signals
from xgb_strategy.runner import generate_xgb_signals


def _make_bars(n: int = 120) -> list:
    """Synthetic bars with trending closes."""
    bars = []
    for i in range(n):
        b = MagicMock()
        b.close = 100.0 + i * 0.5 + (i % 3) * 0.1
        bars.append(b)
    return bars


def test_compute_features_shape():
    bars = _make_bars(100)
    closes = [float(b.close) for b in bars]
    feats = compute_features(closes)
    assert len(feats) == len(closes)
    # First entries may be None (warmup)
    non_none = [f for f in feats if f is not None]
    assert len(non_none) > 0
    # Each feature row is a list of floats
    assert isinstance(non_none[0], list)
    assert all(isinstance(v, float) for v in non_none[0])


def test_compute_features_no_nan_in_valid():
    bars = _make_bars(100)
    closes = [float(b.close) for b in bars]
    feats = compute_features(closes)
    for f in feats:
        if f is not None:
            assert all(not math.isnan(v) and not math.isinf(v) for v in f)


def test_train_model_returns_model():
    bars = _make_bars(120)
    closes = [float(b.close) for b in bars]
    model = train_model(closes, n_estimators=10, max_depth=3, learning_rate=0.1)
    assert model is not None
    # Model has predict_proba
    assert hasattr(model, "predict_proba")


def test_predict_signals_length():
    bars = _make_bars(120)
    closes = [float(b.close) for b in bars]
    model = train_model(closes, n_estimators=10, max_depth=3, learning_rate=0.1)
    from xgb_strategy.features import compute_features
    feats = compute_features(closes)
    signals = predict_signals(model, feats)
    assert len(signals) == len(closes)
    assert all(s in ("BUY", "SELL", "HOLD") for s in signals)


def test_generate_xgb_signals_length():
    bars = _make_bars(150)
    signals = generate_xgb_signals(bars, {
        "train_ratio": 0.7,
        "n_estimators": 10,
        "max_depth": 3,
        "learning_rate": 0.1,
    })
    assert len(signals) == len(bars)
    assert all(s in ("BUY", "SELL", "HOLD") for s in signals)


def test_generate_xgb_signals_train_window_is_hold():
    bars = _make_bars(150)
    signals = generate_xgb_signals(bars, {
        "train_ratio": 0.7,
        "n_estimators": 10,
        "max_depth": 3,
        "learning_rate": 0.1,
    })
    train_n = int(0.7 * len(bars))
    # Training window should all be HOLD
    assert all(s == "HOLD" for s in signals[:train_n])


def test_generate_xgb_signals_test_window_has_signals():
    bars = _make_bars(150)
    signals = generate_xgb_signals(bars, {
        "train_ratio": 0.7,
        "n_estimators": 10,
        "max_depth": 3,
        "learning_rate": 0.1,
    })
    train_n = int(0.7 * len(bars))
    test_signals = signals[train_n:]
    # At least some BUY or SELL in test window
    assert any(s != "HOLD" for s in test_signals)
