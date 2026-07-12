# 크로스벤뉴 오더북 스큐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** HL/Binance/OKX 3개 벤뉴의 오더북 임밸런스가 서로 괴리(스큐)되는 순간이 BTC/ETH 가격의 선행지표인지 통계적으로 검증한다.

**Architecture:** 신규 수집기가 3개 벤뉴 오더북 스냅샷을 가공 없이 raw로 저장 → 신규 가설모듈이 벤뉴별 임밸런스 계산 → 공통 그리드 정렬 → 벤뉴간 괴리(divergence) → z-score 스파이크 탐지 → 다중호라이즌(5s/15s/60s) forward return 라벨링 → 신규 검증러너가 기존 `research/validation/*` 재사용해 랜덤베이스라인 p-value + BH-FDR로 스크리닝. 실집행 없음, 통계적 유의미성 검증이 목표.

**Tech Stack:** Python 3.14, pandas(이미 프로젝트 의존성, `pyproject.toml`에 `pandas>=2.0`), pytest(`asyncio_mode=auto`), 기존 `orderflow/*_adapter.py` 재사용.

## Global Constraints

- `IMBALANCE_DEPTH_N = 5` — OKX books5가 top5까지만 제공하므로 3개 벤뉴 공통 depth. 최적화 금지.
- `RESAMPLE_GRID_S = 1.0` — 정렬 그리드 간격(초).
- `FFILL_TOLERANCE_S = 5.0` — 벤뉴 스냅샷 forward-fill 허용 공백(초). 초과 시 NaN.
- `DIVERGENCE_ZSCORE_LOOKBACK = 300` — 롤링 z-score 윈도우(1s그리드 기준 300틱=5분).
- `SPIKE_ZSCORE_THRESHOLD = 2.0` — 스파이크 판정 임계값.
- `HORIZONS_S = [5, 15, 60]` — 사전등록 호라이즌, 전부 같은 BH-FDR 풀.
- 방향 컨벤션: 모멘텀 고정(스큐 방향=포지션 방향). 반대방향(평균회귀) 테스트 안 함.
- 이 값들은 첫 결과 확인 전 고정 — 결과 보고 바꾸지 않는다.
- BTC/ETH만, 코인 확장 안 함(기존 REJECT 트랙과 모집단 동일 유지).
- 신규 BH-FDR 풀은 기존 배치(16개 오더플로우 신호, context-gate 2개)와 절대 안 섞는다.
- 기존 `orderflow/*.py`(라이브 대시보드 코드패스) 무수정.
- Python 실행: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`
- `@pytest.mark.asyncio` 사용 금지(asyncio_mode=auto가 자동 처리).

**참고 — 스펙 대비 구현 디테일 보정 (설계 의도 불변, 구체화만):**
- 스펙 문서는 "`simulate_long_short`/`random_same_frequency` 재사용"이라 썼으나, 실제 코드베이스에는 이번 것과 동일한 형태(이벤트+다중호라이즌, 방향 있음)의 선례가 이미 있다 — `research/run_orderflow_futures_on_btc.py`의 `run_stop_run`. 그건 `simulate_long_short`(바 단위 연속신호용) 대신 이벤트별 direction×forward_return을 직접 계산하고, 랜덤 베이스라인은 진입 타이밍이 아니라 **방향만** `rng.choice`로 섞는다(이벤트 발생 자체는 고정, 우연히 그 방향이었을 확률만 검정). 이번 가설도 스파이크 타이밍은 고정(스파이크가 언제 뜨는지는 이미 결정된 사실)이고 검증 대상은 "그 방향이 맞았는가"이므로 `run_stop_run` 패턴이 구조적으로 더 맞다. 이 플랜은 `run_stop_run` 패턴을 따른다.
- 같은 이유로 `run_orderflow_futures_on_btc.py`(BTC/ETH 스크리닝 스크립트 전체)는 walk-forward를 쓰지 않는다(자체 docstring: "⚠️ DORMANT 확인용 스크립트. 결과는 통계적 스크리닝일 뿐"). walk-forward는 `research/hypotheses/orderflow_futures.py`(NQ/MNQ 실배치 경로)처럼 실집행을 앞둔 전체 파이프라인에서 쓰는 것으로, 지금 단계(신규 라이브 수집 시작 직후, 표본 미확정)엔 해당 안 함 — 이번도 같은 스크리닝 클래스이므로 walk-forward 생략. 스파이크가 BH-FDR을 통과하면 그때 walk-forward 포함한 전체 파이프라인으로 승격 검토(TSMOM이 Phase102에서 그렇게 승격된 선례와 동일 절차).

---

## Task 1: 벤뉴별 오더북 수집기

**Files:**
- Create: `research/run_cross_venue_skew_collect.py`
- Test: `tests/test_run_cross_venue_skew_collect.py`

**Interfaces:**
- Consumes: `orderflow.binance_adapter.BinanceOrderflowClient.stream_depth(coin) -> AsyncIterator[OrderBookSnapshot]`, `orderflow.okx_adapter.OkxOrderflowClient.stream_depth(coin) -> AsyncIterator[OrderBookSnapshot]`, `orderflow.hl_adapter.HyperliquidOrderflowClient.stream(coin) -> AsyncIterator[OrderBookSnapshot | TradeEvent]`, `orderflow.models.OrderBookSnapshot`(필드: symbol, ts, bids, asks, venues)
- Produces: `research/data/cross_venue_skew/{venue}_{coin}_{date}.jsonl` 파일들(한 줄=`{"venue":..., **OrderBookSnapshot.model_dump()}`). Task 2가 이 파일들을 읽는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_run_cross_venue_skew_collect.py` 새로 작성:

