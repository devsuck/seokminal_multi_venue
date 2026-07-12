# 오더플로우 컨텍스트 게이트(BTC/ETH) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BTC/ETH 오더플로우 confluence에 상위TF트렌드/키레벨/VWAP 3필터 게이트(3/3 만장일치)+killzone을 추가해 새 가설로 통계 검증한다.

**Architecture:** 신규 모듈 `research/hypotheses/orderflow_context_gate.py`에 바 빌더(틱→1분봉→15분봉), 3개 컨텍스트 필터(트렌드/키레벨/VWAP, 기존 ICT 프리미티브 재사용), 게이트 조립 함수를 만든다. `research/run_orderflow_futures_on_btc.py`는 이 모듈을 import해 gated 신호를 별도로 실행하고, 기존 14개 가설 배치와 분리된 새 BH-FDR 풀로 결과를 출력한다.

**Tech Stack:** Python 3.14, pytest (asyncio_mode="auto" 무관 — 이 모듈은 전부 동기 순수함수).

## Global Constraints

- 게이트는 **3/3 만장일치**(트렌드+키레벨+VWAP 전부 같은 방향)여야 bias 성립. 2/3 다수결 아님.
- `KEY_LEVEL_PROXIMITY_PCT = 0.001`(가격의 0.1%) — 고정값, 결과 보고 튜닝 금지.
- `VWAP_WINDOW_BUCKETS = 240`(60s버킷 240개 = 4시간) — 고정값, 결과 보고 튜닝 금지.
- killzone은 `research.ict.primitives.killzone_indices`를 파라미터 변경 없이 그대로 사용(NY오픈 UTC 13:30–15:00).
- `market_structure`/`swings`(`research/ict/primitives.py`)는 시그니처·로직 변경 없이 그대로 재사용 — 신규 지표 발명 금지.
- `build_confluence_signals`는 `research/run_orderflow_futures_on_btc.py`에서 신규 모듈로 **이동만** — 로직 1바이트도 바꾸지 않는다.
- `eligible` 필드는 이 프로젝트 전역 컨벤션과 동일: "신호가 뜬 인덱스"가 아니라 "판정 가능했던 모집단 전체"(HOLD로 끝난 인덱스도 포함).
- 신규 가설(BTC/ETH gated_confluence, 총 2개 p-value)은 `benjamini_hochberg`로 **별도 풀**에서 보정 — 기존 14개 배치(footprint_imbalance/absorption/cvd_divergence/confluence/stop_run × BTC,ETH)와 절대 합치지 않는다.
- 실집행 없음. DORMANT 확인용 스크립트 — 통계적 스크리닝 목적.
- NQ/MNQ 이식, POC/value area, ICT 프리셋(OTE/Unicorn/iFVG/CISD/SMT) 재투입은 스코프 밖 — 손대지 않는다.

---

## 기존 코드베이스 참고 (구현자가 알아야 할 시그니처)

`research/ict/primitives.py`:
```python
def market_structure(h: list[float], l: list[float], c: list[float], k: int = 2) -> list[dict]:
    # 반환: [{"idx": int, "dir": "bullish"|"bearish", "kind": "BOS"|"CHoCH", "level": float}, ...]

def swings(h: list[float], l: list[float], k: int = 2) -> dict:
    # 반환: {"highs": [idx, ...], "lows": [idx, ...]}

def killzone_indices(ts: list[int], start_hour: float = 13.5, end_hour: float = 15.0) -> list[int]:
    # ts(epoch sec) 중 킬존(UTC) 안에 있는 인덱스 리스트
```

`research/hypotheses/orderflow_futures.py`:
```python
CVD_LOOKBACK_BUCKETS = 5

SIGNAL_BUILDERS = {
    "footprint_imbalance": build_footprint_imbalance_signals,
    "absorption": build_absorption_signals,
    "cvd_divergence": build_cvd_divergence_signals,
    "wall_proximity": build_wall_proximity_signals,
    "iceberg_refill": build_iceberg_refill_signals,
}
# 각 build_*_signals(deltas) -> {"closes": [...], "signals": [...], "eligible": [...]}

def _footprint_buckets(deltas: list[dict]) -> tuple[list[float], dict[float,float], dict[float,float], dict[float,float], dict[float,float]]:
    # 반환: (order[버킷ts 시간순], buy_vol_by_bucket, sell_vol_by_bucket, open_price_by_bucket, last_price_by_bucket)
```

`research/run_orderflow_futures_on_btc.py` 현재 상태(수정 대상):
- `build_confluence_signals(deltas)` 함수가 여기 정의돼 있음(62-88행) — Task 4에서 신규 모듈로 이동.
- `main()`이 BTC/ETH 각각에 대해 footprint_imbalance/absorption/cvd_divergence/confluence/stop_run 5개 가설을 실행하고 `benjamini_hochberg`로 14개 p-value 배치 보정.
- `TRADE_SIZE = 1.0`, `N_RUNS = 500`, `SEED = 42`, `COST_BPS = hl_effective_cost_bps("major", taker=True)` 모듈 레벨 상수.

---

### Task 1: 바 빌더 — `build_ohlc_bars` / `resample_bars`

**Files:**
- Create: `research/hypotheses/orderflow_context_gate.py`
- Create: `tests/test_orderflow_context_gate.py`

**Interfaces:**
- Consumes: 없음(순수 함수, 신규 모듈 시작점).
- Produces:
  - `build_ohlc_bars(ticks: list[dict], bucket_sec: float = 60.0) -> list[dict]` — 각 bar는 `{"bucket_ts": float, "o": float, "h": float, "l": float, "c": float}`, 시간순 정렬.
  - `resample_bars(bars: list[dict], factor: int = 15) -> list[dict]` — 같은 dict 형태, `factor`개 미만 남는 마지막 그룹은 버림.

- [ ] **Step 1: 신규 모듈 파일 생성(모듈 docstring + import + 상수)**

`research/hypotheses/orderflow_context_gate.py` 생성:

```python
"""오더플로우 컨텍스트 게이트 — 상위TF 트렌드/키레벨/VWAP 3필터(만장일치)+killzone으로
기존 오더플로우 confluence(footprint/absorption/cvd 2/3 다수결)를 게이트링.

방금 REJECT난 오더플로우 confluence 단독 가설에 실전 트레이더가 쓰는 컨텍스트 필터를
추가한 새 가설 — 컨텍스트가 방향(bias)을 정하고 오더플로우는 그 방향 안에서 타이밍만
잡는 구조. 2/3 다수결이 아니라 트렌드+키레벨+VWAP 3개 전부 일치해야 bias 성립(방향
결정은 더 보수적으로).

신규 지표 발명 없음: market_structure/swings/killzone_indices(research/ict/primitives.py)
그대로 재사용. VWAP만 신규 계산(footprint_delta가 이미 price×volume이라 신규 수집 불필요).

DORMANT 확인용 모듈. 통계적 스크리닝 목적, 실집행 근거 아님.
"""
from __future__ import annotations

from research.hypotheses.orderflow_futures import CVD_LOOKBACK_BUCKETS, SIGNAL_BUILDERS, _footprint_buckets
from research.ict.primitives import killzone_indices, market_structure, swings

KEY_LEVEL_PROXIMITY_PCT = 0.001  # 가격의 0.1% — 고정, 최적화 금지
VWAP_WINDOW_BUCKETS = 240  # 60s버킷 240개 = 4시간, 고정 — 최적화 금지
```

