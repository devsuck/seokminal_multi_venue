# Gold Haven Hypothesis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement and validate a new v2-shadow trading hypothesis for GC (gold futures): long/flat only, gated by a declining real-rate regime, with a risk-off (VIX/credit-spread) position-size boost.

**Architecture:** Mirror the existing `research/hypotheses/tsmom.py` + `research/backtest/portfolio_backtester.py` pattern. New pure-logic weight functions (`gold_haven_weights`, `buyhold_weights`, `random_weights`) plug into the existing `run_portfolio()` engine unchanged. A separate `build_macro_panel()` function fetches and aligns FRED series (real-rate proxy, VIX, credit spread) to the GC price date axis. A new runner script (`research/run_gold_haven.py`) mirrors `research/run_tsmom.py`'s validation flow (random baseline, walk-forward, cost stress, verdict, experiment log).

**Tech Stack:** Python 3.14, pytest (`asyncio_mode="auto"` — never use `@pytest.mark.asyncio`), existing `fred/client.py` (FRED API), existing `research/data/futures_loader.py` GC data (already collected, no new IB pull needed).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-07-gold-haven-hypothesis-design.md`
- Fixed parameters, no tuning at any point in this plan:
  ```python
  DEFAULTS = {
      "real_rate_lookback": 63,
      "vol_window": 60,
      "risk_off_zscore_window": 252,
      "risk_off_zscore_threshold": 1.5,
      "risk_off_boost": 1.5,
      "target_vol": 0.15,
      "cap": 3.0,
  }
  REBAL = 1
  COST_BASE_BPS = 2.0
  COST_STRESS_BPS = 20.0
  N_RUNS = 200
  SEED = 42
  ```
- Long/flat only — no short positions anywhere in this hypothesis (weight is always `>= 0`).
- Risk-off signal only scales position size when the regime gate is already BULLISH; it never triggers entry by itself.
- v2 shadow classification: `CAPITAL = 0`, no live trading wiring in this plan — this plan produces validation-only code.
- Python interpreter: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`
- Test command: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
- `pytest.ini` / `pyproject.toml` already set `testpaths = ["tests"]` and `asyncio_mode = "auto"` at repo root — no `PYTHONPATH` needed, imports like `from research.hypotheses.gold_haven import ...` resolve directly.
- No network calls in unit tests. Tests that touch FRED must monkeypatch `fred.client.FREDClient`.

---

### Task 1: Weight functions (regime gate + risk-off overlay) — pure logic, synthetic-panel tested

**Files:**
- Create: `research/hypotheses/gold_haven.py`
- Test: `tests/test_gold_haven.py`

