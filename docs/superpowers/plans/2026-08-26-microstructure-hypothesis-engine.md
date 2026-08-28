# Microstructure Hypothesis Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `research/autoresearch/engines_microstructure.py` as `collect_candidates()`'s 3rd source — 4 pre-registered crypto microstructure hypotheses (OFI momentum, basis reversion, absorption momentum, skew divergence momentum) feeding the existing BH-FDR + redteam batch pipeline. Paper-tracking only, no live capital.

**Architecture:** One new module mirroring `engines_factor.py`'s pattern (pre-registered config + row-evidence functions + `*_candidates()` assembly). Two sources are new code (OFI, basis) computing daily `(sign, outcome)` series with a fixed-sign/shuffled-outcome permutation test. Two sources are thin adapters over existing frozen dormant modules (`research/strategies/orderflow_absorption.py`, `research/hypotheses/cross_venue_skew.py`) reusing their own random-baseline p-values, adding only walk-forward split. A shared `_assemble_evidence()` builds the batch-consumer evidence dict all 4 sources funnel through.

**Tech Stack:** Python 3.14, pytest (`asyncio_mode="auto"` — no `@pytest.mark.asyncio` needed, none of this code is async), pandas (via `cross_venue_skew.py` reuse only).

**Spec:** `docs/superpowers/specs/2026-08-26-microstructure-hypothesis-engine-design.md` (includes committed Addendum — 4-source scope, `net_stress`-equivalent evidence contract, wf_first/wf_second methodology, symbol/combination pre-registration). Read both together; this plan argues from that spec.

## Global Constraints

