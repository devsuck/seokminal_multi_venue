# Polymarket Sharp-Wallet Confidence Score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a continuous 0-100 `score` per sharp-wallet convergence anchor (alongside the existing `convergence_bucket`), and validate it via score-tercile BH-FDR screening run in parallel with the existing bucket screening.

**Architecture:** Extend the two existing files from the original spec — `research/hypotheses/polymarket_sharp_wallet.py` gets a new `build_convergence_score()` that appends `score` (and its raw components) to the anchor table; `research/run_polymarket_sharp_wallet_validate.py` gets a new `run_score_tercile()` (sharing horizon/p-value logic with the existing `run_bucket()` via an extracted helper) plus `main()` wiring for an independent BH-FDR pool. No new files, no new collectors, no live execution.

**Tech Stack:** Python 3.14, pandas, pytest (`asyncio_mode="auto"`, no `@pytest.mark.asyncio`).

## Global Constraints

- Research/validation pipeline only — no live signal exposure, no alerting, no execution. (spec §2)
- No new data collection — all 4 score components derive from fields the collector already stores. (spec §3)
- Normalization: percentile rank of each raw component within the anchor set of a single validation run, bounded to `[0, 100]` with the minimum raw value mapping to `0` and the maximum to `100` (formula: `(rank(method="average") - 1) / (n - 1) * 100`, `n = len(anchors)`). This is a plan-level refinement of the spec's `.rank(pct=True) * 100` shorthand — that formula does not actually bound at 0/100 for small n, which contradicts the spec's own test-plan example ("3개 anchor면 각각 0/50/100"); the bounded formula is what satisfies that example. (spec §3, §5)
- `score` = equal-weighted average of 4 percentile-normalized components: `wallet_count` (= `convergence_count`), `pnl_sum`, `notional`, `liquidity`. No weight tuning. (spec §3)
- `liquidity` component window = `[anchor.ts, anchor.ts + max(HORIZONS_S)]` on the same `condition_id`, summing `notional_usd` of ALL trades (anchor + context) in that window. `max(HORIZONS_S)` (currently `300`) is used in place of the spec's `MAX_HORIZON_S` name — that constant lives in the collector module, and per the original spec's module-independence convention (§6 of the 2026-07-20 spec) the hypothesis module never imports collector constants. (spec §3, §4.1)
- Fewer than 2 anchors in a run → `score` is `NaN` for all rows (percentile undefined). (spec §4.1)
- `build_labels_multi_horizon` must pass through `score` (default `NaN` when the anchors table lacks a `score` column) without breaking its existing bucket-only callers. (spec §4.1)
- `score_tercile` = `pd.qcut(labels["score"], 3, labels=["low","mid","high"])`, computed per validation run (data-adaptive, not fixed cutoffs). (spec §4.2)
- `run_score_tercile` reuses the same statistical machinery as `run_bucket` (`MIN_EVENTS=10`, `N_RUNS=500`, `SEED=42`, direction-shuffle random baseline, `empirical_p_value`) — must not duplicate that ~20-line block; extract a shared helper. (spec §4.2, writing-plans DRY)
- The score-tercile BH-FDR pool (`alpha=0.1`) is entirely separate from the existing bucket×horizon pool — never mix p-values across the two axes. (spec §4.2, project-wide convention)
- Existing `convergence_bucket` logic, `run_bucket`, and all 11 existing tests in `tests/test_polymarket_sharp_wallet.py` and 4 in `tests/test_run_polymarket_sharp_wallet_validate.py` must keep passing unmodified.

---

### Task 1: `build_convergence_score()` + `score` pass-through in `build_labels_multi_horizon`

**Files:**
- Modify: `research/hypotheses/polymarket_sharp_wallet.py` (append new function after `build_convergence_count`, at line 90; modify `build_labels_multi_horizon` at lines 109-149)
- Test: `tests/test_polymarket_sharp_wallet.py` (append new tests)