**Interfaces:**
- Consumes: nothing from other tasks (first task).
- Produces (used by Task 3):
  - `DEFAULTS: dict` — the fixed params shown in Global Constraints.
  - `gold_haven_weights(panels: dict, date: str, params: dict, rng=None) -> dict` — same `WeightFn` signature as `research.hypotheses.tsmom.tsmom_weights` (`Callable[[dict, str, dict, object], dict]`). `params` must contain a `"macro"` key holding a macro panel dict shaped `{"dates": list[str], "real_rate": {date: float}, "vix": {date: float}, "credit_spread": {date: float}}` (this exact shape is defined and produced by Task 2's `build_macro_panel`).
  - `buyhold_weights(panels: dict, date: str, params: dict, rng=None) -> dict` — same signature, ignores `"macro"`.
  - `random_weights(panels: dict, date: str, params: dict, rng=None) -> dict` — same signature, ignores `"macro"`.

**Notes for the implementer:**
- `panels` here is always a single-asset dict like `{"GC": {"symbol": "GC", "dates": [...], "close": {date: price}}}` — same shape `research/hypotheses/tsmom.py`'s `build_panel()` returns. You do not need to call `build_panel` in this task; tests build synthetic panels directly (see test code below).
- Look at `research/hypotheses/tsmom.py` for the bisect-based history-lookup pattern (`_asset_ctx`) — this task reuses the same idea for volatility only (no momentum).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gold_haven.py`:

```python
"""Gold haven 가설 — 순수 로직 synthetic 테스트 (네트워크 없음)."""
from __future__ import annotations

import datetime as dt

from research.hypotheses.gold_haven import (
    DEFAULTS, gold_haven_weights, buyhold_weights, random_weights,
)


def _price_panel(sym="GC", n=400, slope=0.0005):
    d0 = dt.date(2020, 1, 1)
    dates = [(d0 + dt.timedelta(days=i)).isoformat() for i in range(n)]
    close = {}
    px = 100.0
    for i, d in enumerate(dates):
        noise = 0.006 if i % 2 else -0.005
        px *= (1 + slope + noise)
        close[d] = px
    return dates, {"symbol": sym, "dates": dates, "close": close}


def _macro_panel(dates, real_rate_vals, vix_vals=None, credit_vals=None):
    vix_vals = vix_vals if vix_vals is not None else [15.0] * len(dates)
    credit_vals = credit_vals if credit_vals is not None else [4.0] * len(dates)
    return {
        "dates": dates,
        "real_rate": dict(zip(dates, real_rate_vals)),
        "vix": dict(zip(dates, vix_vals)),
        "credit_spread": dict(zip(dates, credit_vals)),
    }


def test_gate_bullish_when_real_rate_declining():
    dates, gc = _price_panel()
    # 꾸준히 하락하는 실질금리 (오늘 < lookback일 전)
    real_rate_vals = [5.0 - 0.01 * i for i in range(len(dates))]
    macro = _macro_panel(dates, real_rate_vals)
    params = {**DEFAULTS, "macro": macro}
    d = dates[-1]

    w = gold_haven_weights({"GC": gc}, d, params)
    assert w.get("GC", 0.0) > 0.0


def test_gate_flat_when_real_rate_rising():
    dates, gc = _price_panel()
    # 꾸준히 상승하는 실질금리 → 게이트 FLAT
    real_rate_vals = [1.0 + 0.01 * i for i in range(len(dates))]
    macro = _macro_panel(dates, real_rate_vals)
    params = {**DEFAULTS, "macro": macro}
    d = dates[-1]

    w = gold_haven_weights({"GC": gc}, d, params)
    assert w.get("GC", 0.0) == 0.0


def test_risk_off_boosts_weight_when_gate_bullish():
    dates, gc = _price_panel()
    real_rate_vals = [5.0 - 0.01 * i for i in range(len(dates))]
    # VIX 마지막 값만 스파이크 (나머지는 평온) → z-score 급등 → risk_off
    vix_vals = [15.0] * (len(dates) - 1) + [60.0]
    macro_calm = _macro_panel(dates, real_rate_vals, vix_vals=[15.0] * len(dates))
    macro_stress = _macro_panel(dates, real_rate_vals, vix_vals=vix_vals)
    d = dates[-1]

    w_calm = gold_haven_weights({"GC": gc}, d, {**DEFAULTS, "macro": macro_calm})
    w_stress = gold_haven_weights({"GC": gc}, d, {**DEFAULTS, "macro": macro_stress})
    assert w_stress["GC"] > w_calm["GC"]


def test_risk_off_does_not_trigger_entry_when_gate_flat():
    dates, gc = _price_panel()
    real_rate_vals = [1.0 + 0.01 * i for i in range(len(dates))]  # FLAT 게이트
    vix_vals = [15.0] * (len(dates) - 1) + [60.0]  # risk_off 스파이크
    macro = _macro_panel(dates, real_rate_vals, vix_vals=vix_vals)
    params = {**DEFAULTS, "macro": macro}
    d = dates[-1]

    w = gold_haven_weights({"GC": gc}, d, params)
    assert w.get("GC", 0.0) == 0.0


def test_weight_never_negative():
    dates, gc = _price_panel()
    for real_rate_vals in (
        [5.0 - 0.01 * i for i in range(len(dates))],
        [1.0 + 0.01 * i for i in range(len(dates))],
    ):
        macro = _macro_panel(dates, real_rate_vals)
        params = {**DEFAULTS, "macro": macro}
        w = gold_haven_weights({"GC": gc}, dates[-1], params)
        assert w.get("GC", 0.0) >= 0.0


def test_insufficient_history_returns_no_weight():
    dates, gc = _price_panel(n=DEFAULTS["real_rate_lookback"] - 5)
    real_rate_vals = [5.0 - 0.01 * i for i in range(len(dates))]
    macro = _macro_panel(dates, real_rate_vals)
    params = {**DEFAULTS, "macro": macro}
    w = gold_haven_weights({"GC": gc}, dates[-1], params)
    assert w == {} or "GC" not in w


def test_buyhold_always_long_ignores_macro():
    dates, gc = _price_panel()
    w = buyhold_weights({"GC": gc}, dates[-1], {**DEFAULTS})
    assert w.get("GC", 0.0) > 0.0


def test_random_weights_seeded_reproducible():
    import random
    dates, gc = _price_panel()
    r1 = random.Random(42)
    r2 = random.Random(42)
    w1 = random_weights({"GC": gc}, dates[-1], {**DEFAULTS}, r1)
    w2 = random_weights({"GC": gc}, dates[-1], {**DEFAULTS}, r2)
    assert w1 == w2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_gold_haven.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.hypotheses.gold_haven'`

- [ ] **Step 3: Implement `research/hypotheses/gold_haven.py`**

```python
"""금(GC) 안전자산 가설 — 실질금리 하락 레짐 게이트 + VIX/신용스프레드 리스크오프 부스트.

롱/플랫만(숏 없음). 게이트가 BULLISH일 때만 포지션 보유, 리스크오프는 크기만 조절
(게이트가 FLAT이면 리스크오프여도 무포지션). 상세: docs/superpowers/specs/2026-07-07-gold-haven-hypothesis-design.md
"""
from __future__ import annotations

import bisect
import statistics as _st

DEFAULTS = {
    "real_rate_lookback": 63,
    "vol_window": 60,
    "risk_off_zscore_window": 252,
    "risk_off_zscore_threshold": 1.5,
    "risk_off_boost": 1.5,
    "target_vol": 0.15,
    "cap": 3.0,
}


def _bisect_at(dates: list, date: str) -> int | None:
    j = bisect.bisect_right(dates, date) - 1
    if j < 0 or dates[j] != date:
        return None
    return j


def _asset_vol(panel: dict, date: str, vol_window: int) -> float | None:
    dates, close = panel["dates"], panel["close"]
    j = _bisect_at(dates, date)
    if j is None or j < vol_window:
        return None
    rets = [close[dates[k]] / close[dates[k - 1]] - 1.0 for k in range(j - vol_window + 1, j + 1)]
    return _st.stdev(rets) * (252 ** 0.5) if len(rets) >= 2 else 0.0


def _regime_gate(macro: dict, date: str, lookback: int) -> str | None:
    """BULLISH(실질금리 lookback일 전보다 하락)/FLAT/None(이력부족)."""
    dates = macro["dates"]
    j = _bisect_at(dates, date)
    if j is None or j < lookback:
        return None
    now = macro["real_rate"].get(dates[j])
    past = macro["real_rate"].get(dates[j - lookback])
    if now is None or past is None:
        return None
    return "BULLISH" if now < past else "FLAT"


def _zscore_last(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _st.mean(values)
    std = _st.stdev(values)
    return (values[-1] - mean) / std if std > 1e-9 else 0.0


def _risk_off(macro: dict, date: str, window: int, threshold: float) -> bool:
    dates = macro["dates"]
    j = _bisect_at(dates, date)
    if j is None or j < window:
        return False
    span = range(j - window + 1, j + 1)

    vix_vals = [macro["vix"].get(dates[k]) for k in span]
    if all(v is not None for v in vix_vals) and _zscore_last(vix_vals) > threshold:
        return True

    credit_vals = [macro["credit_spread"].get(dates[k]) for k in span]
    if all(v is not None for v in credit_vals) and _zscore_last(credit_vals) > threshold:
        return True

    return False


def gold_haven_weights(panels: dict, date: str, params: dict, rng=None) -> dict:
    p = {**DEFAULTS, **params}
    macro = p["macro"]
    gate = _regime_gate(macro, date, p["real_rate_lookback"])
    out = {}
    for a, pn in panels.items():
        vol = _asset_vol(pn, date, p["vol_window"])
        if vol is None:
            continue
        if gate != "BULLISH":
            out[a] = 0.0
            continue
        boost = p["risk_off_boost"] if _risk_off(
            macro, date, p["risk_off_zscore_window"], p["risk_off_zscore_threshold"]
        ) else 1.0
        base = (p["target_vol"] / vol) if vol > 1e-9 else 0.0
        out[a] = min(base * boost, p["cap"])
    return out


def buyhold_weights(panels: dict, date: str, params: dict, rng=None) -> dict:
    """항상 롱(동일 vol 타겟) — 타이밍 가치 격리용 베이스라인."""
    p = {**DEFAULTS, **params}
    out = {}
    for a, pn in panels.items():
        vol = _asset_vol(pn, date, p["vol_window"])
        if vol is None:
            continue
        out[a] = min(p["target_vol"] / vol, p["cap"]) if vol > 1e-9 else 0.0
    return out


def random_weights(panels: dict, date: str, params: dict, rng=None) -> dict:
    """같은 빈도로 무작위 온(롱)/오프(플랫). 숏 없음 → 0/1 랜덤(TSMOM의 ±1과 다름)."""
    p = {**DEFAULTS, **params}
    out = {}
    for a, pn in panels.items():
        vol = _asset_vol(pn, date, p["vol_window"])
        if vol is None:
            continue
        on = (rng.random() < 0.5) if rng else True
        out[a] = (min(p["target_vol"] / vol, p["cap"]) if vol > 1e-9 else 0.0) if on else 0.0
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_gold_haven.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add research/hypotheses/gold_haven.py tests/test_gold_haven.py
git commit -m "feat: add gold haven weight functions (regime gate + risk-off boost)"
```

---

### Task 2: `build_macro_panel()` — FRED fetch + forward-fill alignment

**Files:**
- Modify: `research/hypotheses/gold_haven.py`
- Test: `tests/test_gold_haven.py` (append)

**Interfaces:**
- Consumes: `fred.client.FREDClient` — `get_series(series_id: str, start: str | None = None, end: str | None = None) -> list[dict]` returning `[{"date": str, "value": float | None}]` sorted ascending by date (confirmed in `fred/client.py`). Series IDs used: `"DGS10"`, `"CPIAUCSL"`, `"VIXCLS"`, `"BAMLH0A0HYM2"` — all already registered in `fred/client.py`'s `SERIES_CATALOG`.
- Produces (used by Task 3): `build_macro_panel(dates: list[str]) -> dict` returning exactly the shape Task 1 already consumes: `{"dates": list[str], "real_rate": {date: float}, "vix": {date: float}, "credit_spread": {date: float}}`.

**Notes for the implementer:**
- `FREDClient()` reads `FRED_API_KEY` from the environment in `__init__` (`fred/client.py:28`) — do not pass a key explicitly, and do not call `FREDClient()` at import time (only inside `build_macro_panel`, so tests that never call it don't need the env var).
- CPI (`CPIAUCSL`) is monthly. Compute year-over-year %% change first (`_cpi_yoy`), then forward-fill that derived series onto the daily `dates` axis — do not try to forward-fill raw CPI level and subtract nominal rate directly, that would give a nonsensical "level minus rate" number instead of a real yield.
- Fetch CPI starting ~400 calendar days before `dates[0]` so the YoY calculation has a trailing 12 months of data available at the very first date you need to align.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gold_haven.py`:

```python
import pytest

from research.hypotheses.gold_haven import build_macro_panel


class _FakeFRED:
    """DGS10=일정, CPIAUCSL=월간 완만 상승, VIXCLS/BAMLH0A0HYM2=일정. 실제 API 미호출."""

    def __init__(self, *args, **kwargs):
        pass

    def get_series(self, series_id, start=None, end=None):
        if series_id == "DGS10":
            return [{"date": f"2024-{m:02d}-01", "value": 4.0} for m in range(1, 13)] + \
                   [{"date": f"2024-{m:02d}-15", "value": 4.0} for m in range(1, 13)]
        if series_id == "CPIAUCSL":
            # 2023-01부터 2024-12까지, 매달 0.3씩 증가하는 지수 (YoY 계산용 앞선 1년 포함)
            out = []
            base = 300.0
            months = [(y, m) for y in (2022, 2023, 2024) for m in range(1, 13)]
            for i, (y, m) in enumerate(months):
                out.append({"date": f"{y}-{m:02d}-01", "value": base + 0.3 * i})
            return out
        if series_id == "VIXCLS":
            return [{"date": f"2024-{m:02d}-01", "value": 15.0} for m in range(1, 13)]
        if series_id == "BAMLH0A0HYM2":
            return [{"date": f"2024-{m:02d}-01", "value": 4.0} for m in range(1, 13)]
        raise AssertionError(f"unexpected series_id {series_id}")


def test_build_macro_panel_aligns_to_dates(monkeypatch):
    monkeypatch.setattr("fred.client.FREDClient", _FakeFRED)
    dates = [f"2024-{m:02d}-10" for m in range(1, 13)]

    macro = build_macro_panel(dates)

    assert macro["dates"] == dates
    assert set(macro["real_rate"]) <= set(dates)
    # 매 시점 real_rate 값 존재 (DGS10/CPI YoY 둘 다 forward-fill로 채워짐)
    assert all(d in macro["real_rate"] for d in dates)
    assert all(d in macro["vix"] for d in dates)
    assert all(d in macro["credit_spread"] for d in dates)
    # DGS10=4.0 고정, CPI YoY 대략 12*0.3/base*100 ~ 1.2%대 → real_rate는 4.0보다 약간 작은 양수
    assert 2.0 < macro["real_rate"]["2024-06-10"] < 4.0


def test_build_macro_panel_requires_no_network_beyond_fake(monkeypatch):
    # FREDClient가 몽키패치 안 됐으면 FRED_API_KEY 없어서 KeyError 나야 정상(네트워크 호출 시도 안 함 확인용)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    dates = ["2024-01-10"]
    with pytest.raises(KeyError):
        build_macro_panel(dates)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_gold_haven.py -v -k build_macro_panel`
Expected: FAIL with `ImportError: cannot import name 'build_macro_panel'`

- [ ] **Step 3: Add `build_macro_panel` and helpers to `research/hypotheses/gold_haven.py`**

Add near the top (after the `DEFAULTS` dict, before `_bisect_at`):

```python
import datetime as _dt
```

Add at the end of the file:

```python
def _shift_back(date_str: str, days: int) -> str:
    d = _dt.date.fromisoformat(date_str)
    return (d - _dt.timedelta(days=days)).isoformat()


def _ffill_align(series: list[dict], dates: list[str]) -> dict:
    """series=[{date,value}] (오름차순, FRED 응답 형식) → dates 축에 forward-fill 정렬."""
    svals = [(s["date"], s["value"]) for s in series if s["value"] is not None]
    out = {}
    idx = 0
    last = None
    for d in dates:
        while idx < len(svals) and svals[idx][0] <= d:
            last = svals[idx][1]
            idx += 1
        out[d] = last
    return out


def _cpi_yoy(series: list[dict]) -> list[dict]:
    """월간 CPI 레벨 → YoY %% 변화율 (12개월 전 대비), 앞 12개월은 계산 불가라 제외."""
    out = []
    for i in range(12, len(series)):
        v0 = series[i]["value"]
        v12 = series[i - 12]["value"]
        if v0 is None or v12 is None or v12 == 0:
            continue
        out.append({"date": series[i]["date"], "value": (v0 / v12 - 1.0) * 100.0})
    return out


def build_macro_panel(dates: list[str]) -> dict:
    """FRED 4개 시리즈를 GC 가격 패널의 날짜축(dates)에 정렬.

    real_rate = DGS10(명목 10년물) - CPI YoY(trailing 12개월, 근사 실질금리).
    """
    from fred.client import FREDClient

    client = FREDClient()
    start, end = dates[0], dates[-1]

    dgs10 = _ffill_align(client.get_series("DGS10", start, end), dates)
    cpi_raw = client.get_series("CPIAUCSL", start=_shift_back(start, 400), end=end)
    cpi = _ffill_align(_cpi_yoy(cpi_raw), dates)
    vix = _ffill_align(client.get_series("VIXCLS", start, end), dates)
    credit = _ffill_align(client.get_series("BAMLH0A0HYM2", start, end), dates)

    real_rate = {
        d: (dgs10[d] - cpi[d])
        for d in dates
        if dgs10.get(d) is not None and cpi.get(d) is not None
    }
    return {"dates": dates, "real_rate": real_rate, "vix": vix, "credit_spread": credit}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_gold_haven.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add research/hypotheses/gold_haven.py tests/test_gold_haven.py
git commit -m "feat: add build_macro_panel (FRED real-rate/VIX/credit-spread alignment)"
```

---

### Task 3: `research/run_gold_haven.py` — validation runner (random baseline + walk-forward + cost stress)

**Files:**
- Create: `research/run_gold_haven.py`

**Interfaces:**
- Consumes:
  - `research.hypotheses.gold_haven.{DEFAULTS, gold_haven_weights, buyhold_weights, random_weights, build_macro_panel}` (Tasks 1-2)
  - `research.hypotheses.tsmom.build_panel(symbol: str) -> dict` (existing, used to load GC price history — same function TSMOM already uses)
  - `research.backtest.portfolio_backtester.run_portfolio(panels, weight_fn, params, cost_bps, rebalance_days, rng=None) -> dict` (existing)
  - `research.validation.baselines.empirical_p_value(strategy_stat, random_stats) -> dict` (existing)
  - `research.agents.experiment_registry.log_experiment(entry: dict) -> None` (existing)
- Produces: nothing consumed by later tasks (this is the terminal script — a human runs it manually and reads the printed verdict).

**Notes for the implementer:**
- This mirrors `research/run_tsmom.py` almost exactly — read that file for the exact pattern before writing this one (random baseline loop, walk-forward split, verdict logic). The only structural difference: this hypothesis is single-asset (`{"GC": panel}` instead of a 32-market dict), and every `params` dict passed to a weight function must include `"macro": macro_panel` (Task 1's functions read `params["macro"]`).
- This script makes live network calls (FRED, and reads locally-cached GC data) — it is not covered by pytest, same as `run_tsmom.py` has no dedicated test file. Verification is a manual run (Step 2 below), not a `pytest` step.
- Do not add a cost-stress walk-forward combination or any other variation beyond what's listed — the spec's Global Constraints fix `COST_BASE_BPS=2.0` (primary) and `COST_STRESS_BPS=20.0` (stress, run once on the full sample only, same as noted in the design spec).

- [ ] **Step 1: Write `research/run_gold_haven.py`**

```python
"""금(GC) 안전자산 가설 판정 (고정 파라미터).

질문: 실질금리 하락 레짐 게이트 + 리스크오프 부스트가 buyhold·랜덤·비용을 이기는가?
베이스라인: random same-frequency 분포 + buy&hold. walk-forward. Sharpe 기준.

실행: PYTHONPATH=. python3 research/run_gold_haven.py
"""
from __future__ import annotations

import random as _random

from research.backtest.portfolio_backtester import run_portfolio
from research.validation.baselines import empirical_p_value
from research.hypotheses.gold_haven import (
    DEFAULTS, gold_haven_weights, buyhold_weights, random_weights, build_macro_panel,
)
from research.hypotheses.tsmom import build_panel
from research.agents.experiment_registry import log_experiment

N_RUNS = 200
SEED = 42
COST_BASE_BPS = 2.0
COST_STRESS_BPS = 20.0
REBAL = 1  # 매일 체크


def _filter(panel: dict, lo: str, hi: str) -> dict:
    ds = [d for d in panel["dates"] if lo <= d < hi]
    return {"symbol": panel["symbol"], "dates": ds, "close": {d: panel["close"][d] for d in ds}}


def _filter_macro(macro: dict, lo: str, hi: str) -> dict:
    ds = [d for d in macro["dates"] if lo <= d < hi]
    return {
        "dates": ds,
        "real_rate": {d: macro["real_rate"][d] for d in ds if d in macro["real_rate"]},
        "vix": {d: macro["vix"][d] for d in ds if d in macro["vix"]},
        "credit_spread": {d: macro["credit_spread"][d] for d in ds if d in macro["credit_spread"]},
    }


def main():
    gc = build_panel("GC")
    print("=" * 74)
    print(f"GOLD HAVEN | GC {len(gc['dates'])}일 | 고정 파라미터")
    print(f"real_rate_lookback={DEFAULTS['real_rate_lookback']}d "
          f"risk_off_boost={DEFAULTS['risk_off_boost']} rebal={REBAL}d cost={COST_BASE_BPS}bps")
    print("=" * 74)

    macro = build_macro_panel(gc["dates"])
    panels = {"GC": gc}
    params = {**DEFAULTS, "macro": macro}

    strat = run_portfolio(panels, gold_haven_weights, params, COST_BASE_BPS, REBAL)
    sm = strat["metrics"]
    bh = run_portfolio(panels, buyhold_weights, params, COST_BASE_BPS, REBAL)["metrics"]
    stress = run_portfolio(panels, gold_haven_weights, params, COST_STRESS_BPS, REBAL)["metrics"]

    rand_sharpes = []
    for k in range(N_RUNS):
        rng = _random.Random(SEED + k)
        m = run_portfolio(panels, random_weights, params, COST_BASE_BPS, REBAL, rng=rng)["metrics"]
        if m["sharpe"] is not None:
            rand_sharpes.append(m["sharpe"])
    pv = empirical_p_value(sm["sharpe"] or -99, rand_sharpes)

    all_dates = gc["dates"]
    mid = all_dates[len(all_dates) // 2]
    gc_first, gc_second = _filter(gc, all_dates[0], mid), _filter(gc, mid, all_dates[-1] + "~")
    macro_first, macro_second = _filter_macro(macro, all_dates[0], mid), _filter_macro(macro, mid, all_dates[-1] + "~")
    fh = run_portfolio({"GC": gc_first}, gold_haven_weights,
                        {**DEFAULTS, "macro": macro_first}, COST_BASE_BPS, REBAL)["metrics"]
    sh = run_portfolio({"GC": gc_second}, gold_haven_weights,
                        {**DEFAULTS, "macro": macro_second}, COST_BASE_BPS, REBAL)["metrics"]

    print(f"\nGOLD HAVEN: ann_ret={sm['ann_return']} vol={sm['ann_vol']} SHARPE={sm['sharpe']} "
          f"maxDD={sm['max_drawdown']} days={sm['days']}")
    print(f"buyhold   : ann_ret={bh['ann_return']} SHARPE={bh['sharpe']}")
    print(f"stress({COST_STRESS_BPS}bps): SHARPE={stress['sharpe']}")
    print(f"vs random: sharpe pct={pv['percentile']} p={pv['p_value']} "
          f"(rand median sharpe={pv['random_median']}, n={len(rand_sharpes)})")
    print(f"walk-forward: 전반 sharpe={fh['sharpe']} / 후반 sharpe={sh['sharpe']}")

    passed = (sm["sharpe"] and sm["sharpe"] > 0 and (pv["percentile"] or 0) >= 95
              and (pv["p_value"] or 1) < 0.05 and (fh["sharpe"] or -9) > 0 and (sh["sharpe"] or -9) > 0
              and sm["sharpe"] > (bh["sharpe"] or -9))
    verdict = ("EDGE 후보 — random 95pct 초과 + WF 양쪽 + buyhold 초과" if passed
               else "REJECT — 기준 미달")
    if sm["underpowered"]:
        verdict = "UNDERPOWERED — " + verdict
    print(f"\nVERDICT: {verdict}")

    log_experiment({"hypothesis_id": "gold_haven", "tf": "1d", "rebalance": "daily",
                    "status": "candidate" if passed else "rejected",
                    "sharpe": sm["sharpe"], "ann_return": sm["ann_return"], "max_drawdown": sm["max_drawdown"],
                    "buyhold_sharpe": bh["sharpe"], "stress_sharpe": stress["sharpe"],
                    "random_percentile": pv["percentile"], "p": pv["p_value"],
                    "wf_first_sharpe": fh["sharpe"], "wf_second_sharpe": sh["sharpe"],
                    "n_markets": 1, "verdict": verdict, "note": "fixed params, no tuning, long/flat only"})


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it manually and record the verdict**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m research.run_gold_haven`
Expected: prints the header, GOLD HAVEN/buyhold/stress metrics, random-baseline percentile/p-value, walk-forward split, and a final `VERDICT:` line (either `EDGE 후보`, `REJECT`, or `UNDERPOWERED — ...`). No exceptions. Requires `FRED_API_KEY` set in the environment and GC data already present in the local `intraday_store` (same data TSMOM already uses — no new IB pull needed).

- [ ] **Step 3: Commit**

```bash
git add research/run_gold_haven.py
git commit -m "feat: add gold haven validation runner (random baseline + WF + cost stress)"
```

---

## After Implementation

Update `docs/superpowers/specs/2026-07-07-gold-haven-hypothesis-design.md`'s "검증 → 다음 단계" section with the actual verdict from Task 3 Step 2, and log the outcome the same way TSMOM's Phase 102 result was recorded in `seokminal-dashboard/docs/progress.md` (per [[project_phase102_tsmom_edge]] precedent) — a candidate promotes to v2 shadow observation (no capital, 3-6 month forward window per [[feedback_tsmom_paper_discipline]]); a rejection gets recorded and the scoped-out alternatives (DXY signal, event-triggered hedge, regime-score integration) get evaluated for a follow-up attempt.