```python
import datetime as dt
import json
from unittest.mock import patch

import research.run_cross_venue_skew_collect as runner
from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent


def _book(symbol="BTC.HL", ts=1.0, price=100.0):
    return OrderBookSnapshot(
        symbol=symbol, ts=ts,
        bids=[OrderBookLevel(price=price - 1, size=1.0)],
        asks=[OrderBookLevel(price=price + 1, size=1.0)],
    )


def _trade(price=100.0, size=1.0, side="buy", ts=1.0, symbol="BTC.HL"):
    return TradeEvent(symbol=symbol, ts=ts, price=price, size=size, side=side)


class FakeClient:
    """venue별 stream()/stream_depth() 호출을 리스트로 미리 정의 —
    매 재연결 사이클마다 다음 behavior 소비. 두 메서드 다 같은 behavior 큐를 씀."""

    def __init__(self, behaviors: list):
        self._behaviors = behaviors
        self.calls: list[str] = []

    async def _consume(self, coin):
        self.calls.append(coin)
        behavior = self._behaviors[len(self.calls) - 1]
        if isinstance(behavior, Exception):
            raise behavior
        for event in behavior:
            yield event

    async def stream(self, coin):
        async for event in self._consume(coin):
            yield event

    async def stream_depth(self, coin):
        async for event in self._consume(coin):
            yield event


def test_append_snapshots_writes_jsonl_to_venue_coin_dated_file(tmp_path):
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_snapshots("binance", "BTC", [_book().model_dump(), _book(price=101.0).model_dump()])
        path = tmp_path / f"binance_BTC_{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["bids"][0]["price"] == 99.0


def test_append_snapshots_skips_write_when_empty(tmp_path):
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_snapshots("binance", "BTC", [])
    assert list(tmp_path.iterdir()) == []


async def test_run_venue_coin_forever_appends_only_book_snapshots_not_trades():
    client = FakeClient([[_book(), _trade(), _book(price=102.0)]])
    appended = []
    await runner.run_venue_coin_forever(
        "hl", "BTC", client=client,
        append_fn=lambda venue, coin, snaps: appended.extend(snaps), max_cycles=1,
    )
    assert len(appended) == 2
    assert appended[0]["bids"][0]["price"] == 99.0
    assert appended[1]["bids"][0]["price"] == 101.0


async def test_run_venue_coin_forever_uses_stream_depth_for_non_hl_venues():
    client = FakeClient([[_book()]])
    appended = []
    await runner.run_venue_coin_forever(
        "binance", "BTC", client=client,
        append_fn=lambda venue, coin, snaps: appended.extend(snaps), max_cycles=1,
    )
    assert len(appended) == 1


async def test_run_venue_coin_forever_backs_off_and_doubles_delay_on_repeated_failure():
    client = FakeClient([ConnectionError("boom"), ConnectionError("boom")])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_venue_coin_forever(
            "hl", "BTC", client=client,
            append_fn=lambda venue, coin, snaps: None, max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY, runner.RECONNECT_BASE_DELAY * 2]


async def test_run_venue_coin_forever_resets_delay_after_success():
    client = FakeClient([ConnectionError("boom"), [_book()]])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_venue_coin_forever(
            "hl", "BTC", client=client,
            append_fn=lambda venue, coin, snaps: None, max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY]


async def test_run_forever_runs_all_venue_coin_combinations_concurrently():
    made_for = []

    def factory(venue):
        made_for.append(venue)
        return FakeClient([[_book()]])

    appended = []
    await runner.run_forever(
        venues=["hl", "binance", "okx"], coins=["BTC", "ETH"],
        client_factory=factory,
        append_fn=lambda venue, coin, snaps: appended.append((venue, coin)),
        max_cycles=1,
    )
    assert len(made_for) == 6
    assert len(appended) == 6
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_cross_venue_skew_collect.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.run_cross_venue_skew_collect'`

- [ ] **Step 3: 구현 작성**

`research/run_cross_venue_skew_collect.py` 새로 작성:

