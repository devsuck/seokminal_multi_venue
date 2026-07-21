# Polymarket Sharp-Wallet Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect whether Polymarket's official top-50 all-time-PnL leaderboard wallets moving (individually, and especially in cross-market convergence) predicts forward price moves, screened via the repo's standard random-baseline + BH-FDR pipeline.

**Architecture:** A 5-layer pipeline mirroring the existing `polymarket_whale` hypothesis: (1) a pure-function leaderboard client that turns the official `data-api.polymarket.com/v1/leaderboard` response into a wallet→{rank,pnl} lookup, (2) a tmux-resident REST-polling collector that tags each global `/trades` fill as `anchor` (sharp-wallet fill ≥ $50 notional) or `context` (any fill in a market currently being watched because of a recent anchor), (3) a pure-function hypothesis module that turns the ledger into cross-market convergence-bucketed, multi-horizon forward-return labels, (4) a validate runner that computes empirical p-values per bucket×horizon and BH-FDR-corrects them in an independent pool, (5) HUD registration (backend `lab_api.py` + frontend `lib/api.ts`/`app/hud/page.tsx`) so the collector's liveness is visible exactly like every other collector in this repo.

**Tech Stack:** Python 3.14, `requests` (leaderboard + trades REST polling), `pandas` (label construction, reused from `polymarket_whale`), `pytest` (`asyncio_mode="auto"` — never use `@pytest.mark.asyncio`, not relevant here since nothing is async), TypeScript/Next.js for the two frontend touch points.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-20-polymarket-sharp-wallet-design.md`. All constants below are copied verbatim from it and are **fixed at design time — never tune them after seeing results.**
- Leaderboard: `LEADERBOARD_URL = "https://data-api.polymarket.com/v1/leaderboard"`, `LEADERBOARD_CATEGORY = "OVERALL"`, `LEADERBOARD_TIME_PERIOD = "ALL"`, `LEADERBOARD_LIMIT = 50`, `orderBy=PNL`, `offset=0`.
- Collector: `POLL_INTERVAL_S = 5.0`, `LEADERBOARD_REFRESH_INTERVAL_S = 86400.0`, `MIN_NOTIONAL_USD = 50.0`, `MAX_HORIZON_S = 300.0`, `DEDUP_HASH_RING_SIZE = 5000`. Data path: `research/data/polymarket_sharp_wallet/{date}.jsonl`. tmux session: `polymarket-sharp-wallet-tick`.
- Hypothesis module: `CONVERGENCE_WINDOW_S = 600.0`, `MAX_CONVERGENCE_BUCKET = 3`, `RESAMPLE_GRID_S = 5.0`, `HORIZONS_S = [30, 120, 300]`.
- Validate runner: `TRADE_SIZE = 1.0`, `N_RUNS = 500`, `SEED = 42`, `MIN_EVENTS = 10`, `alpha = 0.1`, cost via `research.validation.cost_model.polymarket_effective_cost_bps()` (no new cost model). BH-FDR pool is convergence_bucket×horizon only — **never mixed with any other hypothesis's p-values.**
- Convergence counting is **cross-market** (any distinct sharp wallet firing within the trailing window counts, regardless of `condition_id`).
- HUD registration is **mandatory, not optional** — a dead collector must be visible in the HUD (documented lesson from the whale spec, repeated verbatim in this spec §6/§9).
- Directional symmetry: no pre-specified direction, same as `polymarket_whale` — this is a screening pipeline, not a trading signal generator. No real order placement, no wallet signing, anywhere in this plan.
- Follow existing repo conventions found in `research/hypotheses/polymarket_whale.py` and `research/run_polymarket_whale_collect.py` byte-for-byte in style (docstring conventions, `from __future__ import annotations`, `_DATA_DIR` as a module-level `Path` patched via `monkeypatch.setattr`/`patch.object` in tests).
- Python binary for running tests: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`.

---

### Task 1: Leaderboard module

**Files:**
- Create: `research/polymarket_sharp_wallet/__init__.py` (empty file)
- Create: `research/polymarket_sharp_wallet/leaderboard.py`
- Test: `tests/test_polymarket_sharp_wallet_leaderboard.py`

**Interfaces:**
- Consumes: nothing (leaf module, only `requests`)
- Produces: `fetch_leaderboard() -> list[dict]` (each dict: `{"rank": int, "proxyWallet": str, "pnl": float, "vol": float}`), `build_sharp_wallet_set(entries: list[dict]) -> dict[str, dict]` (key = lowercased `proxyWallet`, value = `{"rank": int, "pnl": float}`). Constants `LEADERBOARD_URL`, `LEADERBOARD_CATEGORY`, `LEADERBOARD_TIME_PERIOD`, `LEADERBOARD_LIMIT` — Task 2's collector imports both functions and reuses these names.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_polymarket_sharp_wallet_leaderboard.py`:

```python
from unittest.mock import Mock, patch

import research.polymarket_sharp_wallet.leaderboard as lb


def _entry(rank=1, wallet="0xABC", pnl=1000.0, vol=5000.0):
    return {"rank": rank, "proxyWallet": wallet, "pnl": pnl, "vol": vol}


def test_fetch_leaderboard_returns_parsed_list():
    fake_resp = Mock()
    fake_resp.json.return_value = [_entry(rank=1, wallet="0xAAA"), _entry(rank=2, wallet="0xBBB")]
    fake_resp.raise_for_status.return_value = None
    with patch.object(lb.requests, "get", return_value=fake_resp) as mock_get:
        result = lb.fetch_leaderboard()
    assert result == [
        {"rank": 1, "proxyWallet": "0xAAA", "pnl": 1000.0, "vol": 5000.0},
        {"rank": 2, "proxyWallet": "0xBBB", "pnl": 1000.0, "vol": 5000.0},
    ]
    _, kwargs = mock_get.call_args
    assert kwargs["params"] == {
        "category": lb.LEADERBOARD_CATEGORY, "timePeriod": lb.LEADERBOARD_TIME_PERIOD,
        "orderBy": "PNL", "limit": lb.LEADERBOARD_LIMIT, "offset": 0,
    }


def test_fetch_leaderboard_returns_empty_for_non_list_response():
    fake_resp = Mock()
    fake_resp.json.return_value = {"error": "bad"}
    fake_resp.raise_for_status.return_value = None
    with patch.object(lb.requests, "get", return_value=fake_resp):
        result = lb.fetch_leaderboard()
    assert result == []


def test_build_sharp_wallet_set_lowercases_keys():
    entries = [_entry(rank=1, wallet="0xABCDEF", pnl=500.0)]
    result = lb.build_sharp_wallet_set(entries)
    assert result == {"0xabcdef": {"rank": 1, "pnl": 500.0}}


def test_build_sharp_wallet_set_empty_input_returns_empty_dict():
    assert lb.build_sharp_wallet_set([]) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_sharp_wallet_leaderboard.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'research.polymarket_sharp_wallet'`

- [ ] **Step 3: Create the package and implementation**

Create `research/polymarket_sharp_wallet/__init__.py` (empty).

Create `research/polymarket_sharp_wallet/leaderboard.py`:

```python
"""Polymarket 공식 리더보드 조회 — 전체기간 PnL 상위 지갑을 "샤프월렛" 명단으로 쓴다.

`docs/superpowers/specs/2026-07-20-polymarket-sharp-wallet-design.md` §3,5 참고.
자체 트랙레코드를 쌓는 대신 data-api.polymarket.com/v1/leaderboard(무인증)를
그대로 신뢰한다 — 상수는 설계 시점 고정값이며 결과를 본 뒤 바꾸지 않는다.
"""
from __future__ import annotations

import requests

LEADERBOARD_URL = "https://data-api.polymarket.com/v1/leaderboard"
LEADERBOARD_CATEGORY = "OVERALL"
LEADERBOARD_TIME_PERIOD = "ALL"
LEADERBOARD_LIMIT = 50
_TIMEOUT = 15


def fetch_leaderboard() -> list[dict]:
    """GET 요청 후 rank/proxyWallet/pnl/vol만 남긴 리스트 반환. 응답이 리스트가
    아니면(API 오류 등) 빈 리스트."""
    r = requests.get(LEADERBOARD_URL, params={
        "category": LEADERBOARD_CATEGORY,
        "timePeriod": LEADERBOARD_TIME_PERIOD,
        "orderBy": "PNL",
        "limit": LEADERBOARD_LIMIT,
        "offset": 0,
    }, timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        return []
    return [
        {"rank": e["rank"], "proxyWallet": e["proxyWallet"], "pnl": e["pnl"], "vol": e["vol"]}
        for e in data
    ]


def build_sharp_wallet_set(entries: list[dict]) -> dict[str, dict]:
    """proxyWallet(lowercase) -> {rank, pnl} 매핑. 대소문자 비교 문제 방지용."""
    return {e["proxyWallet"].lower(): {"rank": e["rank"], "pnl": e["pnl"]} for e in entries}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_sharp_wallet_leaderboard.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add research/polymarket_sharp_wallet/__init__.py research/polymarket_sharp_wallet/leaderboard.py tests/test_polymarket_sharp_wallet_leaderboard.py
git commit -m "feat: add polymarket sharp-wallet leaderboard module"
```

---

### Task 2: Collector (anchor/context classification + tmux polling loop)

**Files:**
- Create: `research/run_polymarket_sharp_wallet_collect.py`
- Test: `tests/test_run_polymarket_sharp_wallet_collect.py`

**Interfaces:**
- Consumes: `research.polymarket_sharp_wallet.leaderboard.fetch_leaderboard()`, `research.polymarket_sharp_wallet.leaderboard.build_sharp_wallet_set(entries)` (Task 1).
- Produces: `filter_new_trades(trades, sharp_wallets, watch_until, last_seen_ts, seen_hashes) -> tuple[list[dict], float, list[str], dict[str, float]]`, `prune_stale_watch(watch_until, now) -> dict[str, float]`, `fetch_trades(limit=500) -> list[dict]`, `refresh_leaderboard() -> dict[str, dict]`, `append_trades(trades) -> None`, `run_forever(*, fetch_fn=..., leaderboard_fn=..., append_fn=..., poll_interval_s=..., leaderboard_refresh_interval_s=..., max_cycles=None) -> None`. Constants `POLL_INTERVAL_S`, `LEADERBOARD_REFRESH_INTERVAL_S`, `MIN_NOTIONAL_USD`, `MAX_HORIZON_S`, `DEDUP_HASH_RING_SIZE`, `_DATA_DIR`. Task 3 (HUD backend) references the tmux session name `polymarket-sharp-wallet-tick`, data dir `research/data/polymarket_sharp_wallet`, and module path `research.run_polymarket_sharp_wallet_collect` — all defined here. Task 4 (hypothesis module) reads the JSONL records this collector writes, which carry these extra fields per trade: `notional_usd` (float), `is_sharp_wallet` (bool), `wallet_rank` (int or null), `wallet_pnl` (float or null).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_run_polymarket_sharp_wallet_collect.py`:

```python
import datetime as dt
import json
from unittest.mock import patch

import pytest

import research.run_polymarket_sharp_wallet_collect as runner


def _trade(cid="c1", ts=100.0, tx="tx1", side="BUY", price=0.5, size=1000.0, wallet="0xsharp"):
    return {
        "conditionId": cid, "timestamp": ts, "transactionHash": tx,
        "side": side, "price": price, "size": size, "proxyWallet": wallet,
        "asset": "tok1", "title": "t", "slug": "s", "outcome": "Yes", "name": "trader1",
    }


def test_filter_new_trades_marks_sharp_wallet_trade_as_anchor_and_extends_watch_until():
    trades = [_trade(cid="c1", ts=100.0, wallet="0xsharp")]  # notional = 0.5*1000 = 500
    sharp_wallets = {"0xsharp": {"rank": 1, "pnl": 10000.0}}
    out, last_ts, hashes, watch_until = runner.filter_new_trades(
        trades, sharp_wallets, {}, last_seen_ts=0.0, seen_hashes=[],
    )
    assert len(out) == 1
    assert out[0]["is_sharp_wallet"] is True
    assert out[0]["wallet_rank"] == 1
    assert out[0]["wallet_pnl"] == 10000.0
    assert out[0]["notional_usd"] == pytest.approx(500.0)
    assert watch_until["c1"] == pytest.approx(100.0 + runner.MAX_HORIZON_S)


def test_filter_new_trades_drops_sharp_wallet_trade_below_min_notional():
    trades = [_trade(cid="c1", ts=100.0, wallet="0xsharp", price=0.5, size=10.0)]  # notional = 5.0
    sharp_wallets = {"0xsharp": {"rank": 1, "pnl": 10000.0}}
    out, last_ts, hashes, watch_until = runner.filter_new_trades(
        trades, sharp_wallets, {}, last_seen_ts=0.0, seen_hashes=[],
    )
    assert out == []
    assert watch_until == {}


def test_filter_new_trades_keeps_context_trade_within_watch_until():
    trades = [_trade(cid="c1", ts=150.0, wallet="0xnobody", tx="ctx1")]
    out, last_ts, hashes, watch_until = runner.filter_new_trades(
        trades, {}, {"c1": 200.0}, last_seen_ts=0.0, seen_hashes=[],
    )
    assert len(out) == 1
    assert out[0]["is_sharp_wallet"] is False
    assert out[0]["wallet_rank"] is None
    assert out[0]["wallet_pnl"] is None


def test_filter_new_trades_drops_trade_outside_watch_until_and_not_sharp():
    trades = [_trade(cid="c1", ts=250.0, wallet="0xnobody", tx="late1")]
    out, last_ts, hashes, watch_until = runner.filter_new_trades(
        trades, {}, {"c1": 200.0}, last_seen_ts=0.0, seen_hashes=[],
    )
    assert out == []


def test_filter_new_trades_skips_older_than_last_seen_ts():
    trades = [_trade(ts=50.0, tx="old", wallet="0xsharp"), _trade(ts=150.0, tx="new", wallet="0xsharp")]
    sharp_wallets = {"0xsharp": {"rank": 1, "pnl": 1.0}}
    out, last_ts, hashes, watch_until = runner.filter_new_trades(
        trades, sharp_wallets, {}, last_seen_ts=100.0, seen_hashes=[],
    )
    assert [t["transactionHash"] for t in out] == ["new"]
    assert last_ts == 150.0