**Interfaces:**
- Consumes: `build_convergence_count(trades) -> pd.DataFrame` (existing, returns columns `ts, condition_id, side, direction, notional_usd, proxy_wallet, convergence_count, convergence_bucket`); `CONVERGENCE_WINDOW_S`, `HORIZONS_S` (existing module constants).
- Produces: `build_convergence_score(trades: pd.DataFrame, anchors: pd.DataFrame) -> pd.DataFrame` — returns `anchors` plus 4 new columns `pnl_sum_raw`, `notional_raw`, `liquidity_raw`, `score` (float, `NaN` when undefined). `build_labels_multi_horizon` output gains a `score` column (float, `NaN` if the input `anchors` has no `score` column). Task 2 consumes both.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_polymarket_sharp_wallet.py`:

```python
from research.hypotheses.polymarket_sharp_wallet import build_convergence_score


def test_build_convergence_score_bounded_percentiles_and_liquidity_window():
    anchors = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "side": "BUY", "direction": 1.0,
         "notional_usd": 50.0, "proxy_wallet": "w1", "convergence_count": 1,
         "convergence_bucket": 1},
        {"ts": 1000.0, "condition_id": "c2", "side": "BUY", "direction": 1.0,
         "notional_usd": 100.0, "proxy_wallet": "w2", "convergence_count": 1,
         "convergence_bucket": 1},
        {"ts": 2000.0, "condition_id": "c3", "side": "BUY", "direction": 1.0,
         "notional_usd": 200.0, "proxy_wallet": "w3", "convergence_count": 1,
         "convergence_bucket": 1},
    ])
    trades = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "proxy_wallet": "w1", "notional_usd": 50.0,
         "is_sharp_wallet": True, "wallet_pnl": 100.0},
        {"ts": 100.0, "condition_id": "c1", "proxy_wallet": "ctx1", "notional_usd": 50.0,
         "is_sharp_wallet": False, "wallet_pnl": None},
        {"ts": 301.0, "condition_id": "c1", "proxy_wallet": "ctx1b", "notional_usd": 999.0,
         "is_sharp_wallet": False, "wallet_pnl": None},  # 윈도우(0~300) 밖 — 제외돼야 함
        {"ts": 1000.0, "condition_id": "c2", "proxy_wallet": "w2", "notional_usd": 100.0,
         "is_sharp_wallet": True, "wallet_pnl": 500.0},
        {"ts": 1100.0, "condition_id": "c2", "proxy_wallet": "ctx2", "notional_usd": 100.0,
         "is_sharp_wallet": False, "wallet_pnl": None},
        {"ts": 2000.0, "condition_id": "c3", "proxy_wallet": "w3", "notional_usd": 200.0,
         "is_sharp_wallet": True, "wallet_pnl": 1000.0},
        {"ts": 2100.0, "condition_id": "c3", "proxy_wallet": "ctx3", "notional_usd": 200.0,
         "is_sharp_wallet": False, "wallet_pnl": None},
    ])
    out = build_convergence_score(trades, anchors)

    assert list(out["pnl_sum_raw"]) == [100.0, 500.0, 1000.0]
    assert list(out["liquidity_raw"]) == [100.0, 200.0, 400.0]  # 윈도우 밖 999는 제외

    scores = list(out["score"])
    # wallet_count는 3개 anchor 모두 convergence_count=1로 동석 -> percentile 50 고정.
    # pnl/notional/liquidity는 각각 단조증가 -> 0/50/100.
    assert scores[0] == pytest.approx((50.0 + 0.0 + 0.0 + 0.0) / 4)
    assert scores[1] == pytest.approx((50.0 + 50.0 + 50.0 + 50.0) / 4)
    assert scores[2] == pytest.approx((50.0 + 100.0 + 100.0 + 100.0) / 4)


def test_build_convergence_score_nan_when_fewer_than_two_anchors():
    anchors = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "side": "BUY", "direction": 1.0,
         "notional_usd": 50.0, "proxy_wallet": "w1", "convergence_count": 1,
         "convergence_bucket": 1},
    ])
    trades = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "proxy_wallet": "w1", "notional_usd": 50.0,
         "is_sharp_wallet": True, "wallet_pnl": 100.0},
    ])
    out = build_convergence_score(trades, anchors)
    assert pd.isna(out["score"].iloc[0])


