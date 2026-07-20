# BTC.HL ICT+오더플로우 페이퍼 트레이딩 엔진 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BTC.HL을 15분봉(HTF, OB/iFVG 존)과 1분봉(LTF, CISD+반전형 오더플로우 트리거)으로 동시 감시하다가, 존 안에서 컨플루언스가 뜨면 자동으로 페이퍼 진입하고 스탑/다음 반대편 유동성 레벨 목표 청산까지 자동 기록하는 상시 프로세스를 만든다.

**Architecture:** `research/ict/paper/` 신규 패키지에 감지(반전트리거/존)·상태(포지션)·기록(저널)·조율(상태머신) 4계층을 분리 배치. 상시 진입점(`research/run_ict_paper_engine.py`)이 기존 `orderflow/hl_adapter.py` WS 클라이언트로 트레이드/호가를 받고, HL candleSnapshot REST를 15분 주기로 폴링해 상태머신에 먹인다.

**Tech Stack:** Python 3.14, `httpx`/`requests`(기존 관례상 `requests` 사용), `websockets`(기존 `orderflow/hl_adapter.py` 재사용), pytest(`asyncio_mode=auto`).

## Global Constraints

- Python 인터프리터: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`
- 테스트 실행: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
- `asyncio_mode="auto"` — 테스트 함수에 `@pytest.mark.asyncio` 절대 금지
- 라이브 WS/REST 호출은 테스트에서 하지 않음(기존 `test_orderflow_binance_adapter.py` FakeConnect 패턴처럼 항상 주입 가능한 fake로 대체)
- 오더플로우 반전 트리거 임계값은 `lib/orderflow-data.ts`/`research/strategies/orderflow_absorption.py`와 동일값 — 튜닝 금지, 값 이식만
- 저널 CSV(`seokminal-dashboard/docs/orderflow-journal.csv`) 헤더 순서 고정: `datetime,symbol,direction,ict_context,of_trigger,level_basis,entry,stop,target,risk_r,result_r,note` — 바꾸지 않는다
- 설계 스펙 원본: `docs/superpowers/specs/2026-07-20-ict-orderflow-paper-engine-design.md`

---

### Task 1: LTF 봉 빌더 + 반전형 오더플로우 트리거

**Files:**
- Create: `research/ict/paper/__init__.py` (빈 파일 — 패키지 마커)
- Create: `research/ict/paper/reversal_triggers.py`
- Test: `tests/test_ict_paper_reversal_triggers.py`

**Interfaces:**
- Consumes: `orderflow.models.TradeEvent`(기존)
- Produces:
  - `check_absorption(bar: dict, buy_vol: float, sell_vol: float, rolling_median: float) -> "buy"|"sell"|None`
  - `check_stop_run(bar: dict, recent_bars: list[dict], total_vol: float, rolling_median: float) -> "buy"|"sell"|None`
  - `check_divergence(bar: dict, recent_bars: list[dict], net_delta: float, total_vol: float) -> "buy"|"sell"|None`
  - `class LTFBarBuilder`: `__init__(bucket_sec: float = 60.0)`, `on_trade(trade: TradeEvent) -> dict | None`(봉 마감 시 `{"bar": {"ts","open","high","low","close"}, "of_trigger": "absorption"|"stop_run"|"divergence"|None, "side": "buy"|"sell"|None}` 반환, 아니면 `None`), `.bars: list[dict]`(완성봉 누적, 최대 200개)
  - Task 5(`state_machine.py`)가 `LTFBarBuilder`의 반환 dict를 그대로 `PaperEngine.on_ltf_bar()`에 넘긴다.

- [ ] **Step 1: 패키지 마커 생성**

```bash
mkdir -p research/ict/paper
touch research/ict/paper/__init__.py
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_ict_paper_reversal_triggers.py`:

```python
from orderflow.models import TradeEvent
from research.ict.paper.reversal_triggers import (
    LTFBarBuilder,
    check_absorption,
    check_divergence,
    check_stop_run,
)


def test_check_absorption_detects_sell_dominance_without_price_drop_as_buy_signal():
    bar = {"open": 100.0, "close": 100.2}
    result = check_absorption(bar, buy_vol=3.0, sell_vol=27.0, rolling_median=1.0)
    assert result == "buy"


def test_check_absorption_returns_none_below_noise_floor():
    bar = {"open": 100.0, "close": 100.2}
    result = check_absorption(bar, buy_vol=3.0, sell_vol=4.0, rolling_median=5.0)
    assert result is None


def test_check_absorption_returns_none_before_warmup():
    bar = {"open": 100.0, "close": 100.2}
    result = check_absorption(bar, buy_vol=3.0, sell_vol=27.0, rolling_median=0.0)
    assert result is None


def test_check_stop_run_detects_bullish_stop_run():
    recent_bars = [{"open": 100 + i, "high": 105, "low": 95, "close": 100} for i in range(20)]
    bar = {"open": 100, "high": 101, "low": 90, "close": 96}
    result = check_stop_run(bar, recent_bars, total_vol=100.0, rolling_median=1.0)
    assert result == "buy"


def test_check_stop_run_returns_none_when_lookback_insufficient():
    bar = {"open": 100, "high": 101, "low": 90, "close": 96}
    result = check_stop_run(bar, recent_bars=[], total_vol=100.0, rolling_median=1.0)
    assert result is None


def test_check_divergence_detects_bearish_divergence_on_new_high_with_sell_delta():
    recent_bars = [{"high": 100, "low": 90} for _ in range(20)]
    bar = {"high": 105, "low": 96}
    result = check_divergence(bar, recent_bars, net_delta=-50.0, total_vol=100.0)
    assert result == "sell"


def test_check_divergence_returns_none_when_delta_ratio_too_small():
    recent_bars = [{"high": 100, "low": 90} for _ in range(20)]
    bar = {"high": 105, "low": 96}
    result = check_divergence(bar, recent_bars, net_delta=-5.0, total_vol=100.0)
    assert result is None