def test_filter_new_trades_skips_already_seen_hash():
    trades = [_trade(tx="dup1", wallet="0xsharp"), _trade(tx="dup1", wallet="0xsharp")]
    sharp_wallets = {"0xsharp": {"rank": 1, "pnl": 1.0}}
    out, last_ts, hashes, watch_until = runner.filter_new_trades(
        trades, sharp_wallets, {}, last_seen_ts=0.0, seen_hashes=[],
    )
    assert len(out) == 1
    assert hashes.count("dup1") == 1


def test_filter_new_trades_ring_buffer_caps_at_size():
    seen = [f"old{i}" for i in range(runner.DEDUP_HASH_RING_SIZE)]
    trades = [_trade(tx="new1", wallet="0xsharp")]
    sharp_wallets = {"0xsharp": {"rank": 1, "pnl": 1.0}}
    out, last_ts, hashes, watch_until = runner.filter_new_trades(
        trades, sharp_wallets, {}, last_seen_ts=0.0, seen_hashes=seen,
    )
    assert len(hashes) == runner.DEDUP_HASH_RING_SIZE
    assert hashes[-1] == "new1"


def test_prune_stale_watch_removes_entries_older_than_horizon():
    watch_until = {"c1": 100.0, "c2": 1000.0}
    now = 100.0 + runner.MAX_HORIZON_S + 1.0
    result = runner.prune_stale_watch(watch_until, now)
    assert result == {"c2": 1000.0}


def test_prune_stale_watch_keeps_recent_entries():
    watch_until = {"c1": 100.0}
    now = 100.0
    result = runner.prune_stale_watch(watch_until, now)
    assert result == {"c1": 100.0}


def test_append_trades_writes_jsonl_dated_file(tmp_path):
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_trades([_trade(tx="a"), _trade(tx="b")])
        path = tmp_path / f"{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["transactionHash"] == "a"


def test_append_trades_skips_write_when_empty(tmp_path):
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_trades([])
    assert list(tmp_path.iterdir()) == []


def test_run_forever_refreshes_leaderboard_only_after_interval():
    refresh_calls = []

    def fake_leaderboard():
        refresh_calls.append(1)
        return {"0xsharp": {"rank": 1, "pnl": 1.0}}

    fake_time = [1000.0]

    def fake_time_fn():
        return fake_time[0]

    def fake_sleep(_):
        fake_time[0] += 1.0

    with patch("time.time", side_effect=fake_time_fn), patch("time.sleep", side_effect=fake_sleep):
        runner.run_forever(
            fetch_fn=lambda: [], leaderboard_fn=fake_leaderboard, append_fn=lambda t: None,
            poll_interval_s=1.0, leaderboard_refresh_interval_s=1000.0, max_cycles=3,
        )
    assert len(refresh_calls) == 1  # 최초 1회만, interval 안 지났으니 재조회 없음


def test_run_forever_polls_and_appends_new_trades_across_cycles():
    appended = []
    fetch_calls = [[_trade(ts=100.0, tx="a", wallet="0xsharp")], [_trade(ts=200.0, tx="b", wallet="0xsharp")]]

    def fake_fetch():
        return fetch_calls.pop(0) if fetch_calls else []

    with patch("time.sleep"):
        runner.run_forever(
            fetch_fn=fake_fetch, leaderboard_fn=lambda: {"0xsharp": {"rank": 1, "pnl": 1.0}},
            append_fn=lambda t: appended.extend(t),
            poll_interval_s=0.0, leaderboard_refresh_interval_s=1000.0, max_cycles=2,
        )
    assert [t["transactionHash"] for t in appended] == ["a", "b"]


