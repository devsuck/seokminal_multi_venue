# 오더플로우(풋프린트) + 유동성 히트맵 — 백엔드 데이터 파이프라인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hyperliquid(BTC.HL) + IBKR(NQ)에서 실시간 오더북/체결을 받아 풋프린트·유동성 히트맵으로 집계, `/ws/orderflow/{symbol}`로 델타 스트리밍하는 백엔드 파이프라인을 만든다.

**Architecture:** `orderflow/` 신규 격리 모듈(어댑터 2개 + tick_rule + aggregator + manager) + `api_server/router_orderflow.py`(REST+WS). 매매 실행 로직과 임포트/상태 공유 없음. 심볼 수집 task는 예외를 흡수하고 지수 백오프로 재연결.

**Tech Stack:** Python 3.11+, `ib_async>=2.1.0`(IBKR), `websockets>=15.0`(Hyperliquid WS), `pydantic`(FastAPI 종속으로 이미 존재), `fastapi`, `pytest`+`pytest-asyncio`(`asyncio_mode=auto`).

## Global Constraints

- 격리: `orderflow/` 모듈은 `live_engine`/봇 실행 로직을 import하지 않는다. 반대 방향(실행 로직 → orderflow)도 금지.
- 수집 task는 개별 `try/except`로 감싸 예외를 흡수 — 앱 프로세스에 전파되지 않는다.
- 파일럿 심볼: Hyperliquid `BTC.HL`, IBKR `NQ` (나스닥 미니 선물)만 다룬다.
- WS는 델타만 전송한다 (풀 리렌더 없음). 메시지 타입: `snapshot`, `footprint_delta`, `heatmap_delta`, `status`.
- 재연결 백오프: 시작 지연 2.0s, 최대 60.0s, 실패마다 2배, 성공 시 리셋 — `research/run_polymarket_tick_collect.py`의 `RECONNECT_BASE_DELAY`/`RECONNECT_MAX_DELAY` 패턴을 그대로 재사용한다.
- 테스트는 `@pytest.mark.asyncio` 데코레이터를 쓰지 않는다 (`pytest.ini_options.asyncio_mode = "auto"`, `async def test_...`만으로 충분).
- Python 인터프리터: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`.
- 집계 데이터는 메모리 내 롤링 윈도우만 유지한다 (기본 2시간). 디스크 영속화 없음.
- 스코프 아웃: 멀티 심볼 동시 수집, 히스토리 재생, IBKR market data 구독 설정 자체(사용자 책임).

---

### Task 1: 패키지 스캐폴드 + 데이터 모델

**Files:**
- Create: `orderflow/__init__.py`
- Create: `orderflow/models.py`
- Modify: `pyproject.toml:24` (`[tool.setuptools.packages.find]` include 리스트에 `"orderflow*"` 추가)
- Test: `tests/test_orderflow_models.py`

**Interfaces:**
- Produces: `OrderBookLevel(price: float, size: float)`, `OrderBookSnapshot(symbol: str, ts: float, bids: list[OrderBookLevel], asks: list[OrderBookLevel])`, `TradeEvent(symbol: str, ts: float, price: float, size: float, side: Literal["buy","sell"])`, `FootprintCell(bucket_ts: float, price: float, buy_vol: float, sell_vol: float)`, `HeatmapCell(ts: float, price: float, size: float)` — 모두 `pydantic.BaseModel`, 이후 모든 태스크가 이 타입들을 그대로 사용한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_orderflow_models.py
from orderflow.models import (
    FootprintCell,
    HeatmapCell,
    OrderBookLevel,
    OrderBookSnapshot,
    TradeEvent,
)


def test_order_book_snapshot_round_trip():
    snap = OrderBookSnapshot(
        symbol="BTC.HL",
        ts=1720000000.0,
        bids=[OrderBookLevel(price=65000.0, size=1.5)],
        asks=[OrderBookLevel(price=65010.0, size=2.0)],
    )
    assert snap.bids[0].price == 65000.0
    assert snap.asks[0].size == 2.0


def test_trade_event_side_must_be_buy_or_sell():
    trade = TradeEvent(symbol="NQ", ts=1720000000.0, price=101.0, size=2.0, side="buy")
    assert trade.side == "buy"
    try:
        TradeEvent(symbol="NQ", ts=1720000000.0, price=101.0, size=2.0, side="hold")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for invalid side")


def test_footprint_and_heatmap_cells_construct():
    fp = FootprintCell(bucket_ts=1720000000.0, price=65000.0, buy_vol=1.0, sell_vol=0.5)
    hm = HeatmapCell(ts=1720000000.0, price=65000.0, size=3.4)
    assert fp.buy_vol == 1.0
    assert hm.size == 3.4
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'orderflow.models'` (또는 `orderflow` 자체가 없음)

- [ ] **Step 3: 최소 구현**

```python
# orderflow/__init__.py
```
(빈 파일)

```python
# orderflow/models.py
"""오더플로우(풋프린트)/유동성 히트맵 파이프라인 공용 데이터 모델.
매매 실행 로직(live_engine 등)과 이 모듈 사이에 임포트 의존을 만들지 않는다."""
from typing import Literal

from pydantic import BaseModel


class OrderBookLevel(BaseModel):
    price: float
    size: float


class OrderBookSnapshot(BaseModel):
    symbol: str
    ts: float
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]


class TradeEvent(BaseModel):
    symbol: str
    ts: float
    price: float
    size: float
    side: Literal["buy", "sell"]


class FootprintCell(BaseModel):
    bucket_ts: float
    price: float
    buy_vol: float
    sell_vol: float


class HeatmapCell(BaseModel):
    ts: float
    price: float
    size: float
```