- [ ] **Step 2: 테스트 파일 생성 + 헬퍼 + `build_ohlc_bars` 실패 테스트**

`tests/test_orderflow_context_gate.py` 생성:

```python
from research.hypotheses.orderflow_context_gate import (
    build_ohlc_bars,
    resample_bars,
)


def _tick(ts, price, size=1.0, side="buy"):
    return {"ts": ts, "price": price, "size": size, "side": side}


def _bar(ts, o, h, l, c):
    return {"bucket_ts": ts, "o": o, "h": h, "l": l, "c": c}


def _fd(bucket_ts, price, side, vol):
    return {"type": "footprint_delta", "bucket_ts": bucket_ts, "price": price, "side": side, "delta_vol": vol}


def test_build_ohlc_bars_bucket_boundaries_and_high_low():
    ticks = [
        _tick(0.0, 100.0), _tick(30.0, 105.0), _tick(59.9, 98.0),
        _tick(60.0, 110.0), _tick(90.0, 108.0),
    ]
    bars = build_ohlc_bars(ticks, bucket_sec=60.0)
    assert [b["bucket_ts"] for b in bars] == [0.0, 60.0]
    assert bars[0] == {"bucket_ts": 0.0, "o": 100.0, "h": 105.0, "l": 98.0, "c": 98.0}
    assert bars[1] == {"bucket_ts": 60.0, "o": 110.0, "h": 110.0, "l": 108.0, "c": 108.0}


def test_build_ohlc_bars_sorts_unsorted_input():
    ticks = [_tick(60.0, 110.0), _tick(0.0, 100.0)]
    bars = build_ohlc_bars(ticks, bucket_sec=60.0)
    assert [b["bucket_ts"] for b in bars] == [0.0, 60.0]
```

- [ ] **Step 3: 테스트 실행 — 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_context_gate.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_ohlc_bars'`

- [ ] **Step 4: `build_ohlc_bars` 구현**

`research/hypotheses/orderflow_context_gate.py`에 (상수 아래) 추가:

```python
def build_ohlc_bars(ticks: list[dict], bucket_sec: float = 60.0) -> list[dict]:
    """원시 틱({ts,price,size,side}) -> bucket_sec 버킷 OHLC(틱 기준 진짜 high/low —
    footprint_delta엔 없는 정보라 여기서 별도 계산). 입력 정렬 여부 무관(내부에서 정렬)."""
    ordered = sorted(ticks, key=lambda t: t["ts"])
    bars: dict[float, dict] = {}
    order: list[float] = []
    for t in ordered:
        b = (t["ts"] // bucket_sec) * bucket_sec
        if b not in bars:
            bars[b] = {"bucket_ts": b, "o": t["price"], "h": t["price"], "l": t["price"], "c": t["price"]}
            order.append(b)
        bar = bars[b]
        bar["h"] = max(bar["h"], t["price"])
        bar["l"] = min(bar["l"], t["price"])
        bar["c"] = t["price"]
    return [bars[b] for b in order]
```

- [ ] **Step 5: 테스트 실행 — `build_ohlc_bars` 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_context_gate.py -v -k build_ohlc_bars`
Expected: PASS (2 tests)

- [ ] **Step 6: `resample_bars` 실패 테스트 추가**

`tests/test_orderflow_context_gate.py`에 import 목록에 `resample_bars` 추가(이미 Step2에서 import했음, 그대로 유지) 후 아래 테스트 append:

```python
def test_resample_bars_groups_by_factor_with_ohlc():
    bars = [_bar(float(i * 60), 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i) for i in range(3)]
    out = resample_bars(bars, factor=3)
    assert len(out) == 1
    assert out[0]["bucket_ts"] == 0.0
    assert out[0]["o"] == 100.0
    assert out[0]["h"] == 103.0  # max(h) of bars 0,1,2 = 101,102,103
    assert out[0]["l"] == 99.0   # min(l) of bars 0,1,2 = 99,100,101
    assert out[0]["c"] == 102.5  # 마지막 바(idx2)의 c = 100.5+2


def test_resample_bars_drops_incomplete_trailing_group():
    bars = [_bar(float(i * 60), 100.0, 101.0, 99.0, 100.0) for i in range(5)]
    out = resample_bars(bars, factor=3)
    assert len(out) == 1  # 5바 중 마지막 2개(미완성 그룹)는 버림
```

- [ ] **Step 7: 테스트 실행 — 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_context_gate.py -v -k resample_bars`
Expected: FAIL — `ImportError: cannot import name 'resample_bars'`

- [ ] **Step 8: `resample_bars` 구현**

`research/hypotheses/orderflow_context_gate.py`에 `build_ohlc_bars` 아래 추가:

```python
def resample_bars(bars: list[dict], factor: int = 15) -> list[dict]:
    """연속 factor개 바 묶어 상위 타임프레임 바 생성(o=첫바 o, h=구간 max h,
    l=구간 min l, c=마지막바 c, bucket_ts=첫바 bucket_ts). 마지막 미완성 그룹은 버림."""
    out = []
    for start in range(0, len(bars) - factor + 1, factor):
        group = bars[start:start + factor]
        out.append({
            "bucket_ts": group[0]["bucket_ts"],
            "o": group[0]["o"],
            "h": max(g["h"] for g in group),
            "l": min(g["l"] for g in group),
            "c": group[-1]["c"],
        })
    return out
```