def test_run_forever_continues_after_fetch_exception():
    appended = []
    calls = {"n": 0}

    def flaky_fetch():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("boom")
        return [_trade(ts=100.0, tx="a", wallet="0xsharp")]

    with patch("time.sleep"):
        runner.run_forever(
            fetch_fn=flaky_fetch, leaderboard_fn=lambda: {"0xsharp": {"rank": 1, "pnl": 1.0}},
            append_fn=lambda t: appended.extend(t),
            poll_interval_s=0.0, leaderboard_refresh_interval_s=1000.0, max_cycles=2,
        )
    assert [t["transactionHash"] for t in appended] == ["a"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_sharp_wallet_collect.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'research.run_polymarket_sharp_wallet_collect'`

- [ ] **Step 3: Write the implementation**

Create `research/run_polymarket_sharp_wallet_collect.py`:

```python
"""Polymarket 샤프월렛 체결(fill) 수집기 — Data-API REST 폴링, tmux로 상시 실행.

whale 수집기(`research/run_polymarket_whale_collect.py`)와 동일한 무한루프+폴링
골격(글로벌 `/trades` 피드, transactionHash 기반 dedup, try/except 사이클스킵)을
재사용하되 필터 기준이 다르다: 마켓 family가 아니라 "이 체결의 지갑이(공식
리더보드 top 50 기준) 샤프월렛인지". 리더보드는 1일 1회만 재조회(PnL 랭킹은
느리게 변함 — 매 폴링마다 부르지 않음).

왜 컨텍스트 체결까지 저장하는가: forward-return 계산엔 각 마켓의 조밀한 가격
시계열이 필요하다. 샤프월렛 체결만 저장하면 마켓당 표본이 1건뿐인 경우가
대부분이라(top 50 지갑이 특정 마켓에 동시에 다 몰릴 리 없음) ffill 리샘플이
사실상 "영원히 anchor 가격 고정"이 되어 forward return이 항상 0으로 나온다.
해결: 샤프월렛 체결(anchor)이 마켓 X에서 감지되면, 그 시점부터 MAX_HORIZON_S초
동안 마켓 X의 모든 체결(지갑 무관, context)을 같이 저장해 가격 시계열을
조밀하게 만든다(`docs/superpowers/specs/2026-07-20-polymarket-sharp-wallet-design.md`
§6 참고). 상수는 전부 설계 시점 고정값이며 결과를 본 뒤 바꾸지 않는다.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path

import requests

from research.polymarket_sharp_wallet.leaderboard import (
    build_sharp_wallet_set,
    fetch_leaderboard,
)

_DATA_DIR = Path("research/data/polymarket_sharp_wallet")
_TRADES_URL = "https://data-api.polymarket.com/trades"
_TIMEOUT = 15

POLL_INTERVAL_S = 5.0
LEADERBOARD_REFRESH_INTERVAL_S = 86400.0
MIN_NOTIONAL_USD = 50.0
MAX_HORIZON_S = 300.0
DEDUP_HASH_RING_SIZE = 5000


def append_trades(trades: list[dict]) -> None:
    if not trades:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
    with path.open("a") as f:
        for t in trades:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


def fetch_trades(limit: int = 500) -> list[dict]:
    r = requests.get(_TRADES_URL, params={"limit": limit}, timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def refresh_leaderboard() -> dict[str, dict]:
    """proxyWallet(lowercase) -> {rank, pnl} 매핑(공식 리더보드 top 50)."""
    return build_sharp_wallet_set(fetch_leaderboard())


def prune_stale_watch(watch_until: dict[str, float], now: float) -> dict[str, float]:
    """watch_until[cid] < now - MAX_HORIZON_S인 항목 제거(무한 성장 방지)."""
    cutoff = now - MAX_HORIZON_S
    return {cid: until for cid, until in watch_until.items() if until >= cutoff}


def filter_new_trades(
    trades: list[dict],
    sharp_wallets: dict[str, dict],
    watch_until: dict[str, float],
    last_seen_ts: float,
    seen_hashes: list[str],
) -> tuple[list[dict], float, list[str], dict[str, float]]:
    """anchor(샤프월렛 체결, notional>=MIN_NOTIONAL_USD) 또는 context(watch_until
    안의 체결)만 남기고 나머지는 버린다. anchor 감지 시 watch_until[cid]를
    trade_ts+MAX_HORIZON_S로 갱신(연장 포함). 반환: (필터통과 trades, 갱신된
    last_seen_ts, 갱신된 seen_hashes 링버퍼(최근 DEDUP_HASH_RING_SIZE개), 갱신된
    watch_until)."""
    seen_set = set(seen_hashes)
    hashes = list(seen_hashes)
    watch_until = dict(watch_until)
    out = []
    max_ts = last_seen_ts
    for t in trades:
        cid = t.get("conditionId")
        ts = t.get("timestamp")
        h = t.get("transactionHash")
        if ts is None or ts < last_seen_ts:
            continue
        if h in seen_set:
            continue
        wallet = (t.get("proxyWallet") or "").lower()
        notional = float(t["price"]) * float(t["size"])
        sharp = sharp_wallets.get(wallet)
        is_anchor = sharp is not None and notional >= MIN_NOTIONAL_USD
        is_context = cid in watch_until and ts <= watch_until[cid]
        if not (is_anchor or is_context):
            continue
        if is_anchor:
            watch_until[cid] = ts + MAX_HORIZON_S
        out.append({
            **t, "notional_usd": notional, "is_sharp_wallet": is_anchor,
            "wallet_rank": sharp["rank"] if sharp else None,
            "wallet_pnl": sharp["pnl"] if sharp else None,
        })
        seen_set.add(h)
        hashes.append(h)
        if ts > max_ts:
            max_ts = ts
    if len(hashes) > DEDUP_HASH_RING_SIZE:
        hashes = hashes[-DEDUP_HASH_RING_SIZE:]
    return out, max_ts, hashes, watch_until


def run_forever(
    *,
    fetch_fn=fetch_trades,
    leaderboard_fn=refresh_leaderboard,
    append_fn=append_trades,
    poll_interval_s: float = POLL_INTERVAL_S,
    leaderboard_refresh_interval_s: float = LEADERBOARD_REFRESH_INTERVAL_S,
    max_cycles: int | None = None,
) -> None:
    sharp_wallets = leaderboard_fn()
    last_leaderboard_refresh = time.time()
    watch_until: dict[str, float] = {}
    last_seen_ts = 0.0
    seen_hashes: list[str] = []
    cycle = 0
    while max_cycles is None or cycle < max_cycles:
        try:
            now = time.time()
            if now - last_leaderboard_refresh >= leaderboard_refresh_interval_s:
                sharp_wallets = leaderboard_fn()
                last_leaderboard_refresh = now
            trades = fetch_fn()
            new_trades, last_seen_ts, seen_hashes, watch_until = filter_new_trades(
                trades, sharp_wallets, watch_until, last_seen_ts, seen_hashes,
            )
            watch_until = prune_stale_watch(watch_until, now)
            append_fn(new_trades)
        except Exception:
            logging.exception("polymarket sharp-wallet poll failed, continuing")
        time.sleep(poll_interval_s)
        cycle += 1


if __name__ == "__main__":
    run_forever()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_sharp_wallet_collect.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add research/run_polymarket_sharp_wallet_collect.py tests/test_run_polymarket_sharp_wallet_collect.py
git commit -m "feat: add polymarket sharp-wallet collector with anchor/context capture"
```

---

### Task 3: HUD backend registration

**Files:**
- Modify: `api_server/lab_api.py:213-225` (`COLLECTOR_SESSIONS` dict), `api_server/lab_api.py:296-304` (`lab_status()`'s `out["processes"]` dict)
- Test: `tests/test_lab_api_polymarket_sharp_wallet_status.py`

**Interfaces:**
- Consumes: tmux session name `polymarket-sharp-wallet-tick`, data dir `research/data/polymarket_sharp_wallet`, module `research.run_polymarket_sharp_wallet_collect` (all from Task 2). Existing `_tmux_process_status(session: str, data_dir: str) -> dict` helper (already defined in `lab_api.py`, unchanged).
- Produces: `lab_status()["processes"]["polymarket_sharp_wallet_tick"]` — consumed by Task 6 (frontend).

- [ ] **Step 1: Write the failing test**

Create `tests/test_lab_api_polymarket_sharp_wallet_status.py`:

```python
from unittest.mock import patch

from api_server.lab_api import lab_status


def test_lab_status_processes_includes_polymarket_sharp_wallet_tick():
    fake_status = {"running": False, "last_write": None, "age_sec": None}
    with patch("api_server.lab_api._tmux_process_status", return_value=fake_status) as mock_fn:
        result = lab_status()
    assert "polymarket_sharp_wallet_tick" in result["processes"]
    calls = [c.args for c in mock_fn.call_args_list]
    assert ("polymarket-sharp-wallet-tick", "research/data/polymarket_sharp_wallet") in calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_lab_api_polymarket_sharp_wallet_status.py -v`
Expected: FAIL — `assert "polymarket_sharp_wallet_tick" in result["processes"]` (key not present yet)

- [ ] **Step 3: Register the collector**

In `api_server/lab_api.py`, find the `COLLECTOR_SESSIONS` dict (currently lines 213-225):

```python
COLLECTOR_SESSIONS: dict[str, dict[str, str]] = {
    "polymarket_tick": {"session": "polymarket-tick", "data_dir": "research/data/polymarket_tick",
                        "module": "research.run_polymarket_tick_collect"},
    "polymarket_arb": {"session": "polymarket-arb", "data_dir": "research/data/polymarket_arb",
                       "module": "research.run_polymarket_arb_scan"},
    "hl_orderflow_tick": {"session": "hl-orderflow-tick", "data_dir": "research/data/hl_orderflow_tick",
                          "module": "research.run_hl_orderflow_tick_collect"},
    "cross_venue_skew_tick": {"session": "cross-venue-skew-tick", "data_dir": "research/data/cross_venue_skew",
                              "module": "research.run_cross_venue_skew_collect"},
    "polymarket_whale_tick": {"session": "polymarket-whale-tick", "data_dir": "research/data/polymarket_whale",
                              "module": "research.run_polymarket_whale_collect"},
    "polymarket_updown_arb": {"session": "polymarket-updown-arb", "data_dir": "research/data/polymarket_updown_arb",
                              "module": "research.run_polymarket_updown_arb_scan"},
}
```

Replace with (adds one entry):

```python
COLLECTOR_SESSIONS: dict[str, dict[str, str]] = {
    "polymarket_tick": {"session": "polymarket-tick", "data_dir": "research/data/polymarket_tick",
                        "module": "research.run_polymarket_tick_collect"},
    "polymarket_arb": {"session": "polymarket-arb", "data_dir": "research/data/polymarket_arb",
                       "module": "research.run_polymarket_arb_scan"},
    "hl_orderflow_tick": {"session": "hl-orderflow-tick", "data_dir": "research/data/hl_orderflow_tick",
                          "module": "research.run_hl_orderflow_tick_collect"},
    "cross_venue_skew_tick": {"session": "cross-venue-skew-tick", "data_dir": "research/data/cross_venue_skew",
                              "module": "research.run_cross_venue_skew_collect"},
    "polymarket_whale_tick": {"session": "polymarket-whale-tick", "data_dir": "research/data/polymarket_whale",
                              "module": "research.run_polymarket_whale_collect"},
    "polymarket_updown_arb": {"session": "polymarket-updown-arb", "data_dir": "research/data/polymarket_updown_arb",
                              "module": "research.run_polymarket_updown_arb_scan"},
    "polymarket_sharp_wallet_tick": {"session": "polymarket-sharp-wallet-tick",
                                     "data_dir": "research/data/polymarket_sharp_wallet",
                                     "module": "research.run_polymarket_sharp_wallet_collect"},
}
```

Then find the `out["processes"] = {...}` block inside `lab_status()` (currently lines 296-304):

```python
        out["processes"] = {
            "polymarket_tick": _tmux_process_status("polymarket-tick", "research/data/polymarket_tick"),
            "polymarket_arb": _tmux_process_status("polymarket-arb", "research/data/polymarket_arb"),
            "hl_orderflow_tick": _tmux_process_status("hl-orderflow-tick", "research/data/hl_orderflow_tick"),
            "cross_venue_skew_tick": _tmux_process_status("cross-venue-skew-tick", "research/data/cross_venue_skew"),
            "polymarket_whale_tick": _tmux_process_status("polymarket-whale-tick", "research/data/polymarket_whale"),
            "polymarket_updown_arb": _tmux_process_status("polymarket-updown-arb", "research/data/polymarket_updown_arb"),
        }
```

Replace with (adds one line):

```python
        out["processes"] = {
            "polymarket_tick": _tmux_process_status("polymarket-tick", "research/data/polymarket_tick"),
            "polymarket_arb": _tmux_process_status("polymarket-arb", "research/data/polymarket_arb"),
            "hl_orderflow_tick": _tmux_process_status("hl-orderflow-tick", "research/data/hl_orderflow_tick"),
            "cross_venue_skew_tick": _tmux_process_status("cross-venue-skew-tick", "research/data/cross_venue_skew"),
            "polymarket_whale_tick": _tmux_process_status("polymarket-whale-tick", "research/data/polymarket_whale"),
            "polymarket_updown_arb": _tmux_process_status("polymarket-updown-arb", "research/data/polymarket_updown_arb"),
            "polymarket_sharp_wallet_tick": _tmux_process_status("polymarket-sharp-wallet-tick", "research/data/polymarket_sharp_wallet"),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_lab_api_polymarket_sharp_wallet_status.py tests/test_lab_api_polymarket_whale_status.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add api_server/lab_api.py tests/test_lab_api_polymarket_sharp_wallet_status.py
git commit -m "feat: register polymarket sharp-wallet collector in HUD backend"
```

---

### Task 4: Hypothesis module (convergence counting + labeling)

**Files:**
- Create: `research/hypotheses/polymarket_sharp_wallet.py`
- Test: `tests/test_polymarket_sharp_wallet.py`

**Interfaces:**
- Consumes: JSONL records written by Task 2's collector — each has `conditionId`, `timestamp`, `side`, `price`, `size`, `proxyWallet`, `notional_usd`, `is_sharp_wallet`, `wallet_rank`, `wallet_pnl`.
- Produces: `load_sharp_wallet_trades(dates: list[str]) -> pd.DataFrame` (columns: `ts, condition_id, side, price, size, proxy_wallet, notional_usd, is_sharp_wallet, wallet_rank, wallet_pnl`), `build_convergence_count(trades: pd.DataFrame) -> pd.DataFrame` (columns: `ts, condition_id, side, direction, notional_usd, proxy_wallet, convergence_count, convergence_bucket`), `build_price_series(trades: pd.DataFrame, condition_id: str) -> pd.Series`, `build_labels_multi_horizon(anchors: pd.DataFrame, price_series_by_market: dict[str, pd.Series], horizons: list[int] = HORIZONS_S) -> pd.DataFrame` (columns: `ts, condition_id, horizon_s, entry_price, exit_price, direction, forward_return, convergence_bucket`). Constants `CONVERGENCE_WINDOW_S`, `MAX_CONVERGENCE_BUCKET`, `RESAMPLE_GRID_S`, `HORIZONS_S`. Task 5 (validate runner) imports all four functions and all four constants.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_polymarket_sharp_wallet.py`:

```python
import json

import pandas as pd
import pytest

import research.hypotheses.polymarket_sharp_wallet as psw
from research.hypotheses.polymarket_sharp_wallet import (
    build_convergence_count,
    build_labels_multi_horizon,
    build_price_series,
    load_sharp_wallet_trades,
)


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _raw_row(cid="c1", ts=1.0, side="BUY", price=0.5, size=100.0, wallet="0xsharp",
             is_sharp=True, rank=1, pnl=1000.0):
    return {
        "conditionId": cid, "timestamp": ts, "side": side, "price": price, "size": size,
        "proxyWallet": wallet, "notional_usd": price * size, "is_sharp_wallet": is_sharp,
        "wallet_rank": rank if is_sharp else None, "wallet_pnl": pnl if is_sharp else None,
        "transactionHash": f"tx{ts}",
    }


def _trade_row(ts, cid="c1", wallet="w1", side="BUY", is_sharp=True, notional=100.0, price=0.5):
    return {
        "ts": ts, "condition_id": cid, "side": side, "price": price, "size": notional / price,
        "proxy_wallet": wallet, "notional_usd": notional, "is_sharp_wallet": is_sharp,
        "wallet_rank": 1 if is_sharp else None, "wallet_pnl": 100.0 if is_sharp else None,
    }


def test_load_sharp_wallet_trades_reads_and_preserves_precomputed_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(psw, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "2026-07-20.jsonl", [
        _raw_row(ts=2.0, wallet="0xsharp", is_sharp=True, rank=3, pnl=200.0),
        _raw_row(ts=1.0, wallet="0xother", is_sharp=False),
    ])
    df = load_sharp_wallet_trades(["2026-07-20"])
    assert list(df["ts"]) == [1.0, 2.0]
    assert bool(df.iloc[0]["is_sharp_wallet"]) is False
    assert bool(df.iloc[1]["is_sharp_wallet"]) is True
    assert df.iloc[1]["wallet_rank"] == 3
    assert df.iloc[1]["wallet_pnl"] == 200.0


def test_load_sharp_wallet_trades_merges_multiple_dates(tmp_path, monkeypatch):
    monkeypatch.setattr(psw, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "2026-07-19.jsonl", [_raw_row(ts=1.0)])
    _write_jsonl(tmp_path / "2026-07-20.jsonl", [_raw_row(ts=2.0)])
    df = load_sharp_wallet_trades(["2026-07-19", "2026-07-20"])
    assert list(df["ts"]) == [1.0, 2.0]


def test_load_sharp_wallet_trades_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(psw, "_DATA_DIR", tmp_path)
    df = load_sharp_wallet_trades(["2020-01-01"])
    assert df.empty


def test_build_convergence_count_counts_distinct_wallets_within_window():
    df = pd.DataFrame([
        _trade_row(ts=0.0, cid="c1", wallet="w1"),
        _trade_row(ts=300.0, cid="c2", wallet="w2"),
        _trade_row(ts=650.0, cid="c3", wallet="w3"),
    ])
    out = build_convergence_count(df)
    counts = dict(zip(out["ts"], out["convergence_count"]))
    assert counts[0.0] == 1        # window [-600,0]: only itself
    assert counts[300.0] == 2      # window [-300,300]: w1(ts=0) + w2(ts=300)
    assert counts[650.0] == 2      # window [50,650]: w2(ts=300) + w3(ts=650), w1(ts=0) excluded


def test_build_convergence_count_ignores_context_trades():
    df = pd.DataFrame([
        _trade_row(ts=0.0, cid="c1", wallet="w1", is_sharp=True),
        _trade_row(ts=10.0, cid="c1", wallet="w9", is_sharp=False),
    ])
    out = build_convergence_count(df)
    assert len(out) == 1
    assert out.iloc[0]["convergence_count"] == 1


def test_build_convergence_count_caps_at_max_bucket():
    rows = [_trade_row(ts=float(i), cid=f"c{i}", wallet=f"w{i}") for i in range(5)]
    df = pd.DataFrame(rows)
    out = build_convergence_count(df)
    last = out.iloc[-1]
    assert last["convergence_count"] == 5
    assert last["convergence_bucket"] == psw.MAX_CONVERGENCE_BUCKET


def test_build_convergence_count_empty_when_no_anchors():
    df = pd.DataFrame([_trade_row(ts=0.0, wallet="w1", is_sharp=False)])
    out = build_convergence_count(df)
    assert out.empty


def test_build_price_series_ffill_grid():
    df = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "price": 0.5},
        {"ts": 12.0, "condition_id": "c1", "price": 0.6},
    ])
    series = build_price_series(df, "c1")
    assert series.loc[0.0] == pytest.approx(0.5)
    assert series.loc[5.0] == pytest.approx(0.5)
    assert series.loc[10.0] == pytest.approx(0.5)
    assert series.loc[15.0] == pytest.approx(0.6)


def test_build_price_series_empty_for_unknown_condition():
    df = pd.DataFrame([{"ts": 0.0, "condition_id": "c1", "price": 0.5}])
    series = build_price_series(df, "unknown")
    assert series.empty


def test_build_labels_multi_horizon_computes_forward_return_and_carries_bucket():
    price = pd.Series([0.5, 0.5, 0.6, 0.6, 0.7, 0.7, 0.7],
                       index=[0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0])
    anchors = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "side": "BUY", "direction": 1.0,
         "notional_usd": 100.0, "proxy_wallet": "w1", "convergence_count": 2,
         "convergence_bucket": 2},
    ])
    labels = build_labels_multi_horizon(anchors, {"c1": price}, horizons=[10, 30])
    row10 = labels[labels["horizon_s"] == 10].iloc[0]
    assert row10["forward_return"] == pytest.approx((0.6 - 0.5) / 0.5)
    assert row10["convergence_bucket"] == 2
    row30 = labels[labels["horizon_s"] == 30].iloc[0]
    assert row30["forward_return"] == pytest.approx((0.7 - 0.5) / 0.5)


def test_build_labels_multi_horizon_excludes_missing_condition():
    price = pd.Series([0.5], index=[0.0])
    anchors = pd.DataFrame([
        {"ts": 0.0, "condition_id": "unknown", "side": "BUY", "direction": 1.0,
         "notional_usd": 100.0, "proxy_wallet": "w1", "convergence_count": 1,
         "convergence_bucket": 1},
    ])
    labels = build_labels_multi_horizon(anchors, {"c1": price}, horizons=[10])
    assert labels.empty
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_sharp_wallet.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'research.hypotheses.polymarket_sharp_wallet'`

- [ ] **Step 3: Write the implementation**

Create `research/hypotheses/polymarket_sharp_wallet.py`:

```python
"""Polymarket 샤프월렛 컨버전스 가설 — 공식 리더보드 상위 지갑이 새 포지션을 잡을 때,
같은 트레일링 윈도우 안에 다른 샤프월렛이 몇 명 더 동시에(마켓 무관 — 크로스마켓)
움직였는지가 forward return과 상관 있는지 검증한다.
`research/run_polymarket_sharp_wallet_collect.py`가 쌓은 체결 원장
(research/data/polymarket_sharp_wallet/)을 읽어 컨버전스 카운트 -> 가격 시계열 ->
다중호라이즌 forward return 라벨링까지 조립한다.
`docs/superpowers/specs/2026-07-20-polymarket-sharp-wallet-design.md` §7 참고.
상수는 전부 설계 시점 고정값이며 결과를 본 뒤 바꾸지 않는다.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

_DATA_DIR = Path("research/data/polymarket_sharp_wallet")

CONVERGENCE_WINDOW_S = 600.0
MAX_CONVERGENCE_BUCKET = 3
RESAMPLE_GRID_S = 5.0
HORIZONS_S = [30, 120, 300]


def load_sharp_wallet_trades(dates: list[str]) -> pd.DataFrame:
    """research/data/polymarket_sharp_wallet/{date}.jsonl 로드. ts 오름차순 정렬.
    notional_usd/is_sharp_wallet/wallet_rank/wallet_pnl은 수집기가 이미 계산해
    저장 — 재계산 안 함. 반환 컬럼: ts, condition_id, side, price, size,
    proxy_wallet, notional_usd, is_sharp_wallet, wallet_rank, wallet_pnl."""
    rows = []
    for date in dates:
        path = _DATA_DIR / f"{date}.jsonl"
        if not path.exists():
            continue
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                rows.append({
                    "ts": float(row["timestamp"]), "condition_id": row["conditionId"],
                    "side": row["side"], "price": float(row["price"]), "size": float(row["size"]),
                    "proxy_wallet": row.get("proxyWallet"),
                    "notional_usd": float(row["notional_usd"]),
                    "is_sharp_wallet": bool(row["is_sharp_wallet"]),
                    "wallet_rank": row.get("wallet_rank"), "wallet_pnl": row.get("wallet_pnl"),
                })
    df = pd.DataFrame(rows, columns=[
        "ts", "condition_id", "side", "price", "size", "proxy_wallet",
        "notional_usd", "is_sharp_wallet", "wallet_rank", "wallet_pnl",
    ])
    return df.sort_values("ts").reset_index(drop=True)


def build_convergence_count(trades: pd.DataFrame) -> pd.DataFrame:
    """is_sharp_wallet=True인 행(anchor)만 대상. 각 anchor 시각 t에 대해 마켓
    무관하게 t-CONVERGENCE_WINDOW_S ~ t 구간에 체결이 있는 다른 anchor들의
    distinct proxy_wallet 수(자기 자신 포함)를 convergence_count로 기록.
    convergence_bucket = min(convergence_count, MAX_CONVERGENCE_BUCKET). 반환
    컬럼: ts, condition_id, side, direction, notional_usd, proxy_wallet,
    convergence_count, convergence_bucket. ts 오름차순."""
    empty = pd.DataFrame(columns=[
        "ts", "condition_id", "side", "direction", "notional_usd", "proxy_wallet",
        "convergence_count", "convergence_bucket",
    ])
    if trades.empty:
        return empty
    anchors = trades[trades["is_sharp_wallet"]].sort_values("ts").reset_index(drop=True)
    if anchors.empty:
        return empty
    ts_arr = anchors["ts"].to_numpy()
    wallets = anchors["proxy_wallet"].to_numpy()
    records = []
    for i in range(len(anchors)):
        t = ts_arr[i]
        window_start = t - CONVERGENCE_WINDOW_S
        mask = (ts_arr >= window_start) & (ts_arr <= t)
        count = len(set(wallets[mask]))
        row = anchors.iloc[i]
        direction = 1.0 if str(row["side"]).upper() == "BUY" else -1.0
        records.append({
            "ts": row["ts"], "condition_id": row["condition_id"], "side": row["side"],
            "direction": direction, "notional_usd": row["notional_usd"],
            "proxy_wallet": row["proxy_wallet"], "convergence_count": count,
            "convergence_bucket": min(count, MAX_CONVERGENCE_BUCKET),
        })
    return pd.DataFrame(records)


def build_price_series(trades: pd.DataFrame, condition_id: str) -> pd.Series:
    """해당 condition_id의 모든 행(anchor+context 구분 없이)을 RESAMPLE_GRID_S
    그리드로 ffill 리샘플. whale의 build_price_series와 동일 로직, 입력 필터만
    다름(family 대신 condition_id 단일 마켓). index=ts 그리드(등간격). 데이터
    없으면 빈 Series."""
    sub = trades[trades["condition_id"] == condition_id].sort_values("ts")
    if sub.empty:
        return pd.Series(dtype=float)
    min_ts, max_ts = sub["ts"].iloc[0], sub["ts"].iloc[-1]
    n_steps = math.ceil((max_ts - min_ts) / RESAMPLE_GRID_S) + 1
    grid = [min_ts + i * RESAMPLE_GRID_S for i in range(n_steps)]
    left = pd.DataFrame({"ts": grid})
    right = sub[["ts", "price"]].rename(columns={"price": "value"})
    merged = pd.merge_asof(left, right, on="ts", direction="backward")
    return pd.Series(merged["value"].values, index=grid)


def build_labels_multi_horizon(
    anchors: pd.DataFrame,
    price_series_by_market: dict[str, pd.Series],
    horizons: list[int] = HORIZONS_S,
) -> pd.DataFrame:
    """anchor(build_convergence_count 결과, convergence_bucket 포함)마다 각 h in
    horizons에 대해 forward_return = (price[t+h]-price[t])/price[t] * direction
    (모멘텀 컨벤션). anchor ts는 해당 마켓 그리드의 가장 가까운 이전 포인트로
    스냅한다. t+h가 그리드에 없거나 NaN이면 그 행 제외."""
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
            })
    return pd.DataFrame(records, columns=[
        "ts", "condition_id", "horizon_s", "entry_price", "exit_price",
        "direction", "forward_return", "convergence_bucket",
    ])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_sharp_wallet.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add research/hypotheses/polymarket_sharp_wallet.py tests/test_polymarket_sharp_wallet.py