`pyproject.toml`의 `[tool.setuptools.packages.find]` include 리스트 끝에 `"orderflow*"`를 추가:

```toml
include = ["backends*", "adapters*", "tests*", "api_server*", "backtest_runner*", "condition_engine*", "strategy_spawner*", "correlation_analysis*", "beta_analysis*", "risk_analysis*", "fred*", "ecos*", "corp_finance*", "live_engine*", "monte_carlo*", "regime_filter*", "krx*", "sec_edgar*", "ksd*", "options*", "futures*", "forex*", "hyperliquid*", "kr_universe*", "orderflow*"]
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_models.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add orderflow/__init__.py orderflow/models.py pyproject.toml tests/test_orderflow_models.py
git commit -m "feat(orderflow): add data models for footprint/heatmap pipeline"
```

---

### Task 2: 체결 방향 분류 (tick_rule)

**Files:**
- Create: `orderflow/tick_rule.py`
- Test: `tests/test_orderflow_tick_rule.py`

**Interfaces:**
- Consumes: 없음 (순수 함수, 외부 모듈 의존 없음)
- Produces: `classify(price: float, bid: float, ask: float) -> Literal["buy", "sell"]` — Task 5(`ib_adapter.py`)가 이 함수를 그대로 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_orderflow_tick_rule.py
from orderflow.tick_rule import classify


def test_price_at_or_above_ask_is_buy():
    assert classify(price=101.0, bid=100.0, ask=101.0) == "buy"
    assert classify(price=102.0, bid=100.0, ask=101.0) == "buy"


def test_price_at_or_below_bid_is_sell():
    assert classify(price=100.0, bid=100.0, ask=101.0) == "sell"
    assert classify(price=99.0, bid=100.0, ask=101.0) == "sell"


def test_price_between_bid_and_ask_uses_mid():
    # bid=100, ask=102 -> mid=101
    assert classify(price=101.0, bid=100.0, ask=102.0) == "buy"   # >= mid
    assert classify(price=100.5, bid=100.0, ask=102.0) == "sell"  # < mid
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_tick_rule.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'orderflow.tick_rule'`

- [ ] **Step 3: 최소 구현**

```python
# orderflow/tick_rule.py
"""Lee-Ready 근사 체결 방향 분류. IBKR는 체결에 방향 필드가 없어 이걸로 판정한다.
Hyperliquid는 trades 페이로드에 buyer/seller가 있어 이 함수를 타지 않는다."""
from typing import Literal


def classify(price: float, bid: float, ask: float) -> Literal["buy", "sell"]:
    if price >= ask:
        return "buy"
    if price <= bid:
        return "sell"
    mid = (bid + ask) / 2
    return "buy" if price >= mid else "sell"
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_tick_rule.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add orderflow/tick_rule.py tests/test_orderflow_tick_rule.py
git commit -m "feat(orderflow): add Lee-Ready tick rule classifier for IBKR trades"
```

---

### Task 3: 집계기 (aggregator)

**Files:**
- Create: `orderflow/aggregator.py`
- Test: `tests/test_orderflow_aggregator.py`

**Interfaces:**
- Consumes: `orderflow.models.{OrderBookSnapshot, TradeEvent, FootprintCell, HeatmapCell}` (Task 1)
- Produces: `OrderflowAggregator(tick_size: float = 1.0, footprint_bucket_sec: float = 60.0, heatmap_bucket_sec: float = 2.0, max_window_sec: float = 7200.0)` with methods `on_trade(trade: TradeEvent) -> dict`, `on_book_snapshot(book: OrderBookSnapshot) -> list[dict]`, `snapshot() -> dict` (`{"footprint": [...], "heatmap": [...]}`, 각 원소는 `FootprintCell.model_dump()`/`HeatmapCell.model_dump()`). Task 6(`manager.py`)가 이 클래스를 그대로 사용한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_orderflow_aggregator.py
from orderflow.aggregator import OrderflowAggregator
from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent


def _trade(price, size, side, ts):
    return TradeEvent(symbol="BTC.HL", ts=ts, price=price, size=size, side=side)


def test_on_trade_accumulates_buy_and_sell_volume_in_same_bucket():
    agg = OrderflowAggregator(tick_size=1.0, footprint_bucket_sec=60.0)
    d1 = agg.on_trade(_trade(65000.4, 1.0, "buy", ts=1000.0))
    d2 = agg.on_trade(_trade(65000.6, 0.5, "sell", ts=1010.0))
    assert d1 == {"type": "footprint_delta", "bucket_ts": 960.0, "price": 65000.0, "side": "buy", "delta_vol": 1.0}
    assert d2["side"] == "sell"
    assert d2["bucket_ts"] == 960.0

    snap = agg.snapshot()
    cell = next(c for c in snap["footprint"] if c["price"] == 65000.0)
    assert cell["buy_vol"] == 1.0
    assert cell["sell_vol"] == 0.5


def test_on_trade_separates_buckets_by_time():
    agg = OrderflowAggregator(tick_size=1.0, footprint_bucket_sec=60.0)
    agg.on_trade(_trade(100.0, 1.0, "buy", ts=0.0))
    agg.on_trade(_trade(100.0, 1.0, "buy", ts=120.0))
    snap = agg.snapshot()
    bucket_ts_set = {c["bucket_ts"] for c in snap["footprint"]}
    assert bucket_ts_set == {0.0, 120.0}


def test_on_book_snapshot_creates_heatmap_cells_for_each_level():
    agg = OrderflowAggregator(tick_size=1.0, heatmap_bucket_sec=2.0)
    book = OrderBookSnapshot(
        symbol="BTC.HL", ts=10.0,
        bids=[OrderBookLevel(price=99.4, size=5.0)],
        asks=[OrderBookLevel(price=101.4, size=3.0)],
    )
    deltas = agg.on_book_snapshot(book)
    assert {"type": "heatmap_delta", "ts": 10.0, "price": 99.0, "size": 5.0} in deltas
    assert {"type": "heatmap_delta", "ts": 10.0, "price": 101.0, "size": 3.0} in deltas
    snap = agg.snapshot()
    assert len(snap["heatmap"]) == 2


def test_prunes_footprint_buckets_older_than_max_window():
    agg = OrderflowAggregator(tick_size=1.0, footprint_bucket_sec=60.0, max_window_sec=120.0)
    agg.on_trade(_trade(100.0, 1.0, "buy", ts=0.0))
    agg.on_trade(_trade(100.0, 1.0, "buy", ts=300.0))  # 최신 버킷 기준 120s 밖 -> 첫 버킷 정리
    snap = agg.snapshot()
    bucket_ts_set = {c["bucket_ts"] for c in snap["footprint"]}
    assert 0.0 not in bucket_ts_set
    assert 300.0 in bucket_ts_set
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_aggregator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'orderflow.aggregator'`

