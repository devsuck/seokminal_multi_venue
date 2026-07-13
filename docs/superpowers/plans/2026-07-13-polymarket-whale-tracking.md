# Polymarket Whale Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polymarket 뉴스/스포츠 마켓에서 고래 체결(notional z-score 이상치) 이후
가격이 그 방향으로 선행 움직이는지 검증하는 리서치 파이프라인(수집→가설→검증)을
구축한다. Paper/스크리닝 전용 — 실집행 없음.

**Architecture:** `research/run_cross_venue_skew_collect.py` /
`research/hypotheses/cross_venue_skew.py` / `research/run_cross_venue_skew_validate.py`의
3계층 구조를 그대로 재사용한다. 차이는 수집 방식(WSS 스트림 → REST 폴링)과
벤뉴 정렬 단계(3벤뉴 → 단일 벤뉴라 `align_venues` 불필요) 뿐이다.

**Tech Stack:** Python 3.14, pandas, requests, pytest(asyncio_mode=auto).

## Global Constraints

- 파이썬 실행: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`
- `@pytest.mark.asyncio` 절대 금지(asyncio_mode="auto" 전역 설정, 이번 수집기는
  동기 폴링 루프라 애초에 async 테스트 없음)
- 가설 모듈 상수(`NOTIONAL_ZSCORE_LOOKBACK=100`, `NOTIONAL_ZSCORE_WARMUP=20`,
  `WHALE_ZSCORE_THRESHOLD=2.0`, `RESAMPLE_GRID_S=5.0`, `HORIZONS_S=[30,120,300]`)는
  설계 시점 고정값 — 검증 결과를 본 뒤 바꾸지 않는다
  (`docs/superpowers/specs/2026-07-13-polymarket-whale-tracking-design.md` 6절)
- `MIN_LIQUIDITY`, 마켓 스코프 필터는 `research/polymarket_tick/market_selector.select_target_markets()`
  재사용 — 값 복제 금지
- BH-FDR은 신규 독립 풀(family×horizon만) — 다른 가설 풀과 절대 안 섞음, `alpha=0.1`
- 실주문/지갑서명/실집행 코드 작성 금지 — 전 구간 read-only 수집 + 순수함수 검증까지만
- HUD 등록 필수 — 새 tmux 수집기는 `api_server/lab_api.py`의 `processes` dict +
  `seokminal-dashboard/lib/api.ts`의 `LabStatus.processes` 타입 + `app/hud/page.tsx`
  유닛카드 3곳 전부 수정해야 완료로 친다 (하나라도 빠지면 "안 돌아가는 거 모르는" 문제 재발)

---

## Task 1: Polymarket 비용 모델 함수 추가

**Files:**
- Modify: `research/validation/cost_model.py` (파일 끝에 추가)
- Test: `tests/test_cost_model.py` (신규 — 기존 파일 없으면 생성)

**Interfaces:**
- Produces: `polymarket_effective_cost_bps(spread_bps: float = POLYMARKET_SPREAD_BPS) -> float`,
  모듈 상수 `POLYMARKET_TAKER_BPS = 0.0`, `POLYMARKET_SPREAD_BPS = 200.0`

- [ ] **Step 1: 기존 cost_model.py 확인 (참고용, 이미 읽음 — 재확인만)**

Run: `grep -n "class\|^def\|^IB_" research/validation/cost_model.py`
Expected: `hl_effective_cost_bps`, `ib_futures_effective_cost_bps` 등 기존 함수 목록 출력.

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_cost_model.py` 생성 (파일이 이미 있으면 이 테스트들을 append):

```python
from research.validation.cost_model import (
    POLYMARKET_SPREAD_BPS,
    POLYMARKET_TAKER_BPS,
    polymarket_effective_cost_bps,
)


def test_polymarket_effective_cost_bps_default():
    # taker(0.0) + spread/2(200/2=100) = 100.0
    assert polymarket_effective_cost_bps() == 100.0


def test_polymarket_effective_cost_bps_custom_spread():
    assert polymarket_effective_cost_bps(spread_bps=50.0) == 25.0


def test_polymarket_constants_values():
    assert POLYMARKET_TAKER_BPS == 0.0
    assert POLYMARKET_SPREAD_BPS == 200.0
```

- [ ] **Step 2b: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cost_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'polymarket_effective_cost_bps'`

- [ ] **Step 3: cost_model.py에 함수 추가**

`research/validation/cost_model.py` 파일 끝(IB 섹션 뒤)에 추가:

```python

# ── Polymarket 예측시장 전용 ──────────────────────────────────────────────
# ⚠️ 미검증 근사치. 공식 수수료 0%(2026-07 기준, Polymarket은 트레이딩 수수료
# 없음 — 대신 스프레드가 사실상 비용) — paper 단계 진입 전 재확인 필수.
POLYMARKET_TAKER_BPS = 0.0
POLYMARKET_SPREAD_BPS = 200.0  # 유동성≥5000 컷 통과 마켓 기준 보수적 근사