git commit -m "feat: add polymarket sharp-wallet convergence hypothesis module"
```

---

### Task 5: Validate runner (empirical p-values + BH-FDR)

**Files:**
- Create: `research/run_polymarket_sharp_wallet_validate.py`
- Test: `tests/test_run_polymarket_sharp_wallet_validate.py`

**Interfaces:**
- Consumes: `research.hypotheses.polymarket_sharp_wallet.{load_sharp_wallet_trades, build_convergence_count, build_price_series, build_labels_multi_horizon}` (Task 4); `research.validation.baselines.empirical_p_value(strategy_stat: float, random_stats: list[float]) -> dict`; `research.validation.cost_model.polymarket_effective_cost_bps(spread_bps: float = POLYMARKET_SPREAD_BPS) -> float`; `research.validation.metrics.trade_metrics(trades: list[dict], min_trades: int = MIN_TRADES) -> dict`; `research.validation.multiple_testing.benjamini_hochberg(pvals: list[float], alpha: float = 0.1) -> dict` (all pre-existing, unchanged).
- Produces: `run_bucket(bucket: int, labels: pd.DataFrame) -> dict`, `main() -> None` (prints results), module-level `DATA_DIR`, `CONVERGENCE_BUCKETS`, `MIN_EVENTS`. No downstream task consumes this — it is the pipeline's terminal script.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_run_polymarket_sharp_wallet_validate.py`:

```python
from unittest.mock import patch

import pandas as pd

import research.run_polymarket_sharp_wallet_validate as val


def test_run_bucket_blocked_when_no_labels():
    labels = pd.DataFrame(columns=["ts", "condition_id", "horizon_s", "entry_price",
                                    "exit_price", "direction", "forward_return", "convergence_bucket"])
    result = val.run_bucket(1, labels)
    assert result["blocked"] is True
    assert result["bucket"] == 1


def test_run_bucket_blocked_when_below_min_events():
    rows = [{"ts": float(i), "condition_id": "c1", "horizon_s": 30, "entry_price": 0.5,
             "exit_price": 0.5, "direction": 1.0, "forward_return": 0.0,
             "convergence_bucket": 1} for i in range(5)]
    labels = pd.DataFrame(rows)
    result = val.run_bucket(1, labels)
    assert result["blocked"] is True


def test_run_bucket_computes_pvalue_when_enough_events():
    rows = [{"ts": float(i), "condition_id": "c1", "horizon_s": 30, "entry_price": 0.5,
             "exit_price": 0.55, "direction": 1.0, "forward_return": 0.1,
             "convergence_bucket": 2} for i in range(15)]
    labels = pd.DataFrame(rows)
    result = val.run_bucket(2, labels)
    assert result["blocked"] is False
    assert "30s" in result["horizons"]
    assert result["horizons"]["30s"]["n_events"] == 15
    assert result["horizons"]["30s"]["random"]["p_value"] is not None


def test_main_handles_no_data_dir_without_crash(tmp_path):
    with patch.object(val, "DATA_DIR", str(tmp_path)):
        val.main()  # 예외 없이 끝나야 함(전 버킷 BLOCKED 출력)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_sharp_wallet_validate.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'research.run_polymarket_sharp_wallet_validate'`