- [ ] **Step 9: 전체 테스트 실행 — 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_context_gate.py -v`
Expected: PASS (4 tests)

- [ ] **Step 10: 커밋**

```bash
git add research/hypotheses/orderflow_context_gate.py tests/test_orderflow_context_gate.py
git commit -m "feat: add OHLC bar builder + resampler for orderflow context gate"
```

---

### Task 2: 트렌드 필터 + 키레벨 필터 (기존 ICT 프리미티브 재사용)

**Files:**
- Modify: `research/hypotheses/orderflow_context_gate.py`
- Modify: `tests/test_orderflow_context_gate.py`

**Interfaces:**
- Consumes: `market_structure(h,l,c,k)`, `swings(h,l,k)` (Task 1 이전부터 import돼 있음, 이미 모듈 상단에 import됨). `_bar` 헬퍼(Task 1에서 정의됨).
- Produces:
  - `build_trend_filter(bars_15m: list[dict], k: int = 2) -> list[str]` — `bars_15m`과 같은 길이, 각 원소는 `"BUY"|"SELL"|"HOLD"`.
  - `build_key_level_filter(bars_15m: list[dict], proximity_pct: float = KEY_LEVEL_PROXIMITY_PCT) -> list[str]` — 같은 길이/값 종류.

- [ ] **Step 1: `build_trend_filter` 실패 테스트 추가**

`tests/test_orderflow_context_gate.py` import 줄을 아래로 교체:

```python
from research.hypotheses.orderflow_context_gate import (
    build_key_level_filter,
    build_ohlc_bars,
    build_trend_filter,
    resample_bars,
)
```

파일 끝에 추가:

```python
def test_build_trend_filter_holds_before_first_event_then_forward_fills_direction():
    # k=1로 swing 창을 좁혀 5바만으로 BOS 하나를 만든다.
    # swings(h,l,k=1): swing high idx=1(h=8), swing low idx=2(l=5).
    # market_structure: idx3에서 c=9.5가 직전 swing high(8) 상향 돌파 -> BOS bullish.
    bars = [
        _bar(0.0, 5.0, 5.0, 4.0, 4.5),
        _bar(60.0, 8.0, 8.0, 7.0, 7.5),
        _bar(120.0, 6.0, 6.0, 5.0, 5.5),
        _bar(180.0, 10.0, 10.0, 9.0, 9.5),
        _bar(240.0, 10.0, 10.0, 9.0, 9.5),
    ]
    out = build_trend_filter(bars, k=1)
    assert out == ["HOLD", "HOLD", "HOLD", "BUY", "BUY"]
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_context_gate.py -v -k build_trend_filter`
Expected: FAIL — `ImportError: cannot import name 'build_trend_filter'`

- [ ] **Step 3: `build_trend_filter` 구현**

`research/hypotheses/orderflow_context_gate.py`에 `resample_bars` 아래 추가:

```python
def build_trend_filter(bars_15m: list[dict], k: int = 2) -> list[str]:
    """market_structure(h,l,c,k)를 15분봉에 적용. 최근 BOS/CHoCH의 dir을
    다음 이벤트 나올 때까지 forward-fill(상태 유지). 이벤트 없는 초반 구간은 HOLD."""
    h = [b["h"] for b in bars_15m]
    l = [b["l"] for b in bars_15m]
    c = [b["c"] for b in bars_15m]
    events = market_structure(h, l, c, k)
    dir_by_idx = {e["idx"]: ("BUY" if e["dir"] == "bullish" else "SELL") for e in events}

    out = []
    current = "HOLD"
    for i in range(len(bars_15m)):
        if i in dir_by_idx:
            current = dir_by_idx[i]
        out.append(current)
    return out
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_context_gate.py -v -k build_trend_filter`
Expected: PASS

- [ ] **Step 5: `build_key_level_filter` 실패 테스트 추가**

`tests/test_orderflow_context_gate.py` 파일 끝에 추가:

```python
def test_build_key_level_filter_proximity_in_and_out_of_range():
    # h 전부 20(동률) -> swing high 없음(count!=1 걸림). l=[10,10,5,10,10] -> idx2에서
    # swing low(=5) 유일 확정. levels=[(5.0,"BUY")]. c는 5.003(0.06%,in)/100.0(멀음)/
    # 5.0(정확히 일치,in)/5.006(0.12%,out)/200.0(멀음) — proximity_pct=0.001(0.1%) 기준.
    bars = [
        _bar(0.0, 20.0, 20.0, 10.0, 5.003),
        _bar(60.0, 20.0, 20.0, 10.0, 100.0),
        _bar(120.0, 20.0, 20.0, 5.0, 5.0),
        _bar(180.0, 20.0, 20.0, 10.0, 5.006),
        _bar(240.0, 20.0, 20.0, 10.0, 200.0),
    ]
    out = build_key_level_filter(bars, proximity_pct=0.001)
    assert out == ["BUY", "HOLD", "BUY", "HOLD", "HOLD"]
```

- [ ] **Step 6: 테스트 실행 — 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_context_gate.py -v -k build_key_level_filter`
Expected: FAIL — `ImportError: cannot import name 'build_key_level_filter'`

- [ ] **Step 7: `build_key_level_filter` 구현**

`research/hypotheses/orderflow_context_gate.py`에 `build_trend_filter` 아래 추가:

```python
def build_key_level_filter(bars_15m: list[dict], proximity_pct: float = KEY_LEVEL_PROXIMITY_PCT) -> list[str]:
    """swings(h,l,k=2)로 스윙하이/로우 추출 -> 현재가가 가장 가까운 스윙레벨의
    proximity_pct 이내면 그 방향(스윙로우 근접=BUY, 스윙하이 근접=SELL)."""
    h = [b["h"] for b in bars_15m]
    l = [b["l"] for b in bars_15m]
    c = [b["c"] for b in bars_15m]
    sw = swings(h, l, k=2)
    levels = [(l[i], "BUY") for i in sw["lows"]] + [(h[i], "SELL") for i in sw["highs"]]

    out = []
    for i in range(len(bars_15m)):
        price = c[i]
        sig = "HOLD"
        if levels and price != 0:
            level_price, level_sig = min(levels, key=lambda lv: abs(lv[0] - price))
            if abs(level_price - price) / abs(price) <= proximity_pct:
                sig = level_sig
        out.append(sig)
    return out
```

- [ ] **Step 8: 전체 테스트 실행 — 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_context_gate.py -v`
Expected: PASS (6 tests)

- [ ] **Step 9: 커밋**

```bash
git add research/hypotheses/orderflow_context_gate.py tests/test_orderflow_context_gate.py
git commit -m "feat: add trend + key-level context filters reusing ICT primitives"
```

---

### Task 3: VWAP 필터

**Files:**
- Modify: `research/hypotheses/orderflow_context_gate.py`
- Modify: `tests/test_orderflow_context_gate.py`

**Interfaces:**
- Consumes: `_footprint_buckets(deltas)` (Task 1부터 모듈 상단에 import됨). `_fd` 헬퍼(Task 1에서 정의됨).
- Produces: `build_vwap_filter(deltas: list[dict], window_buckets: int = VWAP_WINDOW_BUCKETS) -> list[str]` — `_footprint_buckets(deltas)`의 `order`와 같은 길이, `"BUY"|"SELL"|"HOLD"`.

- [ ] **Step 1: 실패 테스트 3개 추가**

`tests/test_orderflow_context_gate.py` import 줄에 `build_vwap_filter` 추가:

```python
from research.hypotheses.orderflow_context_gate import (
    build_key_level_filter,
    build_ohlc_bars,
    build_trend_filter,
    build_vwap_filter,
    resample_bars,
)
```

파일 끝에 추가:

```python
def test_build_vwap_filter_close_above_vwap_is_buy():
    # bucket0: price=100,vol=10. bucket1: price=110,vol=10.
    # idx0: window=[100](자기자신만) -> VWAP=100, close=100 -> HOLD(같음).
    # idx1: window=[100,110],vol=[10,10] -> VWAP=105, close=110>105 -> BUY.
    deltas = [
        _fd(0.0, 100.0, "buy", 10.0),
        _fd(60.0, 110.0, "buy", 10.0),
    ]
    out = build_vwap_filter(deltas, window_buckets=10)
    assert out == ["HOLD", "BUY"]