- [ ] **Step 3: 최소 구현**

```python
# orderflow/aggregator.py
"""가격×시간 버킷 롤링 집계 — 풋프린트(체결량) + 히트맵(잔량). 메모리 내 윈도우만 유지."""
import math

from orderflow.models import FootprintCell, HeatmapCell, OrderBookSnapshot, TradeEvent


class OrderflowAggregator:
    def __init__(
        self,
        tick_size: float = 1.0,
        footprint_bucket_sec: float = 60.0,
        heatmap_bucket_sec: float = 2.0,
        max_window_sec: float = 7200.0,
    ) -> None:
        self._tick_size = tick_size
        self._footprint_bucket_sec = footprint_bucket_sec
        self._heatmap_bucket_sec = heatmap_bucket_sec
        self._max_window_sec = max_window_sec
        self._footprint: dict[tuple[float, float], FootprintCell] = {}
        self._heatmap: dict[tuple[float, float], HeatmapCell] = {}

    def _round_price(self, price: float) -> float:
        return round(round(price / self._tick_size) * self._tick_size, 8)

    def _bucket(self, ts: float, bucket_sec: float) -> float:
        return math.floor(ts / bucket_sec) * bucket_sec

    def _prune(self, buckets: dict[tuple[float, float], object], latest_bucket_ts: float) -> None:
        cutoff = latest_bucket_ts - self._max_window_sec
        stale = [key for key in buckets if key[0] < cutoff]
        for key in stale:
            del buckets[key]

    def on_trade(self, trade: TradeEvent) -> dict:
        price = self._round_price(trade.price)
        bucket_ts = self._bucket(trade.ts, self._footprint_bucket_sec)
        key = (bucket_ts, price)
        cell = self._footprint.get(key)
        if cell is None:
            cell = FootprintCell(bucket_ts=bucket_ts, price=price, buy_vol=0.0, sell_vol=0.0)
            self._footprint[key] = cell
        if trade.side == "buy":
            cell.buy_vol += trade.size
        else:
            cell.sell_vol += trade.size
        self._prune(self._footprint, bucket_ts)
        return {
            "type": "footprint_delta",
            "bucket_ts": bucket_ts,
            "price": price,
            "side": trade.side,
            "delta_vol": trade.size,
        }

    def on_book_snapshot(self, book: OrderBookSnapshot) -> list[dict]:
        bucket_ts = self._bucket(book.ts, self._heatmap_bucket_sec)
        deltas = []
        for level in (*book.bids, *book.asks):
            price = self._round_price(level.price)
            key = (bucket_ts, price)
            self._heatmap[key] = HeatmapCell(ts=bucket_ts, price=price, size=level.size)
            deltas.append({"type": "heatmap_delta", "ts": bucket_ts, "price": price, "size": level.size})
        self._prune(self._heatmap, bucket_ts)
        return deltas

    def snapshot(self) -> dict:
        return {
            "footprint": [c.model_dump() for c in self._footprint.values()],
            "heatmap": [c.model_dump() for c in self._heatmap.values()],
        }
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_aggregator.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add orderflow/aggregator.py tests/test_orderflow_aggregator.py
git commit -m "feat(orderflow): add footprint/heatmap rolling aggregator"
```

---

### Task 4: Hyperliquid WS 어댑터

**Files:**
- Create: `orderflow/hl_adapter.py`
- Test: `tests/test_orderflow_hl_adapter.py`

**Interfaces:**
- Consumes: `orderflow.models.{OrderBookLevel, OrderBookSnapshot, TradeEvent}` (Task 1)
- Produces: `HyperliquidOrderflowClient(base_url: str = HL_WS_URL, connect_fn=websockets.connect)` with `async def stream(self, coin: str) -> AsyncIterator[OrderBookSnapshot | TradeEvent]`. Task 6(`manager.py`)가 `.stream(coin)`을 호출한다. 심볼은 `f"{coin}.HL"` 형태로 정규화되어 나온다 (기존 프론트 심볼 접미사 컨벤션과 일치).

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_orderflow_hl_adapter.py
import json