def test_build_convergence_score_empty_anchors_returns_empty():
    trades = pd.DataFrame(columns=["ts", "condition_id", "proxy_wallet", "notional_usd",
                                    "is_sharp_wallet", "wallet_pnl"])
    anchors = pd.DataFrame(columns=["ts", "condition_id", "side", "direction",
                                     "notional_usd", "proxy_wallet", "convergence_count",
                                     "convergence_bucket"])
    out = build_convergence_score(trades, anchors)
    assert out.empty
    assert "score" in out.columns


def test_build_labels_multi_horizon_carries_score_when_present():
    price = pd.Series([0.5, 0.6], index=[0.0, 10.0])
    anchors = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "side": "BUY", "direction": 1.0,
         "notional_usd": 100.0, "proxy_wallet": "w1", "convergence_count": 1,
         "convergence_bucket": 1, "score": 87.5},
    ])
    labels = build_labels_multi_horizon(anchors, {"c1": price}, horizons=[10])
    assert labels.iloc[0]["score"] == pytest.approx(87.5)


def test_build_labels_multi_horizon_score_nan_when_anchors_lack_score_column():
    price = pd.Series([0.5, 0.6], index=[0.0, 10.0])
    anchors = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "side": "BUY", "direction": 1.0,
         "notional_usd": 100.0, "proxy_wallet": "w1", "convergence_count": 1,
         "convergence_bucket": 1},
    ])
    labels = build_labels_multi_horizon(anchors, {"c1": price}, horizons=[10])
    assert pd.isna(labels.iloc[0]["score"])
```

This file already has `import pandas as pd` and `import pytest` at the top (verify — if `pytest` isn't imported yet, add `import pytest` alongside the existing `import pandas as pd` line). Also add `build_convergence_score` to the existing `from research.hypotheses.polymarket_sharp_wallet import (...)` block instead of a separate import line, to match the file's existing import style.

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_sharp_wallet.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_convergence_score'`

- [ ] **Step 3: Implement `build_convergence_score` and the `score` pass-through**

In `research/hypotheses/polymarket_sharp_wallet.py`, insert after `build_convergence_count` (after line 89, before `build_price_series`):

```python
def _percentile_rank_0_100(values: pd.Series) -> pd.Series:
    """값들을 [0,100] 구간 percentile로 변환 — 최솟값=0, 최댓값=100(동석 있으면
    average rank). n<2면 정의 불가 — 전부 NaN."""
    n = len(values)
    if n < 2:
        return pd.Series([float("nan")] * n, index=values.index)
    ranks = values.rank(method="average")
    return (ranks - 1) / (n - 1) * 100.0


def build_convergence_score(trades: pd.DataFrame, anchors: pd.DataFrame) -> pd.DataFrame:
    """anchors(build_convergence_count 반환)에 4개 percentile 컴포넌트 평균인
    score 컬럼을 추가한다. 컴포넌트: wallet_count(convergence_count 재사용),
    pnl_sum(컨버전스 윈도우 내 distinct sharp wallet들의 wallet_pnl 합),
    notional(anchor 자체 notional_usd), liquidity(anchor.ts ~
    anchor.ts+max(HORIZONS_S) 구간 동일 condition_id의 모든 체결 notional_usd
    합). anchor 2건 미만이면 percentile 정의 불가 — score 전부 NaN. 반환 컬럼:
    입력 anchors 전체 + pnl_sum_raw, notional_raw, liquidity_raw, score."""
    out = anchors.copy()
    if out.empty:
        out["pnl_sum_raw"] = pd.Series(dtype=float)
        out["notional_raw"] = pd.Series(dtype=float)
        out["liquidity_raw"] = pd.Series(dtype=float)
        out["score"] = pd.Series(dtype=float)
        return out

    sharp = trades[trades["is_sharp_wallet"]]
    sharp_ts = sharp["ts"].to_numpy()
    sharp_wallets = sharp["proxy_wallet"].to_numpy()
    sharp_pnl = sharp["wallet_pnl"].to_numpy()
    liquidity_window_s = max(HORIZONS_S)

    pnl_sums = []
    liquidity_sums = []
    for _, row in out.iterrows():
        t = row["ts"]
        window_mask = (sharp_ts >= t - CONVERGENCE_WINDOW_S) & (sharp_ts <= t)
        seen: dict[str, float] = {}
        for w, p in zip(sharp_wallets[window_mask], sharp_pnl[window_mask]):
            seen[w] = p
        pnl_sums.append(sum(seen.values()))

        cid = row["condition_id"]
        liq_mask = ((trades["condition_id"] == cid) & (trades["ts"] >= t)
                    & (trades["ts"] <= t + liquidity_window_s))
        liquidity_sums.append(trades.loc[liq_mask, "notional_usd"].sum())

    out["pnl_sum_raw"] = pnl_sums
    out["notional_raw"] = out["notional_usd"].to_numpy()
    out["liquidity_raw"] = liquidity_sums

    if len(out) < 2:
        out["score"] = float("nan")
        return out

    wallet_count_pct = _percentile_rank_0_100(out["convergence_count"])
    pnl_sum_pct = _percentile_rank_0_100(out["pnl_sum_raw"])
    notional_pct = _percentile_rank_0_100(out["notional_raw"])
    liquidity_pct = _percentile_rank_0_100(out["liquidity_raw"])
    out["score"] = (wallet_count_pct.to_numpy() + pnl_sum_pct.to_numpy()
                     + notional_pct.to_numpy() + liquidity_pct.to_numpy()) / 4.0
    return out
```

