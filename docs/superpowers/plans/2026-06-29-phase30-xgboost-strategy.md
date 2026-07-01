# Phase 30: XGBoost ML Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add XGBoost ML strategy to the backtest pipeline — feature engineering from price bars, binary classifier training (up/down), BUY/SELL/HOLD signal generation, API integration, and frontend params panel.

**Architecture:** New `xgb_strategy/` Python module (features → model → runner). `simple_runner.py` dispatches to it for strategy="xgb". Frontend adds XGBoost to the strategy selector with its own params panel.

**Tech Stack:** xgboost 3.3.0, scikit-learn 1.9.0, Python 3.14, FastAPI, Next.js 14

## Global Constraints

- Python: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`
- pytest: asyncio_mode="auto", `@pytest.mark.asyncio` FORBIDDEN
- Pre-existing failures to ignore: test_auth.py ×3, test_backtest_happy_path ×1
- Frontend design tokens only: `bg-panel/panel-2`, `border-border`, `text-text-1/2/3`, `text-accent`
- No `style={{}}` except `style={{ height: "Npx" }}` chart containers
- No raw `fetch` — use `lib/api.ts` functions

---

### Task 1: Backend XGBoost Module

**Files:**
- Create: `xgb_strategy/__init__.py`
- Create: `xgb_strategy/features.py`
- Create: `xgb_strategy/model.py`
- Create: `xgb_strategy/runner.py`
- Create: `tests/test_xgb_strategy.py`

**Interfaces:**
- Produces: `generate_xgb_signals(bars: list, params: dict) -> list[str]`
  - `bars`: list of objects with `.close` attribute (floats)
  - `params`: `{"train_ratio": float, "n_estimators": int, "max_depth": int, "learning_rate": float}`
  - Returns: list of `"BUY"` / `"SELL"` / `"HOLD"` strings, same length as `bars`
  - First `train_ratio` portion gets `"HOLD"` (training window, no signal)

**Design decisions:**
- Features computed from close prices only (no volume — bars may not have volume)
- Train on first `train_ratio=0.7` of data, generate signals only for remaining 0.3
- Label: 1 if next bar's close > current close, 0 otherwise
- Prediction threshold: predict_proba > 0.6 → BUY, < 0.4 → SELL, else HOLD
- XGBClassifier default: n_estimators=100, max_depth=4, learning_rate=0.1, use_label_encoder=False, eval_metric="logloss"

- [ ] **Step 1: Create `xgb_strategy/__init__.py`**

```python
from .runner import generate_xgb_signals

__all__ = ["generate_xgb_signals"]
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_xgb_strategy.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-multi-venue
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_xgb_strategy.py -q 2>&1 | head -20
```

Expected: ImportError or ModuleNotFoundError (xgb_strategy not yet created)

- [ ] **Step 4: Create `xgb_strategy/features.py`**

```python
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
    ema12_s = _ema(closes, 12)
    ema26_s = _ema(closes, 26)

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
```

- [ ] **Step 5: Create `xgb_strategy/model.py`**

```python
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
```

- [ ] **Step 6: Create `xgb_strategy/runner.py`**

```python
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
```

- [ ] **Step 7: Run all xgb tests**

```bash
cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-multi-venue
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_xgb_strategy.py -q
```

Expected: 7/7 pass

- [ ] **Step 8: Commit**

```bash
cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-multi-venue
git add xgb_strategy/ tests/test_xgb_strategy.py
git commit -m "feat: add XGBoost ML strategy module (features, model, runner)"
```

---

### Task 2: API Integration

**Files:**
- Modify: `backtest_runner/simple_runner.py`
- Modify: `api_server/main.py`

**Interfaces:**
- Consumes: `generate_xgb_signals(bars, params)` from `xgb_strategy.runner`
- Produces: `strategy="xgb"` supported in `run_simple_backtest` and `/backtest` endpoint
  - XGBoost API params: `xgb_train_ratio: float = Query(0.7)`, `xgb_n_estimators: int = Query(100)`, `xgb_max_depth: int = Query(4)`, `xgb_learning_rate: float = Query(0.1)`

- [ ] **Step 1: Write failing test**

Add to `tests/test_xgb_strategy.py`:

```python
def test_run_simple_backtest_xgb():
    from backtest_runner.simple_runner import run_simple_backtest
    bars = _make_bars(150)
    result = run_simple_backtest(bars, "xgb", {
        "train_ratio": 0.7,
        "n_estimators": 10,
        "max_depth": 3,
        "learning_rate": 0.1,
        "trade_size": 10,
    })
    assert "total_pnl" in result
    assert "sharpe_ratio" in result
    assert "num_trades" in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-multi-venue
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_xgb_strategy.py::test_run_simple_backtest_xgb -q
```

Expected: FAIL — ValueError "unknown strategy 'xgb'"

- [ ] **Step 3: Add xgb dispatch to `backtest_runner/simple_runner.py`**

After the `elif strategy == "ema_cross":` block (before the `else: raise ValueError`), add:

```python
    elif strategy == "xgb":
        from xgb_strategy.runner import generate_xgb_signals
        signals = generate_xgb_signals(bars, params)