```python
"""벤뉴별(HL/Binance/OKX) BTC/ETH 오더북 스냅샷 수집기 — tmux로 상시 실행.

`orderflow/multi_venue_adapter.py`의 풀링을 거치지 않고 각 벤뉴 어댑터를 직접
물어 벤뉴별 원장을 그대로 저장한다(라이브 대시보드 코드패스 무수정). 크로스벤뉴
스큐(임밸런스 괴리) 계산은 `research/hypotheses/cross_venue_skew.py`에서 나중에
수행 — 수집기는 가공하지 않는다.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from pathlib import Path

from orderflow.binance_adapter import BinanceOrderflowClient
from orderflow.hl_adapter import HyperliquidOrderflowClient
from orderflow.models import OrderBookSnapshot
from orderflow.okx_adapter import OkxOrderflowClient

_DATA_DIR = Path("research/data/cross_venue_skew")

COINS = ["BTC", "ETH"]
VENUES = ["hl", "binance", "okx"]
RECONNECT_BASE_DELAY = 2.0
RECONNECT_MAX_DELAY = 60.0


def append_snapshots(venue: str, coin: str, snapshots: list[dict]) -> None:
    if not snapshots:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{venue}_{coin}_{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
    with path.open("a") as f:
        for s in snapshots:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def _make_client(venue: str):
    if venue == "hl":
        return HyperliquidOrderflowClient()
    if venue == "binance":
        return BinanceOrderflowClient()
    if venue == "okx":
        return OkxOrderflowClient()
    raise ValueError(f"unknown venue: {venue}")


def _venue_stream(client, venue: str, coin: str):
    if venue == "hl":
        return client.stream(coin)
    return client.stream_depth(coin)


async def run_venue_coin_forever(
    venue: str,
    coin: str,
    *,
    client=None,
    append_fn=append_snapshots,
    max_cycles: int | None = None,
) -> None:
    client = client or _make_client(venue)
    cycle = 0
    delay = RECONNECT_BASE_DELAY
    while max_cycles is None or cycle < max_cycles:
        received_snapshot = False
        try:
            async for event in _venue_stream(client, venue, coin):
                if isinstance(event, OrderBookSnapshot):
                    received_snapshot = True
                    append_fn(venue, coin, [event.model_dump()])
            if received_snapshot:
                # 정상 수신하다 스트림 종료 — 백오프 불필요
                delay = RECONNECT_BASE_DELAY
            else:
                # 구독 직후 스냅샷 하나 없이 끊긴 경우 — 핫루프 방지로 백오프
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
        except Exception:
            logging.exception("cross-venue skew stream failed for %s/%s, reconnecting", venue, coin)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)
        cycle += 1


async def run_forever(
    *,
    venues: list[str] = VENUES,
    coins: list[str] = COINS,
    client_factory=_make_client,
    append_fn=append_snapshots,
    max_cycles: int | None = None,
) -> None:
    await asyncio.gather(
        *(
            run_venue_coin_forever(
                venue, coin, client=client_factory(venue), append_fn=append_fn, max_cycles=max_cycles,
            )
            for venue in venues
            for coin in coins
        )
    )


if __name__ == "__main__":
    asyncio.run(run_forever())
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_cross_venue_skew_collect.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: 커밋**

```bash
git add research/run_cross_venue_skew_collect.py tests/test_run_cross_venue_skew_collect.py
git commit -m "feat: 크로스벤뉴 오더북 스큐 벤뉴별 원장 수집기 추가"
```

---

## Task 2: 스냅샷 로딩 + 벤뉴별 임밸런스

**Files:**
- Create: `research/hypotheses/cross_venue_skew.py`
- Test: `tests/test_cross_venue_skew.py`

**Interfaces:**
- Consumes: Task 1이 쓴 `research/data/cross_venue_skew/{venue}_{coin}_{date}.jsonl` (컬럼: venue, symbol, ts, bids, asks, venues — `OrderBookSnapshot.model_dump()` 형태, bids/asks=`list[{"price":float,"size":float}]`)
- Produces: `load_venue_snapshots(venue: str, coin: str, dates: list[str]) -> pd.DataFrame`(컬럼 ts/bids/asks, ts 오름차순), `build_imbalance(df: pd.DataFrame, depth_n: int = IMBALANCE_DEPTH_N) -> pd.Series`(index=ts). Task 3이 이 둘을 그대로 씀.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_cross_venue_skew.py` 새로 작성:

```python
import json

import pandas as pd
import pytest

import research.hypotheses.cross_venue_skew as cvs
from research.hypotheses.cross_venue_skew import build_imbalance, load_venue_snapshots


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_load_venue_snapshots_reads_and_sorts_by_ts(tmp_path, monkeypatch):
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "binance_BTC_2026-07-12.jsonl", [
        {"ts": 2.0, "bids": [{"price": 99.0, "size": 1.0}], "asks": [{"price": 101.0, "size": 1.0}]},
        {"ts": 1.0, "bids": [{"price": 98.0, "size": 2.0}], "asks": [{"price": 102.0, "size": 2.0}]},
    ])
    df = load_venue_snapshots("binance", "BTC", ["2026-07-12"])
    assert list(df["ts"]) == [1.0, 2.0]


def test_load_venue_snapshots_merges_multiple_dates(tmp_path, monkeypatch):
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "binance_BTC_2026-07-12.jsonl", [
        {"ts": 1.0, "bids": [{"price": 99.0, "size": 1.0}], "asks": [{"price": 101.0, "size": 1.0}]},
    ])
    _write_jsonl(tmp_path / "binance_BTC_2026-07-13.jsonl", [
        {"ts": 2.0, "bids": [{"price": 99.0, "size": 1.0}], "asks": [{"price": 101.0, "size": 1.0}]},
    ])
    df = load_venue_snapshots("binance", "BTC", ["2026-07-12", "2026-07-13"])
    assert list(df["ts"]) == [1.0, 2.0]


def test_load_venue_snapshots_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    df = load_venue_snapshots("binance", "BTC", ["2026-01-01"])
    assert df.empty


def test_build_imbalance_neutral_when_bid_ask_equal():
    df = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 99.0, "size": 5.0}]],
        "asks": [[{"price": 101.0, "size": 5.0}]],
    })
    result = build_imbalance(df)
    assert result.iloc[0] == pytest.approx(0.5)


def test_build_imbalance_buy_heavy_above_half():
    df = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 99.0, "size": 8.0}]],
        "asks": [[{"price": 101.0, "size": 2.0}]],
    })
    result = build_imbalance(df)
    assert result.iloc[0] == pytest.approx(0.8)


def test_build_imbalance_respects_depth_n():
    df = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 99.0, "size": 1.0}, {"price": 98.0, "size": 100.0}]],
        "asks": [[{"price": 101.0, "size": 1.0}]],
    })
    result = build_imbalance(df, depth_n=1)
    assert result.iloc[0] == pytest.approx(0.5)  # depth=1이면 size=100 레벨 무시


def test_build_imbalance_empty_book_returns_neutral():
    df = pd.DataFrame({"ts": [1.0], "bids": [[]], "asks": [[]]})
    result = build_imbalance(df)
    assert result.iloc[0] == pytest.approx(0.5)


def test_build_imbalance_index_is_ts():
    df = pd.DataFrame({
        "ts": [1.0, 2.0],
        "bids": [[{"price": 99.0, "size": 1.0}], [{"price": 99.0, "size": 1.0}]],
        "asks": [[{"price": 101.0, "size": 1.0}], [{"price": 101.0, "size": 1.0}]],
    })
    result = build_imbalance(df)
    assert list(result.index) == [1.0, 2.0]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cross_venue_skew.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.hypotheses.cross_venue_skew'`