Then modify `build_labels_multi_horizon` (existing lines 109-149) — add one line to the `records.append` dict and one to the returned-columns list:

```python
def build_labels_multi_horizon(
    anchors: pd.DataFrame,
    price_series_by_market: dict[str, pd.Series],
    horizons: list[int] = HORIZONS_S,
) -> pd.DataFrame:
    """anchor(build_convergence_count 결과, convergence_bucket 포함)마다 각 h in
    horizons에 대해 forward_return = (price[t+h]-price[t])/price[t] * direction
    (모멘텀 컨벤션). anchor ts는 해당 마켓 그리드의 가장 가까운 이전 포인트로
    스냅한다. t+h가 그리드에 없거나 NaN이면 그 행 제외. anchors에 score 컬럼이
    있으면 그대로 pass-through, 없으면 NaN."""
    has_score = "score" in anchors.columns
    records = []
    for _, row in anchors.iterrows():
        cid = row["condition_id"]
        price = price_series_by_market.get(cid)
        if price is None or price.empty:
            continue
        t = row["ts"]
        grid_before = [g for g in price.index if g <= t]
        if not grid_before:
            continue
        t_grid = grid_before[-1]
        entry_price = price.loc[t_grid]
        if pd.isna(entry_price):
            continue
        for h in horizons:
            exit_ts = t_grid + h
            if exit_ts not in price.index:
                continue
            exit_price = price.loc[exit_ts]
            if pd.isna(exit_price):
                continue
            forward_return = (exit_price - entry_price) / entry_price * row["direction"]
            records.append({
                "ts": t_grid, "condition_id": cid, "horizon_s": h,
                "entry_price": entry_price, "exit_price": exit_price,
                "direction": row["direction"], "forward_return": forward_return,
                "convergence_bucket": row["convergence_bucket"],
                "score": row["score"] if has_score else float("nan"),
            })
    return pd.DataFrame(records, columns=[
        "ts", "condition_id", "horizon_s", "entry_price", "exit_price",
        "direction", "forward_return", "convergence_bucket", "score",
    ])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_sharp_wallet.py -q`
Expected: all tests pass (11 existing + 5 new = 16 passed)

- [ ] **Step 5: Commit**

```bash
git add research/hypotheses/polymarket_sharp_wallet.py tests/test_polymarket_sharp_wallet.py
git commit -m "feat: add convergence score (percentile-based confidence) to sharp-wallet hypothesis module"
```

---

### Task 2: `run_score_tercile()` + `main()` wiring in the validation runner