def test_build_vwap_filter_close_below_vwap_is_sell():
    # bucket2 추가: price=90,vol=10. idx2 window=[100,110,90]vol=[10,10,10] ->
    # VWAP=(100+110+90)/3=100, close=90<100 -> SELL.
    deltas = [
        _fd(0.0, 100.0, "buy", 10.0),
        _fd(60.0, 110.0, "buy", 10.0),
        _fd(120.0, 90.0, "sell", 10.0),
    ]
    out = build_vwap_filter(deltas, window_buckets=10)
    assert out[2] == "SELL"


def test_build_vwap_filter_window_excludes_older_buckets():
    # bucket0: price=50,vol=100(거대 볼륨) bucket1: price=200,vol=1 bucket2: price=150,vol=1.
    # 전체창(10): VWAP=(50*100+200+150)/102≈52.45 -> close=150 > VWAP -> BUY.
    # 좁은창(2): idx2 기준 [bucket1,bucket2]만 -> VWAP=(200+150)/2=175 -> close=150 < VWAP -> SELL.
    deltas = [
        _fd(0.0, 50.0, "buy", 100.0),
        _fd(60.0, 200.0, "buy", 1.0),
        _fd(120.0, 150.0, "buy", 1.0),
    ]
    full = build_vwap_filter(deltas, window_buckets=10)
    windowed = build_vwap_filter(deltas, window_buckets=2)
    assert full[2] == "BUY"
    assert windowed[2] == "SELL"
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_context_gate.py -v -k build_vwap_filter`
Expected: FAIL — `ImportError: cannot import name 'build_vwap_filter'`

- [ ] **Step 3: `build_vwap_filter` 구현**

`research/hypotheses/orderflow_context_gate.py`에 `build_key_level_filter` 아래 추가:

```python
def build_vwap_filter(deltas: list[dict], window_buckets: int = VWAP_WINDOW_BUCKETS) -> list[str]:
    """각 60s 버킷 시점 기준 직전 window_buckets 구간(그 버킷 포함) footprint_delta로
    VWAP = sum(price*vol)/sum(vol) 계산. close > VWAP -> BUY, close < VWAP -> SELL."""
    order, buy, sell, _open_price, last_price = _footprint_buckets(deltas)
    closes = [last_price[b] for b in order]
    vols = [buy.get(b, 0.0) + sell.get(b, 0.0) for b in order]

    out = []
    for i in range(len(order)):
        start = max(0, i - window_buckets + 1)
        window_closes = closes[start:i + 1]
        window_vols = vols[start:i + 1]
        total_vol = sum(window_vols)
        sig = "HOLD"
        if total_vol > 0:
            vwap = sum(p * v for p, v in zip(window_closes, window_vols)) / total_vol
            if closes[i] > vwap:
                sig = "BUY"
            elif closes[i] < vwap:
                sig = "SELL"
        out.append(sig)
    return out
```

- [ ] **Step 4: 전체 테스트 실행 — 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_context_gate.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: 커밋**

```bash
git add research/hypotheses/orderflow_context_gate.py tests/test_orderflow_context_gate.py
git commit -m "feat: add VWAP context filter for orderflow context gate"
```

---

### Task 4: `build_confluence_signals` 이동 + `build_gated_confluence_signals` 조립

**Files:**
- Modify: `research/hypotheses/orderflow_context_gate.py`
- Modify: `tests/test_orderflow_context_gate.py`

**Interfaces:**
- Consumes: Task 1-3의 `build_ohlc_bars`, `resample_bars`, `build_trend_filter`, `build_key_level_filter`, `build_vwap_filter`. 모듈 상단에 이미 import된 `CVD_LOOKBACK_BUCKETS`, `SIGNAL_BUILDERS`, `_footprint_buckets`, `killzone_indices`.
- Produces:
  - `build_confluence_signals(deltas: list[dict]) -> dict` — `{"closes","signals","eligible"}` (기존 `run_orderflow_futures_on_btc.py`의 것과 로직 동일, 이동만).
  - `build_gated_confluence_signals(deltas: list[dict], ticks: list[dict]) -> dict` — `{"closes","signals","eligible"}`, `closes`/`eligible`은 `_footprint_buckets(deltas)`의 `order`(60s 버킷) 기준.

- [ ] **Step 1: `build_confluence_signals` 이동(테스트 없이 그대로 이식)**

`research/hypotheses/orderflow_context_gate.py`에 `build_vwap_filter` 아래 추가(로직은 `run_orderflow_futures_on_btc.py`의 기존 함수와 100% 동일 — 이동만):

```python
def build_confluence_signals(deltas: list[dict]) -> dict:
    """footprint_imbalance/absorption/cvd_divergence 3개 다수결(2개 이상 방향 일치) ->
    그 방향, 아니면 HOLD. 세 서브신호 다 _footprint_buckets 기반이라 봉 정렬 동일.

    사전에 고정한 단일 규칙 — 결과 보고 조합 방식 바꾸지 않는다(데이터 스누핑 방지).
    eligible = cvd_divergence 판정 가능 구간(i >= CVD_LOOKBACK_BUCKETS)과 동일 —
    세 의견이 다 갖춰진 구간만 다수결 판정 자격을 준다."""
    fp = SIGNAL_BUILDERS["footprint_imbalance"](deltas)["signals"]
    ab = SIGNAL_BUILDERS["absorption"](deltas)["signals"]
    cvd_data = SIGNAL_BUILDERS["cvd_divergence"](deltas)
    cvd, closes = cvd_data["signals"], cvd_data["closes"]

    signals: list[str] = []
    eligible: list[int] = []
    for i in range(len(closes)):
        sig = "HOLD"
        if i >= CVD_LOOKBACK_BUCKETS:
            eligible.append(i)
            votes = [fp[i], ab[i], cvd[i]]
            buy_votes = votes.count("BUY")
            sell_votes = votes.count("SELL")
            if buy_votes >= 2:
                sig = "BUY"
            elif sell_votes >= 2:
                sig = "SELL"
        signals.append(sig)
    return {"closes": closes, "signals": signals, "eligible": eligible}