from orderflow.hl_adapter import HyperliquidOrderflowClient, parse_hl_message
from orderflow.models import OrderBookSnapshot, TradeEvent


class FakeConnection:
    def __init__(self, incoming: list[str]):
        self._incoming = incoming
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for msg in self._incoming:
            yield msg

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeConnect:
    def __init__(self, incoming: list[str]):
        self._incoming = incoming
        self.called_with = None

    def __call__(self, uri: str):
        self.called_with = uri
        return FakeConnection(self._incoming)


def test_parse_hl_message_l2book():
    raw = json.dumps({
        "channel": "l2Book",
        "data": {
            "coin": "BTC", "time": 1720000000000,
            "levels": [
                [{"px": "65000.0", "sz": "1.5", "n": 2}],
                [{"px": "65010.0", "sz": "2.0", "n": 1}],
            ],
        },
    })
    events = parse_hl_message(raw, coin="BTC")
    assert len(events) == 1
    snap = events[0]
    assert isinstance(snap, OrderBookSnapshot)
    assert snap.symbol == "BTC.HL"
    assert snap.ts == 1720000000.0
    assert snap.bids[0].price == 65000.0
    assert snap.asks[0].size == 2.0


def test_parse_hl_message_trades_maps_side():
    raw = json.dumps({
        "channel": "trades",
        "data": [
            {"coin": "BTC", "side": "B", "px": "65000.0", "sz": "0.1", "time": 1720000001000},
            {"coin": "BTC", "side": "A", "px": "64990.0", "sz": "0.2", "time": 1720000002000},
        ],
    })
    events = parse_hl_message(raw, coin="BTC")
    assert len(events) == 2
    assert all(isinstance(e, TradeEvent) for e in events)
    assert events[0].side == "buy"
    assert events[1].side == "sell"
    assert events[0].symbol == "BTC.HL"


def test_parse_hl_message_ignores_unknown_channel():
    raw = json.dumps({"channel": "subscriptionResponse", "data": {}})
    assert parse_hl_message(raw, coin="BTC") == []


def test_parse_hl_message_ignores_malformed_json():
    assert parse_hl_message("not json", coin="BTC") == []


async def test_stream_subscribes_l2book_and_trades_then_yields_parsed_events():
    raw_book = json.dumps({
        "channel": "l2Book",
        "data": {"coin": "BTC", "time": 1720000000000, "levels": [[], []]},
    })
    fake_connect = FakeConnect([raw_book])
    client = HyperliquidOrderflowClient(connect_fn=fake_connect)
    events = [e async for e in client.stream("BTC")]
    assert len(events) == 1
    assert isinstance(events[0], OrderBookSnapshot)
    assert fake_connect.called_with == client._base_url
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_hl_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'orderflow.hl_adapter'`

- [ ] **Step 3: 최소 구현**

```python
# orderflow/hl_adapter.py
"""Hyperliquid 퍼블릭 WS(L2Book + trades) 어댑터. 신규 클라이언트 — 기존 hyperliquid/client.py(REST)와 별개."""
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets

from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent

HL_WS_URL = "wss://api.hyperliquid.xyz/ws"


class HyperliquidOrderflowClient:
    def __init__(
        self,
        base_url: str = HL_WS_URL,
        connect_fn: Callable[[str], Any] = websockets.connect,
    ) -> None:
        self._base_url = base_url
        self._connect_fn = connect_fn

    async def stream(self, coin: str) -> AsyncIterator[OrderBookSnapshot | TradeEvent]:
        async with self._connect_fn(self._base_url) as connection:
            await connection.send(json.dumps({"method": "subscribe", "subscription": {"type": "l2Book", "coin": coin}}))
            await connection.send(json.dumps({"method": "subscribe", "subscription": {"type": "trades", "coin": coin}}))
            async for raw in connection:
                for event in parse_hl_message(raw, coin=coin):
                    yield event