```

Also update the docstring of `run_simple_backtest` to mention xgb:
```python
def run_simple_backtest(bars: list, strategy: str, params: dict) -> dict:
    """Run MACD, RSI, EMA Cross, or XGBoost backtest on the given bars. Returns same dict format as run_backtest."""
```

- [ ] **Step 4: Add xgb to SUPPORTED_STRATEGIES and endpoint params in `api_server/main.py`**

Find `SUPPORTED_STRATEGIES = {"ema_cross", "gated", "macd", "rsi"}` and change to:
```python
SUPPORTED_STRATEGIES = {"ema_cross", "gated", "macd", "rsi", "xgb"}
```

Find the `/backtest` endpoint function signature (the one with `strategy: str = Query(...)` and all the MACD/RSI/EMA params). Add these new params to its signature:

```python
    xgb_train_ratio: float = Query(0.7, description="XGBoost train/test split ratio"),
    xgb_n_estimators: int = Query(100, description="XGBoost number of trees"),
    xgb_max_depth: int = Query(4, description="XGBoost tree max depth"),
    xgb_learning_rate: float = Query(0.1, description="XGBoost learning rate"),
```

Find the section where `simple_params` is built for xgb (currently falls through to `else: raise`). Add before the `else: raise` block:

```python
    elif strategy == "xgb":
        simple_params = {
            "train_ratio": xgb_train_ratio,
            "n_estimators": xgb_n_estimators,
            "max_depth": xgb_max_depth,
            "learning_rate": xgb_learning_rate,
            "trade_size": trade_size,
        }
        report = run_simple_backtest(simple_bars, strategy, simple_params)
```

Note: look at the existing structure of the `/backtest` endpoint — the xgb block should go in the same if/elif chain as macd/rsi/ema_cross blocks, and must set `report` the same way.

- [ ] **Step 5: Run tests**

```bash
cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-multi-venue
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_xgb_strategy.py -q
```

Expected: all 8 tests pass

- [ ] **Step 6: Run full test suite**

```bash
cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-multi-venue
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q 2>&1 | tail -10
```

Ignore pre-existing failures: test_auth.py ×3, test_backtest_happy_path ×1

- [ ] **Step 7: Commit**

```bash
cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-multi-venue
git add backtest_runner/simple_runner.py api_server/main.py tests/test_xgb_strategy.py
git commit -m "feat: integrate XGBoost strategy into backtest API endpoint"
```

---

### Task 3: Frontend XGBoost Strategy Selector

**Files:**
- Modify: `seokminal-dashboard/app/backtest/page.tsx`
- Modify: `seokminal-dashboard/lib/api.ts` (add xgb params to getBacktest call if needed)

**Context:**
- Backtest page is in `seokminal-dashboard/app/backtest/page.tsx`
- Current strategy types: `"ema_cross" | "macd" | "rsi"` (line ~57)
- `mode` state: `"single"` vs `"gated"` (multi-rule mode)
- Strategy selector is a segmented control with buttons
- Each strategy has its own params panel (MACD: fast/slow/signal, RSI: period/oversold/overbought, EMA: fast/slow)
- `getBacktest` in `lib/api.ts` accepts `strategyParams: Record<string, string>`

**Interfaces:**
- Consumes: `getBacktest(instrumentId, start, end, "xgb", { train_ratio, n_estimators, max_depth, learning_rate }, benchmarkId, signal)`
- All XGBoost params passed as string values in `strategyParams`
- API will map query params: `xgb_train_ratio=0.7&xgb_n_estimators=100&xgb_max_depth=4&xgb_learning_rate=0.1`

**Important:** The `getBacktest` function in `lib/api.ts` spreads `strategyParams` as query params. The API endpoint reads them as `xgb_train_ratio`, `xgb_n_estimators`, etc. So the frontend must pass keys matching the API: `xgb_train_ratio`, `xgb_n_estimators`, `xgb_max_depth`, `xgb_learning_rate`.

- [ ] **Step 1: Check current strategy type union and selector in backtest/page.tsx**

Read `app/backtest/page.tsx` and identify:
1. The `strategyType` state declaration (line ~57)
2. The strategy selector buttons section
3. The MACD params panel section (as template for XGBoost panel)
4. The `run()` function where `strategy` and `strategyParams` are set (line ~91-115)

- [ ] **Step 2: Write TypeScript tests**

Run `npx tsc --noEmit` to see current state. After changes, it must still be 0 errors.

- [ ] **Step 3: Add XGBoost state variables**

Add these state variables near the other strategy param states:

```tsx
const [xgbTrainRatio, setXgbTrainRatio] = useState(0.7);
const [xgbNEstimators, setXgbNEstimators] = useState(100);
const [xgbMaxDepth, setXgbMaxDepth] = useState(4);
const [xgbLearningRate, setXgbLearningRate] = useState(0.1);
```

- [ ] **Step 4: Update strategyType type union**

Change:
```tsx
const [strategyType, setStrategyType] = useState<"ema_cross" | "macd" | "rsi">("ema_cross");
```
To:
```tsx
const [strategyType, setStrategyType] = useState<"ema_cross" | "macd" | "rsi" | "xgb">("ema_cross");
```

- [ ] **Step 5: Add XGBoost button to strategy selector**

Find the strategy selector buttons (the ones for ema_cross, macd, rsi). Add after the RSI button:

```tsx
<button
  onClick={() => setStrategyType("xgb")}
  className={`px-3 py-1 text-xs rounded transition-colors cursor-pointer ${
    strategyType === "xgb"
      ? "bg-accent/10 text-accent border border-accent"
      : "text-text-3 hover:text-text-1 border border-transparent"
  }`}
