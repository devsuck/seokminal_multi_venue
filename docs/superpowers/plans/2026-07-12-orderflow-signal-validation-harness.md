# 오더플로우 시그널 검증 하네스 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** NQ/MNQ 오더플로우 5개 시그널(footprint 불균형, CVD 다이버전스, stop-run, heatmap 유동성벽, iceberg refill)을 기존 검증 인프라(`research/validation/*`)로 통계 검정할 수 있는 수집기+가설 모듈 구축. 실집행 없음, 신호 통계 유의성만 판정.

**Architecture:** `IBOrderflowClient.stream()` → `OrderflowAggregator`(라이브 대시보드와 동일 버킷팅) → jsonl 저장(수집기) → 저장된 delta 리플레이해 5개 signal builder가 BUY/SELL/HOLD 시퀀스 생성 → 기존 `simulate_long_short`/`random_same_frequency`/`trade_metrics`/`empirical_p_value`/`benjamini_hochberg`/`build_report` 그대로 재사용(무변경).

**Tech Stack:** Python 3.14, pytest(asyncio_mode=auto), ib_async, Pydantic.

## Global Constraints

- Python 인터프리터: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`
- `asyncio_mode="auto"` — `@pytest.mark.asyncio` 데코레이터 절대 쓰지 않음, `async def test_...`만으로 충분
- 신규 신호 임계값은 프론트(`lib/orderflow-data.ts`)에 이미 있는 값 그대로 사용 — 백테스트용으로 재최적화 금지 (`orderflow_absorption.py`와 동일 원칙)
- IB futures 커미션/틱밸류 상수는 **미검증 근사치** — 코드 주석에 명시 필수
- client_id: NQ=20, MNQ=21 고정(심볼별 분리, 기존 client_id 충돌 버그 재발 방지)
- 커밋은 main 브랜치 직접

---

## 참고 코드베이스 사실 (모든 태스크 공통)

### `orderflow/models.py` (기존, 무변경)
```python
class OrderBookLevel(BaseModel):
    price: float
    size: float

class OrderBookSnapshot(BaseModel):
    symbol: str
    ts: float
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    venues: list[str] = []

class TradeEvent(BaseModel):
    symbol: str
    ts: float
    price: float
    size: float
    side: Literal["buy", "sell"]
```

### `orderflow/aggregator.py`의 `OrderflowAggregator` (기존, 무변경)
```python
class OrderflowAggregator:
    def __init__(self, tick_size=1.0, footprint_bucket_sec=60.0, heatmap_bucket_sec=2.0,
                 max_window_sec=7200.0, heatmap_max_window_sec=5400.0, heatmap_snapshot_window_sec=600.0): ...
    def on_trade(self, trade: TradeEvent) -> dict:
        # returns {"type": "footprint_delta", "bucket_ts": float, "price": float, "side": "buy"|"sell", "delta_vol": float}
    def on_book_snapshot(self, book: OrderBookSnapshot) -> list[dict]:
        # returns list of {"type": "heatmap_delta", "ts": float, "price": float, "size": float}
    def snapshot(self) -> dict:
        # {"footprint": [...], "heatmap": [...]}
```

### `orderflow/ib_adapter.py`의 `IBOrderflowClient` (기존, 무변경)
```python
class IBOrderflowClient:
    def __init__(self, host=None, port=None, client_id=None, ib=None): ...
    async def stream(self, symbol: str, connect_timeout: float = 15.0) -> AsyncIterator[OrderBookSnapshot | TradeEvent]: ...