def parse_hl_message(raw: str, coin: str) -> list[OrderBookSnapshot | TradeEvent]:
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(msg, dict):
        return []

    channel = msg.get("channel")
    data = msg.get("data")

    if channel == "l2Book" and isinstance(data, dict):
        levels = data.get("levels") or [[], []]
        bids_raw, asks_raw = levels[0], levels[1]
        return [OrderBookSnapshot(
            symbol=f"{coin}.HL",
            ts=data["time"] / 1000.0,
            bids=[OrderBookLevel(price=float(b["px"]), size=float(b["sz"])) for b in bids_raw],
            asks=[OrderBookLevel(price=float(a["px"]), size=float(a["sz"])) for a in asks_raw],
        )]

    if channel == "trades" and isinstance(data, list):
        events: list[OrderBookSnapshot | TradeEvent] = []
        for t in data:
            events.append(TradeEvent(
                symbol=f"{coin}.HL",
                ts=t["time"] / 1000.0,
                price=float(t["px"]),
                size=float(t["sz"]),
                side="buy" if t.get("side") == "B" else "sell",
            ))
        return events

    return []
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_hl_adapter.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add orderflow/hl_adapter.py tests/test_orderflow_hl_adapter.py
git commit -m "feat(orderflow): add Hyperliquid L2Book/trades WS adapter"
```

---

### Task 5: IBKR 지속 연결 어댑터

**Files:**
- Create: `orderflow/ib_adapter.py`
- Test: `tests/test_orderflow_ib_adapter.py`

**Interfaces:**
- Consumes: `orderflow.models.{OrderBookLevel, OrderBookSnapshot, TradeEvent}` (Task 1), `orderflow.tick_rule.classify` (Task 2)
- Produces: `IBOrderflowClient(host=None, port=7497, client_id=1, ib=None)` with `async def stream(self, symbol: str, connect_timeout: float = 15.0) -> AsyncIterator[OrderBookSnapshot | TradeEvent]`. Task 6(`manager.py`)가 `.stream(symbol)`을 호출한다. 기존 `backends/ib/client.py`의 `IBClient`는 건드리지 않는다 — 이건 별도 클래스.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_orderflow_ib_adapter.py
import datetime as dt

from orderflow.ib_adapter import IBOrderflowClient
from orderflow.models import OrderBookSnapshot, TradeEvent


class FakeTickByTickLast:
    def __init__(self, time, price, size):
        self.time = time
        self.price = price
        self.size = size


class FakeTickByTickBidAsk:
    def __init__(self, time, bidPrice, askPrice):
        self.time = time
        self.bidPrice = bidPrice
        self.askPrice = askPrice


class FakeUpdateEvent:
    def __init__(self, ticker, batches):
        self._ticker = ticker
        self._batches = batches

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for batch in self._batches:
            self._ticker.tickByTicks = list(batch)
            yield self._ticker


class FakeTicker:
    def __init__(self, batches):
        self.tickByTicks: list = []
        self.updateEvent = FakeUpdateEvent(self, batches)


class FakeDomLevel:
    def __init__(self, price, size):
        self.price = price
        self.size = size


class FakeDepthUpdateEvent:
    def __init__(self, ticker, batches):
        self._ticker = ticker
        self._batches = batches

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for bids, asks in self._batches:
            self._ticker.domBids = bids
            self._ticker.domAsks = asks
            yield self._ticker


class FakeDepthTicker:
    def __init__(self, batches):
        self.domBids: list = []
        self.domAsks: list = []
        self.updateEvent = FakeDepthUpdateEvent(self, batches)


class FakeMultiIB:
    def __init__(self, last_batches, bidask_batches, depth_batches):
        self.connect_calls: list[tuple] = []
        self.qualify_calls: list[str] = []
        self.tick_calls: list[str] = []
        self.depth_calls = 0
        self._last_ticker = FakeTicker(last_batches)
        self._bidask_ticker = FakeTicker(bidask_batches)
        self._depth_ticker = FakeDepthTicker(depth_batches)

    async def connectAsync(self, host, port, client_id, timeout=15):
        self.connect_calls.append((host, port, client_id))

    async def qualifyContractsAsync(self, contract):
        self.qualify_calls.append(contract.symbol)

    def reqTickByTickData(self, contract, tickType):
        self.tick_calls.append(tickType)
        return self._bidask_ticker if tickType == "BidAsk" else self._last_ticker

    def reqMktDepth(self, contract, numRows=10):
        self.depth_calls += 1
        return self._depth_ticker


async def test_stream_yields_trade_classified_by_bidask_then_book_snapshot():
    t = dt.datetime(2026, 7, 9, 12, 0, 0, tzinfo=dt.timezone.utc)
    ib = FakeMultiIB(
        last_batches=[[FakeTickByTickLast(time=t, price=101.0, size=2.0)]],
        bidask_batches=[[FakeTickByTickBidAsk(time=t, bidPrice=100.0, askPrice=101.0)]],
        depth_batches=[([FakeDomLevel(99.0, 5.0)], [FakeDomLevel(102.0, 3.0)])],
    )
    client = IBOrderflowClient(ib=ib, client_id=1)
    agen = client.stream("NQ")
    try:
        trade = await agen.__anext__()
        book = await agen.__anext__()
    finally:
        await agen.aclose()

    assert isinstance(trade, TradeEvent)
    assert trade.symbol == "NQ"
    assert trade.price == 101.0
    assert trade.side == "buy"  # price == ask -> buy (tick_rule.classify)

    assert isinstance(book, OrderBookSnapshot)
    assert book.symbol == "NQ"
    assert book.bids[0].price == 99.0
    assert book.asks[0].price == 102.0

    assert set(ib.tick_calls) == {"Last", "BidAsk"}
    assert ib.depth_calls == 1
    assert ib.connect_calls == [("127.0.0.1", 7497, 1)]


async def test_stream_skips_trade_before_any_bidask_seen():
    t = dt.datetime(2026, 7, 9, 12, 0, 0, tzinfo=dt.timezone.utc)
    ib = FakeMultiIB(
        last_batches=[[FakeTickByTickLast(time=t, price=101.0, size=2.0)]],
        bidask_batches=[[]],  # 빈 배치 — best_bid/ask 갱신 없음
        depth_batches=[([], [])],
    )
    client = IBOrderflowClient(ib=ib, client_id=2)
    agen = client.stream("NQ")
    try:
        first = await agen.__anext__()  # bidask 배치가 비어 트레이드 스킵 -> 다음은 depth 스냅샷
    finally:
        await agen.aclose()
    assert isinstance(first, OrderBookSnapshot)
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_ib_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'orderflow.ib_adapter'`

- [ ] **Step 3: 최소 구현**