def polymarket_effective_cost_bps(spread_bps: float = POLYMARKET_SPREAD_BPS) -> float:
    """Polymarket 체결 1회당 유효 비용(bps) = taker fee + spread/2 왕복 근사."""
    return POLYMARKET_TAKER_BPS + spread_bps / 2.0
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cost_model.py -v`
Expected: 3 passed.

- [ ] **Step 5: 커밋**

```bash
git add research/validation/cost_model.py tests/test_cost_model.py
git commit -m "Polymarket 유효비용(bps) 함수 추가 — whale tracking 검증러너 선행작업"
```

---

## Task 2: 수집기 — `research/run_polymarket_whale_collect.py`

**Files:**
- Create: `research/run_polymarket_whale_collect.py`
- Test: `tests/test_run_polymarket_whale_collect.py`

**Interfaces:**
- Consumes: `polymarket.client.get_markets(limit: int = 200, active: bool = True, closed: bool = False) -> list[dict]`
  (각 dict에 `condition_id` 키 있음), `research.polymarket_tick.market_selector.select_target_markets(markets: list[dict], now: dt.datetime) -> list[dict]`
  (통과 마켓에 `family` 키("news"|"sports") 추가된 dict 반환)
- Produces: `append_trades(trades: list[dict]) -> None`, `fetch_trades(limit: int = 500) -> list[dict]`,
  `refresh_target_markets() -> dict[str, str]` (condition_id → family),
  `filter_new_trades(trades, target_markets, last_seen_ts, seen_hashes) -> tuple[list[dict], float, list[str]]`,
  `run_forever(*, fetch_fn=..., refresh_fn=..., append_fn=..., poll_interval_s=POLL_INTERVAL_S, market_refresh_interval_s=MARKET_REFRESH_INTERVAL_S, max_cycles=None) -> None`

**참고:** Data-API `/trades` 응답 필드(라이브 curl로 확인됨): `proxyWallet, side("BUY"|"SELL"),
asset, conditionId, size, price, timestamp(unix seconds, float 또는 int), title,
slug, outcome, name, transactionHash`. 이 스펙은 필드명을 그대로 딕셔너리 키로 씀
(camelCase 유지 — API 원본 그대로 저장, 변환 없음).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_run_polymarket_whale_collect.py` 생성:

```python
import datetime as dt
import json
from unittest.mock import patch

import research.run_polymarket_whale_collect as runner


def _trade(cid="c1", ts=100.0, tx="tx1", side="BUY", price=0.5, size=1000.0):
    return {
        "conditionId": cid, "timestamp": ts, "transactionHash": tx,
        "side": side, "price": price, "size": size,
        "proxyWallet": "0xabc", "asset": "tok1", "title": "t", "slug": "s",
        "outcome": "Yes", "name": "whale1",
    }


def test_filter_new_trades_keeps_only_target_condition_ids():
    trades = [_trade(cid="c1"), _trade(cid="c2", tx="tx2")]
    out, last_ts, hashes = runner.filter_new_trades(
        trades, {"c1": "news"}, last_seen_ts=0.0, seen_hashes=[],
    )
    assert len(out) == 1
    assert out[0]["conditionId"] == "c1"
    assert out[0]["family"] == "news"


def test_filter_new_trades_skips_older_than_last_seen_ts():
    trades = [_trade(ts=50.0, tx="old"), _trade(ts=150.0, tx="new")]
    out, last_ts, hashes = runner.filter_new_trades(
        trades, {"c1": "news"}, last_seen_ts=100.0, seen_hashes=[],
    )
    assert [t["transactionHash"] for t in out] == ["new"]
    assert last_ts == 150.0


def test_filter_new_trades_skips_already_seen_hash():
    trades = [_trade(tx="dup1"), _trade(tx="dup1")]
    out, last_ts, hashes = runner.filter_new_trades(
        trades, {"c1": "news"}, last_seen_ts=0.0, seen_hashes=[],
    )
    assert len(out) == 1
    assert hashes.count("dup1") == 1


def test_filter_new_trades_advances_last_seen_ts_to_max():
    trades = [_trade(ts=100.0, tx="a"), _trade(ts=300.0, tx="b"), _trade(ts=200.0, tx="c")]
    out, last_ts, hashes = runner.filter_new_trades(
        trades, {"c1": "news"}, last_seen_ts=0.0, seen_hashes=[],
    )
    assert last_ts == 300.0


def test_filter_new_trades_ring_buffer_caps_at_size():
    seen = [f"old{i}" for i in range(runner.DEDUP_HASH_RING_SIZE)]
    trades = [_trade(tx="new1")]
    out, last_ts, hashes = runner.filter_new_trades(
        trades, {"c1": "news"}, last_seen_ts=0.0, seen_hashes=seen,
    )
    assert len(hashes) == runner.DEDUP_HASH_RING_SIZE
    assert hashes[-1] == "new1"


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


def test_run_forever_refreshes_market_list_only_after_interval():
    refresh_calls = []

    def fake_refresh():
        refresh_calls.append(1)
        return {"c1": "news"}

    fake_time = [1000.0]

    def fake_time_fn():
        return fake_time[0]

    def fake_sleep(_):
        fake_time[0] += 1.0

    with patch("time.time", side_effect=fake_time_fn), patch("time.sleep", side_effect=fake_sleep):
        runner.run_forever(
            fetch_fn=lambda: [], refresh_fn=fake_refresh, append_fn=lambda t: None,
            poll_interval_s=1.0, market_refresh_interval_s=1000.0, max_cycles=3,
        )
    assert len(refresh_calls) == 1  # 최초 1회만, interval 안 지났으니 재조회 없음


def test_run_forever_polls_and_appends_new_trades_across_cycles():
    appended = []
    fetch_calls = [[_trade(ts=100.0, tx="a")], [_trade(ts=200.0, tx="b")]]

    def fake_fetch():
        return fetch_calls.pop(0) if fetch_calls else []

    with patch("time.sleep"):
        runner.run_forever(
            fetch_fn=fake_fetch, refresh_fn=lambda: {"c1": "news"},
            append_fn=lambda t: appended.extend(t),
            poll_interval_s=0.0, market_refresh_interval_s=1000.0, max_cycles=2,
        )
    assert [t["transactionHash"] for t in appended] == ["a", "b"]


def test_run_forever_continues_after_fetch_exception():
    appended = []
    calls = {"n": 0}

    def flaky_fetch():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("boom")
        return [_trade(ts=100.0, tx="a")]

    with patch("time.sleep"):
        runner.run_forever(
            fetch_fn=flaky_fetch, refresh_fn=lambda: {"c1": "news"},
            append_fn=lambda t: appended.extend(t),
            poll_interval_s=0.0, market_refresh_interval_s=1000.0, max_cycles=2,
        )
    assert [t["transactionHash"] for t in appended] == ["a"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_whale_collect.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.run_polymarket_whale_collect'`