```

- [ ] **Step 2: `build_gated_confluence_signals` 실패 테스트 4개 추가**

`tests/test_orderflow_context_gate.py` 맨 위 import 블록을 아래로 교체:

```python
from unittest.mock import patch

from research.hypotheses.orderflow_context_gate import (
    build_gated_confluence_signals,
    build_key_level_filter,
    build_ohlc_bars,
    build_trend_filter,
    build_vwap_filter,
    resample_bars,
)
```

파일 끝에 추가:

```python
# build_gated_confluence_signals는 build_trend_filter/build_key_level_filter/
# build_vwap_filter/build_ohlc_bars/resample_bars/build_confluence_signals를 조립만
# 하는 함수라, 각 구성요소는 이미 위에서 단위테스트했다. 여기서는 조립 로직(3필터
# 만장일치 bias, 15분봉->60s 브로드캐스트, killzone 게이팅, confluence 일치 확인)만
# 독립적으로 검증하기 위해 구성요소를 mock으로 고정한다.

_KZ_OUTSIDE = 1704115740.0  # 2024-01-01 13:29:00 UTC — 킬존(13:30-15:00) 밖
_KZ_START = 1704115800.0    # 2024-01-01 13:30:00 UTC — 킬존 시작(포함)
_KZ_INSIDE = 1704115860.0   # 2024-01-01 13:31:00 UTC — 킬존 안


@patch("research.hypotheses.orderflow_context_gate.build_confluence_signals")
@patch("research.hypotheses.orderflow_context_gate.build_vwap_filter")
@patch("research.hypotheses.orderflow_context_gate.build_key_level_filter")
@patch("research.hypotheses.orderflow_context_gate.build_trend_filter")
@patch("research.hypotheses.orderflow_context_gate.resample_bars")
@patch("research.hypotheses.orderflow_context_gate.build_ohlc_bars")
def test_build_gated_confluence_signals_all_agree_in_killzone_yields_signal(
    mock_ohlc, mock_resample, mock_trend, mock_key_level, mock_vwap, mock_confluence,
):
    deltas = [
        _fd(_KZ_OUTSIDE, 100.0, "buy", 1.0),
        _fd(_KZ_START, 101.0, "buy", 1.0),
        _fd(_KZ_INSIDE, 102.0, "buy", 1.0),
    ]
    mock_ohlc.return_value = []
    mock_resample.return_value = [{"bucket_ts": _KZ_OUTSIDE}]  # 워밍업 완료선 = 가장 이른 버킷
    mock_trend.return_value = ["BUY"]
    mock_key_level.return_value = ["BUY"]
    mock_vwap.return_value = ["BUY", "BUY", "BUY"]
    mock_confluence.return_value = {
        "closes": [100.0, 101.0, 102.0], "signals": ["BUY", "BUY", "BUY"], "eligible": [0, 1, 2],
    }

    result = build_gated_confluence_signals(deltas, ticks=[])

    assert result["closes"] == [100.0, 101.0, 102.0]
    assert result["eligible"] == [0, 1, 2]
    # idx0: 3필터+confluence 전부 BUY 만장일치지만 킬존 밖 -> HOLD.
    # idx1,idx2: 만장일치 + 킬존 안 + confluence 일치 -> BUY.
    assert result["signals"] == ["HOLD", "BUY", "BUY"]


@patch("research.hypotheses.orderflow_context_gate.build_confluence_signals")
@patch("research.hypotheses.orderflow_context_gate.build_vwap_filter")
@patch("research.hypotheses.orderflow_context_gate.build_key_level_filter")
@patch("research.hypotheses.orderflow_context_gate.build_trend_filter")
@patch("research.hypotheses.orderflow_context_gate.resample_bars")
@patch("research.hypotheses.orderflow_context_gate.build_ohlc_bars")
def test_build_gated_confluence_signals_filter_disagreement_is_hold(
    mock_ohlc, mock_resample, mock_trend, mock_key_level, mock_vwap, mock_confluence,
):
    deltas = [
        _fd(_KZ_OUTSIDE, 100.0, "buy", 1.0),
        _fd(_KZ_START, 101.0, "buy", 1.0),
        _fd(_KZ_INSIDE, 102.0, "buy", 1.0),
    ]
    mock_ohlc.return_value = []
    mock_resample.return_value = [{"bucket_ts": _KZ_OUTSIDE}]
    mock_trend.return_value = ["BUY"]
    mock_key_level.return_value = ["SELL"]  # 트렌드와 불일치 -> bias 성립 안 함
    mock_vwap.return_value = ["BUY", "BUY", "BUY"]
    mock_confluence.return_value = {
        "closes": [100.0, 101.0, 102.0], "signals": ["BUY", "BUY", "BUY"], "eligible": [0, 1, 2],
    }

    result = build_gated_confluence_signals(deltas, ticks=[])

    assert result["signals"] == ["HOLD", "HOLD", "HOLD"]


@patch("research.hypotheses.orderflow_context_gate.build_confluence_signals")
@patch("research.hypotheses.orderflow_context_gate.build_vwap_filter")
@patch("research.hypotheses.orderflow_context_gate.build_key_level_filter")
@patch("research.hypotheses.orderflow_context_gate.build_trend_filter")
@patch("research.hypotheses.orderflow_context_gate.resample_bars")
@patch("research.hypotheses.orderflow_context_gate.build_ohlc_bars")
def test_build_gated_confluence_signals_confluence_mismatch_is_hold(
    mock_ohlc, mock_resample, mock_trend, mock_key_level, mock_vwap, mock_confluence,
):
    deltas = [
        _fd(_KZ_START, 101.0, "buy", 1.0),
        _fd(_KZ_INSIDE, 102.0, "buy", 1.0),
    ]
    mock_ohlc.return_value = []
    mock_resample.return_value = [{"bucket_ts": _KZ_START}]
    mock_trend.return_value = ["BUY"]
    mock_key_level.return_value = ["BUY"]
    mock_vwap.return_value = ["BUY", "BUY"]
    # bias는 BUY 성립(만장일치)이지만 confluence가 SELL -> 진입 신호는 HOLD.
    mock_confluence.return_value = {
        "closes": [101.0, 102.0], "signals": ["SELL", "SELL"], "eligible": [0, 1],
    }

    result = build_gated_confluence_signals(deltas, ticks=[])

    assert result["signals"] == ["HOLD", "HOLD"]