```python
# orderflow/ib_adapter.py
"""IBKR 심볼별 지속 연결 어댑터 — reqMktDepth + reqTickByTickData(Last, BidAsk) 동시 구독.
기존 backends/ib/client.py의 IBClient(호출 단위 연결)는 건드리지 않는다 — 이건 별도 클래스."""
import asyncio
import datetime as dt
import os
from collections.abc import AsyncIterator

from ib_async import IB
from ib_async.contract import Contract, Future, Stock

from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent
from orderflow.tick_rule import classify

DEPTH_ROWS = 10
_FUTURES_SYMBOLS = {"NQ": "CME"}


class IBOrderflowClient:
    def __init__(
        self,
        host: str | None = None,
        port: int = 7497,
        client_id: int = 1,
        ib: IB | None = None,
    ) -> None:
        self._host = host or os.environ.get("IB_HOST", "127.0.0.1")
        self._port = port
        self._client_id = client_id
        self._ib = ib if ib is not None else IB()

    def _contract(self, symbol: str) -> Contract:
        exchange = _FUTURES_SYMBOLS.get(symbol)
        if exchange:
            return Future(symbol=symbol, exchange=exchange, currency="USD")
        return Stock(symbol, "SMART", "USD")

    async def stream(
        self, symbol: str, connect_timeout: float = 15.0
    ) -> AsyncIterator[OrderBookSnapshot | TradeEvent]:
        await self._ib.connectAsync(self._host, self._port, self._client_id, timeout=connect_timeout)
        contract = self._contract(symbol)
        await self._ib.qualifyContractsAsync(contract)

        last_ticker = self._ib.reqTickByTickData(contract, "Last")
        bidask_ticker = self._ib.reqTickByTickData(contract, "BidAsk")
        depth_ticker = self._ib.reqMktDepth(contract, numRows=DEPTH_ROWS)

        last_iter = last_ticker.updateEvent.__aiter__()
        bidask_iter = bidask_ticker.updateEvent.__aiter__()
        depth_iter = depth_ticker.updateEvent.__aiter__()

        last_task = asyncio.ensure_future(last_iter.__anext__())
        bidask_task = asyncio.ensure_future(bidask_iter.__anext__())
        depth_task = asyncio.ensure_future(depth_iter.__anext__())

        best_bid: float | None = None
        best_ask: float | None = None

        try:
            while True:
                done, _ = await asyncio.wait(
                    {last_task, bidask_task, depth_task}, return_when=asyncio.FIRST_COMPLETED
                )

                if bidask_task in done:
                    try:
                        bidask_task.result()
                    except StopAsyncIteration:
                        return
                    for tick in bidask_ticker.tickByTicks:
                        best_bid, best_ask = tick.bidPrice, tick.askPrice
                    bidask_ticker.tickByTicks.clear()
                    bidask_task = asyncio.ensure_future(bidask_iter.__anext__())

                if last_task in done:
                    try:
                        last_task.result()
                    except StopAsyncIteration:
                        return
                    for tick in last_ticker.tickByTicks:
                        if best_bid is not None and best_ask is not None:
                            side = classify(tick.price, best_bid, best_ask)
                            yield TradeEvent(
                                symbol=symbol,
                                ts=tick.time.timestamp(),
                                price=tick.price,
                                size=tick.size,
                                side=side,
                            )
                    last_ticker.tickByTicks.clear()
                    last_task = asyncio.ensure_future(last_iter.__anext__())

                if depth_task in done:
                    try:
                        depth_task.result()
                    except StopAsyncIteration:
                        return
                    yield OrderBookSnapshot(
                        symbol=symbol,
                        ts=dt.datetime.now(dt.timezone.utc).timestamp(),
                        bids=[OrderBookLevel(price=lv.price, size=lv.size) for lv in depth_ticker.domBids],
                        asks=[OrderBookLevel(price=lv.price, size=lv.size) for lv in depth_ticker.domAsks],
                    )
                    depth_task = asyncio.ensure_future(depth_iter.__anext__())
        finally:
            for task in (last_task, bidask_task, depth_task):
                if not task.done():
                    task.cancel()
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_ib_adapter.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add orderflow/ib_adapter.py tests/test_orderflow_ib_adapter.py
git commit -m "feat(orderflow): add IBKR persistent depth+tick-by-tick adapter"
```

---

### Task 6: 심볼별 수집 매니저 (재연결 백오프 + 격리)

**Files:**
- Create: `orderflow/manager.py`
- Test: `tests/test_orderflow_manager.py`

**Interfaces:**
- Consumes: `orderflow.aggregator.OrderflowAggregator` (Task 3), `orderflow.hl_adapter.HyperliquidOrderflowClient` (Task 4), `orderflow.ib_adapter.IBOrderflowClient` (Task 5), `orderflow.models.{TradeEvent, OrderBookSnapshot}` (Task 1)
- Produces: `OrderflowManager(adapter_factory=None)` with `subscribe(symbol: str) -> tuple[asyncio.Queue, dict]`, `unsubscribe(symbol: str, queue: asyncio.Queue) -> None`, `active_symbols() -> list[str]`. 모듈 레벨 싱글턴 `default_manager = OrderflowManager()`. Task 7(`router_orderflow.py`)이 `default_manager`를 그대로 임포트해 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_orderflow_manager.py
import asyncio
from unittest.mock import AsyncMock, patch

from orderflow.manager import RECONNECT_BASE_DELAY, OrderflowManager
from orderflow.models import TradeEvent


def _trade(price=100.0, size=1.0, side="buy", ts=1000.0, symbol="BTC.HL"):
    return TradeEvent(symbol=symbol, ts=ts, price=price, size=size, side=side)


async def _one_shot_stream(events):
    for e in events:
        yield e