>
  XGBoost (ML)
</button>
```

- [ ] **Step 6: Add XGBoost params panel**

Find where the MACD params panel is rendered (`{strategyType === "macd" && (...)}`) and add after the RSI params panel:

```tsx
{strategyType === "xgb" && (
  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
    <div>
      <label className="text-text-3 text-[10px] uppercase tracking-wider block mb-1">Train Ratio</label>
      <input
        type="number"
        min="0.5"
        max="0.9"
        step="0.05"
        value={xgbTrainRatio}
        onChange={e => setXgbTrainRatio(parseFloat(e.target.value))}
        className="w-full bg-panel-2 border border-border rounded px-2 py-1 text-text-1 text-xs font-data"
      />
    </div>
    <div>
      <label className="text-text-3 text-[10px] uppercase tracking-wider block mb-1">Trees</label>
      <input
        type="number"
        min="10"
        max="500"
        step="10"
        value={xgbNEstimators}
        onChange={e => setXgbNEstimators(parseInt(e.target.value))}
        className="w-full bg-panel-2 border border-border rounded px-2 py-1 text-text-1 text-xs font-data"
      />
    </div>
    <div>
      <label className="text-text-3 text-[10px] uppercase tracking-wider block mb-1">Max Depth</label>
      <input
        type="number"
        min="2"
        max="10"
        step="1"
        value={xgbMaxDepth}
        onChange={e => setXgbMaxDepth(parseInt(e.target.value))}
        className="w-full bg-panel-2 border border-border rounded px-2 py-1 text-text-1 text-xs font-data"
      />
    </div>
    <div>
      <label className="text-text-3 text-[10px] uppercase tracking-wider block mb-1">Learning Rate</label>
      <input
        type="number"
        min="0.01"
        max="0.5"
        step="0.01"
        value={xgbLearningRate}
        onChange={e => setXgbLearningRate(parseFloat(e.target.value))}
        className="w-full bg-panel-2 border border-border rounded px-2 py-1 text-text-1 text-xs font-data"
      />
    </div>
  </div>
)}
```

- [ ] **Step 7: Add XGBoost case to the `run()` function**

Find the `run()` function's strategy dispatch block (around line 91-115). Add XGBoost case in the same `if/else if` chain, before the EMA cross case or at the end:

```tsx
} else if (strategyType === "xgb") {
  strategy = "xgb";
  strategyParams = {
    xgb_train_ratio: String(xgbTrainRatio),
    xgb_n_estimators: String(xgbNEstimators),
    xgb_max_depth: String(xgbMaxDepth),
    xgb_learning_rate: String(xgbLearningRate),
  };
```

- [ ] **Step 8: TypeScript check**

```bash
cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-dashboard
npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 9: Run tests**

```bash
cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-dashboard
npm test -- --passWithNoTests
```

Expected: all pass

- [ ] **Step 10: Commit**

```bash
cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-dashboard
git add app/backtest/page.tsx
git commit -m "feat: add XGBoost ML strategy to backtest UI"
```

Write report to: `seokminal-dashboard/.superpowers/sdd/task-3-xgb-report.md`