@patch("research.hypotheses.orderflow_context_gate.build_confluence_signals")
@patch("research.hypotheses.orderflow_context_gate.build_vwap_filter")
@patch("research.hypotheses.orderflow_context_gate.build_key_level_filter")
@patch("research.hypotheses.orderflow_context_gate.build_trend_filter")
@patch("research.hypotheses.orderflow_context_gate.resample_bars")
@patch("research.hypotheses.orderflow_context_gate.build_ohlc_bars")
def test_build_gated_confluence_signals_before_warmup_is_not_eligible(
    mock_ohlc, mock_resample, mock_trend, mock_key_level, mock_vwap, mock_confluence,
):
    deltas = [
        _fd(_KZ_OUTSIDE, 100.0, "buy", 1.0),  # 15분봉 워밍업 전(첫 15분봉보다 이름)
        _fd(_KZ_START, 101.0, "buy", 1.0),
        _fd(_KZ_INSIDE, 102.0, "buy", 1.0),
    ]
    mock_ohlc.return_value = []
    mock_resample.return_value = [{"bucket_ts": _KZ_START}]  # 워밍업 완료선 = idx1과 동일 시각
    mock_trend.return_value = ["BUY"]
    mock_key_level.return_value = ["BUY"]
    mock_vwap.return_value = ["BUY", "BUY", "BUY"]
    mock_confluence.return_value = {
        "closes": [100.0, 101.0, 102.0], "signals": ["BUY", "BUY", "BUY"], "eligible": [1, 2],
    }

    result = build_gated_confluence_signals(deltas, ticks=[])

    assert result["eligible"] == [1, 2]  # idx0은 워밍업 전 -> 판정 불가 모집단에서 제외
    assert result["signals"][0] == "HOLD"
```

- [ ] **Step 3: 테스트 실행 — 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_context_gate.py -v -k build_gated_confluence_signals`
Expected: FAIL — `ImportError: cannot import name 'build_gated_confluence_signals'`

- [ ] **Step 4: `build_gated_confluence_signals` 구현**

`research/hypotheses/orderflow_context_gate.py`에 `build_confluence_signals` 아래 추가:

```python
def _broadcast_15m_to_60s(bars_15m_ts: list[float], signal_15m: list[str], target_ts: list[float]) -> list[str]:
    """15분봉 신호를 그 구간에 속한 모든 60s 버킷에 forward-fill로 broadcast.
    target_ts가 첫 15분봉보다 이르면(워밍업 전) HOLD."""
    out = []
    j = -1
    for ts in target_ts:
        while j + 1 < len(bars_15m_ts) and bars_15m_ts[j + 1] <= ts:
            j += 1
        out.append(signal_15m[j] if j >= 0 else "HOLD")
    return out


def build_gated_confluence_signals(deltas: list[dict], ticks: list[dict]) -> dict:
    """전체 파이프라인 조립:
    1. build_ohlc_bars(ticks) -> resample_bars(15) -> trend_filter, key_level_filter (15m)
    2. build_vwap_filter(deltas) (60s)
    3. killzone_indices (60s bucket_ts)
    4. 15m 신호 -> 60s로 broadcast
    5. bias = trend/key_level/vwap 3개 전부 같은 방향이면 그 방향, 아니면 HOLD
    6. 기존 confluence(footprint/absorption/cvd 2/3 다수결) 계산
    7. bias!=HOLD and killzone 안 and confluence==bias -> 그 방향 신호, 아니면 HOLD

    eligible = bias 계산 가능했던 구간(15분봉 워밍업 지난 이후) 전체 —
    신호가 실제로 뜬 곳만이 아니라 판정 가능 모집단 전체(다른 build_*_signals와 동일 규칙)."""
    bars_1m = build_ohlc_bars(ticks, bucket_sec=60.0)
    bars_15m = resample_bars(bars_1m, factor=15)
    bars_15m_ts = [b["bucket_ts"] for b in bars_15m]

    trend_15m = build_trend_filter(bars_15m)
    key_level_15m = build_key_level_filter(bars_15m)
    vwap_60s = build_vwap_filter(deltas)

    order, _buy, _sell, _open_price, last_price = _footprint_buckets(deltas)
    closes = [last_price[b] for b in order]
    kz = set(killzone_indices([int(b) for b in order]))

    trend_60s = _broadcast_15m_to_60s(bars_15m_ts, trend_15m, order)
    key_level_60s = _broadcast_15m_to_60s(bars_15m_ts, key_level_15m, order)

    confluence = build_confluence_signals(deltas)
    conf_signals = confluence["signals"]

    signals: list[str] = []
    eligible: list[int] = []
    for i in range(len(order)):
        warmed_up = bool(bars_15m_ts) and order[i] >= bars_15m_ts[0]
        if warmed_up:
            eligible.append(i)

        bias = "HOLD"
        if warmed_up and trend_60s[i] == key_level_60s[i] == vwap_60s[i] and trend_60s[i] != "HOLD":
            bias = trend_60s[i]

        sig = "HOLD"
        if bias != "HOLD" and i in kz and conf_signals[i] == bias:
            sig = bias
        signals.append(sig)

    return {"closes": closes, "signals": signals, "eligible": eligible}
```

- [ ] **Step 5: 전체 테스트 실행 — 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_context_gate.py -v`
Expected: PASS (13 tests)

- [ ] **Step 6: 커밋**

```bash
git add research/hypotheses/orderflow_context_gate.py tests/test_orderflow_context_gate.py
git commit -m "feat: move build_confluence_signals + add gated confluence assembly"
```

---

### Task 5: `run_orderflow_futures_on_btc.py` 배선 — gated 신호 실행 + 별도 BH-FDR 풀

**Files:**
- Modify: `research/run_orderflow_futures_on_btc.py`

**Interfaces:**
- Consumes: `build_confluence_signals`, `build_gated_confluence_signals` (신규 모듈, Task 4). 기존 모듈 레벨 상수 `TRADE_SIZE`, `N_RUNS`, `SEED`, `COST_BPS`, `DATA_DIR`(기존 파일에 이미 있음, 변경 없음). `simulate_long_short`, `trade_metrics`, `random_same_frequency`, `empirical_p_value`, `benjamini_hochberg`(기존 import, 변경 없음).
- Produces: `load_raw_ticks(paths: list[str]) -> list[dict]`, `run_gated_signal(symbol: str, deltas: list[dict], ticks: list[dict]) -> dict`. `main()`은 콘솔 출력만 하므로 다른 모듈이 소비하는 인터페이스 없음.

이 태스크는 기존 파일을 다음처럼 수정한다(정확한 diff는 아래 단계별로).

- [ ] **Step 1: import 블록 수정**

`research/run_orderflow_futures_on_btc.py`의 1-31행(모듈 docstring 이후 import 블록)에서, 아래 import를:

```python
from research.hypotheses.orderflow_futures import (
    CVD_LOOKBACK_BUCKETS,
    SIGNAL_BUILDERS,
    stop_run_events,
)
```

다음으로 교체(`build_confluence_signals`가 신규 모듈로 이동했으므로 `CVD_LOOKBACK_BUCKETS`는 더 이상 이 파일에서 안 쓰임 — `build_gated_confluence_signals` 조립 내부에서만 쓰임):

```python
from research.hypotheses.orderflow_context_gate import build_confluence_signals, build_gated_confluence_signals
from research.hypotheses.orderflow_futures import SIGNAL_BUILDERS, stop_run_events
```

- [ ] **Step 2: 로컬 `build_confluence_signals` 정의 삭제**

`research/run_orderflow_futures_on_btc.py`에서 아래 함수 정의 전체(원래 62-88행, docstring 포함)를 삭제한다:

```python
def build_confluence_signals(deltas: list[dict]) -> dict:
    """footprint_imbalance/absorption/cvd_divergence 3개 다수결(2개 이상 방향 일치) ->
    그 방향, 아니면 HOLD. 세 서브신호 다 _footprint_buckets 기반이라 봉 정렬 동일.

    사전에 고정한 단일 규칙 — 결과 보고 조합 방식 바꾸지 않는다(데이터 스누핑 방지).
    eligible = cvd_divergence 판정 가능 구간(i >= CVD_LOOKBACK_BUCKETS)과 동일 —
    세 의견이 다 갖춰진 구간만 다수결 판정 자격을 준다."""
    fp = SIGNAL_BUILDERS["footprint_imbalance"](deltas)["signals"]
    ab = SIGNAL_BUILDERS["absorption"](deltas)["signals"]
    cvd_data = SIGNAL_BUILDERS["cvd_divergence"](deltas)
    cvd, closes = cvd_data["signals"], cvd_data["closes"]

    signals: list[str] = []
    eligible: list[int] = []
    for i in range(len(closes)):
        sig = "HOLD"
        if i >= CVD_LOOKBACK_BUCKETS:
            eligible.append(i)
            votes = [fp[i], ab[i], cvd[i]]
            buy_votes = votes.count("BUY")
            sell_votes = votes.count("SELL")
            if buy_votes >= 2:
                sig = "BUY"
            elif sell_votes >= 2:
                sig = "SELL"
        signals.append(sig)
    return {"closes": closes, "signals": signals, "eligible": eligible}