- [ ] **Step 3: 수집기 구현**

`research/run_polymarket_whale_collect.py` 생성:

```python
"""Polymarket whale 체결(fill) 수집기 — Data-API REST 폴링, tmux로 상시 실행.

체결 전용 WSS가 없음(CLOB WSS market 채널은 오더북 델타뿐 — 확인됨,
`research/polymarket_tick/ws_collector.py` 참고). 글로벌 `/trades` 피드를 폴링해
로컬에서 대상 마켓(뉴스/스포츠, `market_selector.select_target_markets()` 기준)으로
필터링한 뒤 저장한다. Gamma 마켓 목록은 5분마다만 재조회(무거움 — 매 폴링마다
부르지 않음). family 태깅은 여기서 한다(스코프 필터링 시점에 이미 알고 있는 값이라
검증러너의 family별 그룹핑을 위해 원본에 붙여 저장 — notional z-score 등 파생 신호
계산은 여전히 가설 모듈 몫).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path

import requests

from polymarket.client import get_markets
from research.polymarket_tick.market_selector import select_target_markets

_DATA_DIR = Path("research/data/polymarket_whale")
_TRADES_URL = "https://data-api.polymarket.com/trades"
_TIMEOUT = 15

POLL_INTERVAL_S = 5.0
MARKET_REFRESH_INTERVAL_S = 300.0
DEDUP_HASH_RING_SIZE = 2000


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


def refresh_target_markets() -> dict[str, str]:
    """condition_id -> family("news"|"sports") 매핑. select_target_markets() 통과분만."""
    now = dt.datetime.now(dt.timezone.utc)
    markets = get_markets(limit=500)
    target = select_target_markets(markets, now)
    return {m["condition_id"]: m["family"] for m in target}


def filter_new_trades(
    trades: list[dict],
    target_markets: dict[str, str],
    last_seen_ts: float,
    seen_hashes: list[str],
) -> tuple[list[dict], float, list[str]]:
    """target_markets 통과 + last_seen_ts보다 새 것 + 중복 hash 아닌 것만 남기고
    family 태그를 붙인다. 반환: (필터통과 trades, 갱신된 last_seen_ts, 갱신된
    seen_hashes 링버퍼(최근 DEDUP_HASH_RING_SIZE개))."""
    seen_set = set(seen_hashes)
    out = []
    max_ts = last_seen_ts
    hashes = list(seen_hashes)
    for t in trades:
        cid = t.get("conditionId")
        family = target_markets.get(cid)
        ts = t.get("timestamp")
        h = t.get("transactionHash")
        if family is None:
            continue
        if ts is None or ts < last_seen_ts:
            continue
        if h in seen_set:
            continue
        out.append({**t, "family": family})
        seen_set.add(h)
        hashes.append(h)
        if ts > max_ts:
            max_ts = ts
    if len(hashes) > DEDUP_HASH_RING_SIZE:
        hashes = hashes[-DEDUP_HASH_RING_SIZE:]
    return out, max_ts, hashes


def run_forever(
    *,
    fetch_fn=fetch_trades,
    refresh_fn=refresh_target_markets,
    append_fn=append_trades,
    poll_interval_s: float = POLL_INTERVAL_S,
    market_refresh_interval_s: float = MARKET_REFRESH_INTERVAL_S,
    max_cycles: int | None = None,
) -> None:
    target_markets = refresh_fn()
    last_market_refresh = time.time()
    last_seen_ts = 0.0
    seen_hashes: list[str] = []
    cycle = 0
    while max_cycles is None or cycle < max_cycles:
        try:
            if time.time() - last_market_refresh >= market_refresh_interval_s:
                target_markets = refresh_fn()
                last_market_refresh = time.time()
            trades = fetch_fn()
            new_trades, last_seen_ts, seen_hashes = filter_new_trades(
                trades, target_markets, last_seen_ts, seen_hashes,
            )
            append_fn(new_trades)
        except Exception:
            logging.exception("polymarket whale poll failed, continuing")
        time.sleep(poll_interval_s)
        cycle += 1


if __name__ == "__main__":
    run_forever()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_whale_collect.py -v`