- [ ] **Step 3: Write the implementation**

Create `research/run_polymarket_sharp_wallet_validate.py`:

```python
"""Polymarket 샤프월렛 컨버전스 가설 검증 러너 — 통계적 유의미성 스크리닝, 실집행 없음.

`research/run_polymarket_sharp_wallet_collect.py`가 쌓은 체결 원장
(research/data/polymarket_sharp_wallet/)을 읽어 컨버전스 버킷(1/2/3) x
다중호라이즌(30s/120s/300s) forward return을 계산하고,
`research/run_polymarket_whale_validate.py`와 동일하게 랜덤 베이스라인(방향
무작위 셔플) 대비 empirical p-value를 구한다. 최대 9개 p-value를 신규 독립
BH-FDR 풀로 correction한다.

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


def run_bucket(bucket: int, labels: pd.DataFrame) -> dict:
    bucket_labels = labels[labels["convergence_bucket"] == bucket]
    if bucket_labels.empty:
        return {"bucket": bucket, "blocked": True, "reason": "라벨 없음"}
    if len(bucket_labels) < MIN_EVENTS:
        return {"bucket": bucket, "blocked": True,
                "reason": f"라벨 {len(bucket_labels)}건뿐 — 최소 표본 미달"}

    rng = _random.Random(SEED)
    horizons: dict[str, dict] = {}
    for h in sorted(bucket_labels["horizon_s"].unique()):
        sub = bucket_labels[bucket_labels["horizon_s"] == h]
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

    return {"bucket": bucket, "blocked": False, "horizons": horizons}


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
            "direction", "forward_return", "convergence_bucket",
        ])
    else:
        price_by_condition = {
            cid: build_price_series(trades, cid) for cid in anchors["condition_id"].unique()
        }
        labels = build_labels_multi_horizon(anchors, price_by_condition)

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

    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {
        "survivors": [], "n_survivors": 0, "threshold": None, "alpha": 0.1,
    }
    bh["keys"] = pval_keys

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


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_sharp_wallet_validate.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add research/run_polymarket_sharp_wallet_validate.py tests/test_run_polymarket_sharp_wallet_validate.py
git commit -m "feat: add polymarket sharp-wallet validate runner"
```