- [ ] **Step 3: 구현 작성**

`research/hypotheses/cross_venue_skew.py` 새로 작성:

```python
"""크로스벤뉴(HL/Binance/OKX) 오더북 임밸런스 괴리(스큐) 가설.

`research/run_cross_venue_skew_collect.py`가 쌓은 벤뉴별 raw 스냅샷을 읽어
임밸런스 계산 -> 공통 그리드 정렬 -> 벤뉴간 괴리 -> 스파이크 탐지 -> 다중호라이즌
forward return 라벨링까지 조립한다. 상수는 전부 설계 시점 고정값이며 결과를 본
뒤 바꾸지 않는다(`docs/superpowers/specs/2026-07-12-cross-venue-skew-design.md`).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

_DATA_DIR = Path("research/data/cross_venue_skew")

IMBALANCE_DEPTH_N = 5  # OKX books5가 top5까지만 주므로 3개 벤뉴 공통 depth.
                        # 최적화 대상 아님, 결과 보고 안 바꿈.
RESAMPLE_GRID_S = 1.0
FFILL_TOLERANCE_S = 5.0
DIVERGENCE_ZSCORE_LOOKBACK = 300
SPIKE_ZSCORE_THRESHOLD = 2.0
HORIZONS_S = [5, 15, 60]


def load_venue_snapshots(venue: str, coin: str, dates: list[str]) -> pd.DataFrame:
    """research/data/cross_venue_skew/{venue}_{coin}_{date}.jsonl 로드.
    반환 컬럼: ts(float), bids(list[dict]), asks(list[dict]). ts 오름차순 정렬."""
    rows = []
    for date in dates:
        path = _DATA_DIR / f"{venue}_{coin}_{date}.jsonl"
        if not path.exists():
            continue
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                rows.append({"ts": row["ts"], "bids": row["bids"], "asks": row["asks"]})
    df = pd.DataFrame(rows, columns=["ts", "bids", "asks"])
    return df.sort_values("ts").reset_index(drop=True)


def build_imbalance(df: pd.DataFrame, depth_n: int = IMBALANCE_DEPTH_N) -> pd.Series:
    """시점별 imbalance = sum(bid.size[:depth_n]) / (sum(bid.size[:depth_n]) + sum(ask.size[:depth_n])).
    0.5=중립, 1에 가까울수록 매수우위. 양쪽 합이 0이면 0.5. index=ts."""
    def _imb(row):
        bid_sum = sum(lvl["size"] for lvl in row["bids"][:depth_n])
        ask_sum = sum(lvl["size"] for lvl in row["asks"][:depth_n])
        total = bid_sum + ask_sum
        return bid_sum / total if total > 0 else 0.5

    values = df.apply(_imb, axis=1)
    return pd.Series(values.values, index=df["ts"].values)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cross_venue_skew.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: 커밋**

```bash
git add research/hypotheses/cross_venue_skew.py tests/test_cross_venue_skew.py
git commit -m "feat: 크로스벤뉴 스큐 - 스냅샷 로딩 + 벤뉴별 임밸런스"
```

---

## Task 3: 벤뉴간 그리드 정렬 + 가격 시계열

**Files:**
- Modify: `research/hypotheses/cross_venue_skew.py`
- Modify: `tests/test_cross_venue_skew.py`

**Interfaces:**
- Consumes: Task 2의 `load_venue_snapshots`, `build_imbalance`, `IMBALANCE_DEPTH_N`/`RESAMPLE_GRID_S`/`FFILL_TOLERANCE_S`
- Produces: `align_venues(imbalance_by_venue: dict[str, pd.Series]) -> pd.DataFrame`(index=1s그리드, 컬럼=벤뉴명), `build_price_series(raw_books_by_venue: dict[str, pd.DataFrame]) -> pd.Series`(index=1s그리드, 벤뉴 평균 mid가). Task 4·5가 `align_venues`를, Task 5가 `build_price_series`를 씀.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_cross_venue_skew.py`에 추가(파일 상단 import에 `align_venues`, `build_price_series` 추가):

```python
from research.hypotheses.cross_venue_skew import (
    align_venues,
    build_imbalance,
    build_price_series,
    load_venue_snapshots,
)


def test_align_venues_forward_fills_within_tolerance():
    a = pd.Series([0.6, 0.7], index=[1.0, 20.0])
    b = pd.Series([0.4], index=[1.0])
    aligned = align_venues({"a": a, "b": b})
    assert aligned.loc[2.0, "a"] == pytest.approx(0.6)
    assert aligned.loc[4.0, "b"] == pytest.approx(0.4)  # gap=3s, 5s 이내


def test_align_venues_nan_when_gap_exceeds_tolerance():
    a = pd.Series([0.6, 0.65], index=[1.0, 20.0])
    b = pd.Series([0.4], index=[1.0])
    aligned = align_venues({"a": a, "b": b})
    assert pd.isna(aligned.loc[9.0, "b"])  # gap=8s, 5s 초과


def test_align_venues_columns_are_venue_names():
    a = pd.Series([0.6], index=[1.0])
    b = pd.Series([0.4], index=[1.0])
    aligned = align_venues({"a": a, "b": b})
    assert set(aligned.columns) == {"a", "b"}


def test_build_price_series_averages_venue_mids():
    venue_a = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 99.0, "size": 1.0}]],
        "asks": [[{"price": 101.0, "size": 1.0}]],
    })  # mid = 100.0
    venue_b = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 98.0, "size": 1.0}]],
        "asks": [[{"price": 102.0, "size": 1.0}]],
    })  # mid = 100.0
    price = build_price_series({"a": venue_a, "b": venue_b})
    assert price.loc[1.0] == pytest.approx(100.0)


def test_build_price_series_uses_max_bid_min_ask_not_list_order():
    venue_a = pd.DataFrame({
        "ts": [1.0],
        "bids": [[{"price": 90.0, "size": 1.0}, {"price": 99.0, "size": 1.0}]],
        "asks": [[{"price": 110.0, "size": 1.0}, {"price": 101.0, "size": 1.0}]],
    })
    price = build_price_series({"a": venue_a})
    assert price.loc[1.0] == pytest.approx(100.0)  # (99+101)/2, 리스트상 첫 항목(90,110) 아님
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cross_venue_skew.py -q`
Expected: FAIL — `ImportError: cannot import name 'align_venues'`