```

(`run_bar_signal`의 `if signal_name == "confluence": data = build_confluence_signals(deltas)` 호출부는 그대로 둔다 — 이제 신규 모듈에서 import된 동일 함수를 가리킨다.)

- [ ] **Step 3: `ticks_to_footprint_deltas` 리팩터 + `load_raw_ticks` 추가**

기존 `ticks_to_footprint_deltas` 함수를:

```python
def ticks_to_footprint_deltas(paths: list[str], symbol: str) -> list[dict]:
    """원시 틱 jsonl들을 시간순 병합 -> OrderflowAggregator.on_trade()로 footprint_delta 스트림 생성.

    라이브 수집기(run_ib_orderflow_tick_collect.py)와 동일하게 Aggregator를
    단일 소스로 재사용 — 버킷팅 로직을 여기서 새로 짜지 않는다."""
    ticks = []
    for path in paths:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    ticks.append(json.loads(line))
    ticks.sort(key=lambda t: t["ts"])

    agg = OrderflowAggregator()
    deltas = []
    for t in ticks:
        ev = TradeEvent(symbol=symbol, ts=t["ts"], price=t["price"], size=t["size"], side=t["side"])
        deltas.append(agg.on_trade(ev))
    return deltas
```

다음으로 교체(틱 로딩 부분을 `load_raw_ticks`로 추출해 컨텍스트 게이트 바 빌더 입력으로도 재사용):

```python
def load_raw_ticks(paths: list[str]) -> list[dict]:
    """원시 틱 jsonl들을 시간순 병합. build_gated_confluence_signals의 바 빌더 입력용
    (footprint_delta로 버킷 합산하기 전, 개별 체결 {ts,price,size,side} 그대로)."""
    ticks = []
    for path in paths:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    ticks.append(json.loads(line))
    ticks.sort(key=lambda t: t["ts"])
    return ticks


def ticks_to_footprint_deltas(paths: list[str], symbol: str) -> list[dict]:
    """원시 틱 -> OrderflowAggregator.on_trade()로 footprint_delta 스트림 생성.

    라이브 수집기(run_ib_orderflow_tick_collect.py)와 동일하게 Aggregator를
    단일 소스로 재사용 — 버킷팅 로직을 여기서 새로 짜지 않는다."""
    ticks = load_raw_ticks(paths)
    agg = OrderflowAggregator()
    deltas = []
    for t in ticks:
        ev = TradeEvent(symbol=symbol, ts=t["ts"], price=t["price"], size=t["size"], side=t["side"])
        deltas.append(agg.on_trade(ev))
    return deltas
```

- [ ] **Step 4: `run_gated_signal` 함수 추가**

`run_stop_run` 함수 아래(그리고 `main()` 위)에 추가:

```python
def run_gated_signal(symbol: str, deltas: list[dict], ticks: list[dict]) -> dict:
    data = build_gated_confluence_signals(deltas, ticks)
    closes, signals, eligible = data["closes"], data["signals"], data["eligible"]
    if len(closes) < 10:
        return {"symbol": symbol, "signal": "gated_confluence", "blocked": True,
                "reason": f"{len(closes)}봉뿐 — 최소 표본 미달"}

    trades = simulate_long_short(closes, signals, TRADE_SIZE, COST_BPS)
    strat = trade_metrics(trades)
    holds = [max(1, t["exit_idx"] - t["entry_idx"]) for t in trades] or [1]
    rnd = random_same_frequency(
        closes, n_trades=strat["num_trades"], holding_periods=holds,
        trade_size=TRADE_SIZE, cost_bps=COST_BPS,
        eligible_indices=eligible, n_runs=N_RUNS, seed=SEED,
    )
    pval = empirical_p_value(strat["total_pnl"], rnd)
    return {"symbol": symbol, "signal": "gated_confluence", "blocked": False,
            "strategy": strat, "random": pval, "n_bars": len(closes), "eligible_count": len(eligible)}