**Files:**
- Modify: `research/run_polymarket_sharp_wallet_validate.py` (extract shared helper from `run_bucket` at lines 51-82; add `SCORE_TERCILES`, `add_score_tercile`, `run_score_tercile`; rewrite `main()` at lines 85-133)
- Test: `tests/test_run_polymarket_sharp_wallet_validate.py` (append new tests)

**Interfaces:**
- Consumes: `build_convergence_score(trades, anchors) -> pd.DataFrame` and the `score`-carrying `build_labels_multi_horizon` from Task 1; existing `MIN_EVENTS`, `N_RUNS`, `SEED`, `TRADE_SIZE`, `COST_BPS`, `CONVERGENCE_BUCKETS`, `empirical_p_value`, `trade_metrics`, `benjamini_hochberg` (all pre-existing, unchanged).
- Produces: `SCORE_TERCILES = ["low", "mid", "high"]`; `add_score_tercile(labels: pd.DataFrame) -> pd.DataFrame` (adds `score_tercile` column, values in `SCORE_TERCILES` or `None`); `run_score_tercile(tercile: str, labels: pd.DataFrame) -> dict` (same shape as `run_bucket`'s return but keyed `"tercile"` instead of `"bucket"`). `main()` prints both the bucket report and a `=== score tercile ===` section with its own BH-FDR pool.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_run_polymarket_sharp_wallet_validate.py`:

```python
def test_add_score_tercile_splits_into_three_groups():
    rows = [{"ts": float(i), "condition_id": "c1", "horizon_s": 30, "entry_price": 0.5,
             "exit_price": 0.5, "direction": 1.0, "forward_return": 0.0,
             "convergence_bucket": 1, "score": float(i * 10)} for i in range(9)]
    labels = pd.DataFrame(rows)
    out = val.add_score_tercile(labels)
    assert set(out["score_tercile"].astype(str)) == {"low", "mid", "high"}
    assert out["score_tercile"].value_counts()["low"] == 3


def test_add_score_tercile_none_when_all_scores_nan():
    rows = [{"ts": 0.0, "condition_id": "c1", "horizon_s": 30, "entry_price": 0.5,
             "exit_price": 0.5, "direction": 1.0, "forward_return": 0.0,
             "convergence_bucket": 1, "score": float("nan")}]
    labels = pd.DataFrame(rows)
    out = val.add_score_tercile(labels)
    assert out["score_tercile"].iloc[0] is None


def test_run_score_tercile_blocked_when_no_labels():
    labels = pd.DataFrame(columns=["ts", "condition_id", "horizon_s", "entry_price",
                                    "exit_price", "direction", "forward_return",
                                    "convergence_bucket", "score", "score_tercile"])
    result = val.run_score_tercile("high", labels)
    assert result["blocked"] is True
    assert result["tercile"] == "high"


def test_run_score_tercile_blocked_when_below_min_events():
    rows = [{"ts": float(i), "condition_id": "c1", "horizon_s": 30, "entry_price": 0.5,
             "exit_price": 0.5, "direction": 1.0, "forward_return": 0.0,
             "convergence_bucket": 1, "score": 80.0, "score_tercile": "high"} for i in range(5)]
    labels = pd.DataFrame(rows)
    result = val.run_score_tercile("high", labels)
    assert result["blocked"] is True


def test_run_score_tercile_computes_pvalue_when_enough_events():
    rows = [{"ts": float(i), "condition_id": "c1", "horizon_s": 30, "entry_price": 0.5,
             "exit_price": 0.55, "direction": 1.0, "forward_return": 0.1,
             "convergence_bucket": 2, "score": 80.0, "score_tercile": "high"} for i in range(15)]
    labels = pd.DataFrame(rows)
    result = val.run_score_tercile("high", labels)
    assert result["blocked"] is False
    assert "30s" in result["horizons"]
    assert result["horizons"]["30s"]["n_events"] == 15
    assert result["horizons"]["30s"]["random"]["p_value"] is not None
```

Do not duplicate `test_main_handles_no_data_dir_without_crash` — the existing one (unchanged) is the regression check that `main()` still runs cleanly end-to-end after the rewrite.

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_sharp_wallet_validate.py -q`
Expected: FAIL — `AttributeError: module 'research.run_polymarket_sharp_wallet_validate' has no attribute 'add_score_tercile'`

- [ ] **Step 3: Implement — extract shared helper, add score-tercile functions, rewrite `main()`**

Replace the whole file `research/run_polymarket_sharp_wallet_validate.py` with:

```python
"""Polymarket 샤프월렛 컨버전스 가설 검증 러너 — 통계적 유의미성 스크리닝, 실집행 없음.

`research/run_polymarket_sharp_wallet_collect.py`가 쌓은 체결 원장
(research/data/polymarket_sharp_wallet/)을 읽어 컨버전스 버킷(1/2/3) x
다중호라이즌(30s/120s/300s) forward return을 계산하고,
`research/run_polymarket_whale_validate.py`와 동일하게 랜덤 베이스라인(방향
무작위 셔플) 대비 empirical p-value를 구한다. 최대 9개 p-value를 신규 독립
BH-FDR 풀로 correction한다.

2026-07-21: 버킷과 나란히 score tercile(연속 confidence score의 3분위) 검증도
추가 — `docs/superpowers/specs/2026-07-21-polymarket-sharp-wallet-scoring-design.md`.
score tercile은 버킷과 완전히 분리된 신규 BH-FDR 풀로 correction한다(다른
가설/축 p-value를 섞지 않는 프로젝트 전역 컨벤션).

⚠️ 스크리닝 스크립트. 결과는 통계적 유의미성 확인일 뿐 실집행 근거 아님.
walk-forward는 생략(신규 라이브 수집 직후라 표본기간 미달 — BH-FDR 통과 시
전체 파이프라인 승격 검토).
"""
from __future__ import annotations

import glob
import random as _random
import re

import pandas as pd

from research.hypotheses.polymarket_sharp_wallet import (
    build_convergence_count,
    build_convergence_score,
    build_labels_multi_horizon,
    build_price_series,
    load_sharp_wallet_trades,
)
from research.validation.baselines import empirical_p_value
from research.validation.cost_model import polymarket_effective_cost_bps
from research.validation.metrics import trade_metrics
from research.validation.multiple_testing import benjamini_hochberg

DATA_DIR = "research/data/polymarket_sharp_wallet"
CONVERGENCE_BUCKETS = [1, 2, 3]
SCORE_TERCILES = ["low", "mid", "high"]
TRADE_SIZE = 1.0
N_RUNS = 500
SEED = 42
COST_BPS = polymarket_effective_cost_bps()
MIN_EVENTS = 10


def _available_dates() -> list[str]:
    dates = set()
    for path in glob.glob(f"{DATA_DIR}/*.jsonl"):
        m = re.search(r"(\d{4}-\d{2}-\d{2})\.jsonl$", path)
        if m:
            dates.add(m.group(1))
    return sorted(dates)


def _score_horizons(group_labels: pd.DataFrame) -> dict[str, dict]:
    """group_labels(이미 버킷/티어사일로 필터링됨)의 horizon별 랜덤베이스라인
    p-value 계산 — run_bucket과 run_score_tercile이 공유하는 핵심 로직."""
    rng = _random.Random(SEED)
    horizons: dict[str, dict] = {}
    for h in sorted(group_labels["horizon_s"].unique()):
        sub = group_labels[group_labels["horizon_s"] == h]
        precomputed = []
        for _, row in sub.iterrows():
            entry_px, exit_px = row["entry_price"], row["exit_price"]
            cost = (abs(entry_px) + abs(exit_px)) * TRADE_SIZE * COST_BPS / 10_000.0
            precomputed.append((row["direction"], entry_px, exit_px, cost))

        actual_pnls = [d * (ex - en) * TRADE_SIZE - c for d, en, ex, c in precomputed]
        strat = trade_metrics([{"pnl": pnl} for pnl in actual_pnls])

        random_totals = []
        for _ in range(N_RUNS):
            total = 0.0
            for _d, en, ex, c in precomputed:
                rsign = rng.choice((1.0, -1.0))
                total += rsign * (ex - en) * TRADE_SIZE - c
            random_totals.append(round(total, 6))
        pval = empirical_p_value(strat["total_pnl"], random_totals)
        horizons[f"{int(h)}s"] = {"strategy": strat, "random": pval, "n_events": len(sub)}
    return horizons


def run_bucket(bucket: int, labels: pd.DataFrame) -> dict:
    bucket_labels = labels[labels["convergence_bucket"] == bucket]
    if bucket_labels.empty:
        return {"bucket": bucket, "blocked": True, "reason": "라벨 없음"}
    if len(bucket_labels) < MIN_EVENTS:
        return {"bucket": bucket, "blocked": True,
                "reason": f"라벨 {len(bucket_labels)}건뿐 — 최소 표본 미달"}
    return {"bucket": bucket, "blocked": False, "horizons": _score_horizons(bucket_labels)}


def add_score_tercile(labels: pd.DataFrame) -> pd.DataFrame:
    """labels(score 컬럼 포함)에 score_tercile("low"/"mid"/"high") 컬럼 추가.
    score가 전부 NaN이거나 고유값이 3개 미만이면(qcut으로 3등분 불가) 전부
    None으로 채운다 — run_score_tercile이 표본부족으로 BLOCKED 처리."""
    out = labels.copy()
    scores = out["score"]
    if scores.isna().all() or scores.nunique() < 3:
        out["score_tercile"] = None
        return out
    try:
        out["score_tercile"] = pd.qcut(scores, 3, labels=SCORE_TERCILES)
    except ValueError:
        out["score_tercile"] = None
    return out


def run_score_tercile(tercile: str, labels: pd.DataFrame) -> dict:
    tercile_labels = labels[labels["score_tercile"] == tercile]
    if tercile_labels.empty:
        return {"tercile": tercile, "blocked": True, "reason": "라벨 없음"}
    if len(tercile_labels) < MIN_EVENTS:
        return {"tercile": tercile, "blocked": True,
                "reason": f"라벨 {len(tercile_labels)}건뿐 — 최소 표본 미달"}
    return {"tercile": tercile, "blocked": False, "horizons": _score_horizons(tercile_labels)}


def main() -> None:
    dates = _available_dates()
    trades = load_sharp_wallet_trades(dates) if dates else pd.DataFrame(columns=[
        "ts", "condition_id", "side", "price", "size", "proxy_wallet",
        "notional_usd", "is_sharp_wallet", "wallet_rank", "wallet_pnl",
    ])

    anchors = build_convergence_count(trades)
    if anchors.empty:
        labels = pd.DataFrame(columns=[
            "ts", "condition_id", "horizon_s", "entry_price", "exit_price",
            "direction", "forward_return", "convergence_bucket", "score",
        ])
    else:
        anchors = build_convergence_score(trades, anchors)
        price_by_condition = {
            cid: build_price_series(trades, cid) for cid in anchors["condition_id"].unique()
        }
        labels = build_labels_multi_horizon(anchors, price_by_condition)
    labels = add_score_tercile(labels)

    results = []
    pvals: list[float] = []
    pval_keys: list[str] = []
    for bucket in CONVERGENCE_BUCKETS:
        r = run_bucket(bucket, labels)
        results.append(r)
        if not r["blocked"]:
            for h_key, h_res in r["horizons"].items():
                pvals.append(h_res["random"]["p_value"])
                pval_keys.append(f"bucket{bucket}:{h_key}")

    score_results = []
    score_pvals: list[float] = []
    score_pval_keys: list[str] = []
    for tercile in SCORE_TERCILES:
        r = run_score_tercile(tercile, labels)
        score_results.append(r)
        if not r["blocked"]:
            for h_key, h_res in r["horizons"].items():
                score_pvals.append(h_res["random"]["p_value"])
                score_pval_keys.append(f"{tercile}:{h_key}")

    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {
        "survivors": [], "n_survivors": 0, "threshold": None, "alpha": 0.1,
    }
    bh["keys"] = pval_keys

    score_bh = benjamini_hochberg(score_pvals, alpha=0.1) if score_pvals else {
        "survivors": [], "n_survivors": 0, "threshold": None, "alpha": 0.1,
    }
    score_bh["keys"] = score_pval_keys

    print(f"\n=== cost_bps(polymarket) = {COST_BPS} ===\n")
    for r in results:
        if r["blocked"]:
            print(f"bucket{r['bucket']} -> BLOCKED ({r['reason']})")
            continue
        for h_key, h_res in r["horizons"].items():
            s, p = h_res["strategy"], h_res["random"]
            print(f"bucket{r['bucket']}:{h_key} n_events={h_res['n_events']} "
                  f"total_pnl={s['total_pnl']} p_value={p['p_value']} percentile={p['percentile']}")

    print("\n=== BH-FDR (신규 Polymarket sharp-wallet 풀, alpha=0.1) ===")
    print(f"survivors: {[k for k, s in zip(bh['keys'], bh['survivors']) if s]}")
    print(f"n_survivors: {bh['n_survivors']} / {len(pvals)}")

    print("\n=== score tercile ===\n")
    for r in score_results:
        if r["blocked"]:
            print(f"{r['tercile']} -> BLOCKED ({r['reason']})")
            continue
        for h_key, h_res in r["horizons"].items():
            s, p = h_res["strategy"], h_res["random"]
            print(f"{r['tercile']}:{h_key} n_events={h_res['n_events']} "
                  f"total_pnl={s['total_pnl']} p_value={p['p_value']} percentile={p['percentile']}")

    print("\n=== BH-FDR (score tercile 풀, alpha=0.1, 버킷 풀과 분리) ===")
    print(f"survivors: {[k for k, s in zip(score_bh['keys'], score_bh['survivors']) if s]}")
    print(f"n_survivors: {score_bh['n_survivors']} / {len(score_pvals)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_sharp_wallet_validate.py tests/test_polymarket_sharp_wallet.py -q`
Expected: all pass (existing 4 + new 5 in validate test file = 9 passed; Task 1's 16 still passed — confirms the `run_bucket` extraction didn't regress its 3 existing tests, and `main()`'s rewrite didn't break `test_main_handles_no_data_dir_without_crash`)

- [ ] **Step 5: Commit**

```bash
git add research/run_polymarket_sharp_wallet_validate.py tests/test_run_polymarket_sharp_wallet_validate.py
git commit -m "feat: add score-tercile BH-FDR validation alongside existing convergence-bucket screening"
```

---

## Self-Review Notes

**Spec coverage:** §3 formula → Task 1 (`build_convergence_score`, `_percentile_rank_0_100`). §4.1 anchor pass-through → Task 1 (`build_labels_multi_horizon` diff). §4.2 `run_score_tercile`, qcut tercile, separate BH-FDR pool, `=== score tercile ===` output → Task 2. §5 test plan (raw-value accuracy, percentile normalization, NaN at ≤1 anchor, liquidity boundary exclusion, `run_score_tercile` MIN_EVENTS/tercile-split/pool-separation) → covered by Task 1 and Task 2 test steps. §6 out-of-scope items (live alerting, orderbook depth, wallet clustering, weight tuning) → nothing in either task touches these.

**Placeholder scan:** No TBD/TODO. Every step has complete, runnable code — no "similar to Task N" references.

**Type consistency:** `build_convergence_score(trades: pd.DataFrame, anchors: pd.DataFrame) -> pd.DataFrame` (Task 1) matches the call site in Task 2's `main()`. `run_score_tercile(tercile: str, labels: pd.DataFrame) -> dict` mirrors `run_bucket(bucket: int, labels: pd.DataFrame) -> dict`'s shape exactly (`blocked`, `reason`/`horizons` keys) except the identifying key name (`tercile` vs `bucket`), consistent with spec §4.2's "동일 구조" requirement. `score` column name is identical across `build_convergence_score`, `build_labels_multi_horizon`, and `add_score_tercile` — no drift.