async def test_subscribe_starts_worker_and_broadcasts_delta():
    manager = OrderflowManager(adapter_factory=lambda symbol: _one_shot_stream([_trade()]))
    queue, snapshot = manager.subscribe("BTC.HL")
    assert snapshot == {"footprint": [], "heatmap": []}
    assert manager.active_symbols() == ["BTC.HL"]

    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert msg["type"] == "footprint_delta"
    assert msg["side"] == "buy"

    manager.unsubscribe("BTC.HL", queue)
    assert manager.active_symbols() == []


async def test_second_subscriber_reuses_worker_and_gets_same_snapshot():
    manager = OrderflowManager(adapter_factory=lambda symbol: _one_shot_stream([]))
    queue1, _ = manager.subscribe("NQ")
    queue2, _ = manager.subscribe("NQ")
    assert manager.active_symbols() == ["NQ"]
    manager.unsubscribe("NQ", queue1)
    assert manager.active_symbols() == ["NQ"]  # queue2 아직 구독 중 -> worker 유지
    manager.unsubscribe("NQ", queue2)
    assert manager.active_symbols() == []


async def test_reconnects_with_backoff_then_broadcasts_live_before_delta():
    call_count = 0

    async def flaky(symbol):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("boom")
        yield _trade()

    manager = OrderflowManager(adapter_factory=flaky)
    with patch("orderflow.manager.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        queue, _ = manager.subscribe("NQ")
        reconnecting_msg = await asyncio.wait_for(queue.get(), timeout=1.0)
        live_msg = await asyncio.wait_for(queue.get(), timeout=1.0)
        delta_msg = await asyncio.wait_for(queue.get(), timeout=1.0)
        manager.unsubscribe("NQ", queue)

    assert reconnecting_msg == {"type": "status", "state": "reconnecting"}
    assert live_msg == {"type": "status", "state": "live"}
    assert delta_msg["type"] == "footprint_delta"
    mock_sleep.assert_any_call(RECONNECT_BASE_DELAY)
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'orderflow.manager'`

- [ ] **Step 3: 최소 구현**

```python
# orderflow/manager.py
"""심볼별 수집 task 감독 — 재연결 백오프, 예외 흡수(앱 전체에 전파 안 함).
매매 실행 로직(live_engine 등)과 임포트/상태 공유 없음."""
import asyncio
import logging
from dataclasses import dataclass, field

from orderflow.aggregator import OrderflowAggregator
from orderflow.hl_adapter import HyperliquidOrderflowClient
from orderflow.ib_adapter import IBOrderflowClient
from orderflow.models import TradeEvent

RECONNECT_BASE_DELAY = 2.0
RECONNECT_MAX_DELAY = 60.0

TICK_SIZE_BY_SYMBOL = {"BTC.HL": 1.0, "NQ": 0.25}
DEFAULT_TICK_SIZE = 1.0


def _default_adapter_factory(symbol: str):
    if symbol.endswith(".HL"):
        coin = symbol[: -len(".HL")]
        return HyperliquidOrderflowClient().stream(coin)
    return IBOrderflowClient().stream(symbol)


@dataclass
class _SymbolWorker:
    task: "asyncio.Task"
    aggregator: OrderflowAggregator
    subscribers: set = field(default_factory=set)


class OrderflowManager:
    def __init__(self, adapter_factory=None) -> None:
        self._adapter_factory = adapter_factory or _default_adapter_factory
        self._workers: dict[str, _SymbolWorker] = {}

    def active_symbols(self) -> list[str]:
        return list(self._workers.keys())

    def subscribe(self, symbol: str) -> tuple[asyncio.Queue, dict]:
        worker = self._workers.get(symbol)
        if worker is None:
            tick_size = TICK_SIZE_BY_SYMBOL.get(symbol, DEFAULT_TICK_SIZE)
            aggregator = OrderflowAggregator(tick_size=tick_size)
            task = asyncio.ensure_future(self._run(symbol, aggregator))
            worker = _SymbolWorker(task=task, aggregator=aggregator)
            self._workers[symbol] = worker
        queue: asyncio.Queue = asyncio.Queue()
        worker.subscribers.add(queue)
        return queue, worker.aggregator.snapshot()

    def unsubscribe(self, symbol: str, queue: asyncio.Queue) -> None:
        worker = self._workers.get(symbol)
        if worker is None:
            return
        worker.subscribers.discard(queue)
        if not worker.subscribers:
            worker.task.cancel()
            del self._workers[symbol]

    def _broadcast(self, symbol: str, messages: list[dict]) -> None:
        worker = self._workers.get(symbol)
        if worker is None:
            return
        for queue in worker.subscribers:
            for msg in messages:
                queue.put_nowait(msg)

    def _broadcast_status(self, symbol: str, state: str) -> None:
        worker = self._workers.get(symbol)
        if worker is None:
            return
        for queue in worker.subscribers:
            queue.put_nowait({"type": "status", "state": state})

    async def _run(self, symbol: str, aggregator: OrderflowAggregator) -> None:
        delay = RECONNECT_BASE_DELAY
        was_reconnecting = False
        while True:
            try:
                async for event in self._adapter_factory(symbol):
                    delay = RECONNECT_BASE_DELAY
                    if was_reconnecting:
                        self._broadcast_status(symbol, "live")
                        was_reconnecting = False
                    if isinstance(event, TradeEvent):
                        deltas = [aggregator.on_trade(event)]
                    else:
                        deltas = aggregator.on_book_snapshot(event)
                    self._broadcast(symbol, deltas)
                self._broadcast_status(symbol, "reconnecting")
                was_reconnecting = True
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("orderflow adapter failed for %s, reconnecting", symbol)
                self._broadcast_status(symbol, "reconnecting")
                was_reconnecting = True
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)