```

- [ ] **Step 5: `main()` 수정 — gated 신호 실행 + 별도 BH-FDR 풀 출력**

기존 `main()` 전체를 다음으로 교체:

```python
def main() -> None:
    all_results: list[dict] = []
    pvals: list[float] = []
    pval_keys: list[str] = []

    gated_results: list[dict] = []
    gated_pvals: list[float] = []
    gated_pval_keys: list[str] = []

    for symbol in ("BTC", "ETH"):
        paths = sorted(glob.glob(f"{DATA_DIR}/{symbol}_*.jsonl"))
        if not paths:
            print(f"{symbol}: 데이터 없음, 스킵")
            continue
        ticks = load_raw_ticks(paths)
        deltas = ticks_to_footprint_deltas(paths, f"{symbol}.HL")

        for signal_name in ("footprint_imbalance", "absorption", "cvd_divergence", "confluence"):
            r = run_bar_signal(symbol, signal_name, deltas)
            all_results.append(r)
            if not r["blocked"]:
                pvals.append(r["random"]["p_value"])
                pval_keys.append(f"{symbol}:{signal_name}")

        r = run_stop_run(symbol, deltas)
        all_results.append(r)
        if not r["blocked"]:
            for h_key, h_res in r["horizons"].items():
                pvals.append(h_res["random"]["p_value"])
                pval_keys.append(f"{symbol}:stop_run:{h_key}")

        for signal_name in ("wall_proximity", "iceberg_refill"):
            all_results.append({"symbol": symbol, "signal": signal_name, "blocked": True,
                                 "reason": "HL 틱 수집기는 heatmap_delta(오더북) 미저장 — 항상 BLOCKED"})

        gr = run_gated_signal(symbol, deltas, ticks)
        gated_results.append(gr)
        if not gr["blocked"]:
            gated_pvals.append(gr["random"]["p_value"])
            gated_pval_keys.append(f"{symbol}:gated_confluence")

    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {"survivors": [], "alpha": 0.1}
    bh["keys"] = pval_keys

    gated_bh = benjamini_hochberg(gated_pvals, alpha=0.1) if gated_pvals else {"survivors": [], "alpha": 0.1}
    gated_bh["keys"] = gated_pval_keys

    print(f"\n=== cost_bps(HL major taker) = {COST_BPS} ===\n")
    for r in all_results:
        if r["blocked"]:
            print(f"{r['symbol']}:{r['signal']} -> BLOCKED ({r['reason']})")
            continue
        if "strategy" in r:
            s = r["strategy"]
            print(f"{r['symbol']}:{r['signal']} -> trades={s['num_trades']} "
                  f"win_rate={s['win_rate']:.3f} total_pnl={s['total_pnl']:.2f} "
                  f"p_value={r['random']['p_value']:.4f} (n_bars={r['n_bars']}, eligible={r['eligible_count']})")
        elif "horizons" in r:
            for h_key, h_res in r["horizons"].items():
                s = h_res["strategy"]
                print(f"{r['symbol']}:{r['signal']}:{h_key} -> trades={s['num_trades']} "
                      f"win_rate={s['win_rate']:.3f} total_pnl={s['total_pnl']:.2f} "
                      f"p_value={h_res['random']['p_value']:.4f} (n_events={r['n_events']})")

    print(f"\n=== BH-FDR (alpha=0.1) ===")
    print(f"keys: {bh['keys']}")
    print(f"survivors: {bh['survivors']}")

    print(f"\n=== 컨텍스트 게이트 신규 가설 (별도 BH-FDR 풀, 이전 배치와 안 섞음) ===\n")
    for r in gated_results:
        if r["blocked"]:
            print(f"{r['symbol']}:{r['signal']} -> BLOCKED ({r['reason']})")
            continue
        s = r["strategy"]
        print(f"{r['symbol']}:{r['signal']} -> trades={s['num_trades']} "
              f"win_rate={s['win_rate']:.3f} total_pnl={s['total_pnl']:.2f} "
              f"p_value={r['random']['p_value']:.4f} (n_bars={r['n_bars']}, eligible={r['eligible_count']})")

    print(f"\n=== 컨텍스트 게이트 BH-FDR (alpha=0.1) ===")
    print(f"keys: {gated_bh['keys']}")
    print(f"survivors: {gated_bh['survivors']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 신규 모듈 테스트 전체 재실행 — 회귀 없는지 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_orderflow_context_gate.py -v`
Expected: PASS (13 tests, 변경 없음 — Task 5는 신규 모듈을 건드리지 않음)

- [ ] **Step 7: 프로젝트 전체 테스트 스위트 실행 — 기존 회귀 없는지 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: PASS 전체(pre-existing failures — `test_auth.py` 3~4개, `test_backtest_happy_path` — 는 이 프로젝트 CLAUDE.md에 기록된 기존 실패이므로 무시. 그 외 신규 실패가 없어야 함)

- [ ] **Step 8: 실제 BTC/ETH 틱 데이터로 스크립트 실행 — 문법/런타임 에러 없는지 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m research.run_orderflow_futures_on_btc`
Expected: 에러 없이 실행 완료, 마지막에 "컨텍스트 게이트 BH-FDR" 섹션 출력 확인(데이터 없으면 "데이터 없음, 스킵" 출력 후 gated_pvals가 비어 survivors=[] — 이것도 정상 종료).

- [ ] **Step 9: 커밋**

```bash
git add research/run_orderflow_futures_on_btc.py
git commit -m "feat: wire gated confluence signal into BTC/ETH orderflow validation script"
```

---

## Self-Review 결과

**Spec coverage:**
- 바 빌더(`build_ohlc_bars`/`resample_bars`) — Task 1 ✅
- 트렌드 필터(`build_trend_filter`, market_structure 재사용) — Task 2 ✅
- 키레벨 필터(`build_key_level_filter`, swings 재사용) — Task 2 ✅
- VWAP 필터(`build_vwap_filter`, 신규 계산) — Task 3 ✅
- 세션 필터(killzone_indices, 파라미터 안 건드림) — Task 4의 `build_gated_confluence_signals` 내부에서 그대로 재사용 ✅
- 해상도 정렬(15분봉→60s broadcast) — Task 4 `_broadcast_15m_to_60s` ✅
- 게이트 합성+진입(3/3 만장일치, killzone, confluence 일치) — Task 4 `build_gated_confluence_signals` ✅
- `build_confluence_signals` 이동(로직 불변) — Task 4 Step1 + Task 5 Step1-2 ✅
- 검증 엔진 재사용(`simulate_long_short`/`trade_metrics`/`random_same_frequency`/`empirical_p_value`, HL 비용모델) — Task 5 `run_gated_signal` ✅
- 신규 독립 BH-FDR 풀(이전 14개 배치와 분리) — Task 5 `main()` ✅
- 테스트 계획 6개 항목(버킷경계/고저, factor그룹핑, BOS forward-fill, proximity in/out, VWAP window in/out, 게이트 조립 3케이스) — Task 1-4 전체 커버 ✅

**Placeholder scan:** 없음 — 모든 스텝에 실행 가능한 완전한 코드/커맨드 포함.

**Type consistency:** `build_ohlc_bars`/`resample_bars`가 반환하는 bar dict 키(`bucket_ts,o,h,l,c`)는 Task 2/4 전체에서 동일하게 사용. `build_*_filter` 반환값(`list[str]`, 값은 `"BUY"|"SELL"|"HOLD"`)이 `build_gated_confluence_signals`의 비교 로직과 일치. `build_gated_confluence_signals` 반환 dict 키(`closes,signals,eligible`)는 다른 `build_*_signals`와 동일 컨벤션이며 `run_gated_signal`(Task 5)이 그대로 소비.