- [ ] **Step 3: 구현 작성**

`research/hypotheses/cross_venue_skew.py` 끝에 추가:

```python
def align_venues(imbalance_by_venue: dict[str, pd.Series]) -> pd.DataFrame:
    """RESAMPLE_GRID_S 그리드로 각 벤뉴 시계열을 asof-backward-fill
    (tolerance=FFILL_TOLERANCE_S) 정렬. 컬럼=벤뉴명. tolerance 초과분은 NaN으로
    남기고(추정값으로 메우지 않음), 이후 계산에서 자연스럽게 제외된다."""
    if not imbalance_by_venue:
        return pd.DataFrame()

    non_empty = {v: s for v, s in imbalance_by_venue.items() if len(s)}
    if not non_empty:
        return pd.DataFrame(columns=list(imbalance_by_venue))

    min_ts = min(s.index.min() for s in non_empty.values())
    max_ts = max(s.index.max() for s in non_empty.values())
    n_steps = int((max_ts - min_ts) // RESAMPLE_GRID_S) + 1
    grid = [min_ts + i * RESAMPLE_GRID_S for i in range(n_steps)]

    out = pd.DataFrame(index=grid)
    for venue, series in imbalance_by_venue.items():
        s = series.sort_index()
        left = pd.DataFrame({"ts": grid})
        right = pd.DataFrame({"ts": s.index.values, "value": s.values}).sort_values("ts")
        merged = pd.merge_asof(left, right, on="ts", direction="backward", tolerance=FFILL_TOLERANCE_S)
        out[venue] = merged["value"].values
    out.index.name = "ts"
    return out


def build_price_series(raw_books_by_venue: dict[str, pd.DataFrame]) -> pd.Series:
    """RESAMPLE_GRID_S 그리드에서 벤뉴별 mid=(best_bid+best_ask)/2를 구하고
    벤뉴간 평균 — 레이블 계산용 단일 가격 시계열(코인당 1개).
    best_bid/best_ask는 리스트 순서를 신뢰하지 않고 명시적으로
    best_bid=max(bid.price), best_ask=min(ask.price)로 계산한다."""
    if not raw_books_by_venue:
        return pd.Series(dtype=float)

    def _mid(row):
        if not row["bids"] or not row["asks"]:
            return float("nan")
        best_bid = max(lvl["price"] for lvl in row["bids"])
        best_ask = min(lvl["price"] for lvl in row["asks"])
        return (best_bid + best_ask) / 2.0

    mids_by_venue: dict[str, pd.Series] = {}
    for venue, df in raw_books_by_venue.items():
        values = df.apply(_mid, axis=1)
        mids_by_venue[venue] = pd.Series(values.values, index=df["ts"].values)

    aligned = align_venues(mids_by_venue)
    return aligned.mean(axis=1, skipna=True)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cross_venue_skew.py -q`
Expected: PASS (12 passed)

- [ ] **Step 5: 커밋**

```bash
git add research/hypotheses/cross_venue_skew.py tests/test_cross_venue_skew.py
git commit -m "feat: 크로스벤뉴 스큐 - 벤뉴간 그리드 정렬 + 가격 시계열"
```

---

## Task 4: 벤뉴간 괴리 + 스파이크 탐지

**Files:**
- Modify: `research/hypotheses/cross_venue_skew.py`
- Modify: `tests/test_cross_venue_skew.py`

**Interfaces:**
- Consumes: Task 3의 `align_venues` 출력 형태(index=1s그리드, 컬럼=벤뉴명), `DIVERGENCE_ZSCORE_LOOKBACK`/`SPIKE_ZSCORE_THRESHOLD`
- Produces: `build_skew_divergence(aligned: pd.DataFrame) -> pd.DataFrame`(컬럼=벤뉴명, 값=그 벤뉴의 divergence), `build_spike_signal(divergence: pd.DataFrame, lookback=DIVERGENCE_ZSCORE_LOOKBACK, threshold=SPIKE_ZSCORE_THRESHOLD) -> pd.DataFrame`(long-format, 컬럼=ts/venue/spike/direction). Task 5가 `build_spike_signal`의 출력을 씀.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_cross_venue_skew.py`에 추가(import에 `build_skew_divergence`, `build_spike_signal` 추가):

```python
from research.hypotheses.cross_venue_skew import (
    align_venues,
    build_imbalance,
    build_price_series,
    build_skew_divergence,
    build_spike_signal,
    load_venue_snapshots,
)


def test_build_skew_divergence_computes_v_minus_mean_of_others():
    aligned = pd.DataFrame({"a": [0.8], "b": [0.4], "c": [0.5]}, index=[1.0])
    div = build_skew_divergence(aligned)
    assert div.loc[1.0, "a"] == pytest.approx(0.8 - (0.4 + 0.5) / 2)
    assert div.loc[1.0, "b"] == pytest.approx(0.4 - (0.8 + 0.5) / 2)


