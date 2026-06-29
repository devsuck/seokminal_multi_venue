"""XGBoost classifier training and signal prediction."""
from __future__ import annotations
from xgboost import XGBClassifier
from xgb_strategy.features import compute_features


def train_model(
    closes: list[float],
    train_ratio: float = 0.7,
    n_estimators: int = 100,
    max_depth: int = 4,
    learning_rate: float = 0.1,
):
    """Train XGBClassifier on first train_ratio of closes. Returns fitted model."""
    feats = compute_features(closes)
    train_n = int(len(closes) * train_ratio)

    X, y = [], []
    for i in range(train_n - 1):
        if feats[i] is not None and i + 1 < len(closes):
            label = 1 if closes[i + 1] > closes[i] else 0
            X.append(feats[i])
            y.append(label)

    # Ensure both classes are present (XGBoost requires at least one sample per class)
    if len(X) > 1 and len(set(y)) < 2:
        missing_class = 0 if 1 in y else 1
        y[-1] = missing_class

    model = XGBClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        eval_metric="logloss",
        verbosity=0,
    )
    model.fit(X, y)
    return model


def predict_signals(model, feats: list[list[float] | None]) -> list[str]:
    """Run model on feature list. Returns BUY/SELL/HOLD per bar."""
    signals = []
    valid_idx = [i for i, f in enumerate(feats) if f is not None]
    if not valid_idx:
        return ["HOLD"] * len(feats)

    X = [feats[i] for i in valid_idx]
    probas = model.predict_proba(X)

    proba_map = {i: probas[j, 1] for j, i in enumerate(valid_idx)}

    for i in range(len(feats)):
        if i not in proba_map:
            signals.append("HOLD")
        elif proba_map[i] > 0.6:
            signals.append("BUY")
        elif proba_map[i] < 0.4:
            signals.append("SELL")
        else:
            signals.append("HOLD")
    return signals