def test_ltf_bar_builder_finalizes_bar_with_absorption_trigger_on_bucket_rollover():
    builder = LTFBarBuilder(bucket_sec=60.0)
    # 워밍업(버킷0): 작은 체결로 rolling median을 낮게 유지
    for i in range(20):
        builder.on_trade(TradeEvent(symbol="BTC.HL", ts=float(i), price=99.0, size=0.1, side="buy"))

    # 버킷1: 매도 우세(27) vs 매수(3), 종가>=시가 → 흡수(강세) 신호가 나야 함
    bucket1_trades = [
        TradeEvent(symbol="BTC.HL", ts=60.0, price=100.0, size=3.0, side="buy"),
        TradeEvent(symbol="BTC.HL", ts=70.0, price=100.1, size=9.0, side="sell"),
        TradeEvent(symbol="BTC.HL", ts=80.0, price=100.2, size=9.0, side="sell"),
        TradeEvent(symbol="BTC.HL", ts=90.0, price=100.2, size=9.0, side="sell"),
    ]
    for t in bucket1_trades:
        builder.on_trade(t)

    # 버킷2 진입 트레이드 — 이 시점에 버킷1이 finalize된다
    result = builder.on_trade(TradeEvent(symbol="BTC.HL", ts=121.0, price=100.5, size=1.0, side="buy"))

    assert result is not None
    assert result["bar"]["open"] == 100.0
    assert result["bar"]["high"] == 100.2
    assert result["bar"]["low"] == 100.0
    assert result["bar"]["close"] == 100.2
    assert result["of_trigger"] == "absorption"
    assert result["side"] == "buy"
    assert len(builder.bars) == 2  # 버킷0, 버킷1 둘 다 완성됨
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ict_paper_reversal_triggers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.ict.paper.reversal_triggers'`

- [ ] **Step 4: 구현 작성**

`research/ict/paper/reversal_triggers.py`:

```python
"""LTF(1분) 봉 빌더 + 반전형 오더플로우 트리거(흡수/스탑런/다이버전스) 라이브 감지.
프론트(lib/orderflow-data.ts: detectAbsorption/detectStopRuns/detectDeltaDivergence)와
동일 임계값 — 대시보드와 다른 신호를 보면 안 되므로 값만 이식하고 튜닝하지 않는다."""
from __future__ import annotations

from collections import deque
from typing import Literal

from orderflow.models import TradeEvent

ROLLING_WINDOW = 200
ABSORPTION_DOMINANCE_RATIO = 0.7
ABSORPTION_NOISE_FLOOR_MULTIPLIER = 10.0
STOP_RUN_LOOKBACK_BARS = 20
STOP_RUN_NOISE_FLOOR_MULTIPLIER = 10.0
DIVERGENCE_LOOKBACK_BARS = 20
DIVERGENCE_MIN_DELTA_RATIO = 0.25
MAX_BARS_KEPT = 200

Side = Literal["buy", "sell"]


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return (s[mid - 1] + s[mid]) / 2.0 if n % 2 == 0 else s[mid]


def check_absorption(bar: dict, buy_vol: float, sell_vol: float, rolling_median: float) -> Side | None:
    """`lib/orderflow-data.ts::detectAbsorption`과 동일 규칙."""
    if rolling_median <= 0:
        return None
    total = buy_vol + sell_vol
    noise_floor = rolling_median * ABSORPTION_NOISE_FLOOR_MULTIPLIER
    if total < noise_floor:
        return None
    sell_ratio = sell_vol / total
    buy_ratio = buy_vol / total
    if sell_ratio >= ABSORPTION_DOMINANCE_RATIO and bar["close"] >= bar["open"]:
        return "buy"  # 매도 우세인데 안 밀림 = 매도 흡수 = 강세
    if buy_ratio >= ABSORPTION_DOMINANCE_RATIO and bar["close"] <= bar["open"]:
        return "sell"
    return None


def check_stop_run(bar: dict, recent_bars: list[dict], total_vol: float, rolling_median: float) -> Side | None:
    """`lib/orderflow-data.ts::detectStopRuns`와 동일 규칙. recent_bars = 직전 20봉(현재봉 제외)."""
    if rolling_median <= 0 or len(recent_bars) < STOP_RUN_LOOKBACK_BARS:
        return None
    noise_floor = rolling_median * STOP_RUN_NOISE_FLOOR_MULTIPLIER
    if total_vol < noise_floor:
        return None
    window = recent_bars[-STOP_RUN_LOOKBACK_BARS:]
    recent_high = max(b["high"] for b in window)
    recent_low = min(b["low"] for b in window)
    if bar["high"] > recent_high and bar["close"] < recent_high:
        return "sell"
    if bar["low"] < recent_low and bar["close"] > recent_low:
        return "buy"
    return None


def check_divergence(bar: dict, recent_bars: list[dict], net_delta: float, total_vol: float) -> Side | None:
    """`lib/orderflow-data.ts::detectDeltaDivergence`와 동일 규칙."""
    if len(recent_bars) < DIVERGENCE_LOOKBACK_BARS or total_vol <= 0:
        return None
    if abs(net_delta) < total_vol * DIVERGENCE_MIN_DELTA_RATIO:
        return None
    window = recent_bars[-DIVERGENCE_LOOKBACK_BARS:]
    recent_high = max(b["high"] for b in window)
    recent_low = min(b["low"] for b in window)
    if bar["high"] > recent_high and net_delta < 0:
        return "sell"
    if bar["low"] < recent_low and net_delta > 0:
        return "buy"
    return None


def _classify(
    bar: dict, recent_bars: list[dict], buy_vol: float, sell_vol: float, rolling_median: float
) -> tuple[str | None, Side | None]:
    side = check_absorption(bar, buy_vol, sell_vol, rolling_median)
    if side is not None:
        return "absorption", side
    total_vol = buy_vol + sell_vol
    side = check_stop_run(bar, recent_bars, total_vol, rolling_median)
    if side is not None:
        return "stop_run", side
    side = check_divergence(bar, recent_bars, buy_vol - sell_vol, total_vol)
    if side is not None:
        return "divergence", side
    return None, None


class LTFBarBuilder:
    """1분 트레이드를 봉으로 집계, 봉 마감마다 반전형 트리거 판정까지 함께 반환."""

    def __init__(self, bucket_sec: float = 60.0) -> None:
        self._bucket_sec = bucket_sec
        self._cur_bucket: int | None = None
        self._o = self._h = self._l = self._c = 0.0
        self._buy_vol = 0.0
        self._sell_vol = 0.0
        self._recent_sizes: deque[float] = deque(maxlen=ROLLING_WINDOW)
        self.bars: list[dict] = []

    def on_trade(self, trade: TradeEvent) -> dict | None:
        bucket = int(trade.ts // self._bucket_sec)
        finalized: dict | None = None
        if self._cur_bucket is None:
            self._cur_bucket = bucket
            self._o = self._h = self._l = self._c = trade.price
            self._buy_vol = 0.0
            self._sell_vol = 0.0
        elif bucket != self._cur_bucket:
            finalized = self._finalize()
            self._cur_bucket = bucket
            self._o = self._h = self._l = self._c = trade.price
            self._buy_vol = 0.0
            self._sell_vol = 0.0

        self._h = max(self._h, trade.price)
        self._l = min(self._l, trade.price)
        self._c = trade.price
        if trade.side == "buy":
            self._buy_vol += trade.size
        else:
            self._sell_vol += trade.size
        self._recent_sizes.append(trade.size)
        return finalized

    def _finalize(self) -> dict:
        bar = {
            "ts": self._cur_bucket * self._bucket_sec,
            "open": self._o, "high": self._h, "low": self._l, "close": self._c,
        }
        rolling_median = _median(list(self._recent_sizes))
        recent_bars = self.bars[-MAX_BARS_KEPT:]
        trigger_name, side = _classify(bar, recent_bars, self._buy_vol, self._sell_vol, rolling_median)

        self.bars.append(bar)
        if len(self.bars) > MAX_BARS_KEPT:
            self.bars.pop(0)

        return {"bar": bar, "of_trigger": trigger_name, "side": side}
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ict_paper_reversal_triggers.py -v`
Expected: PASS(9 tests)