def test_build_skew_divergence_nan_when_fewer_than_two_valid():
    aligned = pd.DataFrame({"a": [0.8], "b": [float("nan")], "c": [float("nan")]}, index=[1.0])
    div = build_skew_divergence(aligned)
    assert pd.isna(div.loc[1.0, "a"])


def test_build_spike_signal_flags_above_threshold_after_warmup():
    n = cvs.DIVERGENCE_ZSCORE_LOOKBACK
    values = [0.0] * n + [10.0]
    divergence = pd.DataFrame({"a": values}, index=[float(i) for i in range(n + 1)])
    spikes = build_spike_signal(divergence)
    assert list(spikes["ts"]) == [float(n)]
    assert spikes.iloc[0]["venue"] == "a"
    assert spikes.iloc[0]["direction"] == 1.0


def test_build_spike_signal_no_spikes_during_warmup():
    n = cvs.DIVERGENCE_ZSCORE_LOOKBACK
    divergence = pd.DataFrame({"a": [float(i) for i in range(n - 1)]}, index=list(range(n - 1)))
    spikes = build_spike_signal(divergence)
    assert spikes.empty


def test_build_spike_signal_negative_direction():
    n = cvs.DIVERGENCE_ZSCORE_LOOKBACK
    values = [0.0] * n + [-10.0]
    divergence = pd.DataFrame({"a": values}, index=[float(i) for i in range(n + 1)])
    spikes = build_spike_signal(divergence)
    assert spikes.iloc[0]["direction"] == -1.0
```

주의: 이 스텝의 테스트는 파일 상단에 `import research.hypotheses.cross_venue_skew as cvs`가 이미 Task 2에서 추가되어 있어야 함(없으면 이 스텝에서 추가).

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cross_venue_skew.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_skew_divergence'`

- [ ] **Step 3: 구현 작성**

`research/hypotheses/cross_venue_skew.py` 끝에 추가:

```python
def build_skew_divergence(aligned: pd.DataFrame) -> pd.DataFrame:
    """벤뉴 컬럼 2개 이상 유효한 시점만 대상. 각 벤뉴 v에 대해
    divergence[v] = imbalance[v] - mean(imbalance[다른 벤뉴들])."""
    venues = list(aligned.columns)
    out = pd.DataFrame(index=aligned.index)
    valid_count = aligned.notna().sum(axis=1)
    for v in venues:
        others = [c for c in venues if c != v]
        others_mean = aligned[others].mean(axis=1, skipna=True) if others else pd.Series(float("nan"), index=aligned.index)
        div = aligned[v] - others_mean
        out[v] = div.where(valid_count >= 2)
    return out


def build_spike_signal(
    divergence: pd.DataFrame,
    lookback: int = DIVERGENCE_ZSCORE_LOOKBACK,
    threshold: float = SPIKE_ZSCORE_THRESHOLD,
) -> pd.DataFrame:
    """벤뉴별 divergence 컬럼마다 롤링(lookback) z-score 계산, |z|>=threshold인
    시점을 스파이크로 표시. long-format 반환(컬럼: ts, venue, spike, direction) —
    build_labels_multi_horizon이 이벤트 단위로 순회하기 위함."""
    records = []
    for venue in divergence.columns:
        series = divergence[venue]
        roll_mean = series.rolling(window=lookback, min_periods=lookback).mean()
        roll_std = series.rolling(window=lookback, min_periods=lookback).std()
        z = (series - roll_mean) / roll_std
        spike = (z.abs() >= threshold) & roll_std.gt(0)
        for ts, is_spike, div_val in zip(divergence.index, spike.values, series.values):
            if is_spike:
                records.append({
                    "ts": ts, "venue": venue, "spike": True,
                    "direction": 1.0 if div_val > 0 else -1.0,
                })
    return pd.DataFrame(records, columns=["ts", "venue", "spike", "direction"])
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cross_venue_skew.py -q`
Expected: PASS (17 passed)

- [ ] **Step 5: 커밋**

```bash
git add research/hypotheses/cross_venue_skew.py tests/test_cross_venue_skew.py
git commit -m "feat: 크로스벤뉴 스큐 - 벤뉴간 괴리 + z-score 스파이크 탐지"
```

---

## Task 5: 다중호라이즌 라벨링

**Files:**
- Modify: `research/hypotheses/cross_venue_skew.py`
- Modify: `tests/test_cross_venue_skew.py`

**Interfaces:**
- Consumes: Task 3의 `build_price_series` 출력(index=1s그리드), Task 4의 `build_spike_signal` 출력(컬럼: ts/venue/spike/direction), `HORIZONS_S`
- Produces: `build_labels_multi_horizon(price: pd.Series, spikes: pd.DataFrame, horizons_s: list[int] = HORIZONS_S) -> pd.DataFrame`(컬럼: ts, venue, horizon_s, entry_price, exit_price, direction, forward_return). Task 6이 이 출력을 씀.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_cross_venue_skew.py`에 추가(import에 `build_labels_multi_horizon` 추가):

```python
from research.hypotheses.cross_venue_skew import (
    align_venues,
    build_imbalance,
    build_labels_multi_horizon,
    build_price_series,
    build_skew_divergence,
    build_spike_signal,
    load_venue_snapshots,
)