---

### Task 6: HUD frontend registration

**Files:**
- Modify: `../seokminal-dashboard/lib/api.ts:2437-2438` (`LabStatus.processes` type), `../seokminal-dashboard/lib/api.ts:2465-2466` (`CollectorKey` union)
- Modify: `../seokminal-dashboard/app/hud/page.tsx:228-231` (unit-card list)

**Interfaces:**
- Consumes: `polymarket_sharp_wallet_tick` key produced by Task 3's `lab_status()["processes"]`.
- Produces: nothing downstream — this is the pipeline's final, user-visible surface.

- [ ] **Step 1: Extend the `processes` type in `lib/api.ts`**

Find (currently lines 2432-2439, inside the `processes?` block of `LabStatus`):

```typescript
  processes?: {
    polymarket_tick?: { running: boolean; session_exists?: boolean; last_write: string | null; age_sec: number | null };
    polymarket_arb?: { running: boolean; session_exists?: boolean; last_write: string | null; age_sec: number | null };
    hl_orderflow_tick?: { running: boolean; session_exists?: boolean; last_write: string | null; age_sec: number | null };
    cross_venue_skew_tick?: { running: boolean; session_exists?: boolean; last_write: string | null; age_sec: number | null };
    polymarket_whale_tick?: { running: boolean; session_exists?: boolean; last_write: string | null; age_sec: number | null };
    polymarket_updown_arb?: { running: boolean; session_exists?: boolean; last_write: string | null; age_sec: number | null };
    error?: string;
  }
```

Replace with (adds one line before `error?: string;`):

```typescript
  processes?: {
    polymarket_tick?: { running: boolean; session_exists?: boolean; last_write: string | null; age_sec: number | null };
    polymarket_arb?: { running: boolean; session_exists?: boolean; last_write: string | null; age_sec: number | null };
    hl_orderflow_tick?: { running: boolean; session_exists?: boolean; last_write: string | null; age_sec: number | null };
    cross_venue_skew_tick?: { running: boolean; session_exists?: boolean; last_write: string | null; age_sec: number | null };
    polymarket_whale_tick?: { running: boolean; session_exists?: boolean; last_write: string | null; age_sec: number | null };
    polymarket_updown_arb?: { running: boolean; session_exists?: boolean; last_write: string | null; age_sec: number | null };
    polymarket_sharp_wallet_tick?: { running: boolean; session_exists?: boolean; last_write: string | null; age_sec: number | null };
    error?: string;
  }
```

- [ ] **Step 2: Extend the `CollectorKey` union in `lib/api.ts`**

Find (currently lines 2465-2466):

```typescript
export type CollectorKey = "polymarket_tick" | "polymarket_arb" | "hl_orderflow_tick"
  | "cross_venue_skew_tick" | "polymarket_whale_tick" | "polymarket_updown_arb";
```

Replace with:

```typescript
export type CollectorKey = "polymarket_tick" | "polymarket_arb" | "hl_orderflow_tick"
  | "cross_venue_skew_tick" | "polymarket_whale_tick" | "polymarket_updown_arb"
  | "polymarket_sharp_wallet_tick";
```

- [ ] **Step 3: Add the unit card in `app/hud/page.tsx`**

Find (currently lines 228-231, the whale collector's unit-card block):

```typescript
  if (sys?.processes?.polymarket_whale_tick) units.push({
    kind: "BOT", name: "폴리마켓 고래 체결 수집기", running: sys.processes.polymarket_whale_tick.running,
    detail: formatAge(sys.processes.polymarket_whale_tick.age_sec), href: "/orderflow", collectorKey: "polymarket_whale_tick",
  });
```

Add immediately after it (same file, same function):

```typescript
  if (sys?.processes?.polymarket_sharp_wallet_tick) units.push({
    kind: "BOT", name: "폴리마켓 샤프월렛 수집기", running: sys.processes.polymarket_sharp_wallet_tick.running,
    detail: formatAge(sys.processes.polymarket_sharp_wallet_tick.age_sec), href: "/orderflow", collectorKey: "polymarket_sharp_wallet_tick",
  });
```

- [ ] **Step 4: Type-check the frontend**

Run: `cd ../seokminal-dashboard && npx tsc --noEmit`
Expected: no new errors (pre-existing errors, if any, are unrelated to these three edits — check that no error references `lib/api.ts` or `app/hud/page.tsx` lines touched in this task)

- [ ] **Step 5: Commit**

```bash
cd ../seokminal-dashboard
git add lib/api.ts app/hud/page.tsx
git commit -m "feat: register polymarket sharp-wallet collector in HUD frontend"
cd ../seokminal-multi-venue
```

---

## After all tasks

Run the full backend test suite once to confirm nothing regressed:

```bash
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q
```

Expected: all pass except the known pre-existing failures (`test_auth.py` ×3-4, `test_backtest_happy_path`).

The collector is not started automatically by this plan — starting the `polymarket-sharp-wallet-tick` tmux session (`tmux new-session -d -s polymarket-sharp-wallet-tick /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m research.run_polymarket_sharp_wallet_collect`, run from `seokminal-multi-venue/`) and letting it accumulate enough days of data before running `run_polymarket_sharp_wallet_validate.py` is a follow-up operational step, not part of this implementation plan.