- No live capital. Every source is `direction="research"` (paper-tracking `Candidate`, same as KR factor sources) — never wired to `jarvis/execution/edge_providers.py` or `jarvis/paper/deploy.py` in this plan.
- No new data collectors. Only read `research/data/hl_orderflow_tick/` and `research/data/cross_venue_skew/` (already-running tmux collectors).
- No modification of dormant modules: `research/strategies/orderflow_absorption.py`, `research/hypotheses/cross_venue_skew.py`, `research/run_cross_venue_skew_validate.py` are read-only reuse — their own docstrings forbid tuning.
- No modification of `research/autoresearch/engines_factor.py` or `research/scanner/families.py`.
- Cost model (fixed, pre-registered): `COST_BASE_BPS = 10.0`, `COST_STRESS_BPS = 20.0` for OFI/basis (new-code sources). Absorption/skew adapters use `research.validation.cost_model.hl_effective_cost_bps("major", taker=True)` for base cost and `× _STRESS_MULT = 2.0` for stress — matches each dormant module's own convention, do not substitute the flat 10/20bps there.
- Sample-size honesty: `_MIN_DAYS = 30` for daily-bucket sources (OFI/basis), `_MIN_EVENTS = 10` for event-bucket sources (absorption/skew) — matches each dormant module's own existing `< 10` gate. Below threshold → `run()` returns `None` (engine.py's `run_batch()` already treats `None` as `UNDERPOWERED`), never force a result.
- Direction: all 4 sources register exactly ONE economic direction (momentum for OFI/absorption/skew, reversion for basis) — never register the opposite direction too.
- Evidence-dict pass conditions are **unidirectional** (`net > 0 and wf1 > 0 and wf2 > 0`), NOT the bidirectional OR-pattern `engines_factor.py` uses for KR factor's direction-agnostic quintile test — that pattern doesn't apply here since each source pre-registers one direction.
- `_spec` contract (verbatim from spec Addendum): `{"market": "CRYPTO", "family": "microstructure", "n_variants": <actual total candidate count, computed at runtime — not a hardcoded cap>}`.
- `evidence["survivorship"] = "na"` (BTC/ETH/PAXG always-listed majors, no delisting risk; `review_strategy()` treats `"na"` same as `"passed"`). `evidence["multiple_testing"] = "passed"` (batch BH-FDR applies regardless of source). `evidence["lookahead"] = "passed"` (all 4 sources are causally computed — daily sources use only same-day-or-earlier data per pair, adapters reuse each dormant module's own causal bar/signal construction).
- Symbol/combination pre-registration (locked, do not change after implementation): OFI momentum → BTC, ETH, PAXG. Basis reversion → BTC/ETH × (binance,okx)/(binance,hl)/(okx,hl), top 4 by actual overlapping-date count ≥ `_MIN_DAYS`, selected by data availability not performance. Absorption momentum → BTC, ETH, PAXG. Skew divergence momentum → BTC, ETH × single horizon = 15s.
- File-naming convention confirmed from real data directories: orderflow files are `{SYMBOL}_{YYYY-MM-DD}.jsonl[.gz]` under `research/data/hl_orderflow_tick/`; skew files are `{venue}_{coin}_{YYYY-MM-DD}.jsonl[.gz]` under `research/data/cross_venue_skew/`.

---

## Task 1: Shared evidence-assembly harness

**Files:**
- Create: `research/autoresearch/engines_microstructure.py`
- Test: `tests/test_engines_microstructure.py`

**Interfaces:**
- Consumes: `research.validation.baselines.empirical_p_value(strategy_stat: float, random_stats: list[float]) -> dict` (returns `{"p_value", "percentile", "n_random", "random_beating", "random_median"}`).
- Produces (for all later tasks): `_assemble_evidence(net, median, wf1, wf2, pv, net_stress, n, n_variants) -> dict`, `_series_evidence(signs: list[float], outcomes: list[float], cost_bps: float, stress_bps: float, n_variants: int, seed: int = _SEED, n_runs: int = _N_PERMS) -> dict | None`, `_event_pnl_evidence(pnls: list[float], net_stress: float, pv: dict, n_variants: int) -> dict`. Module constants: `_MIN_DAYS = 30`, `_MIN_EVENTS = 10`, `_N_PERMS = 500`, `_SEED = 42`, `COST_BASE_BPS = 10.0`, `COST_STRESS_BPS = 20.0`, `_STRESS_MULT = 2.0`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_engines_microstructure.py
from research.autoresearch import engines_microstructure as em


def test_assemble_evidence_contract_shape():
    pv = {"p_value": 0.002, "percentile": 99.8, "n_random": 500, "random_beating": 1, "random_median": -0.0001}
    ev = em._assemble_evidence(net=0.001, median=0.0009, wf1=0.0011, wf2=0.0009,
                                pv=pv, net_stress=0.0005, n=40, n_variants=10)
    assert ev["n"] == 40
    assert ev["net"] == 0.001
    assert ev["net_stress"] == 0.0005
    assert ev["percentile"] == 99.8
    assert ev["p"] == 0.002
    assert ev["wf_first"] == 0.0011
    assert ev["wf_second"] == 0.0009
    assert ev["top_tail_share"] is None
    assert ev["_spec"] == {"market": "CRYPTO", "family": "microstructure", "n_variants": 10}
    assert ev["evidence"]["random_baseline"] == "passed"
    assert ev["evidence"]["walk_forward"] == "passed"
    assert ev["evidence"]["cost_stress"] == "passed"
    assert ev["evidence"]["survivorship"] == "na"
    assert ev["evidence"]["multiple_testing"] == "passed"
    assert ev["evidence"]["lookahead"] == "passed"


def test_assemble_evidence_fails_when_wf_second_negative():
    pv = {"p_value": 0.002, "percentile": 99.8, "n_random": 500, "random_beating": 1, "random_median": -0.0001}
    ev = em._assemble_evidence(net=0.001, median=0.0009, wf1=0.0011, wf2=-0.0002,
                                pv=pv, net_stress=0.0005, n=40, n_variants=10)
    assert ev["evidence"]["walk_forward"] == "failed"


def test_assemble_evidence_fails_when_stress_flips_negative():
    pv = {"p_value": 0.002, "percentile": 99.8, "n_random": 500, "random_beating": 1, "random_median": -0.0001}
    ev = em._assemble_evidence(net=0.001, median=0.0009, wf1=0.0011, wf2=0.0009,
                                pv=pv, net_stress=-0.0001, n=40, n_variants=10)
    assert ev["evidence"]["cost_stress"] == "failed"


def test_series_evidence_none_below_min_days():
    signs = [1.0] * 10
    outcomes = [0.01] * 10
    assert em._series_evidence(signs, outcomes, em.COST_BASE_BPS, em.COST_STRESS_BPS, n_variants=4) is None


def test_series_evidence_strong_signal_scores_high_percentile():
    # signs alternate, outcomes perfectly track sign*const -> near-unbeatable vs shuffled-outcome permutations
    n = 40
    signs = [1.0 if i % 2 == 0 else -1.0 for i in range(n)]
    outcomes = [0.02 if s > 0 else -0.02 for s in signs]
    ev = em._series_evidence(signs, outcomes, em.COST_BASE_BPS, em.COST_STRESS_BPS, n_variants=4)
    assert ev is not None
    assert ev["n"] == n
    assert ev["net"] > 0
    assert ev["percentile"] == 100.0
    assert ev["evidence"]["random_baseline"] == "passed"
    assert ev["evidence"]["walk_forward"] == "passed"


def test_event_pnl_evidence_splits_chronologically():
    pnls = [1.0] * 10 + [2.0] * 10  # first half mean 1.0, second half mean 2.0
    pv = {"p_value": 0.01, "percentile": 99.0, "n_random": 500, "random_beating": 5, "random_median": 0.1}
    ev = em._event_pnl_evidence(pnls, net_stress=0.5, pv=pv, n_variants=4)
    assert ev["n"] == 20
    assert ev["wf_first"] == 1.0
    assert ev["wf_second"] == 2.0
    assert ev["net"] == 1.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_engines_microstructure.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.autoresearch.engines_microstructure'`

- [ ] **Step 3: Write the module skeleton + harness**

```python
# research/autoresearch/engines_microstructure.py
"""HL orderflow/cross-venue-skew 가설 엔진 — collect_candidates() 3번째 소스.

사전등록 4소스(등록 후 변경 금지, 근거:
docs/superpowers/specs/2026-08-26-microstructure-hypothesis-engine-design.md):
  1. ofi_momentum              — 일별 OFI 부호 -> 익일 수익률 (신규)
  2. basis_reversion           — 거래소간 일별 basis 수렴 베팅 (신규)
  3. absorption_momentum       — research/strategies/orderflow_absorption.py 어댑터
  4. skew_divergence_momentum  — research/hypotheses/cross_venue_skew.py 어댑터

engines_factor.py와 동일 패턴(사전등록 config + 결과행 함수 + candidates() 조립함수).
paper-tracking 전용, live capital 없음.
"""
from __future__ import annotations

import datetime as dt
import json
import random as _random
import statistics as _st
from pathlib import Path

from research import jsonl_dates
from research.validation.baselines import empirical_p_value

_ORDERFLOW_DIR = Path("research/data/hl_orderflow_tick")
_SKEW_DIR = Path("research/data/cross_venue_skew")

_MIN_DAYS = 30
_MIN_EVENTS = 10
_N_PERMS = 500
_SEED = 42

COST_BASE_BPS = 10.0
COST_STRESS_BPS = 20.0
_STRESS_MULT = 2.0

OFI_SYMBOLS = ["BTC", "ETH", "PAXG"]
BASIS_COINS = ["BTC", "ETH"]
BASIS_VENUE_PAIRS = [("binance", "okx"), ("binance", "hl"), ("okx", "hl")]
MAX_BASIS_CANDIDATES = 4
ABSORPTION_SYMBOLS = ["BTC", "ETH", "PAXG"]
SKEW_COINS = ["BTC", "ETH"]
SKEW_HORIZON_S = 15
SKEW_VENUES = ["hl", "binance", "okx"]


def _assemble_evidence(net, median, wf1, wf2, pv, net_stress, n, n_variants) -> dict:
    """net/median/wf1/wf2 + empirical_p_value(pv) -> 배치 컨슈머 계약 evidence dict
    (engine.py::run_batch, verdict.py::classify, redteam/review.py::review_strategy 계약).
    단방향 통과조건(net>0 and wf1>0 and wf2>0) — 각 소스가 방향 1개만 사전등록하므로
    engines_factor.py KR팩터의 양방향 OR 패턴은 적용 안 함."""
    rnd_pass = pv["percentile"] is not None and pv["percentile"] >= 95 and net > 0
    wf_pass = net > 0 and wf1 > 0 and wf2 > 0
    cost_pass = net > 0 and net_stress > 0
    return {
        "n": n, "net": round(net, 6), "median": round(median, 6),
        "percentile": pv["percentile"], "p": pv["p_value"],
        "net_stress": round(net_stress, 6),
        "wf_first": round(wf1, 6), "wf_second": round(wf2, 6),
        "top_tail_share": None,
        "_spec": {"market": "CRYPTO", "family": "microstructure", "n_variants": n_variants},
        "evidence": {
            "random_baseline": "passed" if rnd_pass else "failed",
            "walk_forward": "passed" if wf_pass else "failed",
            "cost_stress": "passed" if cost_pass else "failed",
            "survivorship": "na",
            "multiple_testing": "passed",
            "lookahead": "passed",
        },
    }


def _series_evidence(signs, outcomes, cost_bps, stress_bps, n_variants,
                      seed=_SEED, n_runs=_N_PERMS):
    """일별 (sign,outcome) 페어 -> ls=sign*outcome 시리즈 -> net/median/wf/순열p.
    순열: outcome만 셔플(sign 고정) — 신호·결과 연결을 끊는 올바른 순열귀무
    (ls=sign*outcome 자체를 셔플하면 평균 불변이라 무의미해짐 — 별도 배열 유지 필수)."""
    n = len(signs)
    if n < _MIN_DAYS:
        return None
    cost = cost_bps / 10_000.0
    stress_cost = stress_bps / 10_000.0
    ls = [s * o for s, o in zip(signs, outcomes)]
    gross = _st.mean(ls)
    net = gross - cost
    net_stress = gross - stress_cost
    med = _st.median(ls) - cost
    half = n // 2
    wf1 = _st.mean(ls[:half]) - cost
    wf2 = _st.mean(ls[half:]) - cost

    rng = _random.Random(seed)
    perm = []
    for _ in range(n_runs):
        shuffled = outcomes[:]
        rng.shuffle(shuffled)
        perm_ls = [s * o for s, o in zip(signs, shuffled)]
        perm.append(_st.mean(perm_ls) - cost)
    pv = empirical_p_value(round(net, 6), perm)
    return _assemble_evidence(net, med, wf1, wf2, pv, net_stress, n, n_variants)


def _event_pnl_evidence(pnls, net_stress, pv, n_variants):
    """체결(trade/event)순 pnl 리스트 -> net/median/wf. p/percentile은 소스 자체
    random baseline 그대로 재사용(중복 순열 안 돌림) — absorption/skew 어댑터 전용."""
    n = len(pnls)
    net = _st.mean(pnls)
    med = _st.median(pnls)
    half = n // 2
    wf1 = _st.mean(pnls[:half])
    wf2 = _st.mean(pnls[half:])
    return _assemble_evidence(net, med, wf1, wf2, pv, net_stress, n, n_variants)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_engines_microstructure.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add research/autoresearch/engines_microstructure.py tests/test_engines_microstructure.py
git commit -m "feat: microstructure engine harness — shared evidence assembly"
```

---

## Task 2: OFI momentum source

**Files:**
- Modify: `research/autoresearch/engines_microstructure.py` (append)
- Test: `tests/test_engines_microstructure.py` (append)

**Interfaces:**
- Consumes: Task 1's `_series_evidence`, `COST_BASE_BPS`, `COST_STRESS_BPS`, `_ORDERFLOW_DIR`, `OFI_SYMBOLS`. `research.jsonl_dates.list_dates(dirpath: Path, glob_prefix: str = "") -> list[str]`, `research.jsonl_dates.open_stem(dirpath: Path, stem: str)` (returns open text-mode file handle or `None`).
- Produces: `_daily_ofi_and_price(symbol: str) -> tuple[dict[str, float], dict[str, float]]`, `_ofi_signs_outcomes(symbol: str) -> tuple[list[float], list[float]]`, `_ofi_candidate(symbol: str, n_variants: int) -> Candidate` (consumed by Task 6's `microstructure_candidates()`).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_engines_microstructure.py
import gzip
import json as _json

import pytest


def _write_orderflow_day(dirpath, symbol, date, rows):
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / f"{symbol}_{date}.jsonl"
    with path.open("w") as f:
        for r in rows:
            f.write(_json.dumps(r) + "\n")


def test_daily_ofi_and_price_aggregates_signed_size(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_ORDERFLOW_DIR", tmp_path)
    _write_orderflow_day(tmp_path, "BTC", "2026-07-10", [
        {"ts": 1.0, "side": "buy", "size": 10.0, "price": 100.0},
        {"ts": 2.0, "side": "sell", "size": 4.0, "price": 101.0},
        {"ts": 3.0, "side": "buy", "size": 1.0, "price": 102.0},
    ])
    ofi, price = em._daily_ofi_and_price("BTC")
    assert ofi["2026-07-10"] == pytest.approx(7.0)
    assert price["2026-07-10"] == 102.0


def test_ofi_signs_outcomes_next_day_pairing(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_ORDERFLOW_DIR", tmp_path)
    _write_orderflow_day(tmp_path, "BTC", "2026-07-10", [
        {"ts": 1.0, "side": "buy", "size": 10.0, "price": 100.0},
    ])
    _write_orderflow_day(tmp_path, "BTC", "2026-07-11", [
        {"ts": 1.0, "side": "sell", "size": 5.0, "price": 110.0},
    ])
    signs, outcomes = em._ofi_signs_outcomes("BTC")
    assert signs == [1.0]
    assert outcomes == [pytest.approx(0.10)]


def test_ofi_candidate_run_returns_none_with_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_ORDERFLOW_DIR", tmp_path)
    cand = em._ofi_candidate("BTC", n_variants=4)
    assert cand.cid == "micro_ofi_momentum_BTC"
    assert cand.category == "microstructure"
    assert cand.direction == "research"
    assert cand.run() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_engines_microstructure.py -v -k ofi`
Expected: FAIL — `AttributeError: module ... has no attribute '_daily_ofi_and_price'`

- [ ] **Step 3: Implement**

```python
# append to research/autoresearch/engines_microstructure.py

def _daily_ofi_and_price(symbol: str) -> tuple[dict, dict]:
    """hl_orderflow_tick/{symbol}_*.jsonl(.gz) -> (날짜->OFI합, 날짜->그날 마지막 체결가)."""
    dates = jsonl_dates.list_dates(_ORDERFLOW_DIR, glob_prefix=f"{symbol}_")
    ofi: dict[str, float] = {}
    last_px: dict[str, float] = {}
    last_ts: dict[str, float] = {}
    for date in dates:
        f = jsonl_dates.open_stem(_ORDERFLOW_DIR, f"{symbol}_{date}")
        if f is None:
            continue
        with f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                sign = 1.0 if row["side"] == "buy" else -1.0
                ofi[date] = ofi.get(date, 0.0) + sign * row["size"]
                if date not in last_ts or row["ts"] > last_ts[date]:
                    last_ts[date] = row["ts"]
                    last_px[date] = row["price"]
    return ofi, last_px


def _ofi_signs_outcomes(symbol: str) -> tuple[list, list]:
    """정렬된 날짜 인접쌍 -> (그날 OFI 부호, 익일 수익률). OFI=0인 날/비양수가는 skip."""
    ofi, price = _daily_ofi_and_price(symbol)
    dates = sorted(d for d in ofi if d in price)
    signs, outcomes = [], []
    for i in range(len(dates) - 1):
        d, d_next = dates[i], dates[i + 1]
        s = ofi[d]
        if s == 0.0:
            continue
        p0, p1 = price[d], price[d_next]
        if p0 <= 0:
            continue
        signs.append(1.0 if s > 0 else -1.0)
        outcomes.append(p1 / p0 - 1.0)
    return signs, outcomes


def _ofi_candidate(symbol: str, n_variants: int):
    from research.autoresearch.engine import Candidate

    def _run():
        signs, outcomes = _ofi_signs_outcomes(symbol)
        return _series_evidence(signs, outcomes, COST_BASE_BPS, COST_STRESS_BPS, n_variants)

    return Candidate(
        cid=f"micro_ofi_momentum_{symbol}", category="microstructure",
        thesis=f"{symbol} 일별 order flow imbalance 부호 -> 익일 방향(informed flow persistence, Kyle 1985 계열)",
        direction="research", run=_run, meta={})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_engines_microstructure.py -v -k ofi`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add research/autoresearch/engines_microstructure.py tests/test_engines_microstructure.py
git commit -m "feat: microstructure engine — OFI momentum source"
```

---

## Task 3: Basis reversion source

**Files:**
- Modify: `research/autoresearch/engines_microstructure.py` (append)
- Test: `tests/test_engines_microstructure.py` (append)

**Interfaces:**
- Consumes: Task 1's `_series_evidence`. `research.hypotheses.cross_venue_skew.load_venue_snapshots(venue: str, coin: str, dates: list[str]) -> pd.DataFrame` (columns `ts, bids, asks`; `bids`/`asks` are lists of `{"price": float, "size": float}` dicts). `research.jsonl_dates.list_dates`.
- Produces: `_daily_mid(venue: str, coin: str) -> dict[str, float]`, `_basis_signs_outcomes(coin, venue_a, venue_b) -> tuple[list[float], list[float], int]`, `_select_basis_pairs() -> list[tuple]`, `_basis_candidates(selection: list[tuple], n_variants: int) -> list[Candidate]` (consumed by Task 6).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_engines_microstructure.py
from research.hypotheses import cross_venue_skew as cvs


def _write_skew_day(dirpath, venue, coin, date, rows):
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / f"{venue}_{coin}_{date}.jsonl"
    with path.open("w") as f:
        for r in rows:
            f.write(_json.dumps(r) + "\n")


def test_daily_mid_computes_utc_date_and_mean(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_SKEW_DIR", tmp_path)
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    # ts=1752105600 -> 2025-07-10T00:00:00Z-ish; use two snapshots same UTC date
    ts0 = 1752105600.0
    _write_skew_day(tmp_path, "binance", "BTC", "2025-07-10", [
        {"ts": ts0, "bids": [{"price": 100.0, "size": 1.0}], "asks": [{"price": 102.0, "size": 1.0}]},
        {"ts": ts0 + 60.0, "bids": [{"price": 104.0, "size": 1.0}], "asks": [{"price": 106.0, "size": 1.0}]},
    ])
    mids = em._daily_mid("binance", "BTC")
    assert set(mids.keys()) == {"2025-07-10"}
    assert mids["2025-07-10"] == pytest.approx((101.0 + 105.0) / 2.0)


def test_basis_signs_outcomes_reversion_direction(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_SKEW_DIR", tmp_path)
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    ts0 = 1752105600.0
    ts1 = ts0 + 86400.0
    # day0: binance mid=110, okx mid=100 -> basis=+0.10 (binance rich)
    _write_skew_day(tmp_path, "binance", "BTC", "2025-07-10", [
        {"ts": ts0, "bids": [{"price": 109.0, "size": 1.0}], "asks": [{"price": 111.0, "size": 1.0}]}])
    _write_skew_day(tmp_path, "okx", "BTC", "2025-07-10", [
        {"ts": ts0, "bids": [{"price": 99.0, "size": 1.0}], "asks": [{"price": 101.0, "size": 1.0}]}])
    # day1: basis shrinks to +0.02 -> reversion bet (sign=+1) profits
    _write_skew_day(tmp_path, "binance", "BTC", "2025-07-11", [
        {"ts": ts1, "bids": [{"price": 101.0, "size": 1.0}], "asks": [{"price": 103.0, "size": 1.0}]}])
    _write_skew_day(tmp_path, "okx", "BTC", "2025-07-11", [
        {"ts": ts1, "bids": [{"price": 99.0, "size": 1.0}], "asks": [{"price": 101.0, "size": 1.0}]}])
    signs, outcomes, n_overlap = em._basis_signs_outcomes("BTC", "binance", "okx")
    assert n_overlap == 2
    assert signs == [1.0]
    assert outcomes[0] > 0  # basis shrank -> sign*outcome positive -> reversion profit


def test_select_basis_pairs_filters_by_min_days(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_SKEW_DIR", tmp_path)
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    # no data at all -> every pair has n_overlap=0 < _MIN_DAYS -> empty selection
    assert em._select_basis_pairs() == []


def test_basis_candidates_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_SKEW_DIR", tmp_path)
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    selection = [(35, "BTC", "binance", "okx", [1.0] * 35, [0.001] * 35)]
    cands = em._basis_candidates(selection, n_variants=4)
    assert len(cands) == 1
    assert cands[0].cid == "micro_basis_reversion_BTC_binance_okx"
    assert cands[0].category == "microstructure"
    assert cands[0].direction == "research"
    result = cands[0].run()
    assert result is not None
    assert result["n"] == 35
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_engines_microstructure.py -v -k basis`
Expected: FAIL — `AttributeError: module ... has no attribute '_daily_mid'`

- [ ] **Step 3: Implement**

```python
# append to research/autoresearch/engines_microstructure.py

def _daily_mid(venue: str, coin: str) -> dict:
    """venue×coin 오더북 스냅샷 -> 날짜별 평균 mid((best_bid+best_ask)/2).
    UTC 날짜 경계 사용(dt.timezone.utc — Python 3.14 대상, utcfromtimestamp 미사용)."""
    from research.hypotheses.cross_venue_skew import load_venue_snapshots

    dates = jsonl_dates.list_dates(_SKEW_DIR, glob_prefix=f"{venue}_{coin}_")
    if not dates:
        return {}
    df = load_venue_snapshots(venue, coin, dates)
    if df.empty:
        return {}
    mids: dict[str, list] = {}
    for _, row in df.iterrows():
        if not row["bids"] or not row["asks"]:
            continue
        best_bid = max(lvl["price"] for lvl in row["bids"])
        best_ask = min(lvl["price"] for lvl in row["asks"])
        mid = (best_bid + best_ask) / 2.0
        date = dt.datetime.fromtimestamp(row["ts"], tz=dt.timezone.utc).strftime("%Y-%m-%d")
        mids.setdefault(date, []).append(mid)
    return {d: _st.mean(vs) for d, vs in mids.items()}


def _basis_signs_outcomes(coin: str, venue_a: str, venue_b: str) -> tuple:
    """basis_t = (mid_a-mid_b)/mid_b -> (부호[t], 수렴폭 basis_t-basis_next[t], 겹치는 날짜수).
    수렴방향 베팅: basis_t>0(A가 비쌈)이면 sign=+1 -> basis가 줄어들수록(outcome>0) 이익."""
    mid_a = _daily_mid(venue_a, coin)
    mid_b = _daily_mid(venue_b, coin)
    dates = sorted(d for d in mid_a if d in mid_b)
    signs, outcomes = [], []
    for i in range(len(dates) - 1):
        d, d_next = dates[i], dates[i + 1]
        if mid_b[d] <= 0 or mid_b[d_next] <= 0:
            continue
        basis_t = (mid_a[d] - mid_b[d]) / mid_b[d]
        basis_next = (mid_a[d_next] - mid_b[d_next]) / mid_b[d_next]
        if basis_t == 0.0:
            continue
        signs.append(1.0 if basis_t > 0 else -1.0)
        outcomes.append(basis_t - basis_next)
    return signs, outcomes, len(dates)


def _select_basis_pairs() -> list:
    """coin×거래소쌍 전체 계산 -> 실제 겹치는 날짜수 >= _MIN_DAYS인 것만, 많은 순 최대
    MAX_BASIS_CANDIDATES개 — 데이터 가용성으로 선정(성과로 선정 아님, 사후선택 방지)."""
    scored = []
    for coin in BASIS_COINS:
        for venue_a, venue_b in BASIS_VENUE_PAIRS:
            signs, outcomes, n_overlap = _basis_signs_outcomes(coin, venue_a, venue_b)
            if n_overlap >= _MIN_DAYS:
                scored.append((n_overlap, coin, venue_a, venue_b, signs, outcomes))
    scored.sort(key=lambda t: -t[0])
    return scored[:MAX_BASIS_CANDIDATES]


def _basis_candidates(selection: list, n_variants: int) -> list:
    from research.autoresearch.engine import Candidate
    out = []
    for _, coin, venue_a, venue_b, signs, outcomes in selection:
        def _run(signs=signs, outcomes=outcomes):
            return _series_evidence(signs, outcomes, COST_BASE_BPS, COST_STRESS_BPS, n_variants)
        out.append(Candidate(
            cid=f"micro_basis_reversion_{coin}_{venue_a}_{venue_b}", category="microstructure",
            thesis=f"{coin} {venue_a}-{venue_b} 일별 basis 수렴(cash-and-carry 재정거래)",
            direction="research", run=_run, meta={}))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_engines_microstructure.py -v -k basis`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add research/autoresearch/engines_microstructure.py tests/test_engines_microstructure.py
git commit -m "feat: microstructure engine — basis reversion source"
```

---

## Task 4: Absorption momentum adapter

**Files:**
- Modify: `research/autoresearch/engines_microstructure.py` (append)
- Test: `tests/test_engines_microstructure.py` (append)

**Interfaces:**
- Consumes: Task 1's `_event_pnl_evidence`. `research.strategies.orderflow_absorption.load_ticks(paths: list[str]) -> list[dict]`, `.build_bars_and_signals(ticks: list[dict], bucket_sec: int = 60) -> dict` (returns `{"closes": list[float], "signals": list[str], "eligible": list[int]}`), `.TARGET_NOTIONAL_USD = 1000.0`, `._median(values: list[float]) -> float`. `research.validation.engine.simulate_long_short(closes, signals, trade_size, cost_bps) -> list[dict]` (each: `{entry_idx, exit_idx, side, entry_price, exit_price, pnl}`). `research.validation.metrics.trade_metrics(trades: list[dict], min_trades: int = 30) -> dict` (`{"num_trades","total_pnl",...}`). `research.validation.baselines.random_same_frequency(closes, n_trades, holding_periods, trade_size=10.0, cost_bps=0.0, eligible_indices=None, n_runs=500, seed=42) -> list[float]`. `research.validation.cost_model.hl_effective_cost_bps(liquidity="major", taker=True) -> float`.
- Produces: `_absorption_result(symbol: str) -> dict | None` (`{"pnls": list[float], "net_stress": float, "pv": dict}`), `_absorption_candidate(symbol: str, n_variants: int) -> Candidate` (consumed by Task 6).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_engines_microstructure.py

def test_absorption_result_none_with_no_ticks(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_ORDERFLOW_DIR", tmp_path)
    assert em._absorption_result("BTC") is None


def test_absorption_candidate_shape_and_none_run(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_ORDERFLOW_DIR", tmp_path)
    cand = em._absorption_candidate("BTC", n_variants=4)
    assert cand.cid == "micro_absorption_momentum_BTC"
    assert cand.category == "microstructure"
    assert cand.direction == "research"
    assert cand.run() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_engines_microstructure.py -v -k absorption`
Expected: FAIL — `AttributeError: module ... has no attribute '_absorption_result'`

- [ ] **Step 3: Implement**

```python
# append to research/autoresearch/engines_microstructure.py

def _absorption_result(symbol: str) -> dict | None:
    """orderflow_absorption.py 어댑터 — run_hypothesis()와 동일 시퀀스를 직접 재현해
    체결별 pnl 리스트(wf 분할용)를 추가로 확보. 자체 로직/임계값 불변(dormant 모듈)."""
    from research.strategies.orderflow_absorption import TARGET_NOTIONAL_USD, _median, build_bars_and_signals
    from research.validation.engine import simulate_long_short
    from research.validation.baselines import random_same_frequency
    from research.validation.cost_model import hl_effective_cost_bps
    from research.validation.metrics import trade_metrics

    dates = jsonl_dates.list_dates(_ORDERFLOW_DIR, glob_prefix=f"{symbol}_")
    ticks = []
    for date in dates:
        f = jsonl_dates.open_stem(_ORDERFLOW_DIR, f"{symbol}_{date}")
        if f is None:
            continue
        with f:
            ticks.extend(json.loads(line) for line in f if line.strip())
    if not ticks:
        return None
    ticks.sort(key=lambda t: t["ts"])

    data = build_bars_and_signals(ticks)
    closes, signals, eligible = data["closes"], data["signals"], data["eligible"]
    if len(closes) < _MIN_EVENTS:
        return None

    trade_size = TARGET_NOTIONAL_USD / _median(closes)
    cost_bps = hl_effective_cost_bps("major", taker=True)
    trades = simulate_long_short(closes, signals, trade_size, cost_bps)
    if len(trades) < _MIN_EVENTS:
        return None

    strat = trade_metrics(trades)
    stress_trades = simulate_long_short(closes, signals, trade_size, cost_bps * _STRESS_MULT)
    stress_strat = trade_metrics(stress_trades)

    holds = [max(1, t["exit_idx"] - t["entry_idx"]) for t in trades]
    rnd = random_same_frequency(
        closes, n_trades=strat["num_trades"], holding_periods=holds,
        trade_size=trade_size, cost_bps=cost_bps,
        eligible_indices=eligible, n_runs=_N_PERMS, seed=_SEED)
    pv = empirical_p_value(strat["total_pnl"], rnd)

    pnls = [t["pnl"] for t in trades]
    return {"pnls": pnls, "net_stress": stress_strat["total_pnl"] / len(pnls), "pv": pv}


def _absorption_candidate(symbol: str, n_variants: int):
    from research.autoresearch.engine import Candidate

    def _run():
        r = _absorption_result(symbol)
        if r is None:
            return None
        return _event_pnl_evidence(r["pnls"], r["net_stress"], r["pv"], n_variants)

    return Candidate(
        cid=f"micro_absorption_momentum_{symbol}", category="microstructure",
        thesis=(f"{symbol} 1분봉 오더플로우 흡수(매도우세인데 안 밀림=롱, 매수우세인데 "
                f"안 오름=숏) — research/strategies/orderflow_absorption.py 그대로(어댑터)"),
        direction="research", run=_run, meta={})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_engines_microstructure.py -v -k absorption`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add research/autoresearch/engines_microstructure.py tests/test_engines_microstructure.py
git commit -m "feat: microstructure engine — absorption momentum adapter"
```

---

## Task 5: Skew divergence momentum adapter

**Files:**
- Modify: `research/autoresearch/engines_microstructure.py` (append)
- Test: `tests/test_engines_microstructure.py` (append)

**Interfaces:**
- Consumes: Task 1's `_event_pnl_evidence`. `research.hypotheses.cross_venue_skew.load_venue_snapshots`, `.build_imbalance(df, depth_n=5) -> pd.Series`, `.align_venues(imbalance_by_venue: dict) -> pd.DataFrame`, `.build_skew_divergence(aligned) -> pd.DataFrame`, `.build_spike_signal(divergence, lookback=300, threshold=2.0) -> pd.DataFrame`, `.build_price_series(raw_books_by_venue: dict) -> pd.Series`, `.build_labels_multi_horizon(price, spikes, horizons_s=[15]) -> pd.DataFrame` (columns `ts, venue, horizon_s, entry_price, exit_price, direction, forward_return`). `research.validation.metrics.trade_metrics`. `research.validation.cost_model.hl_effective_cost_bps`.
- Produces: `_skew_divergence_result(coin: str) -> dict | None`, `_skew_candidate(coin: str, n_variants: int) -> Candidate` (consumed by Task 6).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_engines_microstructure.py

def test_skew_divergence_result_none_with_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_SKEW_DIR", tmp_path)
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    assert em._skew_divergence_result("BTC") is None


def test_skew_candidate_shape_and_none_run(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_SKEW_DIR", tmp_path)
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    cand = em._skew_candidate("BTC", n_variants=4)
    assert cand.cid == "micro_skew_divergence_momentum_BTC_15s"
    assert cand.category == "microstructure"
    assert cand.direction == "research"
    assert cand.run() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_engines_microstructure.py -v -k skew`
Expected: FAIL — `AttributeError: module ... has no attribute '_skew_divergence_result'`

- [ ] **Step 3: Implement**

```python
# append to research/autoresearch/engines_microstructure.py

def _skew_divergence_result(coin: str) -> dict | None:
    """cross_venue_skew.py 어댑터 — run_cross_venue_skew_validate.run_coin()의 페어링 로직을
    단일 사전등록 horizon(SKEW_HORIZON_S=15)에 국한해 재현 + wf 분할 신규 추가."""
    from research.hypotheses.cross_venue_skew import (
        align_venues, build_imbalance, build_labels_multi_horizon,
        build_price_series, build_skew_divergence, build_spike_signal, load_venue_snapshots,
    )
    from research.validation.metrics import trade_metrics
    from research.validation.cost_model import hl_effective_cost_bps

    cost_bps = hl_effective_cost_bps("major", taker=True)
    dates = set()
    for venue in SKEW_VENUES:
        dates |= set(jsonl_dates.list_dates(_SKEW_DIR, glob_prefix=f"{venue}_{coin}_"))
    dates = sorted(dates)
    if not dates:
        return None

    raw_by_venue = {v: load_venue_snapshots(v, coin, dates) for v in SKEW_VENUES}
    raw_by_venue = {v: df for v, df in raw_by_venue.items() if not df.empty}
    if len(raw_by_venue) < 2:
        return None

    imbalance_by_venue = {v: build_imbalance(df) for v, df in raw_by_venue.items()}
    aligned = align_venues(imbalance_by_venue)
    divergence = build_skew_divergence(aligned)
    spikes = build_spike_signal(divergence)
    price = build_price_series(raw_by_venue)
    labels = build_labels_multi_horizon(price, spikes, horizons_s=[SKEW_HORIZON_S])
    labels = labels[labels["horizon_s"] == SKEW_HORIZON_S].sort_values("ts")
    if len(labels) < _MIN_EVENTS:
        return None

    trade_size = 1.0
    precomputed = []
    for _, row in labels.iterrows():
        entry_px, exit_px, direction = row["entry_price"], row["exit_price"], row["direction"]
        cost = (abs(entry_px) + abs(exit_px)) * trade_size * cost_bps / 10_000.0
        precomputed.append((direction, entry_px, exit_px, cost))

    pnls = [d * (ex - en) * trade_size - c for d, en, ex, c in precomputed]
    strat = trade_metrics([{"pnl": p} for p in pnls])

    stress_cost_bps = cost_bps * _STRESS_MULT
    stress_pnls = [d * (ex - en) * trade_size - (abs(en) + abs(ex)) * trade_size * stress_cost_bps / 10_000.0
                   for d, en, ex, _c in precomputed]

    rng = _random.Random(_SEED)
    perm = []
    for _ in range(_N_PERMS):
        total = 0.0
        for _d, en, ex, c in precomputed:
            rsign = rng.choice((1.0, -1.0))
            total += rsign * (ex - en) * trade_size - c
        perm.append(round(total, 6))
    pv = empirical_p_value(strat["total_pnl"], perm)

    return {"pnls": pnls, "net_stress": _st.mean(stress_pnls), "pv": pv}


def _skew_candidate(coin: str, n_variants: int):
    from research.autoresearch.engine import Candidate

    def _run():
        r = _skew_divergence_result(coin)
        if r is None:
            return None
        return _event_pnl_evidence(r["pnls"], r["net_stress"], r["pv"], n_variants)

    return Candidate(
        cid=f"micro_skew_divergence_momentum_{coin}_{SKEW_HORIZON_S}s", category="microstructure",
        thesis=(f"{coin} 거래소간(HL/Binance/OKX) 오더북 임밸런스 괴리 스파이크 -> "
                f"{SKEW_HORIZON_S}초 방향지속 — research/hypotheses/cross_venue_skew.py "
                f"그대로(어댑터, 단일 사전등록 horizon)"),
        direction="research", run=_run, meta={})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_engines_microstructure.py -v -k skew`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add research/autoresearch/engines_microstructure.py tests/test_engines_microstructure.py
git commit -m "feat: microstructure engine — skew divergence momentum adapter"
```

---

## Task 6: Assembly + `collect_candidates()` wiring

**Files:**
- Modify: `research/autoresearch/engines_microstructure.py` (append)
- Modify: `research/autoresearch/engine.py:84-90`
- Test: `tests/test_engines_microstructure.py` (append)

**Interfaces:**
- Consumes: all of Tasks 2-5's `_ofi_candidate`, `_select_basis_pairs`, `_basis_candidates`, `_absorption_candidate`, `_skew_candidate`. `research.autoresearch.engine.Candidate` dataclass (`cid: str, category: str, thesis: str, direction: str, run: Callable[[], Optional[dict]], meta: dict = field(default_factory=dict)`).
- Produces: `microstructure_candidates() -> list[Candidate]` — wired into `collect_candidates()` as the 3rd source.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_engines_microstructure.py

def test_microstructure_candidates_assembles_all_four_sources_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(em, "_ORDERFLOW_DIR", tmp_path)
    monkeypatch.setattr(em, "_SKEW_DIR", tmp_path)
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    cands = em.microstructure_candidates()
    # no data anywhere -> basis selection empty, but OFI(3)+absorption(3)+skew(2) still present
    cids = {c.cid for c in cands}
    assert cids == {
        "micro_ofi_momentum_BTC", "micro_ofi_momentum_ETH", "micro_ofi_momentum_PAXG",
        "micro_absorption_momentum_BTC", "micro_absorption_momentum_ETH", "micro_absorption_momentum_PAXG",
        "micro_skew_divergence_momentum_BTC_15s", "micro_skew_divergence_momentum_ETH_15s",
    }
    for c in cands:
        assert c.category == "microstructure"
        assert c.direction == "research"
        assert c.run() is None  # no data in tmp_path


def test_microstructure_candidates_n_variants_uses_actual_basis_count(monkeypatch):
    # n_variants must reflect the REAL selected basis-pair count, not MAX_BASIS_CANDIDATES
    monkeypatch.setattr(em, "_select_basis_pairs", lambda: [
        (35, "BTC", "binance", "okx", [1.0] * 35, [0.001] * 35),
    ])
    captured = {}
    orig = em._ofi_candidate

    def _spy(symbol, n_variants):
        captured["n_variants"] = n_variants
        return orig(symbol, n_variants)

    monkeypatch.setattr(em, "_ofi_candidate", _spy)
    em.microstructure_candidates()
    # 3 OFI + 1 basis(selected) + 3 absorption + 2 skew = 9, NOT 3+4(cap)+3+2=12
    assert captured["n_variants"] == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_engines_microstructure.py -v -k microstructure_candidates`
Expected: FAIL — `AttributeError: module ... has no attribute 'microstructure_candidates'`

- [ ] **Step 3: Implement assembly**

```python
# append to research/autoresearch/engines_microstructure.py

def microstructure_candidates() -> list:
    """4개 사전등록 소스 조립 — n_variants(레드팀 multiple_testing 판단용)는
    실제 등록 후보 총수. basis는 데이터가용성 기준 선정을 먼저 끝내고 나서
    그 실제 선정 개수로 n_variants를 계산(이론상 최대치 MAX_BASIS_CANDIDATES를
    쓰면 실제보다 부풀려질 수 있어 오류)."""
    basis_selection = _select_basis_pairs()
    n_variants = len(OFI_SYMBOLS) + len(basis_selection) + len(ABSORPTION_SYMBOLS) + len(SKEW_COINS)
    out = []
    out += [_ofi_candidate(s, n_variants) for s in OFI_SYMBOLS]
    out += _basis_candidates(basis_selection, n_variants)
    out += [_absorption_candidate(s, n_variants) for s in ABSORPTION_SYMBOLS]
    out += [_skew_candidate(c, n_variants) for c in SKEW_COINS]
    return out
```

- [ ] **Step 4: Wire into `collect_candidates()`**

Read `research/autoresearch/engine.py:84-90` first to confirm the exact current text before editing:

```python
def collect_candidates() -> tuple[list[Candidate], dict]:
    series = load_series()
    cands = _event_family_candidates(series)
    from research.autoresearch.engines_factor import factor_candidates, load_fundamentals
    fund = load_fundamentals(list(series.keys()))
    cands += factor_candidates(series, fund=fund)
    return cands, series
```

Replace with:

```python
def collect_candidates() -> tuple[list[Candidate], dict]:
    series = load_series()
    cands = _event_family_candidates(series)
    from research.autoresearch.engines_factor import factor_candidates, load_fundamentals
    fund = load_fundamentals(list(series.keys()))
    cands += factor_candidates(series, fund=fund)
    from research.autoresearch.engines_microstructure import microstructure_candidates
    cands += microstructure_candidates()
    return cands, series
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_engines_microstructure.py -v`
Expected: PASS (all tests in the file, ~17 total across Tasks 1-6)

- [ ] **Step 6: Run full regression suite**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: same 94 pre-existing failures as documented in `seokminal/CLAUDE.md` (unrelated modules: `jarvis/architecture_docs`, `integration_audit`, `local_runtime`, `production_review`, `release_candidate`, `research_navigation`, `research_workflow`, `system_integration`) — zero NEW failures. If any failure touches `engine.py`, `engines_microstructure.py`, or `engines_factor.py`, stop and fix before proceeding.

- [ ] **Step 7: Manual real-data smoke run**

Run:
```bash
PYTHONPATH=. /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -c "
from research.autoresearch.engines_microstructure import microstructure_candidates
cands = microstructure_candidates()
print(f'{len(cands)} candidates')
for c in cands:
    r = c.run()
    if r is None:
        print(f'{c.cid}: UNDERPOWERED')
    else:
        print(f'{c.cid}: n={r[\"n\"]} net={r[\"net\"]} p={r[\"p\"]} percentile={r[\"percentile\"]} '
              f'wf1={r[\"wf_first\"]} wf2={r[\"wf_second\"]} evidence={r[\"evidence\"]}')
"
```
Expected: prints 8-12 candidates (3 OFI + up to 4 basis + 3 absorption + 2 skew). Report every line verbatim — including any `UNDERPOWERED` — do not discard or re-run to force a different result (per spec's "억지 통과 금지").

- [ ] **Step 8: Commit**

```bash
git add research/autoresearch/engines_microstructure.py research/autoresearch/engine.py tests/test_engines_microstructure.py
git commit -m "feat: microstructure engine — assemble 4 sources, wire into collect_candidates()"
```

---

## Self-Review Notes (completed during plan authoring)

- **Spec coverage:** Background/Architecture → Task 6 wiring snippet (verbatim from spec's integration point). OFI momentum → Task 2. Basis reversion → Task 3 (with `_select_basis_pairs()`-first `n_variants` fix per Addendum's "데이터 가용성으로 선정" rule). Absorption adapter → Task 4. Skew divergence adapter → Task 5. Cost model → Global Constraints + each task's evidence assembly. Sample-size honesty (`_MIN_DAYS`/`_MIN_EVENTS`) → Task 1 constants, enforced in `_series_evidence`/dormant-module reuse. wf_first/wf_second methodology (Addendum) → `_series_evidence` (chronological half-split of `ls`) and `_event_pnl_evidence` (chronological half-split of trade/event pnls). Redteam `_spec` contract → `_assemble_evidence`. Testing section → unit tests per function + Task 6 integration test + manual smoke run.
- **Placeholder scan:** no TBD/TODO; every step has real code with exact signatures verified against fresh reads of `engine.py`, `engines_factor.py`, `orderflow_absorption.py`, `cross_venue_skew.py`, `run_cross_venue_skew_validate.py`, `baselines.py`, `jsonl_dates.py`, `metrics.py`, `validation/engine.py`, `cost_model.py`.
- **Type/signature consistency:** `net_stress` key used consistently across `_assemble_evidence`/all tests/all evidence-producing call sites (matches `engines_factor.py`'s established naming, not the spec's informal "stress" wording). `Candidate` field names (`cid/category/thesis/direction/run/meta`) consistent across all 4 candidate-builder functions and Task 6's assembly. `_ORDERFLOW_DIR`/`_SKEW_DIR` module-level `Path` constants are monkeypatched consistently across all tests (matching `tests/test_cross_venue_skew.py`'s existing `_DATA_DIR` monkeypatch convention) — note Task 3/5/6 tests must patch BOTH `engines_microstructure._SKEW_DIR` (date discovery) AND `cross_venue_skew._DATA_DIR` (actual snapshot loading) since `_daily_mid`/`_skew_divergence_result` use `jsonl_dates.list_dates` against the former but `load_venue_snapshots` reads via the latter.

---

Plan complete and saved to `docs/superpowers/plans/2026-08-26-microstructure-hypothesis-engine.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