- [ ] **Step 6: 커밋**

```bash
git add research/ict/paper/__init__.py research/ict/paper/reversal_triggers.py tests/test_ict_paper_reversal_triggers.py
git commit -m "feat: LTF 봉 빌더 + 반전형 오더플로우 트리거(흡수/스탑런/다이버전스) 라이브 포팅"
```

---

### Task 2: HTF 존(OB/iFVG) 추적기

**Files:**
- Create: `research/ict/paper/htf_zones.py`
- Test: `tests/test_ict_paper_htf_zones.py`

**Interfaces:**
- Consumes: `research.ict.primitives.order_blocks`, `research.ict.primitives.fair_value_gaps`(기존, 미수정)
- Produces:
  - `fetch_htf_bars(coin: str, interval: str = "15m", bars: int = 100, timeout: float = 20.0) -> list[dict]`(각 원소 `{"ts","open","high","low","close"}`) — 라이브 REST 호출, 테스트 대상 아님
  - `ifvg_zones(h: list[float], l: list[float], c: list[float], window: int = 8) -> list[dict]`(각 원소 `{"idx","type","zone_lo","zone_hi"}`)
  - `class ZoneTracker`: `__init__(max_bars: int = 500)`, `update(bar: dict) -> None`(bar는 `{"ts","open","high","low","close"}`), `zone_at_price(price: float) -> dict | None`(활성 존만, `{"source","type","zone_lo","zone_hi","status"}`), `mark_consumed(zone: dict) -> None`, `next_opposing_level(side: "bullish"|"bearish", entry_price: float) -> float | None`(HTF 스윙 기준 진입가 다음 반대편 유동성 레벨 — 없으면 `None`)
  - Task 5(`state_machine.py`)가 `ZoneTracker`를 소비: `on_htf_bar`에서 `update()`, 진입판정에서 `zone_at_price()`+`next_opposing_level()`(목표가 계산)+`mark_consumed()`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ict_paper_htf_zones.py`:

```python
from research.ict.paper.htf_zones import ZoneTracker, ifvg_zones


def test_ifvg_zones_detects_bullish_zone_after_bearish_fvg_violation():
    h = [10, 9, 5, 12]
    l = [8, 7, 4, 11]
    c = [8.5, 7.5, 4.5, 11.5]
    zones = ifvg_zones(h, l, c, window=8)
    assert {"idx": 3, "type": "bullish", "zone_lo": 5, "zone_hi": 8} in zones


def test_ifvg_zones_returns_empty_when_no_violation():
    h = [10, 9, 5]
    l = [8, 7, 4]
    c = [8.5, 7.5, 4.5]
    assert ifvg_zones(h, l, c, window=8) == []