Expected: 9 passed.

- [ ] **Step 5: 커밋**

```bash
git add research/run_polymarket_whale_collect.py tests/test_run_polymarket_whale_collect.py
git commit -m "Polymarket whale 체결 수집기 추가 — Data-API REST 폴링, 뉴스/스포츠 스코프"
```

---

## Task 3: 가설 모듈 — `research/hypotheses/polymarket_whale.py`

**Files:**
- Create: `research/hypotheses/polymarket_whale.py`
- Test: `tests/test_polymarket_whale.py`

**Interfaces:**
- Consumes: 저장된 jsonl 행 형태 = Task 2의 `filter_new_trades` 출력 dict
  (`conditionId, timestamp, transactionHash, side, price, size, family, ...`)
- Produces: `load_whale_trades(dates: list[str]) -> pd.DataFrame` (컬럼: ts, condition_id,
  side, price, size, notional_usd, family), `build_notional_zscore(df) -> pd.DataFrame`
  (입력 컬럼 + notional_z), `build_spike_signal(df_with_z, threshold=WHALE_ZSCORE_THRESHOLD) -> pd.DataFrame`
  (컬럼: ts, condition_id, family, side, direction, notional_usd, notional_z),
  `build_price_series(df, condition_id) -> pd.Series` (index=ts 그리드),
  `build_labels_multi_horizon(price_by_condition: dict[str, pd.Series], spikes, horizons_s=HORIZONS_S) -> pd.DataFrame`
  (컬럼: ts, condition_id, family, horizon_s, entry_price, exit_price, direction, forward_return)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_polymarket_whale.py` 생성:

```python
import json

import pandas as pd
import pytest

import research.hypotheses.polymarket_whale as pw
from research.hypotheses.polymarket_whale import (
    build_labels_multi_horizon,
    build_notional_zscore,
    build_price_series,
    build_spike_signal,
    load_whale_trades,
)


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _row(cid="c1", ts=1.0, side="BUY", price=0.5, size=100.0, family="news"):
    return {"conditionId": cid, "timestamp": ts, "side": side, "price": price,
            "size": size, "family": family, "transactionHash": f"tx{ts}"}


def test_load_whale_trades_reads_and_computes_notional(tmp_path, monkeypatch):
    monkeypatch.setattr(pw, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "2026-07-13.jsonl", [_row(ts=2.0, price=0.5, size=100.0),
                                                  _row(ts=1.0, price=0.4, size=50.0)])
    df = load_whale_trades(["2026-07-13"])
    assert list(df["ts"]) == [1.0, 2.0]
    assert df.iloc[0]["notional_usd"] == pytest.approx(20.0)
    assert df.iloc[1]["notional_usd"] == pytest.approx(50.0)


def test_load_whale_trades_merges_multiple_dates(tmp_path, monkeypatch):
    monkeypatch.setattr(pw, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "2026-07-12.jsonl", [_row(ts=1.0)])
    _write_jsonl(tmp_path / "2026-07-13.jsonl", [_row(ts=2.0)])
    df = load_whale_trades(["2026-07-12", "2026-07-13"])
    assert list(df["ts"]) == [1.0, 2.0]


def test_load_whale_trades_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(pw, "_DATA_DIR", tmp_path)
    df = load_whale_trades(["2020-01-01"])
    assert df.empty


def test_build_notional_zscore_nan_before_warmup():
    rows = [{"ts": float(i), "condition_id": "c1", "side": "BUY", "price": 0.5,
              "size": 10.0, "notional_usd": 5.0, "family": "news"} for i in range(10)]
    df = pd.DataFrame(rows)
    out = build_notional_zscore(df)
    assert out["notional_z"].isna().all()  # WARMUP=20 미달


def test_build_notional_zscore_flags_spike_after_warmup():
    rows = [{"ts": float(i), "condition_id": "c1", "side": "BUY", "price": 0.5,
              "size": 10.0, "notional_usd": 5.0, "family": "news"} for i in range(25)]
    rows.append({"ts": 25.0, "condition_id": "c1", "side": "BUY", "price": 0.5,
                  "size": 2000.0, "notional_usd": 1000.0, "family": "news"})
    df = pd.DataFrame(rows)
    out = build_notional_zscore(df)
    last_z = out.iloc[-1]["notional_z"]
    assert last_z > pw.WHALE_ZSCORE_THRESHOLD


def test_build_notional_zscore_groups_by_condition_id_independently():
    rows = (
        [{"ts": float(i), "condition_id": "c1", "side": "BUY", "price": 0.5,
          "size": 10.0, "notional_usd": 5.0, "family": "news"} for i in range(25)]
        + [{"ts": float(i), "condition_id": "c2", "side": "BUY", "price": 0.5,
            "size": 500.0, "notional_usd": 250.0, "family": "sports"} for i in range(25)]
    )
    df = pd.DataFrame(rows)
    out = build_notional_zscore(df)
    c2_z = out[out["condition_id"] == "c2"]["notional_z"]
    assert (c2_z.dropna().abs() < 1e-6).all()  # c2는 전부 동일값 -> std=0 -> NaN 처리