def test_build_labels_multi_horizon_applies_direction_and_horizon():
    price = pd.Series([100.0, 100.0, 100.0, 100.0, 105.0, 100.0], index=[0.0, 1.0, 2.0, 3.0, 5.0, 15.0])
    spikes = pd.DataFrame([{"ts": 0.0, "venue": "a", "spike": True, "direction": 1.0}])
    labels = build_labels_multi_horizon(price, spikes, horizons_s=[5, 15])
    row5 = labels[labels["horizon_s"] == 5].iloc[0]
    assert row5["forward_return"] == pytest.approx((105.0 - 100.0) / 100.0 * 1.0)
    row15 = labels[labels["horizon_s"] == 15].iloc[0]
    assert row15["forward_return"] == pytest.approx((100.0 - 100.0) / 100.0 * 1.0)


def test_build_labels_multi_horizon_flips_sign_for_short_direction():
    price = pd.Series([100.0, 95.0], index=[0.0, 5.0])
    spikes = pd.DataFrame([{"ts": 0.0, "venue": "a", "spike": True, "direction": -1.0}])
    labels = build_labels_multi_horizon(price, spikes, horizons_s=[5])
    assert labels.iloc[0]["forward_return"] == pytest.approx((95.0 - 100.0) / 100.0 * -1.0)


def test_build_labels_multi_horizon_excludes_out_of_range_horizon():
    price = pd.Series([100.0], index=[0.0])
    spikes = pd.DataFrame([{"ts": 0.0, "venue": "a", "spike": True, "direction": 1.0}])
    labels = build_labels_multi_horizon(price, spikes, horizons_s=[5])
    assert labels.empty


def test_build_labels_multi_horizon_excludes_entry_ts_missing_from_price():
    price = pd.Series([100.0, 101.0], index=[1.0, 6.0])
    spikes = pd.DataFrame([{"ts": 0.0, "venue": "a", "spike": True, "direction": 1.0}])
    labels = build_labels_multi_horizon(price, spikes, horizons_s=[5])
    assert labels.empty
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cross_venue_skew.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_labels_multi_horizon'`

- [ ] **Step 3: 구현 작성**

`research/hypotheses/cross_venue_skew.py` 끝에 추가:

```python
def build_labels_multi_horizon(
    price: pd.Series,
    spikes: pd.DataFrame,
    horizons_s: list[int] = HORIZONS_S,
) -> pd.DataFrame:
    """스파이크 시점 t마다 각 h in horizons_s에 대해
    forward_return = (price[t+h] - price[t]) / price[t] * direction(모멘텀 컨벤션).
    t+h가 price 인덱스에 없거나(범위 밖) NaN이면 그 행 제외. price/spikes 모두
    align_venues가 만든 동일 1s그리드 위에 있으므로 t+h는 정확히 그리드 포인트에
    떨어진다(horizons_s가 전부 RESAMPLE_GRID_S의 배수)."""
    price = price.sort_index()
    records = []
    for _, row in spikes.iterrows():
        t, venue, direction = row["ts"], row["venue"], row["direction"]
        if t not in price.index or pd.isna(price.loc[t]):
            continue
        entry_price = price.loc[t]
        for h in horizons_s:
            exit_ts = t + h
            if exit_ts not in price.index:
                continue
            exit_price = price.loc[exit_ts]
            if pd.isna(exit_price):
                continue
            forward_return = (exit_price - entry_price) / entry_price * direction
            records.append({
                "ts": t, "venue": venue, "horizon_s": h,
                "entry_price": entry_price, "exit_price": exit_price,
                "direction": direction, "forward_return": forward_return,
            })
    return pd.DataFrame(records, columns=[
        "ts", "venue", "horizon_s", "entry_price", "exit_price", "direction", "forward_return",
    ])
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cross_venue_skew.py -q`
Expected: PASS (21 passed)

- [ ] **Step 5: 커밋**

```bash
git add research/hypotheses/cross_venue_skew.py tests/test_cross_venue_skew.py
git commit -m "feat: 크로스벤뉴 스큐 - 다중호라이즌 forward return 라벨링"
```

---

## Task 6: 검증러너 (BH-FDR 신규풀)

**Files:**
- Create: `research/run_cross_venue_skew_validate.py`

**Interfaces:**
- Consumes: Task 2~5의 `load_venue_snapshots`/`build_imbalance`/`align_venues`/`build_skew_divergence`/`build_spike_signal`/`build_price_series`/`build_labels_multi_horizon`, `research.validation.baselines.empirical_p_value(strategy_stat: float, random_stats: list[float]) -> dict`, `research.validation.cost_model.hl_effective_cost_bps(tier: str, taker: bool) -> float`, `research.validation.metrics.trade_metrics(trades: list[dict]) -> dict`(키: num_trades/total_pnl/...), `research.validation.multiple_testing.benjamini_hochberg(pvals: list[float], alpha: float) -> dict`(키: survivors/n_survivors/threshold/alpha)
- Produces: `main()` 실행 시 stdout에 코인×호라이즌별 결과 + BH-FDR survivors 출력. 이 태스크는 코드베이스의 다른 모듈이 import하지 않는 최종 스크립트(터미널 노드) — 자동 테스트 없음(기존 `run_orderflow_futures_on_btc.py`도 동일하게 스크립트 실행으로만 검증되는 관례).

이 태스크는 순수 스크립트라 TDD 사이클(실패하는 테스트 → 구현) 대상이 아니다 — 기존 `research/run_orderflow_futures_on_btc.py`도 테스트 파일이 없다. 대신 실제 데이터로 실행해 에러 없이 끝까지 도는지 수동 확인한다(Step 2).

- [ ] **Step 1: 구현 작성**

`research/run_cross_venue_skew_validate.py` 새로 작성:

```python
"""크로스벤뉴 오더북 스큐 가설 검증 러너 — 통계적 유의미성 스크리닝, 실집행 없음.

`research/run_cross_venue_skew_collect.py`가 쌓은 벤뉴별 원장(research/data/cross_venue_skew/)을
읽어 임밸런스 괴리 스파이크 -> 다중호라이즌(5s/15s/60s) forward return을 계산하고,
`research/run_orderflow_futures_on_btc.py`의 `run_stop_run` 패턴과 동일하게(이벤트
타이밍은 고정, 방향만 무작위로 섞는) 랜덤 베이스라인 대비 empirical p-value를 구한다.
코인2 x 호라이즌3 = 6개 p-value를 기존 오더플로우 배치들과 분리된 신규 BH-FDR 풀로
correction한다.

⚠️ 스크리닝 스크립트. 결과는 통계적 유의미성 확인일 뿐 실집행 근거 아님. walk-forward는
생략(`run_orderflow_futures_on_btc.py`와 동일 사유 — 신규 라이브 수집 직후라 표본 기간이
walk-forward 분할에 미달, BH-FDR 통과 시 전체 파이프라인으로 승격 검토).
"""
from __future__ import annotations

import glob
import random as _random
import re

from research.hypotheses.cross_venue_skew import (
    align_venues,
    build_imbalance,
    build_labels_multi_horizon,
    build_price_series,
    build_skew_divergence,
    build_spike_signal,
    load_venue_snapshots,
)
from research.validation.baselines import empirical_p_value
from research.validation.cost_model import hl_effective_cost_bps
from research.validation.metrics import trade_metrics
from research.validation.multiple_testing import benjamini_hochberg

DATA_DIR = "research/data/cross_venue_skew"
COINS = ["BTC", "ETH"]
VENUES = ["hl", "binance", "okx"]
TRADE_SIZE = 1.0
N_RUNS = 500
SEED = 42
COST_BPS = hl_effective_cost_bps("major", taker=True)
MIN_EVENTS = 10


def _available_dates(coin: str) -> list[str]:
    dates = set()
    for venue in VENUES:
        for path in glob.glob(f"{DATA_DIR}/{venue}_{coin}_*.jsonl"):
            m = re.search(r"(\d{4}-\d{2}-\d{2})\.jsonl$", path)
            if m:
                dates.add(m.group(1))
    return sorted(dates)


def run_coin(coin: str) -> dict:
    dates = _available_dates(coin)
    if not dates:
        return {"coin": coin, "blocked": True, "reason": "데이터 없음"}

    raw_by_venue = {venue: load_venue_snapshots(venue, coin, dates) for venue in VENUES}
    raw_by_venue = {v: df for v, df in raw_by_venue.items() if not df.empty}
    if len(raw_by_venue) < 2:
        return {"coin": coin, "blocked": True, "reason": f"유효 벤뉴 {len(raw_by_venue)}개뿐 — 최소 2개 필요"}

    imbalance_by_venue = {v: build_imbalance(df) for v, df in raw_by_venue.items()}
    aligned = align_venues(imbalance_by_venue)
    divergence = build_skew_divergence(aligned)
    spikes = build_spike_signal(divergence)
    price = build_price_series(raw_by_venue)
    labels = build_labels_multi_horizon(price, spikes)

    if len(labels) < MIN_EVENTS:
        return {"coin": coin, "blocked": True, "reason": f"스파이크 이벤트 {len(labels)}건뿐 — 최소 표본 미달"}

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

    return {"coin": coin, "blocked": False, "horizons": horizons}


def main() -> None:
    results = []
    pvals: list[float] = []
    pval_keys: list[str] = []

    for coin in COINS:
        r = run_coin(coin)
        results.append(r)
        if not r["blocked"]:
            for h_key, h_res in r["horizons"].items():
                pvals.append(h_res["random"]["p_value"])
                pval_keys.append(f"{coin}:{h_key}")

    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {
        "survivors": [], "n_survivors": 0, "threshold": None, "alpha": 0.1,
    }
    bh["keys"] = pval_keys

    print(f"\n=== cost_bps(HL major taker) = {COST_BPS} ===\n")
    for r in results:
        if r["blocked"]:
            print(f"{r['coin']} -> BLOCKED ({r['reason']})")
            continue
        for h_key, h_res in r["horizons"].items():
            s, p = h_res["strategy"], h_res["random"]
            print(f"{r['coin']}:{h_key} n_events={h_res['n_events']} "
                  f"total_pnl={s['total_pnl']} p_value={p['p_value']} percentile={p['percentile']}")

    print("\n=== BH-FDR (신규 크로스벤뉴 스큐 풀, alpha=0.1) ===")
    print(f"survivors: {[k for k, s in zip(bh['keys'], bh['survivors']) if s]}")
    print(f"n_survivors: {bh['n_survivors']} / {len(pvals)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 수동 실행 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 research/run_cross_venue_skew_validate.py`
Expected: `research/data/cross_venue_skew/`에 아직 데이터가 없으므로 두 코인 다 `BLOCKED (데이터 없음)` 출력, 에러 없이 종료(exit code 0). import 에러나 예외 스택트레이스가 나오면 실패.

- [ ] **Step 3: 커밋**

```bash
git add research/run_cross_venue_skew_validate.py
git commit -m "feat: 크로스벤뉴 스큐 검증러너 - 신규 BH-FDR 풀"
```

---

## 최종 확인

- [ ] 전체 테스트 스위트 실행: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
  Expected: 기존 pre-existing failures(test_auth.py ×3~4, test_backtest_happy_path) 외 전부 PASS. 신규 실패 없어야 함.
- [ ] `docs/progress.md`에 이번 작업 요약 추가(완료된 작업/변경파일/다음 할 일 — 다음 할 일: `tmux new -s cross-venue-skew-tick`으로 수집기 상시 실행 시작, 며칠 데이터 축적 후 `run_cross_venue_skew_validate.py` 재실행해 실제 스파이크 이벤트로 검증)