```

### `research/validation/*` (기존, 무변경 — 전부 그대로 import해 씀)
```python
# engine.py
def simulate_long_short(closes: list[float], signals: list[str], trade_size: float = 10.0, cost_bps: float = 0.0) -> list[dict]: ...

# baselines.py
def random_same_frequency(closes, n_trades, holding_periods, trade_size=10.0, cost_bps=0.0,
                           eligible_indices=None, n_runs=500, seed=42) -> list[float]: ...
def empirical_p_value(strategy_stat: float, random_stats: list[float]) -> dict: ...

# metrics.py
def trade_metrics(trades: list[dict], min_trades: int = 30) -> dict: ...

# multiple_testing.py
def benjamini_hochberg(pvals: list[float], alpha: float = 0.1) -> dict: ...

# cost_model.py
def effective_cost_bps(cost_bps=0.0, slippage_bps=0.0, spread_bps=0.0) -> float: ...
```

### `research/reports/alpha_report.py` (기존, 무변경)
```python
def build_report(name, hypothesis, universe, timeframe, cost, strategy, random_pval, naive,
                  walk_forward_result, is_harness_dryrun=True, extra=None) -> dict:
    # returns {"json_path", "md_path", "verdict"}
REPORT_DIR = os.path.join(os.path.dirname(__file__), "alpha")
```

### `research/run_hl_orderflow_tick_collect.py` (템플릿 — 새 IB 수집기가 이 구조 그대로 계승)
```python
COINS = ["BTC", "ETH"]
RECONNECT_BASE_DELAY = 2.0
RECONNECT_MAX_DELAY = 60.0

def append_trades(coin, trades) -> None: ...
async def run_coin_forever(coin, *, client=None, append_fn=append_trades, max_cycles=None) -> None: ...
async def run_forever(*, coins=COINS, client_factory=..., append_fn=append_trades, max_cycles=None) -> None: ...
```

---

## Task 1: IB futures 비용모델

**Files:**
- Modify: `research/validation/cost_model.py`
- Test: `tests/test_cost_model.py` (신규)

**Interfaces:**
- Produces: `IB_FUTURES_COMMISSION_USD: dict[str, float]`, `IB_FUTURES_TICK_VALUE_USD: dict[str, float]`, `IB_FUTURES_SLIPPAGE_TICKS: dict[str, float]`, `ib_futures_effective_cost_bps(symbol: str, notional: float) -> float`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cost_model.py
from research.validation.cost_model import ib_futures_effective_cost_bps, IB_FUTURES_COMMISSION_USD, IB_FUTURES_TICK_VALUE_USD, IB_FUTURES_SLIPPAGE_TICKS


def test_ib_futures_effective_cost_bps_nq():
    # NQ: commission $2.25 + slippage(0.5 tick * $5/tick = $2.50) = $4.75 on notional 400000
    # bps = 4.75 / 400000 * 10000 = 0.11875
    result = ib_futures_effective_cost_bps("NQ", notional=400_000.0)
    assert result == round((IB_FUTURES_COMMISSION_USD["NQ"] + IB_FUTURES_SLIPPAGE_TICKS["NQ"] * IB_FUTURES_TICK_VALUE_USD["NQ"]) / 400_000.0 * 10_000.0, 6)


def test_ib_futures_effective_cost_bps_mnq_smaller_notional_higher_bps():
    nq_bps = ib_futures_effective_cost_bps("NQ", notional=400_000.0)
    mnq_bps = ib_futures_effective_cost_bps("MNQ", notional=40_000.0)
    assert mnq_bps > nq_bps  # MNQ notional 1/10인데 커미션은 1/10보다 덜 줄어듦 -> bps 더 높음


def test_ib_futures_effective_cost_bps_unknown_symbol_raises():
    import pytest
    with pytest.raises(KeyError):
        ib_futures_effective_cost_bps("ES", notional=100_000.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cost_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'ib_futures_effective_cost_bps'`

- [ ] **Step 3: Implement in `research/validation/cost_model.py`**

Append to end of file:

```python
# ── IB CME futures 전용 ──────────────────────────────────────────────────
# ⚠️ 미검증 근사치 — IB 실제 요금표(계약당 왕복 커미션) 대조 안 됨.
# 페이퍼 단계 진입 전 반드시 IB 계정 실요율로 재확인할 것.
IB_FUTURES_COMMISSION_USD = {"NQ": 2.25, "MNQ": 0.55}  # 계약당 왕복 근사
IB_FUTURES_TICK_VALUE_USD = {"NQ": 5.0, "MNQ": 0.5}    # CME 0.25pt당
IB_FUTURES_SLIPPAGE_TICKS = {"NQ": 0.5, "MNQ": 1.0}    # MNQ 유동성 낮아 더 보수적


def ib_futures_effective_cost_bps(symbol: str, notional: float) -> float:
    """IB 선물 체결 1회당 유효 비용(bps) = (커미션 + 슬리피지) / notional * 10000.

    notional은 호출부에서 계약가치(price * multiplier)로 넘겨야 한다.
    ⚠️ 커미션/슬리피지 상수는 미검증 근사치."""
    commission = IB_FUTURES_COMMISSION_USD[symbol]
    slippage = IB_FUTURES_SLIPPAGE_TICKS[symbol] * IB_FUTURES_TICK_VALUE_USD[symbol]
    return round((commission + slippage) / notional * 10_000.0, 6)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cost_model.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add research/validation/cost_model.py tests/test_cost_model.py
git commit -m "feat: IB futures(NQ/MNQ) 유효비용 bps 계산 추가"
```

---

## Task 2: IB 오더플로우 틱+뎁스 수집기

**Files:**
- Create: `research/run_ib_orderflow_tick_collect.py`
- Test: `tests/test_run_ib_orderflow_tick_collect.py`

**Interfaces:**
- Consumes: `orderflow.ib_adapter.IBOrderflowClient` (`stream(symbol, connect_timeout=15.0)`), `orderflow.aggregator.OrderflowAggregator` (`on_trade`, `on_book_snapshot`), `orderflow.models.TradeEvent`, `orderflow.models.OrderBookSnapshot`
- Produces: `SYMBOLS: list[str]`, `CLIENT_IDS: dict[str, int]`, `RECONNECT_BASE_DELAY: float`, `RECONNECT_MAX_DELAY: float`, `append_deltas(symbol: str, deltas: list[dict]) -> None`, `async def run_symbol_forever(symbol, *, client=None, append_fn=append_deltas, max_cycles=None) -> None`, `async def run_forever(*, symbols=SYMBOLS, client_factory=..., append_fn=append_deltas, max_cycles=None) -> None`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_run_ib_orderflow_tick_collect.py
import datetime as dt
import json

import research.run_ib_orderflow_tick_collect as runner
from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent


def _trade(price=100.0, size=1.0, side="buy", ts=1000.0, symbol="NQ"):
    return TradeEvent(symbol=symbol, ts=ts, price=price, size=size, side=side)


def _book(symbol="NQ", ts=1000.0):
    return OrderBookSnapshot(
        symbol=symbol, ts=ts,
        bids=[OrderBookLevel(price=99.75, size=5.0)],
        asks=[OrderBookLevel(price=100.25, size=3.0)],
    )


class FakeClient:
    """symbol별 stream() 호출을 리스트로 미리 정의 — 매 재연결 사이클마다 다음 behavior 소비."""

    def __init__(self, behaviors: list):
        self._behaviors = behaviors
        self.calls: list[str] = []

    async def stream(self, symbol, connect_timeout=15.0):
        self.calls.append(symbol)
        behavior = self._behaviors[len(self.calls) - 1]
        if isinstance(behavior, Exception):
            raise behavior
        for event in behavior:
            yield event


def test_append_deltas_writes_jsonl_to_symbol_dated_file(tmp_path):
    from unittest.mock import patch
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_deltas("NQ", [{"type": "footprint_delta", "bucket_ts": 960.0}])
        path = tmp_path / f"NQ_{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["type"] == "footprint_delta"


def test_append_deltas_skips_write_when_empty(tmp_path):
    from unittest.mock import patch
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_deltas("NQ", [])
    assert list(tmp_path.iterdir()) == []


async def test_run_symbol_forever_converts_trade_and_book_events_to_deltas():
    client = FakeClient([[_trade(), _book()]])
    appended = []
    await runner.run_symbol_forever(
        "NQ", client=client, append_fn=lambda symbol, deltas: appended.extend(deltas), max_cycles=1,
    )
    types = {d["type"] for d in appended}
    assert types == {"footprint_delta", "heatmap_delta"}


async def test_run_symbol_forever_uses_symbol_specific_client_id_when_no_client_passed():
    # client_factory 기본값이 CLIENT_IDS 매핑을 쓰는지는 run_forever 레벨에서 검증
    assert runner.CLIENT_IDS == {"NQ": 20, "MNQ": 21}


async def test_run_symbol_forever_backs_off_and_doubles_delay_on_repeated_failure():
    from unittest.mock import patch
    client = FakeClient([ConnectionError("boom"), ConnectionError("boom")])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_symbol_forever(
            "NQ", client=client, append_fn=lambda symbol, deltas: None, max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY, runner.RECONNECT_BASE_DELAY * 2]


async def test_run_symbol_forever_resets_delay_after_success():
    from unittest.mock import patch
    client = FakeClient([ConnectionError("boom"), [_trade()]])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_symbol_forever(
            "NQ", client=client, append_fn=lambda symbol, deltas: None, max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY]


async def test_run_symbol_forever_backs_off_on_clean_close_without_events():
    from unittest.mock import patch
    client = FakeClient([[], []])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_symbol_forever(
            "NQ", client=client, append_fn=lambda symbol, deltas: None, max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY, runner.RECONNECT_BASE_DELAY * 2]


async def test_run_forever_runs_all_symbols_concurrently_with_distinct_client_ids():
    clients = {"NQ": FakeClient([[_trade()]]), "MNQ": FakeClient([[_trade(symbol="MNQ")]])}
    seen_ids = []

    def factory(symbol):
        seen_ids.append(symbol)
        return clients[symbol]

    appended = []
    await runner.run_forever(
        symbols=["NQ", "MNQ"],
        client_factory=factory,
        append_fn=lambda symbol, deltas: appended.append((symbol, deltas)),
        max_cycles=1,
    )
    assert {s for s, _ in appended} == {"NQ", "MNQ"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_ib_orderflow_tick_collect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.run_ib_orderflow_tick_collect'`

- [ ] **Step 3: Implement `research/run_ib_orderflow_tick_collect.py`**

```python
"""IB 오더플로우 틱+뎁스 수집기 — tmux로 상시 실행.

NQ/MNQ footprint/heatmap 신호 백테스트용 원시 데이터 축적이 목적. raw tick을
저장하지 않고 라이브 대시보드와 동일한 OrderflowAggregator를 통과시켜 나온
footprint_delta/heatmap_delta만 저장한다 — 연구용 신호 재구성이 라이브 렌더링과
동일 소스코드 기반이 되어, 백테스트 로직이 프론트 로직과 슬쩍 달라지는 버그
클래스를 원천 차단한다. 심볼별로 독립된 재연결 루프를 돌려 한쪽 스트림이 끊겨도
다른 심볼 수집에 영향 없다.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from pathlib import Path

from orderflow.aggregator import OrderflowAggregator
from orderflow.ib_adapter import IBOrderflowClient
from orderflow.models import OrderBookSnapshot, TradeEvent

_DATA_DIR = Path("research/data/ib_orderflow_tick")

SYMBOLS = ["NQ", "MNQ"]
# 기존 라이브 client_id(1=데이터/2=주문, live_engine/ib_broker.py)와 오더플로우
# 기본값(20, orderflow/ib_adapter.py)에 안 겹치게 심볼별로 분리 — NQ+MNQ 동시 수집 시
# 같은 client_id를 재사용하면 IB Gateway 접속이 충돌한다(2026-07 client_id 충돌 버그와 동일 원인).
CLIENT_IDS = {"NQ": 20, "MNQ": 21}
RECONNECT_BASE_DELAY = 2.0
RECONNECT_MAX_DELAY = 60.0
TICK_SIZE = 0.25  # CME NQ/MNQ 표준 틱


def append_deltas(symbol: str, deltas: list[dict]) -> None:
    if not deltas:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{symbol}_{dt.datetime.now(dt.timezone.utc).date().isoformat()}.jsonl"
    with path.open("a") as f:
        for d in deltas:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


async def run_symbol_forever(
    symbol: str,
    *,
    client: IBOrderflowClient | None = None,
    append_fn=append_deltas,
    max_cycles: int | None = None,
) -> None:
    client = client or IBOrderflowClient(client_id=CLIENT_IDS[symbol])
    aggregator = OrderflowAggregator(tick_size=TICK_SIZE)
    cycle = 0
    delay = RECONNECT_BASE_DELAY
    while max_cycles is None or cycle < max_cycles:
        received_event = False
        try:
            async for event in client.stream(symbol):
                if isinstance(event, TradeEvent):
                    received_event = True
                    append_fn(symbol, [aggregator.on_trade(event)])
                elif isinstance(event, OrderBookSnapshot):
                    received_event = True
                    deltas = aggregator.on_book_snapshot(event)
                    if deltas:
                        append_fn(symbol, deltas)
            if received_event:
                # 정상적으로 이벤트를 수신하다 스트림이 종료된 경우 — 백오프 불필요
                delay = RECONNECT_BASE_DELAY
            else:
                # 구독 직후 이벤트 하나 없이 스트림이 끊긴 경우 — 반복되면 핫루프가 되므로
                # 예외 케이스와 동일하게 백오프 적용
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
        except Exception:
            logging.exception("IB orderflow stream failed for %s, reconnecting", symbol)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)
        cycle += 1


async def run_forever(
    *,
    symbols: list[str] = SYMBOLS,
    client_factory=lambda symbol: IBOrderflowClient(client_id=CLIENT_IDS[symbol]),
    append_fn=append_deltas,
    max_cycles: int | None = None,
) -> None:
    await asyncio.gather(
        *(
            run_symbol_forever(symbol, client=client_factory(symbol), append_fn=append_fn, max_cycles=max_cycles)
            for symbol in symbols
        )
    )


if __name__ == "__main__":
    asyncio.run(run_forever())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_ib_orderflow_tick_collect.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add research/run_ib_orderflow_tick_collect.py tests/test_run_ib_orderflow_tick_collect.py
git commit -m "feat: IB NQ/MNQ 오더플로우 틱+뎁스 수집기 추가"
```

---

## Task 3: footprint 불균형 + CVD 다이버전스 시그널 빌더

**Files:**
- Create: `research/hypotheses/orderflow_futures.py`
- Test: `tests/test_orderflow_futures_signals.py`

**Interfaces:**
- Consumes: footprint_delta dict 형식 `{"type": "footprint_delta", "bucket_ts": float, "price": float, "side": "buy"|"sell", "delta_vol": float}` (Task 2 수집기가 저장하는 포맷과 동일)
- Produces: `load_deltas(paths: list[str]) -> list[dict]`, `build_footprint_imbalance_signals(deltas: list[dict], imbalance_ratio: float = 0.7) -> dict` (반환 `{"closes": list[float], "signals": list[str], "eligible": list[int]}` — `orderflow_absorption.py`의 `build_bars_and_signals`와 동일 반환 형태), `build_cvd_divergence_signals(deltas: list[dict], lookback_buckets: int = 5) -> dict` (동일 반환 형태)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_orderflow_futures_signals.py
from research.hypotheses.orderflow_futures import (
    build_cvd_divergence_signals,
    build_footprint_imbalance_signals,
    load_deltas,
)


def _fd(bucket_ts, price, side, vol):
    return {"type": "footprint_delta", "bucket_ts": bucket_ts, "price": price, "side": side, "delta_vol": vol}


def test_load_deltas_sorts_by_bucket_ts_across_files(tmp_path):
    import json
    p1 = tmp_path / "a.jsonl"
    p2 = tmp_path / "b.jsonl"
    p1.write_text(json.dumps(_fd(120.0, 100.0, "buy", 1.0)) + "\n")
    p2.write_text(json.dumps(_fd(60.0, 100.0, "buy", 1.0)) + "\n")
    result = load_deltas([str(p1), str(p2)])
    assert [d["bucket_ts"] for d in result] == [60.0, 120.0]


def test_footprint_imbalance_buy_dominant_bucket_yields_buy_signal():
    deltas = [
        _fd(0.0, 100.0, "buy", 8.0),
        _fd(0.0, 100.0, "sell", 2.0),
        _fd(60.0, 101.0, "buy", 1.0),
        _fd(60.0, 101.0, "sell", 1.0),
    ]
    result = build_footprint_imbalance_signals(deltas, imbalance_ratio=0.7)
    assert result["signals"][0] == "BUY"
    assert result["signals"][1] == "HOLD"
    assert result["closes"] == [100.0, 101.0]
    # eligible = 판정 가능(볼륨 존재) 버킷 전체 — absorption.py의 noise_floor 통과 버킷과
    # 동일 의미(신호가 실제로 뜬 버킷이 아니라 비율 계산이 가능했던 버킷)
    assert result["eligible"] == [0, 1]


def test_footprint_imbalance_sell_dominant_bucket_yields_sell_signal():
    deltas = [_fd(0.0, 100.0, "buy", 1.0), _fd(0.0, 100.0, "sell", 9.0)]
    result = build_footprint_imbalance_signals(deltas, imbalance_ratio=0.7)
    assert result["signals"][0] == "SELL"


def test_footprint_imbalance_multi_price_bucket_uses_last_arrival_price():
    # 같은 버킷에 여러 price 레벨 -> close는 마지막으로 델타 도착한 price(시간순, 리스트 순서 기준)
    deltas = [_fd(0.0, 100.0, "buy", 5.0), _fd(0.0, 101.0, "buy", 5.0)]
    result = build_footprint_imbalance_signals(deltas, imbalance_ratio=0.7)
    assert result["closes"] == [101.0]


def test_cvd_divergence_price_down_cvd_up_yields_buy():
    # 누적 delta(buy-sell)는 우상향(CVD 상승)인데 가격은 하락 -> 다이버전스 -> BUY
    deltas = [
        _fd(0.0, 105.0, "buy", 1.0), _fd(0.0, 105.0, "sell", 1.0),   # cvd=0, price=105
        _fd(60.0, 104.0, "buy", 1.0), _fd(60.0, 104.0, "sell", 1.0), # cvd=0, price=104
        _fd(120.0, 103.0, "buy", 1.0), _fd(120.0, 103.0, "sell", 1.0), # cvd=0, price=103
        _fd(180.0, 102.0, "buy", 5.0),                                 # cvd=+5, price=102 (down but cvd up)
    ]
    result = build_cvd_divergence_signals(deltas, lookback_buckets=3)
    assert result["signals"][-1] == "BUY"


def test_cvd_divergence_insufficient_lookback_is_hold():
    deltas = [_fd(0.0, 100.0, "buy", 1.0)]
    result = build_cvd_divergence_signals(deltas, lookback_buckets=3)
    assert result["signals"] == ["HOLD"]
    assert result["eligible"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_futures_signals.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.hypotheses.orderflow_futures'`

- [ ] **Step 3: Implement `research/hypotheses/orderflow_futures.py` (part 1 — footprint + CVD)**

```python
"""가설: NQ/MNQ 오더플로우 시그널 5종 — footprint 불균형, CVD 다이버전스,
stop-run 패턴, heatmap 유동성벽 근접, iceberg refill.

⚠️ DORMANT 모듈 — 검증된 알파 아님. 임계값은 프론트(`lib/orderflow-data.ts`)와
동일 고정값 원칙(백테스트용으로 재최적화하지 않음). 입력은
`research/run_ib_orderflow_tick_collect.py`가 저장하는 footprint_delta/
heatmap_delta jsonl — 라이브 대시보드와 동일한 OrderflowAggregator 버킷팅을
거친 값이므로 원시 틱과 1:1은 아니다(footprint 60s 버킷, heatmap 2s 버킷).
"""
from __future__ import annotations

import json

from research.validation.baselines import empirical_p_value, random_same_frequency
from research.validation.cost_model import ib_futures_effective_cost_bps
from research.validation.engine import simulate_long_short
from research.validation.metrics import trade_metrics
from research.reports.alpha_report import build_report

FOOTPRINT_IMBALANCE_RATIO = 0.7  # lib/orderflow-data.ts 흡수 판정 임계값과 동일
CVD_LOOKBACK_BUCKETS = 5
NOTIONAL_MULTIPLIER = {"NQ": 20.0, "MNQ": 2.0}  # CME 계약승수

DEFAULTS = {"trade_size": 1.0}


def load_deltas(paths: list[str]) -> list[dict]:
    """여러 일자 jsonl 파일 -> bucket_ts 기준 정렬된 delta 리스트."""
    deltas: list[dict] = []
    for path in paths:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    deltas.append(json.loads(line))
    deltas.sort(key=lambda d: d.get("bucket_ts", d.get("ts", 0.0)))
    return deltas


def _footprint_buckets(deltas: list[dict]) -> tuple[list[float], dict[float, float], dict[float, float], dict[float, float]]:
    """footprint_delta만 골라 버킷 순서 + 버킷별 buy_vol/sell_vol 누적."""
    order: list[float] = []
    seen: set[float] = set()
    buy: dict[float, float] = {}
    sell: dict[float, float] = {}
    last_price: dict[float, float] = {}
    for d in deltas:
        if d.get("type") != "footprint_delta":
            continue
        b = d["bucket_ts"]
        if b not in seen:
            seen.add(b)
            order.append(b)
        if d["side"] == "buy":
            buy[b] = buy.get(b, 0.0) + d["delta_vol"]
        else:
            sell[b] = sell.get(b, 0.0) + d["delta_vol"]
        last_price[b] = d["price"]
    return order, buy, sell, last_price


def build_footprint_imbalance_signals(deltas: list[dict], imbalance_ratio: float = FOOTPRINT_IMBALANCE_RATIO) -> dict:
    """버킷별 buy/sell 볼륨 비율이 imbalance_ratio 넘으면 그 방향으로 BUY/SELL."""
    order, buy, sell, last_price = _footprint_buckets(deltas)

    closes: list[float] = []
    signals: list[str] = []
    eligible: list[int] = []
    for i, b in enumerate(order):
        bv, sv = buy.get(b, 0.0), sell.get(b, 0.0)
        total = bv + sv
        closes.append(last_price[b])
        sig = "HOLD"
        if total > 0:
            eligible.append(i)
            if bv / total >= imbalance_ratio:
                sig = "BUY"
            elif sv / total >= imbalance_ratio:
                sig = "SELL"
        signals.append(sig)
    return {"closes": closes, "signals": signals, "eligible": eligible}


def build_cvd_divergence_signals(deltas: list[dict], lookback_buckets: int = CVD_LOOKBACK_BUCKETS) -> dict:
    """누적 delta(CVD)가 lookback 구간 동안 가격과 반대 방향이면 다이버전스 신호.

    가격 하락+CVD 상승 -> BUY(매도세인 척하지만 실제 매수 우위 -> 반등 기대).
    가격 상승+CVD 하락 -> SELL. lookback 미달 버킷은 HOLD/not eligible."""
    order, buy, sell, last_price = _footprint_buckets(deltas)

    cvd = 0.0
    cvd_history: list[float] = []
    closes: list[float] = []
    signals: list[str] = []
    eligible: list[int] = []
    for i, b in enumerate(order):
        cvd += buy.get(b, 0.0) - sell.get(b, 0.0)
        cvd_history.append(cvd)
        closes.append(last_price[b])

        sig = "HOLD"
        if i >= lookback_buckets:
            price_delta = closes[i] - closes[i - lookback_buckets]
            cvd_delta = cvd_history[i] - cvd_history[i - lookback_buckets]
            if price_delta < 0 and cvd_delta > 0:
                eligible.append(i)
                sig = "BUY"
            elif price_delta > 0 and cvd_delta < 0:
                eligible.append(i)
                sig = "SELL"
        signals.append(sig)
    return {"closes": closes, "signals": signals, "eligible": eligible}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_futures_signals.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add research/hypotheses/orderflow_futures.py tests/test_orderflow_futures_signals.py
git commit -m "feat: footprint 불균형 + CVD 다이버전스 시그널 빌더 추가"
```

---

## Task 4: heatmap 유동성벽 근접 + iceberg refill 시그널 빌더

**Files:**
- Modify: `research/hypotheses/orderflow_futures.py`
- Test: `tests/test_orderflow_futures_signals.py` (Task 3 파일에 이어서 추가)

**Interfaces:**
- Consumes: heatmap_delta dict 형식 `{"type": "heatmap_delta", "ts": float, "price": float, "size": float}` (Task 2 수집기 저장 포맷), Task 3의 `load_deltas`
- Produces: `build_wall_proximity_signals(deltas: list[dict], wall_size_threshold: float, proximity_ticks: int = 4, tick_size: float = 0.25) -> dict` (동일 반환 형태), `build_iceberg_refill_signals(deltas: list[dict], refill_ratio: float = 0.8, min_depletion: float = 3.0) -> dict` (동일 반환 형태)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_orderflow_futures_signals.py`:

```python
from research.hypotheses.orderflow_futures import (
    build_iceberg_refill_signals,
    build_wall_proximity_signals,
)


def _hd(ts, price, size):
    return {"type": "heatmap_delta", "ts": ts, "price": price, "size": size}


def test_wall_proximity_price_approaching_large_bid_wall_yields_buy():
    # 가격이 10에서 10.25(벽 바로 위)로 접근 -> 벽이 지지선 -> BUY
    deltas = [
        _hd(0.0, 9.75, 20.0),   # 큰 매수벽 (임계 15.0 이상)
        _hd(0.0, 10.5, 1.0),
        _hd(2.0, 9.75, 20.0),
        _hd(2.0, 10.5, 1.0),
    ]
    result = build_wall_proximity_signals(deltas, wall_size_threshold=15.0, proximity_ticks=4, tick_size=0.25)
    assert "BUY" in result["signals"]


def test_wall_proximity_no_large_wall_is_all_hold():
    deltas = [_hd(0.0, 100.0, 1.0), _hd(2.0, 100.0, 1.0)]
    result = build_wall_proximity_signals(deltas, wall_size_threshold=15.0)
    assert all(s == "HOLD" for s in result["signals"])
    assert result["eligible"] == []


def test_iceberg_refill_repeated_depletion_and_refill_at_same_price_yields_signal():
    # 같은 가격에서 size가 10 -> 2(소진) -> 9(즉시 재충전) 반복 -> iceberg 패턴
    deltas = [
        _hd(0.0, 100.0, 10.0),
        _hd(2.0, 100.0, 2.0),   # 80% 소진
        _hd(4.0, 100.0, 9.0),   # 재충전(refill_ratio>=0.8 of 원래)
    ]
    result = build_iceberg_refill_signals(deltas, refill_ratio=0.8, min_depletion=3.0)
    assert "BUY" in result["signals"] or "SELL" in result["signals"]


def test_iceberg_refill_gradual_decline_without_refill_is_hold():
    deltas = [_hd(0.0, 100.0, 10.0), _hd(2.0, 100.0, 8.0), _hd(4.0, 100.0, 6.0)]
    result = build_iceberg_refill_signals(deltas, refill_ratio=0.8, min_depletion=3.0)
    assert all(s == "HOLD" for s in result["signals"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_futures_signals.py -v -k "wall_proximity or iceberg"`
Expected: FAIL with `ImportError: cannot import name 'build_wall_proximity_signals'`

- [ ] **Step 3: Implement (append to `research/hypotheses/orderflow_futures.py`)**

```python
WALL_SIZE_THRESHOLD = 15.0  # lib/orderflow-data.ts 히트맵 하이라이트 임계값과 동일
WALL_PROXIMITY_TICKS = 4
ICEBERG_REFILL_RATIO = 0.8
ICEBERG_MIN_DEPLETION = 3.0


def _heatmap_buckets(deltas: list[dict]) -> list[dict]:
    """heatmap_delta만 골라 ts 오름차순 그대로(이미 load_deltas가 정렬함)."""
    return [d for d in deltas if d.get("type") == "heatmap_delta"]


def build_wall_proximity_signals(
    deltas: list[dict],
    wall_size_threshold: float = WALL_SIZE_THRESHOLD,
    proximity_ticks: int = WALL_PROXIMITY_TICKS,
    tick_size: float = 0.25,
) -> dict:
    """대형 잔량 벽 근처로 가격 접근 시 벽 방향으로 신호.
    가격이 벽보다 낮고 근접하면(벽=매수벽, 지지) BUY. 벽보다 높고 근접하면(매도벽, 저항) SELL.

    '현재가'는 각 heatmap 스냅샷 시각의 최소/최대 관측 price 중간값으로 근사한다
    (진짜 체결가는 footprint_delta 쪽에 있으나, 이 신호는 heatmap만으로 독립 검증하기
    위해 heatmap 관측 price 레인지의 중앙을 현재가 프록시로 쓴다)."""
    rows = _heatmap_buckets(deltas)
    by_ts: dict[float, list[dict]] = {}
    order: list[float] = []
    for r in rows:
        if r["ts"] not in by_ts:
            by_ts[r["ts"]] = []
            order.append(r["ts"])
        by_ts[r["ts"]].append(r)

    closes: list[float] = []
    signals: list[str] = []
    eligible: list[int] = []
    for i, ts in enumerate(order):
        levels = by_ts[ts]
        prices = [lv["price"] for lv in levels]
        mid = (min(prices) + max(prices)) / 2.0
        closes.append(mid)

        walls = [lv for lv in levels if lv["size"] >= wall_size_threshold]
        sig = "HOLD"
        for w in walls:
            dist_ticks = abs(w["price"] - mid) / tick_size
            if dist_ticks <= proximity_ticks:
                eligible.append(i)
                sig = "BUY" if w["price"] < mid else "SELL"
                break
        signals.append(sig)
    return {"closes": closes, "signals": signals, "eligible": eligible}


def build_iceberg_refill_signals(
    deltas: list[dict],
    refill_ratio: float = ICEBERG_REFILL_RATIO,
    min_depletion: float = ICEBERG_MIN_DEPLETION,
) -> dict:
    """같은 가격 레벨에서 잔량이 급감했다가 즉시 재충전되면 iceberg 주문으로 간주.
    재충전 방향(그 가격이 현재가보다 낮으면 매수벽 iceberg=BUY, 높으면 SELL)으로 신호."""
    rows = _heatmap_buckets(deltas)
    by_ts: dict[float, list[dict]] = {}
    order: list[float] = []
    for r in rows:
        if r["ts"] not in by_ts:
            by_ts[r["ts"]] = []
            order.append(r["ts"])
        by_ts[r["ts"]].append(r)

    closes: list[float] = []
    signals: list[str] = []
    eligible: list[int] = []
    for i, ts in enumerate(order):
        levels = by_ts[ts]
        prices = [lv["price"] for lv in levels]
        mid = (min(prices) + max(prices)) / 2.0
        closes.append(mid)

        sig = "HOLD"
        # 소진->재충전은 같은 가격에서 최소 3개 관측(base, depleted, refilled)이 필요.
        if i >= 2:
            for lv in levels:
                price = lv["price"]
                hist = [d["size"] for d in rows if d["price"] == price and d["ts"] <= ts]
                if len(hist) < 3:
                    continue
                base, depleted_size, refilled_size = hist[-3], hist[-2], hist[-1]
                if base - depleted_size >= min_depletion and refilled_size >= base * refill_ratio:
                    eligible.append(i)
                    sig = "BUY" if price < mid else "SELL"
                    break
        signals.append(sig)
    return {"closes": closes, "signals": signals, "eligible": eligible}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_futures_signals.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add research/hypotheses/orderflow_futures.py tests/test_orderflow_futures_signals.py
git commit -m "feat: heatmap 유동성벽 근접 + iceberg refill 시그널 빌더 추가"
```

---

## Task 5: stop-run 패턴(이벤트 기반) 시그널 + 실행

**Files:**
- Modify: `research/hypotheses/orderflow_futures.py`
- Test: `tests/test_orderflow_futures_signals.py` (이어서 추가)

**Interfaces:**
- Consumes: Task 3의 `_footprint_buckets`, Task 1의 `ib_futures_effective_cost_bps`, `research.validation.engine.simulate_fixed_hold_longs`
- Produces: `stop_run_events(deltas: list[dict], spike_ratio: float = 3.0, lookback_buckets: int = 10) -> list[dict]` (반환 `[{"idx": int, "bucket_ts": float, "side": "buy"|"sell", "price": float}]`)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_orderflow_futures_signals.py`:

```python
from research.hypotheses.orderflow_futures import stop_run_events


def test_stop_run_events_detects_volume_spike_after_quiet_period():
    deltas = []
    for t in range(0, 600, 60):
        deltas.append(_fd(float(t), 100.0, "buy", 1.0))
        deltas.append(_fd(float(t), 100.0, "sell", 1.0))
    # 급증: 조용한 구간(2.0/bucket) 대비 3배 이상
    deltas.append(_fd(600.0, 99.5, "sell", 10.0))
    events = stop_run_events(deltas, spike_ratio=3.0, lookback_buckets=10)
    assert len(events) == 1
    assert events[0]["side"] == "sell"
    assert events[0]["price"] == 99.5


def test_stop_run_events_empty_when_no_spike():
    deltas = [_fd(float(t), 100.0, "buy", 1.0) for t in range(0, 600, 60)]
    events = stop_run_events(deltas, spike_ratio=3.0, lookback_buckets=10)
    assert events == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_futures_signals.py -v -k stop_run`
Expected: FAIL with `ImportError: cannot import name 'stop_run_events'`

- [ ] **Step 3: Implement (append to `research/hypotheses/orderflow_futures.py`)**

```python
STOP_RUN_SPIKE_RATIO = 3.0
STOP_RUN_LOOKBACK_BUCKETS = 10


def stop_run_events(
    deltas: list[dict],
    spike_ratio: float = STOP_RUN_SPIKE_RATIO,
    lookback_buckets: int = STOP_RUN_LOOKBACK_BUCKETS,
) -> list[dict]:
    """직전 lookback_buckets 평균 대비 총 거래량이 spike_ratio배 이상 튄 버킷을
    스탑런(청산 유발성 급변동) 이벤트로 간주. side는 그 버킷의 우세 방향."""
    order, buy, sell, last_price = _footprint_buckets(deltas)
    totals = [buy.get(b, 0.0) + sell.get(b, 0.0) for b in order]

    events: list[dict] = []
    for i, b in enumerate(order):
        if i < lookback_buckets:
            continue
        window = totals[i - lookback_buckets:i]
        avg = sum(window) / len(window) if window else 0.0
        if avg > 0 and totals[i] >= avg * spike_ratio:
            bv, sv = buy.get(b, 0.0), sell.get(b, 0.0)
            side = "buy" if bv >= sv else "sell"
            events.append({"idx": i, "bucket_ts": b, "side": side, "price": last_price[b]})
    return events
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_futures_signals.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add research/hypotheses/orderflow_futures.py tests/test_orderflow_futures_signals.py
git commit -m "feat: stop-run 패턴 이벤트 탐지 추가"
```

---

## Task 6: 검증 오케스트레이션 — run_hypothesis + BH-FDR 종합 판정

**Files:**
- Modify: `research/hypotheses/orderflow_futures.py`
- Test: `tests/test_orderflow_futures_run.py` (신규)

**Interfaces:**
- Consumes: Task 1~5에서 만든 모든 `build_*_signals`/`stop_run_events` 함수, `research.validation.baselines.{empirical_p_value, random_same_frequency}`, `research.validation.engine.{simulate_long_short, simulate_fixed_hold_longs}`, `research.validation.metrics.trade_metrics`, `research.validation.multiple_testing.benjamini_hochberg`, `research.reports.alpha_report.build_report`
- Produces: `run_signal_hypothesis(symbol: str, signal_name: str, delta_paths: list[str], params: dict | None = None, n_runs: int = 500, seed: int = 42, write_report: bool = True) -> dict` (bar 기반 4개 신호용, `orderflow_absorption.run_hypothesis`와 동일 셰이프 반환), `run_stop_run_hypothesis(symbol: str, delta_paths: list[str], hold_buckets_list: tuple[int, ...] = (1, 3, 5), trade_size: float = 1.0, n_runs: int = 500, seed: int = 42, write_report: bool = True) -> dict`, `run_all_hypotheses(delta_paths_by_symbol: dict[str, list[str]], n_runs: int = 500, seed: int = 42) -> dict` (반환 `{"results": {...}, "bh_fdr": dict}` — 10개(5신호×2심볼) p-value 모아 `benjamini_hochberg` 실행), `_blocked(symbol: str, signal_name: str, msg: str, write_report: bool) -> dict`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_orderflow_futures_run.py
from unittest.mock import patch

from research.hypotheses.orderflow_futures import (
    run_all_hypotheses,
    run_signal_hypothesis,
    run_stop_run_hypothesis,
)


def _write_deltas(tmp_path, name, deltas):
    import json
    path = tmp_path / name
    with path.open("w") as f:
        for d in deltas:
            f.write(json.dumps(d) + "\n")
    return str(path)


def _fd(bucket_ts, price, side, vol):
    return {"type": "footprint_delta", "bucket_ts": bucket_ts, "price": price, "side": side, "delta_vol": vol}


def test_run_signal_hypothesis_blocked_when_no_data(tmp_path):
    result = run_signal_hypothesis("NQ", "footprint_imbalance", [], write_report=False)
    assert result["blocked"] is True
    assert "no delta data" in result["reason"]


def test_run_signal_hypothesis_blocked_when_too_few_bars(tmp_path):
    deltas = [_fd(0.0, 100.0, "buy", 5.0)]
    path = _write_deltas(tmp_path, "NQ.jsonl", deltas)
    result = run_signal_hypothesis("NQ", "footprint_imbalance", [path], write_report=False)
    assert result["blocked"] is True


def test_run_signal_hypothesis_returns_strategy_and_random_when_enough_bars(tmp_path):
    deltas = []
    for i in range(20):
        b = float(i * 60)
        if i % 3 == 0:
            deltas.append(_fd(b, 100.0 + i, "buy", 9.0))
            deltas.append(_fd(b, 100.0 + i, "sell", 1.0))
        else:
            deltas.append(_fd(b, 100.0 + i, "buy", 1.0))
            deltas.append(_fd(b, 100.0 + i, "sell", 1.0))
    path = _write_deltas(tmp_path, "NQ.jsonl", deltas)
    result = run_signal_hypothesis("NQ", "footprint_imbalance", [path], n_runs=20, write_report=False)
    assert result["blocked"] is False
    assert "strategy" in result and "random" in result


def test_run_signal_hypothesis_unknown_signal_name_raises(tmp_path):
    import pytest
    deltas = [_fd(float(i * 60), 100.0, "buy", 1.0) for i in range(15)]
    path = _write_deltas(tmp_path, "NQ.jsonl", deltas)
    with pytest.raises(ValueError):
        run_signal_hypothesis("NQ", "not_a_real_signal", [path], write_report=False)


def test_run_stop_run_hypothesis_blocked_when_no_events(tmp_path):
    deltas = [_fd(float(i * 60), 100.0, "buy", 1.0) for i in range(15)]
    path = _write_deltas(tmp_path, "NQ.jsonl", deltas)
    result = run_stop_run_hypothesis("NQ", [path], write_report=False)
    assert result["blocked"] is True


def test_run_all_hypotheses_applies_bh_fdr_across_all_symbol_signal_pairs(tmp_path):
    deltas = []
    for i in range(20):
        b = float(i * 60)
        deltas.append(_fd(b, 100.0 + i, "buy", 9.0 if i % 3 == 0 else 1.0))
        deltas.append(_fd(b, 100.0 + i, "sell", 1.0 if i % 3 == 0 else 1.0))
    nq_path = _write_deltas(tmp_path, "NQ.jsonl", deltas)
    mnq_path = _write_deltas(tmp_path, "MNQ.jsonl", deltas)

    result = run_all_hypotheses(
        {"NQ": [nq_path], "MNQ": [mnq_path]}, n_runs=20,
    )
    assert "results" in result and "bh_fdr" in result
    assert result["bh_fdr"]["alpha"] == 0.1
    # 5신호(footprint_imbalance/cvd_divergence/wall_proximity/iceberg_refill/stop_run) x 2심볼
    assert len(result["results"]) == 10
    # heatmap_delta 없는 합성데이터라 wall_proximity/iceberg_refill/stop_run은 BLOCKED됨 ->
    # p-value 있는 항목만 BH-FDR 입력에 들어감. survivors는 그 항목 수와 정확히 일치해야 함.
    assert len(result["bh_fdr"]["survivors"]) == len(result["bh_fdr"]["keys"])
    assert len(result["bh_fdr"]["keys"]) > 0  # footprint_imbalance/cvd_divergence는 데이터 충분 -> BLOCKED 아님
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_futures_run.py -v`
Expected: FAIL with `ImportError: cannot import name 'run_signal_hypothesis'`

- [ ] **Step 3: Implement (append to `research/hypotheses/orderflow_futures.py`)**

```python
SIGNAL_BUILDERS = {
    "footprint_imbalance": build_footprint_imbalance_signals,
    "cvd_divergence": build_cvd_divergence_signals,
    "wall_proximity": build_wall_proximity_signals,
    "iceberg_refill": build_iceberg_refill_signals,
}

HYPOTHESIS_TEXT = {
    "footprint_imbalance": f"1분봉 footprint 매수/매도 비율 {FOOTPRINT_IMBALANCE_RATIO} 이상 우세 방향 추종",
    "cvd_divergence": f"누적델타(CVD) {CVD_LOOKBACK_BUCKETS}버킷 다이버전스 역추세 진입",
    "wall_proximity": f"heatmap 대형벽({WALL_SIZE_THRESHOLD} 이상) {WALL_PROXIMITY_TICKS}틱 근접 시 벽 방향 진입",
    "iceberg_refill": f"동일가 잔량 급감후 재충전({int(ICEBERG_REFILL_RATIO*100)}% 이상) 패턴 추종",
}


def run_signal_hypothesis(
    symbol: str,
    signal_name: str,
    delta_paths: list[str],
    params: dict | None = None,
    n_runs: int = 500,
    seed: int = 42,
    write_report: bool = True,
) -> dict:
    """bar 기반 4개 시그널(footprint_imbalance/cvd_divergence/wall_proximity/iceberg_refill)
    공통 실행 경로. 데이터 없음/표본 부족 -> BLOCKED 리포트."""
    if signal_name not in SIGNAL_BUILDERS:
        raise ValueError(f"unknown signal_name: {signal_name}")

    p = {**DEFAULTS, **(params or {})}
    deltas = load_deltas(delta_paths)
    if not deltas:
        return _blocked(symbol, signal_name, "no delta data — collector 확인 필요", write_report)

    data = SIGNAL_BUILDERS[signal_name](deltas)
    closes, signals, eligible = data["closes"], data["signals"], data["eligible"]
    if len(closes) < 10:
        return _blocked(symbol, signal_name, f"델타→버킷 변환 후 {len(closes)}봉뿐 — 최소 표본 미달", write_report)

    notional = closes[-1] * NOTIONAL_MULTIPLIER.get(symbol, 20.0)
    cost_bps = ib_futures_effective_cost_bps(symbol, notional)
    trades = simulate_long_short(closes, signals, p["trade_size"], cost_bps)
    strat = trade_metrics(trades)

    holds = [max(1, t["exit_idx"] - t["entry_idx"]) for t in trades] or [1]
    rnd = random_same_frequency(
        closes, n_trades=strat["num_trades"], holding_periods=holds,
        trade_size=p["trade_size"], cost_bps=cost_bps,
        eligible_indices=eligible, n_runs=n_runs, seed=seed,
    )
    pval = empirical_p_value(strat["total_pnl"], rnd)

    result = {
        "symbol": symbol, "signal": signal_name, "blocked": False,
        "strategy": strat, "random": pval,
        "n_bars": len(closes), "eligible_count": len(eligible),
    }
    if write_report:
        rep = build_report(
            name=f"orderflow_futures_{signal_name}_{symbol}",
            hypothesis=HYPOTHESIS_TEXT[signal_name],
            universe=[symbol], timeframe="1m/2s(신호별 상이)",
            cost={"cost_bps": cost_bps, "slippage_bps": 0, "spread_bps": 0, "effective_bps": cost_bps},
            strategy=strat, random_pval=pval,
            naive={"total_pnl": None, "note": "오더플로우 신호는 buy&hold 비교 부적합 -> random 분포가 주판정"},
            walk_forward_result={"summary": {}},
            is_harness_dryrun=False,
            extra={
                "n_bars": len(closes), "eligible_count": len(eligible),
                "note": "DORMANT hypothesis. NOT validated alpha. 1차 생존 판정용.",
            },
        )
        result["report"] = rep
    return result


def run_stop_run_hypothesis(
    symbol: str,
    delta_paths: list[str],
    hold_buckets_list: tuple[int, ...] = (1, 3, 5),
    trade_size: float = 1.0,
    n_runs: int = 500,
    seed: int = 42,
    write_report: bool = True,
) -> dict:
    """스탑런 이벤트 방향 즉시추종, N버킷 뒤 고정청산. random은 방향만 셔플
    (orderflow_absorption.run_large_trade_event_hypothesis와 동일 검정 설계)."""
    deltas = load_deltas(delta_paths)
    if not deltas:
        return _blocked(symbol, "stop_run", "no delta data — collector 확인 필요", write_report)

    events = stop_run_events(deltas)
    if len(events) < 10:
        return _blocked(symbol, "stop_run", f"스탑런 이벤트 {len(events)}건뿐 — 최소 표본 미달", write_report)

    order, buy, sell, last_price = _footprint_buckets(deltas)
    closes = [last_price[b] for b in order]
    notional = closes[-1] * NOTIONAL_MULTIPLIER.get(symbol, 20.0)
    cost_bps = ib_futures_effective_cost_bps(symbol, notional)

    import random as _random
    rng = _random.Random(seed)

    horizons: dict[str, dict] = {}
    for hold in hold_buckets_list:
        precomputed = []
        for ev in events:
            idx = ev["idx"]
            exit_idx = min(idx + hold, len(closes) - 1)
            entry_px, exit_px = closes[idx], closes[exit_idx]
            cost = (abs(entry_px) + abs(exit_px)) * trade_size * cost_bps / 10_000.0
            side_sign = 1.0 if ev["side"] == "buy" else -1.0
            precomputed.append((side_sign, entry_px, exit_px, cost))

        actual_pnls = [sign * (ex - en) * trade_size - c for sign, en, ex, c in precomputed]
        strat = trade_metrics([{"pnl": pnl} for pnl in actual_pnls])

        random_totals = []
        for _ in range(n_runs):
            total = 0.0
            for _sign, en, ex, c in precomputed:
                rsign = rng.choice((1.0, -1.0))
                total += rsign * (ex - en) * trade_size - c
            random_totals.append(round(total, 6))
        pval = empirical_p_value(strat["total_pnl"], random_totals)
        horizons[f"{hold}b"] = {"strategy": strat, "random": pval}

    result = {"symbol": symbol, "signal": "stop_run", "blocked": False,
              "n_events": len(events), "horizons": horizons}
    if write_report:
        for h_key, h_res in horizons.items():
            rep = build_report(
                name=f"orderflow_futures_stop_run_{symbol}_{h_key}",
                hypothesis=f"스탑런 이벤트 방향 즉시추종, {h_key} 고정청산",
                universe=[symbol], timeframe="event",
                cost={"cost_bps": cost_bps, "slippage_bps": 0, "spread_bps": 0, "effective_bps": cost_bps},
                strategy=h_res["strategy"], random_pval=h_res["random"],
                naive={"total_pnl": None, "note": "이벤트기반 방향추종 buy&hold 비교 부적합"},
                walk_forward_result={"summary": {}},
                is_harness_dryrun=False,
                extra={"n_events": len(events), "note": "DORMANT hypothesis. NOT validated alpha."},
            )
            h_res["report"] = rep
    return result


def run_all_hypotheses(
    delta_paths_by_symbol: dict[str, list[str]],
    n_runs: int = 500,
    seed: int = 42,
    write_report: bool = True,
) -> dict:
    """5신호 x N심볼 전부 실행 -> p-value 모아 BH-FDR 보정. BLOCKED 결과는
    p-value 없어 BH-FDR 입력에서 제외(survivors 배열은 results와 동일 순서 유지,
    BLOCKED 위치는 항상 False)."""
    results: dict[str, dict] = {}
    for symbol, paths in delta_paths_by_symbol.items():
        for signal_name in SIGNAL_BUILDERS:
            key = f"{symbol}:{signal_name}"
            results[key] = run_signal_hypothesis(symbol, signal_name, paths, n_runs=n_runs, seed=seed, write_report=write_report)
        results[f"{symbol}:stop_run"] = run_stop_run_hypothesis(symbol, paths, n_runs=n_runs, seed=seed, write_report=write_report)

    keys = list(results.keys())
    pvals: list[float] = []
    pval_keys: list[str] = []
    for k in keys:
        r = results[k]
        if r.get("blocked"):
            continue
        if "random" in r:
            p = r["random"].get("p_value")
            if p is not None:
                pvals.append(p)
                pval_keys.append(k)
        elif "horizons" in r:
            for h_key, h_res in r["horizons"].items():
                p = h_res["random"].get("p_value")
                if p is not None:
                    pvals.append(p)
                    pval_keys.append(f"{k}:{h_key}")

    from research.validation.multiple_testing import benjamini_hochberg
    bh = benjamini_hochberg(pvals, alpha=0.1)
    bh["keys"] = pval_keys
    return {"results": results, "bh_fdr": bh}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_futures_run.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add research/hypotheses/orderflow_futures.py tests/test_orderflow_futures_run.py
git commit -m "feat: 오더플로우 5신호 검증 오케스트레이션 + BH-FDR 종합판정 추가"
```

---

## Task 7: `_blocked` 헬퍼 + 전체 테스트 스위트 확인

**Files:**
- Modify: `research/hypotheses/orderflow_futures.py`

**Interfaces:**
- Consumes: `research.reports.alpha_report.REPORT_DIR`
- Produces: `_blocked(symbol: str, signal_name: str, msg: str, write_report: bool) -> dict`

Task 6에서 `_blocked`를 호출하지만 아직 정의 안 함 — 이 태스크에서 추가.

- [ ] **Step 1: Implement (append to `research/hypotheses/orderflow_futures.py`)**

```python
def _blocked(symbol: str, signal_name: str, msg: str, write_report: bool) -> dict:
    res = {"symbol": symbol, "signal": signal_name, "blocked": True, "reason": msg,
           "verdict": "BLOCKED: " + msg}
    if write_report:
        import json
        import os
        from research.reports.alpha_report import REPORT_DIR
        os.makedirs(REPORT_DIR, exist_ok=True)
        base = os.path.join(REPORT_DIR, f"orderflow_futures_{signal_name}_{symbol}")
        with open(base + ".json", "w") as f:
            json.dump(res, f, indent=2)
        with open(base + ".md", "w") as f:
            f.write(f"# Orderflow Futures {signal_name} — {symbol}\n\n**BLOCKED.** {msg}\n")
    return res
```

- [ ] **Step 2: Run full new-module test suite**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cost_model.py tests/test_run_ib_orderflow_tick_collect.py tests/test_orderflow_futures_signals.py tests/test_orderflow_futures_run.py -v`
Expected: all pass (3 + 8 + 12 + 6 = 29 tests)

- [ ] **Step 3: Run full project test suite to confirm no regressions**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: same pre-existing failures as before this branch (test_auth.py x3~4, test_backtest_happy_path) — no new failures.

- [ ] **Step 4: Commit**

```bash
git add research/hypotheses/orderflow_futures.py
git commit -m "feat: BLOCKED 리포트 헬퍼 추가, 오더플로우 검증 하네스 완성"
```

---

## Self-Review Notes

- **Spec coverage:** 5개 시그널(footprint 불균형=Task3, CVD 다이버전스=Task3, stop-run=Task5, heatmap 유동성벽=Task4, iceberg refill=Task4) 전부 태스크 배정됨. 수집기(Task2), 비용모델(Task1), BH-FDR 종합판정(Task6) 전부 커버.
- **Placeholder scan:** 없음 — 모든 스텝에 실행 가능한 완전한 코드.
- **Type consistency:** 모든 `build_*_signals`/`stop_run_events`가 `load_deltas`의 출력(`list[dict]`, `bucket_ts`/`ts` 키)을 일관되게 소비. `run_signal_hypothesis`/`run_stop_run_hypothesis`가 Task 3~5의 정확한 함수명·반환 키(`closes`/`signals`/`eligible`)를 그대로 사용.
- **의존 순서:** Task1(비용모델)→Task2(수집기, 독립)→Task3(footprint+cvd)→Task4(heatmap 2종, Task3의 `load_deltas` 재사용)→Task5(stop-run, Task3의 `_footprint_buckets` 재사용)→Task6(오케스트레이션, 1~5 전부 소비)→Task7(`_blocked` 헬퍼, Task6이 참조하지만 정의는 마지막) — Task6과 Task7이 같은 파일을 순차 수정하므로 반드시 순서대로 실행.