def test_build_spike_signal_filters_by_threshold_and_sets_direction():
    df = pd.DataFrame([
        {"ts": 1.0, "condition_id": "c1", "side": "BUY", "notional_usd": 100.0,
         "notional_z": 2.5, "family": "news"},
        {"ts": 2.0, "condition_id": "c1", "side": "SELL", "notional_usd": 50.0,
         "notional_z": 1.0, "family": "news"},
        {"ts": 3.0, "condition_id": "c1", "side": "SELL", "notional_usd": 90.0,
         "notional_z": -2.1, "family": "news"},
    ])
    spikes = build_spike_signal(df)
    assert list(spikes["ts"]) == [1.0, 3.0]
    assert spikes.iloc[0]["direction"] == 1.0
    assert spikes.iloc[1]["direction"] == -1.0


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


def test_build_labels_multi_horizon_computes_forward_return():
    price = pd.Series([0.5, 0.5, 0.6, 0.6, 0.7, 0.7, 0.7],
                       index=[0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0])
    spikes = pd.DataFrame([
        {"ts": 0.0, "condition_id": "c1", "family": "news", "side": "BUY",
         "direction": 1.0, "notional_usd": 100.0, "notional_z": 2.5},
    ])
    labels = build_labels_multi_horizon({"c1": price}, spikes, horizons_s=[10, 30])
    row10 = labels[labels["horizon_s"] == 10].iloc[0]
    assert row10["forward_return"] == pytest.approx((0.6 - 0.5) / 0.5)
    row30 = labels[labels["horizon_s"] == 30].iloc[0]
    assert row30["forward_return"] == pytest.approx((0.7 - 0.5) / 0.5)


def test_build_labels_multi_horizon_excludes_missing_condition():
    price = pd.Series([0.5], index=[0.0])
    spikes = pd.DataFrame([
        {"ts": 0.0, "condition_id": "unknown", "family": "news", "side": "BUY",
         "direction": 1.0, "notional_usd": 100.0, "notional_z": 2.5},
    ])
    labels = build_labels_multi_horizon({"c1": price}, spikes, horizons_s=[10])
    assert labels.empty
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_whale.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.hypotheses.polymarket_whale'`

- [ ] **Step 3: 가설 모듈 구현**

`research/hypotheses/polymarket_whale.py` 생성:

```python
"""Polymarket whale tracking 가설 — 큰 체결 이후 가격이 그 방향으로 선행 이동하는지.

`research/run_polymarket_whale_collect.py`가 쌓은 체결 원장(research/data/polymarket_whale/)을
읽어 마켓별 notional z-score -> 스파이크(고래) 탐지 -> 가격 시계열 -> 다중호라이즌
forward return 라벨링까지 조립한다. 상수는 전부 설계 시점 고정값이며 결과를 본 뒤
바꾸지 않는다(`docs/superpowers/specs/2026-07-13-polymarket-whale-tracking-design.md`).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

_DATA_DIR = Path("research/data/polymarket_whale")

NOTIONAL_ZSCORE_LOOKBACK = 100  # 트레이드 개수 기준(시간 기준 아님) — 마켓별 체결빈도 편차 커서.
NOTIONAL_ZSCORE_WARMUP = 20     # 이 미만 샘플이면 z-score 미계산(NaN).
WHALE_ZSCORE_THRESHOLD = 2.0
RESAMPLE_GRID_S = 5.0           # 수집기 폴링주기(5s)와 동일 — 이보다 촘촘한 그리드는 의미 없음.
HORIZONS_S = [30, 120, 300]


def load_whale_trades(dates: list[str]) -> pd.DataFrame:
    """research/data/polymarket_whale/{date}.jsonl 로드. notional_usd=price*size
    컬럼 추가. 반환 컬럼: ts, condition_id, side, price, size, notional_usd, family.
    ts 오름차순 정렬."""
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
                price = float(row["price"])
                size = float(row["size"])
                rows.append({
                    "ts": float(row["timestamp"]), "condition_id": row["conditionId"],
                    "side": row["side"], "price": price, "size": size,
                    "notional_usd": price * size, "family": row.get("family"),
                })
    df = pd.DataFrame(rows, columns=[
        "ts", "condition_id", "side", "price", "size", "notional_usd", "family",
    ])
    return df.sort_values("ts").reset_index(drop=True)


def build_notional_zscore(df: pd.DataFrame) -> pd.DataFrame:
    """condition_id별로 그룹핑해 notional_usd의 롤링(NOTIONAL_ZSCORE_LOOKBACK, 트레이드
    개수 기준) z-score를 계산한다. 그룹 내 표본이 NOTIONAL_ZSCORE_WARMUP 미만이거나
    표준편차 0이면 z=NaN. 반환: 입력 컬럼 + notional_z, ts 오름차순."""
    if df.empty:
        return df.assign(notional_z=pd.Series(dtype=float))
    out_parts = []
    for _cid, g in df.groupby("condition_id", sort=False):
        g = g.sort_values("ts").copy()
        roll_mean = g["notional_usd"].rolling(
            window=NOTIONAL_ZSCORE_LOOKBACK, min_periods=NOTIONAL_ZSCORE_WARMUP).mean()
        roll_std = g["notional_usd"].rolling(
            window=NOTIONAL_ZSCORE_LOOKBACK, min_periods=NOTIONAL_ZSCORE_WARMUP).std()
        z = (g["notional_usd"] - roll_mean) / roll_std
        g["notional_z"] = z.where(roll_std.gt(0))
        out_parts.append(g)
    return pd.concat(out_parts).sort_values("ts").reset_index(drop=True)


def build_spike_signal(df_with_z: pd.DataFrame, threshold: float = WHALE_ZSCORE_THRESHOLD) -> pd.DataFrame:
    """|notional_z| >= threshold인 행만 남긴다(고래 체결). direction: side가 BUY면
    +1.0(가격 상승 방향), 그 외(SELL)면 -1.0. 반환 컬럼: ts, condition_id, family,
    side, direction, notional_usd, notional_z."""
    mask = df_with_z["notional_z"].abs() >= threshold
    spikes = df_with_z[mask.fillna(False)].copy()
    spikes["direction"] = spikes["side"].apply(lambda s: 1.0 if str(s).upper() == "BUY" else -1.0)
    return spikes[[
        "ts", "condition_id", "family", "side", "direction", "notional_usd", "notional_z",
    ]].reset_index(drop=True)


def build_price_series(df: pd.DataFrame, condition_id: str) -> pd.Series:
    """해당 condition_id 체결가를 RESAMPLE_GRID_S 그리드로 ffill 리샘플.
    index=ts 그리드(등간격). 데이터 없으면 빈 Series."""
    sub = df[df["condition_id"] == condition_id].sort_values("ts")
    if sub.empty:
        return pd.Series(dtype=float)
    min_ts, max_ts = sub["ts"].iloc[0], sub["ts"].iloc[-1]
    n_steps = int((max_ts - min_ts) // RESAMPLE_GRID_S) + 1
    grid = [min_ts + i * RESAMPLE_GRID_S for i in range(n_steps)]
    left = pd.DataFrame({"ts": grid})
    right = sub[["ts", "price"]].rename(columns={"price": "value"})
    merged = pd.merge_asof(left, right, on="ts", direction="backward")
    return pd.Series(merged["value"].values, index=grid)


def build_labels_multi_horizon(
    price_by_condition: dict[str, pd.Series],
    spikes: pd.DataFrame,
    horizons_s: list[int] = HORIZONS_S,
) -> pd.DataFrame:
    """스파이크마다 각 h in horizons_s에 대해 forward_return =
    (price[t+h]-price[t])/price[t] * direction(모멘텀 컨벤션). 스파이크 ts는 해당
    마켓 그리드의 가장 가까운 이전 포인트로 스냅한다. t+h가 그리드에 없거나(범위 밖)
    NaN이면 그 행 제외. horizons_s는 RESAMPLE_GRID_S의 배수라 정확히 그리드에
    떨어진다(align_venues 방식과 동일 보장)."""
    records = []
    for _, row in spikes.iterrows():
        cid = row["condition_id"]
        price = price_by_condition.get(cid)
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
        for h in horizons_s:
            exit_ts = t_grid + h
            if exit_ts not in price.index:
                continue
            exit_price = price.loc[exit_ts]
            if pd.isna(exit_price):
                continue
            forward_return = (exit_price - entry_price) / entry_price * row["direction"]
            records.append({
                "ts": t_grid, "condition_id": cid, "family": row["family"], "horizon_s": h,
                "entry_price": entry_price, "exit_price": exit_price,
                "direction": row["direction"], "forward_return": forward_return,
            })
    return pd.DataFrame(records, columns=[
        "ts", "condition_id", "family", "horizon_s", "entry_price", "exit_price",
        "direction", "forward_return",
    ])
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_whale.py -v`
Expected: 10 passed.

- [ ] **Step 5: 커밋**

```bash
git add research/hypotheses/polymarket_whale.py tests/test_polymarket_whale.py
git commit -m "Polymarket whale tracking 가설 모듈 추가 — notional z-score 스파이크 + 다중호라이즌 라벨"
```

---

## Task 4: 검증 러너 — `research/run_polymarket_whale_validate.py`

**Files:**
- Create: `research/run_polymarket_whale_validate.py`
- Test: `tests/test_run_polymarket_whale_validate.py`

**Interfaces:**
- Consumes: Task 1의 `polymarket_effective_cost_bps() -> float`, Task 3의
  `load_whale_trades`, `build_notional_zscore`, `build_spike_signal`,
  `build_price_series`, `build_labels_multi_horizon`; `research.validation.baselines.empirical_p_value`,
  `research.validation.metrics.trade_metrics`, `research.validation.multiple_testing.benjamini_hochberg`
- Produces: `run_family(family: str, df: pd.DataFrame) -> dict`, `main() -> None`
  (stdout 출력, 다른 러너들과 실행 형태 통일)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_run_polymarket_whale_validate.py` 생성:

```python
from unittest.mock import patch

import pandas as pd

import research.run_polymarket_whale_validate as val


def test_run_family_blocked_when_no_data_for_family():
    df = pd.DataFrame(columns=["ts", "condition_id", "side", "price", "size", "notional_usd", "family"])
    result = val.run_family("news", df)
    assert result["blocked"] is True
    assert result["family"] == "news"