def test_zone_tracker_creates_ob_zone_and_finds_it_by_price():
    tracker = ZoneTracker()
    tracker.update({"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5})
    tracker.update({"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105})
    zone = tracker.zone_at_price(100.0)
    assert zone is not None
    assert zone["source"] == "OB"
    assert zone["type"] == "bullish"
    assert zone["zone_lo"] == 99
    assert zone["zone_hi"] == 101.5


def test_zone_tracker_zone_at_price_returns_none_outside_zone():
    tracker = ZoneTracker()
    tracker.update({"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5})
    tracker.update({"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105})
    assert tracker.zone_at_price(50.0) is None


def test_zone_tracker_invalidates_zone_on_opposite_close():
    tracker = ZoneTracker()
    tracker.update({"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5})
    tracker.update({"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105})
    assert tracker.zone_at_price(100.0) is not None
    tracker.update({"ts": 1800, "open": 105, "high": 105, "low": 90, "close": 90})
    assert tracker.zone_at_price(100.0) is None


def test_zone_tracker_mark_consumed_removes_zone_from_active_lookup():
    tracker = ZoneTracker()
    tracker.update({"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5})
    tracker.update({"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105})
    zone = tracker.zone_at_price(100.0)
    tracker.mark_consumed(zone)
    assert tracker.zone_at_price(100.0) is None


def test_next_opposing_level_finds_nearest_swing_high_above_entry():
    tracker = ZoneTracker()
    bars = [
        {"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5},
        {"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105},
        {"ts": 1800, "open": 105, "high": 110, "low": 104, "close": 108},
        {"ts": 2700, "open": 103.5, "high": 104, "low": 100, "close": 103},
        {"ts": 3600, "open": 103, "high": 103, "low": 99.5, "close": 102},
    ]
    for bar in bars:
        tracker.update(bar)
    assert tracker.next_opposing_level("bullish", entry_price=101.0) == 110.0


def test_next_opposing_level_returns_none_when_no_swing_yet():
    tracker = ZoneTracker()
    tracker.update({"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5})
    tracker.update({"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105})
    assert tracker.next_opposing_level("bullish", entry_price=101.0) is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ict_paper_htf_zones.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.ict.paper.htf_zones'`

- [ ] **Step 3: 구현 작성**

`research/ict/paper/htf_zones.py`:

```python
"""HTF(15분봉) OB/iFVG 존 추적 — HL candleSnapshot REST 폴링, research.ict.primitives 재사용."""
from __future__ import annotations

import time

import requests

from research.ict.primitives import fair_value_gaps, order_blocks, swings

HL_INFO_URL = "https://api.hyperliquid.xyz/info"
IFVG_WINDOW = 8
_INTERVAL_SEC = {"1m": 60, "15m": 900, "1h": 3600}


def fetch_htf_bars(coin: str, interval: str = "15m", bars: int = 100, timeout: float = 20.0) -> list[dict]:
    """최근 `bars`개 캔들만 REST로 받는다 — 아카이빙용 hl_candle_loader.fetch와 달리
    지속 저장 없이 라이브 폴링 전용, 매 호출 최근 구간만 재조회."""
    interval_sec = _INTERVAL_SEC[interval]
    now = int(time.time() * 1000)
    start = now - bars * interval_sec * 1000
    resp = requests.post(
        HL_INFO_URL,
        json={"type": "candleSnapshot", "req": {"coin": coin, "interval": interval, "startTime": start, "endTime": now}},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {
            "ts": int(c["t"] // 1000), "open": float(c["o"]), "high": float(c["h"]),
            "low": float(c["l"]), "close": float(c["c"]),
        }
        for c in data
    ]


def ifvg_zones(h: list[float], l: list[float], c: list[float], window: int = IFVG_WINDOW) -> list[dict]:
    """`primitives.ifvg_events`는 되돌림 터치 시점 idx 하나만 남기지만, 존 추적엔 FVG 원래
    가격구간(zone_lo/zone_hi)이 필요해 관통 시점(idx)에 그 구간을 존으로 되돌려준다."""
    fvgs = fair_value_gaps(h, l)
    n = len(c)
    out = []
    for f in fvgs:
        i = f["idx"]
        if f["type"] == "bearish":
            viol = next((j for j in range(i + 1, min(i + 1 + window, n)) if c[j] > f["gap_hi"]), None)
            if viol is not None:
                out.append({"idx": viol, "type": "bullish", "zone_lo": f["gap_lo"], "zone_hi": f["gap_hi"]})
        else:
            viol = next((j for j in range(i + 1, min(i + 1 + window, n)) if c[j] < f["gap_lo"]), None)
            if viol is not None:
                out.append({"idx": viol, "type": "bearish", "zone_lo": f["gap_lo"], "zone_hi": f["gap_hi"]})
    return out


class ZoneTracker:
    """OB/iFVG 존을 15분봉마다 갱신·무효화 추적. 단일 코인용, 인스턴스당 봉 히스토리 보유."""

    def __init__(self, max_bars: int = 500) -> None:
        self._max_bars = max_bars
        self._o: list[float] = []
        self._h: list[float] = []
        self._l: list[float] = []
        self._c: list[float] = []
        self._zones: dict[tuple, dict] = {}  # key=(source,type,zone_lo,zone_hi) -> record

    def update(self, bar: dict) -> None:
        self._o.append(bar["open"]); self._h.append(bar["high"])
        self._l.append(bar["low"]); self._c.append(bar["close"])
        if len(self._c) > self._max_bars:
            self._o.pop(0); self._h.pop(0); self._l.pop(0); self._c.pop(0)

        obs = order_blocks(self._o, self._h, self._l, self._c)
        ifvgs = ifvg_zones(self._h, self._l, self._c)
        for z in obs:
            key = ("OB", z["type"], z["zone_lo"], z["zone_hi"])
            self._zones.setdefault(
                key, {"source": "OB", "type": z["type"], "zone_lo": z["zone_lo"], "zone_hi": z["zone_hi"], "status": "active"}
            )
        for z in ifvgs:
            key = ("iFVG", z["type"], z["zone_lo"], z["zone_hi"])
            self._zones.setdefault(
                key, {"source": "iFVG", "type": z["type"], "zone_lo": z["zone_lo"], "zone_hi": z["zone_hi"], "status": "active"}
            )

        latest_close = self._c[-1]
        for rec in self._zones.values():
            if rec["status"] != "active":
                continue
            if rec["type"] == "bullish" and latest_close < rec["zone_lo"]:
                rec["status"] = "invalidated"
            elif rec["type"] == "bearish" and latest_close > rec["zone_hi"]:
                rec["status"] = "invalidated"

    def zone_at_price(self, price: float) -> dict | None:
        for rec in self._zones.values():
            if rec["status"] == "active" and rec["zone_lo"] <= price <= rec["zone_hi"]:
                return rec
        return None

    def mark_consumed(self, zone: dict) -> None:
        zone["status"] = "consumed"

    def next_opposing_level(self, side: str, entry_price: float) -> float | None:
        """진입가 기준 다음 반대편 유동성 레벨(HTF 스윙) — 없으면 None(목표 미확정,
        진입 스킵 신호로 쓰인다)."""
        sw = swings(self._h, self._l)
        if side == "bullish":
            candidates = [self._h[i] for i in sw["highs"] if self._h[i] > entry_price]
            return min(candidates) if candidates else None
        candidates = [self._l[i] for i in sw["lows"] if self._l[i] < entry_price]
        return max(candidates) if candidates else None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ict_paper_htf_zones.py -v`
Expected: PASS(8 tests)

- [ ] **Step 5: 커밋**

```bash
git add research/ict/paper/htf_zones.py tests/test_ict_paper_htf_zones.py
git commit -m "feat: HTF 15분봉 OB/iFVG 존 추적기(REST 폴링+무효화) 추가"
```

---

### Task 3: 포지션 상태 파일 (크래시 복구)

**Files:**
- Create: `research/ict/paper/position_state.py`
- Test: `tests/test_ict_paper_position_state.py`

**Interfaces:**
- Consumes: 없음(순수 dataclass + 파일 I/O)
- Produces:
  - `@dataclass class PositionState`: `side: str, entry_price: float, stop: float, target: float, zone_source: str, of_trigger: str, entered_ts: float`
  - `save_position_state(path: str, state: PositionState) -> None`
  - `load_position_state(path: str) -> PositionState | None`
  - `clear_position_state(path: str) -> None`
  - Task 5가 `PaperEngine.__init__`에서 `load_position_state`로 재시작 복구, 진입 시 `save_position_state`, 청산 시 `clear_position_state`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ict_paper_position_state.py`:

```python
import os

from research.ict.paper.position_state import (
    PositionState,
    clear_position_state,
    load_position_state,
    save_position_state,
)


def test_save_and_load_roundtrip(tmp_path):
    path = str(tmp_path / "state.json")
    state = PositionState(
        side="bullish", entry_price=101.0, stop=99.0, target=105.0,
        zone_source="OB", of_trigger="absorption", entered_ts=180.0,
    )
    save_position_state(path, state)
    loaded = load_position_state(path)
    assert loaded == state


def test_load_missing_returns_none(tmp_path):
    assert load_position_state(str(tmp_path / "nope.json")) is None


def test_clear_removes_file(tmp_path):
    path = str(tmp_path / "state.json")
    save_position_state(
        path,
        PositionState(side="bullish", entry_price=101.0, stop=99.0, target=105.0,
                       zone_source="OB", of_trigger="absorption", entered_ts=180.0),
    )
    clear_position_state(path)
    assert not os.path.exists(path)


def test_clear_missing_file_does_not_raise(tmp_path):
    clear_position_state(str(tmp_path / "nope.json"))
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ict_paper_position_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.ict.paper.position_state'`

- [ ] **Step 3: 구현 작성**

`research/ict/paper/position_state.py`:

```python
"""IN_POSITION 상태 크래시 복구용 상태파일. 프로세스 재시작 시 진행 중이던
페이퍼 포지션을 잃지 않도록 진입 시점에 기록, 청산 시 삭제한다."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass


@dataclass
class PositionState:
    side: str  # "bullish" | "bearish"
    entry_price: float
    stop: float
    target: float
    zone_source: str  # "OB" | "iFVG"
    of_trigger: str  # "absorption" | "stop_run" | "divergence"
    entered_ts: float


def save_position_state(path: str, state: PositionState) -> None:
    with open(path, "w") as f:
        json.dump(asdict(state), f)


def load_position_state(path: str) -> PositionState | None:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    return PositionState(**data)


def clear_position_state(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ict_paper_position_state.py -v`
Expected: PASS(4 tests)

- [ ] **Step 5: 커밋**

```bash
git add research/ict/paper/position_state.py tests/test_ict_paper_position_state.py
git commit -m "feat: 페이퍼 포지션 크래시 복구 상태파일(save/load/clear) 추가"
```

---

### Task 4: 저널 CSV 기록기

**Files:**
- Create: `research/ict/paper/journal_writer.py`
- Test: `tests/test_ict_paper_journal_writer.py`

**Interfaces:**
- Consumes: 없음(순수 CSV I/O)
- Produces:
  - `append_trade_row(path: str, *, entered_ts: float, symbol: str, direction: str, ict_context: str, of_trigger: str, level_basis: str, entry: float, stop: float, target: float, risk_r: float, result_r: float, note: str) -> None`
  - Task 5가 청산 시점에 이 함수 1회 호출.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ict_paper_journal_writer.py`:

```python
import csv

from research.ict.paper.journal_writer import append_trade_row


def test_append_trade_row_creates_file_with_header_and_row(tmp_path):
    path = str(tmp_path / "journal.csv")
    append_trade_row(
        path, entered_ts=1700000000.0, symbol="BTC.HL", direction="long",
        ict_context="CISD+OB", of_trigger="absorption", level_basis="OB",
        entry=101.0, stop=99.0, target=105.0, risk_r=1.0, result_r=2.0, note="test",
    )
    with open(path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTC.HL"
    assert rows[0]["direction"] == "long"
    assert rows[0]["result_r"] == "2.0"


def test_append_trade_row_appends_without_duplicating_header(tmp_path):
    path = str(tmp_path / "journal.csv")
    for i in range(2):
        append_trade_row(
            path, entered_ts=1700000000.0 + i, symbol="BTC.HL", direction="long",
            ict_context="CISD+OB", of_trigger="absorption", level_basis="OB",
            entry=101.0, stop=99.0, target=105.0, risk_r=1.0, result_r=2.0, note="",
        )
    with open(path) as f:
        lines = f.readlines()
    assert lines[0].startswith("datetime,")
    assert len(lines) == 3  # 헤더 1 + 행 2
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ict_paper_journal_writer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.ict.paper.journal_writer'`

- [ ] **Step 3: 구현 작성**

`research/ict/paper/journal_writer.py`:

```python
"""완료된 페이퍼 트레이드 1건을 저널 CSV(프론트 repo)에 append.
docs/orderflow-journal.csv 헤더 순서 고정 — 바꾸지 않는다."""
from __future__ import annotations

import csv
import datetime as _dt
import os

FIELDS = [
    "datetime", "symbol", "direction", "ict_context", "of_trigger", "level_basis",
    "entry", "stop", "target", "risk_r", "result_r", "note",
]


def append_trade_row(
    path: str,
    *,
    entered_ts: float,
    symbol: str,
    direction: str,
    ict_context: str,
    of_trigger: str,
    level_basis: str,
    entry: float,
    stop: float,
    target: float,
    risk_r: float,
    result_r: float,
    note: str,
) -> None:
    row = {
        "datetime": _dt.datetime.fromtimestamp(entered_ts, tz=_dt.timezone.utc).isoformat(),
        "symbol": symbol, "direction": direction, "ict_context": ict_context,
        "of_trigger": of_trigger, "level_basis": level_basis,
        "entry": entry, "stop": stop, "target": target,
        "risk_r": risk_r, "result_r": result_r, "note": note,
    }
    is_new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ict_paper_journal_writer.py -v`
Expected: PASS(2 tests)

- [ ] **Step 5: 커밋**

```bash
git add research/ict/paper/journal_writer.py tests/test_ict_paper_journal_writer.py
git commit -m "feat: 페이퍼 트레이드 저널 CSV append 기록기 추가"
```

---

### Task 5: 상태머신(FLAT/IN_POSITION) — 진입·청산 조율

**Files:**
- Create: `research/ict/paper/state_machine.py`
- Test: `tests/test_ict_paper_state_machine.py`

**Interfaces:**
- Consumes:
  - `research.ict.paper.htf_zones.ZoneTracker`(Task 2)
  - `research.ict.paper.position_state.{PositionState, save_position_state, load_position_state, clear_position_state}`(Task 3)
  - `research.ict.paper.journal_writer.append_trade_row`(Task 4)
  - `research.ict.primitives.cisd_events`(기존, 미수정)
  - `LTFBarBuilder.on_trade()`가 반환하는 `dict`(Task 1) — `on_ltf_bar()`가 그대로 받음
- Produces:
  - `class PaperEngine`: `__init__(symbol: str, state_path: str, journal_path: str)`, `on_htf_bar(bar: dict) -> None`, `on_ltf_bar(result: dict) -> None`, `on_price_tick(price: float) -> None`, `.position: PositionState | None`, `.zones: ZoneTracker`
  - Task 6(`run_ict_paper_engine.py`)이 `PaperEngine`을 생성해 WS/REST 이벤트를 그대로 흘려넣는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ict_paper_state_machine.py`:

```python
import csv
import os

import pytest

from research.ict.paper.state_machine import PaperEngine


@pytest.fixture
def engine_with_open_bullish_position(tmp_path):
    state_path = str(tmp_path / "state.json")
    journal_path = str(tmp_path / "journal.csv")
    engine = PaperEngine(symbol="BTC.HL", state_path=state_path, journal_path=journal_path)

    # HTF: bullish OB 존 [99, 101.5] 형성(봉0-1) + 진입가(101.0) 위쪽 swing high(110,
    # 봉2, k=2 기본값 — 5봉 있어야 idx2가 평가됨)를 다음 반대편 유동성 레벨로 잡는다.
    htf_bars = [
        {"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5},
        {"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105},
        {"ts": 1800, "open": 105, "high": 110, "low": 104, "close": 108},
        {"ts": 2700, "open": 103.5, "high": 104, "low": 100, "close": 103},
        {"ts": 3600, "open": 103, "high": 103, "low": 99.5, "close": 102},
    ]
    for bar in htf_bars:
        engine.on_htf_bar(bar)

    # LTF: 봉1~2 연속 하락 후 봉3에서 봉1 시가 위로 종가 관통 = 강세 CISD(min_run=2)
    ltf_bars = [
        {"ts": 0, "open": 100, "high": 100.6, "low": 99.9, "close": 100.5},
        {"ts": 60, "open": 100.5, "high": 100.6, "low": 99.3, "close": 99.5},
        {"ts": 120, "open": 99.5, "high": 99.6, "low": 98.3, "close": 98.5},
        {"ts": 180, "open": 98.5, "high": 101.2, "low": 98.4, "close": 101.0},
    ]
    for bar in ltf_bars[:-1]:
        engine.on_ltf_bar({"bar": bar, "of_trigger": None, "side": None})
    # 마지막 봉에서 CISD + 반전형 트리거(흡수) 동시 발생 → 진입
    engine.on_ltf_bar({"bar": ltf_bars[-1], "of_trigger": "absorption", "side": "buy"})

    assert engine.position is not None
    return engine, journal_path, state_path


def test_enters_position_on_zone_plus_cisd_plus_trigger_confluence(engine_with_open_bullish_position):
    engine, _, state_path = engine_with_open_bullish_position
    assert engine.position.side == "bullish"
    assert engine.position.entry_price == 101.0
    assert engine.position.stop == 99.0
    assert engine.position.target == 110.0  # 다음 반대편 유동성 레벨(HTF swing high)
    assert engine.position.zone_source == "OB"
    assert engine.position.of_trigger == "absorption"
    assert os.path.exists(state_path)


def test_exits_on_target_touch_and_writes_journal_row(engine_with_open_bullish_position):
    engine, journal_path, state_path = engine_with_open_bullish_position
    engine.on_price_tick(110.0)
    assert engine.position is None
    assert not os.path.exists(state_path)
    with open(journal_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["direction"] == "long"
    assert rows[0]["of_trigger"] == "absorption"
    assert rows[0]["level_basis"] == "OB"
    assert float(rows[0]["result_r"]) == pytest.approx(4.5)  # (110-101)/2


def test_exits_on_stop_touch_result_r_negative(engine_with_open_bullish_position):
    engine, journal_path, _ = engine_with_open_bullish_position
    engine.on_price_tick(99.0)
    assert engine.position is None
    with open(journal_path) as f:
        rows = list(csv.DictReader(f))
    assert float(rows[0]["result_r"]) == pytest.approx(-1.0)


def test_no_reentry_on_same_zone_after_exit(engine_with_open_bullish_position):
    engine, _, _ = engine_with_open_bullish_position
    engine.on_price_tick(99.0)  # 청산(스탑) — 존 consumed 처리됨
    assert engine.position is None
    engine.on_ltf_bar({
        "bar": {"ts": 240, "open": 101.0, "high": 101.3, "low": 100.8, "close": 101.0},
        "of_trigger": "absorption", "side": "buy",
    })
    assert engine.position is None


def test_skips_entry_when_no_opposing_swing_level_yet(tmp_path):
    state_path = str(tmp_path / "state.json")
    journal_path = str(tmp_path / "journal.csv")
    engine = PaperEngine(symbol="BTC.HL", state_path=state_path, journal_path=journal_path)

    # HTF: OB 존만 형성(봉 2개) — swing 평가엔 최소 5봉 필요하므로 next_opposing_level은 None
    engine.on_htf_bar({"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5})
    engine.on_htf_bar({"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105})

    ltf_bars = [
        {"ts": 0, "open": 100, "high": 100.6, "low": 99.9, "close": 100.5},
        {"ts": 60, "open": 100.5, "high": 100.6, "low": 99.3, "close": 99.5},
        {"ts": 120, "open": 99.5, "high": 99.6, "low": 98.3, "close": 98.5},
        {"ts": 180, "open": 98.5, "high": 101.2, "low": 98.4, "close": 101.0},
    ]
    for bar in ltf_bars[:-1]:
        engine.on_ltf_bar({"bar": bar, "of_trigger": None, "side": None})
    engine.on_ltf_bar({"bar": ltf_bars[-1], "of_trigger": "absorption", "side": "buy"})

    assert engine.position is None
    assert not os.path.exists(state_path)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ict_paper_state_machine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.ict.paper.state_machine'`

- [ ] **Step 3: 구현 작성**

`research/ict/paper/state_machine.py`:

```python
"""FLAT/IN_POSITION 상태머신 — HTF 존 + LTF CISD + 반전형 오더플로우 트리거 컨플루언스로
진입, 스탑/다음 반대편 유동성 레벨 목표로 청산. 단일 포지션만 추적(겹치면 저널 채점이 꼬임)."""
from __future__ import annotations

from research.ict.paper.htf_zones import ZoneTracker
from research.ict.paper.journal_writer import append_trade_row
from research.ict.paper.position_state import (
    PositionState,
    clear_position_state,
    load_position_state,
    save_position_state,
)
from research.ict.primitives import cisd_events

# CISD와 반전형 트리거가 서로 이 봉 수 이내면 컨플루언스로 인정 — 임의 기본값,
# 30건 미만 표본에서는 튜닝하지 않는다(design spec 7절).
CONFLUENCE_WINDOW_BARS = 5

_TRIGGER_TO_ZONE_TYPE = {"buy": "bullish", "sell": "bearish"}


class PaperEngine:
    def __init__(self, symbol: str, state_path: str, journal_path: str) -> None:
        self.symbol = symbol
        self._state_path = state_path
        self._journal_path = journal_path
        self.zones = ZoneTracker()
        self._ltf_bars: list[dict] = []
        self._recent_ltf_triggers: list[dict] = []  # {"bar_index","of_trigger","side"}
        self.position: PositionState | None = load_position_state(state_path)

    def on_htf_bar(self, bar: dict) -> None:
        self.zones.update(bar)

    def on_ltf_bar(self, result: dict) -> None:
        """LTFBarBuilder._finalize()가 반환한 dict를 그대로 받는다."""
        bar = result["bar"]
        self._ltf_bars.append(bar)
        if len(self._ltf_bars) > 200:
            self._ltf_bars.pop(0)
            self._recent_ltf_triggers = [
                {**t, "bar_index": t["bar_index"] - 1} for t in self._recent_ltf_triggers if t["bar_index"] > 0
            ]

        if result["of_trigger"] is not None:
            self._recent_ltf_triggers.append({
                "bar_index": len(self._ltf_bars) - 1,
                "of_trigger": result["of_trigger"],
                "side": result["side"],
            })

        if self.position is None:
            self._check_entry(bar)

    def on_price_tick(self, price: float) -> None:
        if self.position is None:
            return
        pos = self.position
        if pos.side == "bullish":
            if price <= pos.stop:
                self._exit(price, hit="stop")
            elif price >= pos.target:
                self._exit(price, hit="target")
        else:
            if price >= pos.stop:
                self._exit(price, hit="stop")
            elif price <= pos.target:
                self._exit(price, hit="target")

    def _check_entry(self, bar: dict) -> None:
        zone = self.zones.zone_at_price(bar["close"])
        if zone is None:
            return

        o = [b["open"] for b in self._ltf_bars]
        h = [b["high"] for b in self._ltf_bars]
        l = [b["low"] for b in self._ltf_bars]
        c = [b["close"] for b in self._ltf_bars]
        last_idx = len(c) - 1
        window_start = max(0, last_idx - CONFLUENCE_WINDOW_BARS)

        cisd = cisd_events(o, h, l, c)
        cisd_in_window = any(e["idx"] >= window_start and e["type"] == zone["type"] for e in cisd)
        if not cisd_in_window:
            return

        matching_trigger = next(
            (
                t for t in reversed(self._recent_ltf_triggers)
                if t["bar_index"] >= window_start and _TRIGGER_TO_ZONE_TYPE[t["side"]] == zone["type"]
            ),
            None,
        )
        if matching_trigger is None:
            return

        entry_price = bar["close"]
        if zone["type"] == "bullish":
            stop = zone["zone_lo"]
            risk = entry_price - stop
        else:
            stop = zone["zone_hi"]
            risk = stop - entry_price
        if risk <= 0:
            return  # 존 경계가 진입가와 같거나 역전된 기형 케이스 — 진입 스킵

        target = self.zones.next_opposing_level(zone["type"], entry_price)
        if target is None:
            return  # 다음 반대편 유동성 레벨이 아직 안 잡힘 — 목표 미확정, 진입 스킵

        self.position = PositionState(
            side=zone["type"], entry_price=entry_price, stop=stop, target=target,
            zone_source=zone["source"], of_trigger=matching_trigger["of_trigger"],
            entered_ts=bar["ts"],
        )
        self.zones.mark_consumed(zone)
        save_position_state(self._state_path, self.position)

    def _exit(self, price: float, hit: str) -> None:
        pos = self.position
        risk = abs(pos.entry_price - pos.stop)
        if pos.side == "bullish":
            result_r = (price - pos.entry_price) / risk
        else:
            result_r = (pos.entry_price - price) / risk
        append_trade_row(
            self._journal_path,
            entered_ts=pos.entered_ts,
            symbol=self.symbol,
            direction="long" if pos.side == "bullish" else "short",
            ict_context=f"CISD+{pos.zone_source}",
            of_trigger=pos.of_trigger,
            level_basis=pos.zone_source,
            entry=pos.entry_price,
            stop=pos.stop,
            target=pos.target,
            risk_r=1.0,
            result_r=round(result_r, 4),
            note=f"auto paper engine, exit={hit}",
        )
        clear_position_state(self._state_path)
        self.position = None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ict_paper_state_machine.py -v`
Expected: PASS(5 tests)

- [ ] **Step 5: 커밋**

```bash
git add research/ict/paper/state_machine.py tests/test_ict_paper_state_machine.py
git commit -m "feat: ICT+오더플로우 페이퍼 상태머신(진입/청산/저널기록) 추가"
```

---

### Task 6: 상시 진입점 — WS/REST 배선

**Files:**
- Create: `research/run_ict_paper_engine.py`
- Test: `tests/test_run_ict_paper_engine.py`

**Interfaces:**
- Consumes:
  - `orderflow.hl_adapter.HyperliquidOrderflowClient`(기존, 미수정) — `.stream(coin) -> AsyncIterator[OrderBookSnapshot | TradeEvent]`
  - `research.ict.paper.reversal_triggers.LTFBarBuilder`(Task 1)
  - `research.ict.paper.htf_zones.fetch_htf_bars`(Task 2)
  - `research.ict.paper.state_machine.PaperEngine`(Task 5)
- Produces: `_poll_htf(engine, fetch_fn=fetch_htf_bars, poll_sec=HTF_POLL_SEC) -> None`(무한루프 코루틴), `_stream_ltf(engine, client) -> None`(코루틴), `main() -> None`. 이 태스크가 마지막 — 이후 소비자 없음.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_run_ict_paper_engine.py`:

```python
import asyncio

import pytest

from orderflow.models import OrderBookLevel, OrderBookSnapshot, TradeEvent
from research.ict.paper.state_machine import PaperEngine
from research.run_ict_paper_engine import _poll_htf, _stream_ltf


class FakeHLClient:
    def __init__(self, events: list):
        self._events = events

    async def stream(self, coin: str):
        for e in self._events:
            yield e


async def test_stream_ltf_consumes_trades_and_book_snapshots_without_error(tmp_path):
    engine = PaperEngine(
        symbol="BTC.HL", state_path=str(tmp_path / "s.json"), journal_path=str(tmp_path / "j.csv")
    )
    events = [
        TradeEvent(symbol="BTC.HL", ts=0.0, price=100.0, size=1.0, side="buy"),
        OrderBookSnapshot(
            symbol="BTC.HL", ts=1.0,
            bids=[OrderBookLevel(price=99.5, size=1.0)],
            asks=[OrderBookLevel(price=100.5, size=1.0)],
        ),
    ]
    client = FakeHLClient(events)
    await _stream_ltf(engine, client)  # 예외 없이 전체 스트림 소비하면 통과(와이어링 스모크)


async def test_poll_htf_calls_fetch_fn_and_feeds_engine(tmp_path):
    engine = PaperEngine(
        symbol="BTC.HL", state_path=str(tmp_path / "s.json"), journal_path=str(tmp_path / "j.csv")
    )
    calls = {"n": 0}

    def fake_fetch(coin: str, interval: str, bars: int) -> list[dict]:
        calls["n"] += 1
        return [{"ts": 0, "open": 100, "high": 101, "low": 99, "close": 100.5}]

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(_poll_htf(engine, fetch_fn=fake_fetch, poll_sec=0.01), timeout=0.03)

    assert calls["n"] >= 1
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_ict_paper_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.run_ict_paper_engine'`

- [ ] **Step 3: 구현 작성**

`research/run_ict_paper_engine.py`:

```python
"""BTC.HL ICT+오더플로우 페이퍼 엔진 진입점 — 상시 프로세스.

CLI: PYTHONPATH=. python3 research/run_ict_paper_engine.py
tmux 상시구동: tmux new -s ict-orderflow-paper 'PYTHONPATH=. python3 research/run_ict_paper_engine.py'
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable

from orderflow.hl_adapter import HyperliquidOrderflowClient
from orderflow.models import OrderBookSnapshot, TradeEvent
from research.ict.paper.htf_zones import fetch_htf_bars
from research.ict.paper.reversal_triggers import LTFBarBuilder
from research.ict.paper.state_machine import PaperEngine

COIN = "BTC"
HTF_POLL_SEC = 900.0  # 15분
STATE_PATH = "research/data/ict_paper_state.json"
JOURNAL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "seokminal-dashboard", "docs", "orderflow-journal.csv"
)


async def _poll_htf(
    engine: PaperEngine,
    fetch_fn: Callable[[str, str, int], list[dict]] = fetch_htf_bars,
    poll_sec: float = HTF_POLL_SEC,
) -> None:
    while True:
        try:
            bars = fetch_fn(COIN, "15m", 100)
            for bar in bars:
                engine.on_htf_bar(bar)
        except Exception:
            logging.exception("HTF 폴링 실패 — 이번 사이클 스킵")
        await asyncio.sleep(poll_sec)


async def _stream_ltf(engine: PaperEngine, client: HyperliquidOrderflowClient) -> None:
    bar_builder = LTFBarBuilder()
    async for event in client.stream(COIN):
        if isinstance(event, TradeEvent):
            result = bar_builder.on_trade(event)
            if result is not None:
                engine.on_ltf_bar(result)
            engine.on_price_tick(event.price)
        elif isinstance(event, OrderBookSnapshot) and event.bids and event.asks:
            mid = (event.bids[0].price + event.asks[0].price) / 2.0
            engine.on_price_tick(mid)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = PaperEngine(symbol=f"{COIN}.HL", state_path=STATE_PATH, journal_path=JOURNAL_PATH)
    client = HyperliquidOrderflowClient()
    await asyncio.gather(_poll_htf(engine), _stream_ltf(engine, client))


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_ict_paper_engine.py -v`
Expected: PASS(2 tests)

- [ ] **Step 5: 전체 백엔드 스위트 회귀 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: 기존 pre-existing failures(test_auth.py ×3~4, test_backtest_happy_path) 외 전부 PASS — 신규 실패 없어야 함

- [ ] **Step 6: 커밋**

```bash
git add research/run_ict_paper_engine.py tests/test_run_ict_paper_engine.py
git commit -m "feat: ICT+오더플로우 페이퍼 엔진 상시 진입점(WS/REST 배선) 추가"
```

---

## 실행 후 수동 확인 (자동화 범위 밖)

이 플랜은 코드까지만 다룬다. 실제 상시 구동은 별도 수동 단계:

```bash
tmux new -s ict-orderflow-paper 'cd /Users/seokhun/Desktop/claude-test/seokminal/seokminal-multi-venue && PYTHONPATH=. /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 research/run_ict_paper_engine.py'
```

구동 후 `seokminal-dashboard/docs/orderflow-journal.csv`에 행이 쌓이는지, `research/data/ict_paper_state.json`이 포지션 진입 중에만 존재하는지 육안 확인 필요 — 30건 쌓이면 저장된 메모리(`feedback_ict_orderflow_journal_progress_report`) 규칙대로 매번 N/30 진행상황 보고.