default_manager = OrderflowManager()
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_manager.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add orderflow/manager.py tests/test_orderflow_manager.py
git commit -m "feat(orderflow): add symbol collection manager with backoff reconnect"
```

---

### Task 7: REST + WS 라우터, main.py 등록

**Files:**
- Create: `api_server/router_orderflow.py`
- Modify: `api_server/main.py` (라우터 임포트 + `app.include_router(...)` 추가 — 기존 `router_ict` 등록부 근처, `api_server/main.py:5094-5095` 다음 줄)
- Test: `tests/test_router_orderflow.py`

**Interfaces:**
- Consumes: `orderflow.manager.default_manager` (Task 6) — `subscribe`/`unsubscribe`/`active_symbols` 시그니처 그대로 사용.
- Produces: `GET /orderflow/symbols` → `{"symbols": [...]}`; `WS /ws/orderflow/{symbol}` → 연결 시 `{"type":"snapshot","symbol":...,"footprint":[...],"heatmap":[...]}` 1회, 이후 매니저 큐에서 나오는 델타/상태 메시지를 그대로 relay. 이건 이 스펙의 최종 소비자(프론트엔드, 별도 스펙)가 붙는 지점.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_router_orderflow.py
import asyncio
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_server.router_orderflow import router


class _StubManager:
    def __init__(self, symbols=None, subscribe_result=None):
        self._symbols = symbols or []
        self._subscribe_result = subscribe_result
        self.unsubscribed: list[tuple[str, object]] = []

    def active_symbols(self):
        return self._symbols

    def subscribe(self, symbol):
        return self._subscribe_result

    def unsubscribe(self, symbol, queue):
        self.unsubscribed.append((symbol, queue))


def _app():
    app = FastAPI()
    app.include_router(router)
    return app


def test_get_symbols_returns_manager_active_list():
    stub = _StubManager(symbols=["BTC.HL", "NQ"])
    client = TestClient(_app())
    with patch("api_server.router_orderflow.default_manager", stub):
        r = client.get("/orderflow/symbols")
    assert r.status_code == 200
    assert r.json() == {"symbols": ["BTC.HL", "NQ"]}


def test_ws_orderflow_sends_snapshot_then_queued_delta_then_cleans_up_on_disconnect():
    queue = asyncio.Queue()
    queue.put_nowait({"type": "footprint_delta", "bucket_ts": 0.0, "price": 100.0, "side": "buy", "delta_vol": 1.0})
    snapshot = {"footprint": [], "heatmap": []}
    stub = _StubManager(subscribe_result=(queue, snapshot))
    client = TestClient(_app())

    with patch("api_server.router_orderflow.default_manager", stub):
        with client.websocket_connect("/ws/orderflow/BTC.HL") as ws:
            first = ws.receive_json()
            second = ws.receive_json()

    assert first == {"type": "snapshot", "symbol": "BTC.HL", "footprint": [], "heatmap": []}
    assert second["type"] == "footprint_delta"
    assert stub.unsubscribed == [("BTC.HL", queue)]
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_router_orderflow.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api_server.router_orderflow'`

- [ ] **Step 3: 최소 구현**

```python
# api_server/router_orderflow.py
"""오더플로우(풋프린트)/유동성 히트맵 REST+WS. orderflow/manager.py의 OrderflowManager를 소비만 한다.
매매 실행 로직(live_engine 등)과 임포트/상태 공유 없음."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from orderflow.manager import default_manager

router = APIRouter()


@router.get("/orderflow/symbols")
def get_orderflow_symbols() -> dict:
    return {"symbols": default_manager.active_symbols()}


@router.websocket("/ws/orderflow/{symbol}")
async def ws_orderflow(websocket: WebSocket, symbol: str) -> None:
    await websocket.accept()
    queue, snapshot = default_manager.subscribe(symbol)
    try:
        await websocket.send_json({"type": "snapshot", "symbol": symbol, **snapshot})
        while True:
            msg = await queue.get()
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        pass
    finally:
        default_manager.unsubscribe(symbol, queue)
```

`api_server/main.py`의 기존 `router_ict` 등록부(현재 5094-5095행) 바로 다음에 추가:

```python
from api_server.router_orderflow import router as orderflow_router
app.include_router(orderflow_router)
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_router_orderflow.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: main.py 등록 후 전체 회귀 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: 기존 pre-existing failures(test_auth.py ×3~4, test_backtest_happy_path)만 남고 나머지 전부 통과. `orderflow`/`router_orderflow` 관련 테스트는 전부 PASS.

- [ ] **Step 6: 커밋**

```bash
git add api_server/router_orderflow.py api_server/main.py tests/test_router_orderflow.py
git commit -m "feat(orderflow): expose REST/WS orderflow router and register in main app"
```

---

## 완료 후 다음 단계

백엔드 태스크 7개 완료·리뷰 후, `seokminal-dashboard/docs/superpowers/specs/2026-07-09-orderflow-heatmap-design.md`(프론트엔드 스펙)를 `writing-plans`로 플랜화 — `/ws/orderflow/{symbol}` 계약이 여기서 확정되므로 프론트 플랜은 이 계약을 그대로 인터페이스로 참조한다.