def test_run_family_blocked_when_below_min_events():
    rows = [{"ts": float(i), "condition_id": "c1", "side": "BUY", "price": 0.5,
              "size": 10.0, "notional_usd": 5.0, "family": "news"} for i in range(5)]
    df = pd.DataFrame(rows)
    result = val.run_family("news", df)
    assert result["blocked"] is True


def test_main_handles_no_data_dir_without_crash(tmp_path):
    with patch.object(val, "DATA_DIR", str(tmp_path)):
        val.main()  # 예외 없이 끝나야 함(전 family BLOCKED 출력)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_whale_validate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.run_polymarket_whale_validate'`

- [ ] **Step 3: 검증 러너 구현**

`research/run_polymarket_whale_validate.py` 생성:

```python
"""Polymarket whale tracking 가설 검증 러너 — 통계적 유의미성 스크리닝, 실집행 없음.

`research/run_polymarket_whale_collect.py`가 쌓은 체결 원장(research/data/polymarket_whale/)을
읽어 마켓별 notional z-score 스파이크(고래 체결) -> 다중호라이즌(30s/120s/300s)
forward return을 계산하고, `research/run_cross_venue_skew_validate.py`와 동일하게
랜덤 베이스라인(체결 방향 무작위 셔플) 대비 empirical p-value를 구한다. family
(news/sports) x 호라이즌3 = 최대 6개 p-value를 신규 독립 BH-FDR 풀로 correction한다.

⚠️ 스크리닝 스크립트. 결과는 통계적 유의미성 확인일 뿐 실집행 근거 아님. walk-forward는
생략(신규 라이브 수집 직후라 표본기간 미달 — BH-FDR 통과 시 전체 파이프라인 승격 검토).
"""
from __future__ import annotations

import glob
import random as _random
import re

import pandas as pd

from research.hypotheses.polymarket_whale import (
    build_labels_multi_horizon,
    build_notional_zscore,
    build_price_series,
    build_spike_signal,
    load_whale_trades,
)
from research.validation.baselines import empirical_p_value
from research.validation.cost_model import polymarket_effective_cost_bps
from research.validation.metrics import trade_metrics
from research.validation.multiple_testing import benjamini_hochberg

DATA_DIR = "research/data/polymarket_whale"
FAMILIES = ["news", "sports"]
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


def run_family(family: str, df: pd.DataFrame) -> dict:
    fam_df = df[df["family"] == family]
    if fam_df.empty:
        return {"family": family, "blocked": True, "reason": "데이터 없음"}

    df_z = build_notional_zscore(fam_df)
    spikes = build_spike_signal(df_z)
    if spikes.empty:
        return {"family": family, "blocked": True, "reason": "스파이크 이벤트 없음"}

    price_by_condition = {
        cid: build_price_series(fam_df, cid) for cid in spikes["condition_id"].unique()
    }
    labels = build_labels_multi_horizon(price_by_condition, spikes)

    if len(labels) < MIN_EVENTS:
        return {"family": family, "blocked": True, "reason": f"라벨 {len(labels)}건뿐 — 최소 표본 미달"}

    rng = _random.Random(SEED)
    horizons: dict[str, dict] = {}
    for h in sorted(labels["horizon_s"].unique()):
        sub = labels[labels["horizon_s"] == h]
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

    return {"family": family, "blocked": False, "horizons": horizons}


def main() -> None:
    dates = _available_dates()
    df = load_whale_trades(dates) if dates else pd.DataFrame(
        columns=["ts", "condition_id", "side", "price", "size", "notional_usd", "family"])

    results = []
    pvals: list[float] = []
    pval_keys: list[str] = []

    for family in FAMILIES:
        r = run_family(family, df)
        results.append(r)
        if not r["blocked"]:
            for h_key, h_res in r["horizons"].items():
                pvals.append(h_res["random"]["p_value"])
                pval_keys.append(f"{family}:{h_key}")

    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {
        "survivors": [], "n_survivors": 0, "threshold": None, "alpha": 0.1,
    }
    bh["keys"] = pval_keys

    print(f"\n=== cost_bps(polymarket) = {COST_BPS} ===\n")
    for r in results:
        if r["blocked"]:
            print(f"{r['family']} -> BLOCKED ({r['reason']})")
            continue
        for h_key, h_res in r["horizons"].items():
            s, p = h_res["strategy"], h_res["random"]
            print(f"{r['family']}:{h_key} n_events={h_res['n_events']} "
                  f"total_pnl={s['total_pnl']} p_value={p['p_value']} percentile={p['percentile']}")

    print("\n=== BH-FDR (신규 Polymarket whale 풀, alpha=0.1) ===")
    print(f"survivors: {[k for k, s in zip(bh['keys'], bh['survivors']) if s]}")
    print(f"n_survivors: {bh['n_survivors']} / {len(pvals)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_whale_validate.py -v`
Expected: 3 passed.

- [ ] **Step 5: 커밋**

```bash
git add research/run_polymarket_whale_validate.py tests/test_run_polymarket_whale_validate.py
git commit -m "Polymarket whale tracking 검증러너 추가 — family x horizon p-value + 신규 BH-FDR 풀"
```

---

## Task 5: HUD 등록 — 백엔드 processes + 프론트 타입/카드

**Files:**
- Modify: `api_server/lab_api.py` (processes dict, `hl_orderflow_tick`/`cross_venue_skew_tick` 라인 근처)
- Modify: `seokminal-dashboard/lib/api.ts` (`LabStatus.processes` 타입)
- Modify: `seokminal-dashboard/app/hud/page.tsx` (유닛카드 push 블록)
- Test: `tests/test_lab_api_polymarket_whale_status.py`

**Interfaces:**
- Consumes: Task 2에서 만든 tmux 세션명 `polymarket-whale-tick`, 데이터 디렉토리
  `research/data/polymarket_whale`; 기존 `_tmux_process_status(session: str, data_dir: str) -> dict`
  (이미 존재, `api_server/lab_api.py:178` 부근)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_lab_api_polymarket_whale_status.py` 생성 (기존 lab_api 테스트 있으면
그 파일 스타일을 따르되, 독립 신규 파일로):

```python
from unittest.mock import patch

from api_server.lab_api import lab_status


def test_lab_status_processes_includes_polymarket_whale_tick():
    fake_status = {"running": False, "last_write": None, "age_sec": None}
    with patch("api_server.lab_api._tmux_process_status", return_value=fake_status) as mock_fn:
        result = lab_status()
    assert "polymarket_whale_tick" in result["processes"]
    calls = [c.args for c in mock_fn.call_args_list]
    assert ("polymarket-whale-tick", "research/data/polymarket_whale") in calls
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_lab_api_polymarket_whale_status.py -v`
Expected: FAIL — `AssertionError: 'polymarket_whale_tick' not in result['processes']` (또는 유사)

- [ ] **Step 3: 백엔드 processes dict에 등록**

`api_server/lab_api.py`에서 (이번 세션에 이미 있는) 다음 줄:

```python
            "cross_venue_skew_tick": _tmux_process_status("cross-venue-skew-tick", "research/data/cross_venue_skew"),
```

바로 뒤에 추가:

```python
            "polymarket_whale_tick": _tmux_process_status("polymarket-whale-tick", "research/data/polymarket_whale"),
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_lab_api_polymarket_whale_status.py -v`
Expected: 1 passed.

- [ ] **Step 5: 프론트 타입 추가**

`seokminal-dashboard/lib/api.ts`에서 `LabStatus.processes` 안, 이번 세션에 추가한
`cross_venue_skew_tick` 필드 뒤에 추가:

```typescript
    cross_venue_skew_tick?: { running: boolean; last_write: string | null; age_sec: number | null };
    polymarket_whale_tick?: { running: boolean; last_write: string | null; age_sec: number | null };
    error?: string;
```

(기존 `cross_venue_skew_tick?: ...` 줄과 `error?: string;` 줄 사이에 새 줄 삽입.)

- [ ] **Step 6: HUD 유닛카드 추가**

`seokminal-dashboard/app/hud/page.tsx`에서 이번 세션에 추가한
`cross_venue_skew_tick` 유닛카드 블록 뒤에 추가:

```tsx
    if (sys?.processes?.polymarket_whale_tick) units.push({
      kind: "BOT", name: "폴리마켓 고래 체결 수집기", running: sys.processes.polymarket_whale_tick.running,
      detail: formatAge(sys.processes.polymarket_whale_tick.age_sec), href: "/orderflow",
    });
```

- [ ] **Step 7: 프론트 타입체크**

Run: `cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-dashboard && npx tsc --noEmit`
Expected: 에러 없음(0 errors).

- [ ] **Step 8: 커밋 (백엔드 + 테스트, 별도 저장소)**

```bash
cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-multi-venue
git add api_server/lab_api.py tests/test_lab_api_polymarket_whale_status.py
git commit -m "HUD에 polymarket_whale_tick 상태 등록"
```

- [ ] **Step 9: 커밋 (프론트, 별도 저장소)**

```bash
cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-dashboard
git add lib/api.ts app/hud/page.tsx
git commit -m "HUD 유닛 로스터에 폴리마켓 고래 수집기 카드 추가"
```

---

## Task 6: tmux 수집기 실행 + 전 구간 회귀 테스트

**Files:** 없음(실행/검증 전용 태스크)

- [ ] **Step 1: 백엔드 전체 테스트 회귀 확인**

Run: `cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-multi-venue && /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: 전부 PASS, 단 프로젝트 CLAUDE.md에 기록된 pre-existing failures(`test_auth.py` 3~4건,
`test_backtest_happy_path`)는 무시 — 그 외 신규 실패가 있으면 원인 파악 후 수정.

- [ ] **Step 2: 수집기 tmux 세션으로 기동**

```bash
cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-multi-venue
tmux new-session -d -s polymarket-whale-tick \
  '/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m research.run_polymarket_whale_collect'
```

- [ ] **Step 3: 기동 확인 (수 분 후 재확인 필요 — 즉시 empty일 수 있음, 정상)**

Run: `tmux list-sessions | grep polymarket-whale-tick`
Expected: 세션 존재. `ls research/data/polymarket_whale/ 2>/dev/null` — 파일은 첫 고래
체결이 잡혀야 생성되므로 즉시 없어도 정상(수집기 살아있는지가 핵심).

- [ ] **Step 4: HUD 라이브 확인**

Run: `curl -s http://localhost:8000/lab/status | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['processes'].get('polymarket_whale_tick'))"`
Expected: `{'running': True, 'last_write': None 또는 타임스탬프, 'age_sec': ...}` — `running: True`가 핵심.
