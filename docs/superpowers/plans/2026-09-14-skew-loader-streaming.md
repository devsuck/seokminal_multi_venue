# cross_venue_skew 오토리서치 로더 스트리밍 재설계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `engines_microstructure.py`(skew_divergence_momentum/basis_reversion 소스)가 cross_venue_skew 원본 오더북 스냅샷을 pandas DataFrame으로 통째로 적재하던 것을, 줄 단위 스트리밍으로 필요한 스칼라(imbalance/mid)만 뽑는 방식으로 바꿔 배치 실행 시 물리 메모리 사용량을 GB급에서 MB급으로 낮춘다.

**Architecture:** `research/hypotheses/cross_venue_skew.py`에 `_imbalance_of`/`_mid_of` 스칼라 헬퍼와 `stream_imbalance_and_mid()`를 신설(기존 `build_imbalance`/`build_price_series`는 헬퍼 재사용으로 리팩터, 동작 불변). `engines_microstructure.py`의 `_snapshot_cache`가 DataFrame 대신 (imbalance Series, mid Series) 튜플을 캐시하도록 바꾸고, `_daily_mid`/`_skew_divergence_result`가 그 값을 직접 소비하도록 재작성한다.

**Tech Stack:** Python 3.14 (`/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`), pandas, pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-skew-loader-streaming-design.md`

## Global Constraints

- `research/hypotheses/cross_venue_skew.py::load_venue_snapshots`와 `research/run_cross_venue_skew_validate.py`는 수정 금지 — validate.py 전용 경로, 이번 이슈와 무관.
- `SKEW_LOOKBACK_DAYS=45`, `_MIN_DAYS=30`, `_MIN_EVENTS=10` 등 사전등록 통계 게이트 값 변경 금지.
- 신규 의존성 추가 금지 — 표준 라이브러리 + 이미 쓰는 pandas/gzip/json만 사용.
- 테스트 실행: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`.
- 각 태스크 커밋은 그 태스크가 건드린 파일만 `git add`(레포에 무관한 미변경/노이즈 파일 — `.DS_Store`, `jarvis/_state/*`, `research/data/*` 등 — 절대 같이 스테이징하지 말 것. `git status`로 diff 범위 확인 후 커밋).
- 이 플랜은 이미 미커밋 상태로 존재하는 45일 윈도 fix(`research/autoresearch/engine.py`의 예외격리, `engines_microstructure.py`의 `_snapshot_cache`/`_load_venue_snapshots_cached`/`SKEW_LOOKBACK_DAYS`, `tests/test_autoresearch_engine.py`, `tests/test_engines_microstructure.py`) 위에 쌓는다 — 그 파일들은 이미 수정된 상태에서 시작한다(재작성 대상이지 처음부터 새로 만드는 게 아님).

---

### Task 1: cross_venue_skew.py — 스칼라 헬퍼 추출 + 스트리밍 로더 신설

**Files:**
- Modify: `research/hypotheses/cross_venue_skew.py:53-64` (`build_imbalance`), `research/hypotheses/cross_venue_skew.py:93-114` (`build_price_series`)
- Create (in same file, after `load_venue_snapshots`, before `build_imbalance`): `_imbalance_of`, `_mid_of`, `stream_imbalance_and_mid`
- Test: `tests/test_cross_venue_skew.py`

**Interfaces:**
- Consumes: 없음(이 태스크가 최하위 레이어).
- Produces:
  - `_imbalance_of(bids: list[dict], asks: list[dict], depth_n: int = IMBALANCE_DEPTH_N) -> float`
  - `_mid_of(bids: list[dict], asks: list[dict]) -> float`
  - `stream_imbalance_and_mid(venue: str, coin: str, dates: list[str], depth_n: int = IMBALANCE_DEPTH_N) -> tuple[pd.Series, pd.Series]` — 반환 두 Series 모두 index=ts(float, 오름차순 정렬), 값=imbalance/mid. 데이터 없으면 `(pd.Series(dtype=float), pd.Series(dtype=float))`.
  - Task 2가 `stream_imbalance_and_mid`를 import해서 쓴다.

- [ ] **Step 1: 기존 `build_imbalance`/`build_price_series` 테스트가 계속 통과하는지 기준선 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cross_venue_skew.py -q`
Expected: 전부 PASS (리팩터 전 베이스라인).

- [ ] **Step 2: 신규 테스트 작성 — `_imbalance_of`/`_mid_of`/`stream_imbalance_and_mid`**

`tests/test_cross_venue_skew.py` 상단 import에 추가:

```python
from research.hypotheses.cross_venue_skew import (
    _imbalance_of,
    _mid_of,
    align_venues,
    build_imbalance,
    build_labels_multi_horizon,
    build_price_series,
    build_skew_divergence,
    build_spike_signal,
    load_venue_snapshots,
    stream_imbalance_and_mid,
)
```

파일 끝에 추가:

```python
def test_imbalance_of_neutral_when_bid_ask_equal():
    result = _imbalance_of([{"price": 99.0, "size": 5.0}], [{"price": 101.0, "size": 5.0}])
    assert result == pytest.approx(0.5)


def test_imbalance_of_buy_heavy_above_half():
    result = _imbalance_of([{"price": 99.0, "size": 8.0}], [{"price": 101.0, "size": 2.0}])
    assert result == pytest.approx(0.8)


def test_imbalance_of_respects_depth_n():
    bids = [{"price": 99.0, "size": 1.0}, {"price": 98.0, "size": 100.0}]
    asks = [{"price": 101.0, "size": 1.0}]
    result = _imbalance_of(bids, asks, depth_n=1)
    assert result == pytest.approx(0.5)  # depth=1이면 size=100 레벨 무시


def test_imbalance_of_empty_book_returns_neutral():
    assert _imbalance_of([], []) == pytest.approx(0.5)


def test_mid_of_uses_max_bid_min_ask_not_list_order():
    bids = [{"price": 90.0, "size": 1.0}, {"price": 99.0, "size": 1.0}]
    asks = [{"price": 105.0, "size": 1.0}, {"price": 101.0, "size": 1.0}]
    # correct mid = (max(90,99)=99 + min(105,101)=101)/2 = 100.0
    assert _mid_of(bids, asks) == pytest.approx(100.0)


def test_mid_of_empty_book_returns_nan():
    assert pd.isna(_mid_of([], []))


def test_stream_imbalance_and_mid_matches_dataframe_path(tmp_path, monkeypatch):
    """스트리밍 경로가 기존 DataFrame 경로(load_venue_snapshots -> build_imbalance /
    행단위 _mid_of)와 정확히 같은 값을 내는지 확인 — 회귀 방지 핵심 테스트."""
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "binance_BTC_2026-07-12.jsonl", [
        {"ts": 2.0, "bids": [{"price": 99.0, "size": 1.0}, {"price": 98.0, "size": 3.0}],
         "asks": [{"price": 101.0, "size": 2.0}]},
        {"ts": 1.0, "bids": [{"price": 98.0, "size": 2.0}],
         "asks": [{"price": 102.0, "size": 2.0}, {"price": 103.0, "size": 1.0}]},
    ])
    df = load_venue_snapshots("binance", "BTC", ["2026-07-12"])
    expected_imbalance = build_imbalance(df)
    expected_mid = pd.Series(
        df.apply(lambda r: _mid_of(r["bids"], r["asks"]), axis=1).to_numpy(), index=df["ts"].to_numpy())

    imbalance, mid = stream_imbalance_and_mid("binance", "BTC", ["2026-07-12"])

    assert list(imbalance.index) == list(expected_imbalance.index)
    assert imbalance.to_numpy() == pytest.approx(expected_imbalance.to_numpy())
    assert list(mid.index) == list(expected_mid.index)
    assert mid.to_numpy() == pytest.approx(expected_mid.to_numpy())


def test_stream_imbalance_and_mid_merges_multiple_dates_sorted(tmp_path, monkeypatch):
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    _write_jsonl(tmp_path / "binance_BTC_2026-07-12.jsonl", [
        {"ts": 1.0, "bids": [{"price": 99.0, "size": 1.0}], "asks": [{"price": 101.0, "size": 1.0}]},
    ])
    _write_jsonl(tmp_path / "binance_BTC_2026-07-13.jsonl", [
        {"ts": 2.0, "bids": [{"price": 99.0, "size": 1.0}], "asks": [{"price": 101.0, "size": 1.0}]},
    ])
    imbalance, mid = stream_imbalance_and_mid("binance", "BTC", ["2026-07-12", "2026-07-13"])
    assert list(imbalance.index) == [1.0, 2.0]
    assert list(mid.index) == [1.0, 2.0]


def test_stream_imbalance_and_mid_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    imbalance, mid = stream_imbalance_and_mid("binance", "BTC", ["2026-01-01"])
    assert imbalance.empty
    assert mid.empty
```

- [ ] **Step 3: 테스트 실행 — 신규 테스트가 실패하는지 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cross_venue_skew.py -q`
Expected: FAIL — `ImportError: cannot import name '_imbalance_of'` (아직 미구현).

- [ ] **Step 4: `_imbalance_of`/`_mid_of` 추출 + `build_imbalance`/`build_price_series` 리팩터**

`research/hypotheses/cross_venue_skew.py:53-64`를 다음으로 교체:

```python
def _imbalance_of(bids: list[dict], asks: list[dict], depth_n: int = IMBALANCE_DEPTH_N) -> float:
    bid_sum = sum(lvl["size"] for lvl in bids[:depth_n])
    ask_sum = sum(lvl["size"] for lvl in asks[:depth_n])
    total = bid_sum + ask_sum
    return bid_sum / total if total > 0 else 0.5


def build_imbalance(df: pd.DataFrame, depth_n: int = IMBALANCE_DEPTH_N) -> pd.Series:
    """시점별 imbalance = sum(bid.size[:depth_n]) / (sum(bid.size[:depth_n]) + sum(ask.size[:depth_n])).
    0.5=중립, 1에 가까울수록 매수우위. 양쪽 합이 0이면 0.5. index=ts."""
    values = df.apply(lambda row: _imbalance_of(row["bids"], row["asks"], depth_n), axis=1)
    return pd.Series(values.values, index=df["ts"].values)
```

`research/hypotheses/cross_venue_skew.py:93-114`(`build_price_series` 전체)를 다음으로 교체:

```python
def _mid_of(bids: list[dict], asks: list[dict]) -> float:
    if not bids or not asks:
        return float("nan")
    best_bid = max(lvl["price"] for lvl in bids)
    best_ask = min(lvl["price"] for lvl in asks)
    return (best_bid + best_ask) / 2.0


def build_price_series(raw_books_by_venue: dict[str, pd.DataFrame]) -> pd.Series:
    """RESAMPLE_GRID_S 그리드에서 벤뉴별 mid=(best_bid+best_ask)/2를 구하고
    벤뉴간 평균 — 레이블 계산용 단일 가격 시계열(코인당 1개).
    best_bid/best_ask는 리스트 순서를 신뢰하지 않고 명시적으로
    best_bid=max(bid.price), best_ask=min(ask.price)로 계산한다."""
    if not raw_books_by_venue:
        return pd.Series(dtype=float)

    mids_by_venue: dict[str, pd.Series] = {}
    for venue, df in raw_books_by_venue.items():
        values = df.apply(lambda row: _mid_of(row["bids"], row["asks"]), axis=1)
        mids_by_venue[venue] = pd.Series(values.values, index=df["ts"].values)

    aligned = align_venues(mids_by_venue)
    return aligned.mean(axis=1, skipna=True)
```

- [ ] **Step 5: 테스트 재실행 — 리팩터가 기존 동작을 안 깼는지 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cross_venue_skew.py -q`
Expected: 신규 6개 중 스트리밍 관련 3개(`test_stream_imbalance_and_mid_*`)만 FAIL(`AttributeError`/`ImportError: stream_imbalance_and_mid`), 나머지(기존 전체 + `_imbalance_of`/`_mid_of` 신규 4개)는 PASS.

- [ ] **Step 6: `stream_imbalance_and_mid` 구현**

`load_venue_snapshots` 함수(현재 27-50행) 바로 뒤, `_imbalance_of` 정의 이전에 추가:

```python
def stream_imbalance_and_mid(
    venue: str, coin: str, dates: list[str], depth_n: int = IMBALANCE_DEPTH_N,
) -> tuple[pd.Series, pd.Series]:
    """load_venue_snapshots와 동일 파일 탐색(평문 우선, 없으면 .gz)이지만 bids/asks를
    DataFrame에 적재하지 않고 줄마다 imbalance/mid 스칼라만 뽑아 즉시 버림 — 피크
    메모리가 파일 크기(GB)가 아니라 날짜수×스냅샷수에 비례(2026-09-14: 원본
    DataFrame 캐시가 45일 윈도로도 배치 1시간 만에 물리메모리 70.6GB 찍고 GC
    스래싱 재현). 반환값은 build_imbalance/행단위 _mid_of 결과와 동일 형태
    (index=ts인 pd.Series, ts 오름차순) — align_venues 등 하위 함수는 무수정으로
    그대로 받는다."""
    ts_list: list[float] = []
    imb_list: list[float] = []
    mid_list: list[float] = []
    for date in dates:
        plain = _DATA_DIR / f"{venue}_{coin}_{date}.jsonl"
        gz = _DATA_DIR / f"{venue}_{coin}_{date}.jsonl.gz"
        if plain.exists():
            opener = plain.open
        elif gz.exists():
            opener = lambda: gzip.open(gz, "rt")
        else:
            continue
        with opener() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                bids, asks = row["bids"], row["asks"]
                ts_list.append(row["ts"])
                imb_list.append(_imbalance_of(bids, asks, depth_n))
                mid_list.append(_mid_of(bids, asks))

    if not ts_list:
        empty = pd.Series(dtype=float)
        return empty, empty

    order = pd.DataFrame({"ts": ts_list, "imbalance": imb_list, "mid": mid_list}).sort_values("ts")
    ts_sorted = order["ts"].to_numpy()
    imbalance = pd.Series(order["imbalance"].to_numpy(), index=ts_sorted)
    mid = pd.Series(order["mid"].to_numpy(), index=ts_sorted)
    return imbalance, mid
```

- [ ] **Step 7: 전체 테스트 실행 — 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_cross_venue_skew.py -q`
Expected: PASS (전건).

- [ ] **Step 8: 커밋**

```bash
git add research/hypotheses/cross_venue_skew.py tests/test_cross_venue_skew.py
git commit -m "$(cat <<'EOF'
refactor: cross_venue_skew imbalance/mid 스칼라 헬퍼 추출 + 스트리밍 로더 신설

build_imbalance/build_price_series의 행단위 클로저(_imb/_mid)를 모듈 함수
_imbalance_of/_mid_of로 추출(DRY, 동작 불변) — stream_imbalance_and_mid()가
같은 공식을 재사용해 파일을 줄 단위로 읽으며 bids/asks 원본을 DataFrame에
안 올리고 imbalance/mid 스칼라만 뽑는다. load_venue_snapshots/validate.py는
무수정.
EOF
)"
```

---

### Task 2: engines_microstructure.py — 캐시/로더/일별 mid/skew 결과 재작성

**Files:**
- Modify: `research/autoresearch/engines_microstructure.py` (`_snapshot_cache`~`_load_venue_snapshots_cached` 블록, `_daily_mid`, `_skew_divergence_result`의 import+로딩부)
- Test: `tests/test_engines_microstructure.py`

**Interfaces:**
- Consumes: `stream_imbalance_and_mid(venue, coin, dates, depth_n=...) -> tuple[pd.Series, pd.Series]` (Task 1).
- Produces:
  - `_load_venue_series_cached(venue: str, coin: str) -> tuple[pd.Series, pd.Series] | None` — `_load_venue_snapshots_cached` 대체. `None`은 "해당 venue×coin 데이터 없음"(기존과 동일 의미).
  - `_snapshot_cache: dict[tuple[str,str], tuple[pd.Series, pd.Series] | None]` — 타입만 바뀜, 변수명/`microstructure_candidates()`의 `.clear()` 호출부는 그대로.

- [ ] **Step 1: 기존 테스트 기준선 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_engines_microstructure.py -q`
Expected: 전부 PASS (Task 1 반영 전 베이스라인 — 아직 `_load_venue_snapshots_cached` 그대로라 영향 없음).

- [ ] **Step 2: 캐시 공유/윈도클립 테스트를 새 함수명 기준으로 재작성**

`tests/test_engines_microstructure.py`에서 `test_select_basis_pairs_caches_daily_mid_across_pairs`를 찾아 전체 교체:

```python
def test_select_basis_pairs_caches_daily_mid_across_pairs(tmp_path, monkeypatch):
    """BASIS_VENUE_PAIRS의 binance/okx/hl는 각각 2개 페어에 재등장 — 캐시 없으면
    같은 (venue,coin) 스냅샷을 배치 1회당 2번씩 중복 스트리밍(2026-09-03 실서버:
    3.1GB cross_venue_skew 원본을 이 경로가 중복 로드해 GC 스톨 유발 실측).
    캐시 도입 후 distinct (venue,coin) 조합당 stream_imbalance_and_mid 호출이
    1번만 되는지 확인."""
    monkeypatch.setattr(em, "_SKEW_DIR", tmp_path)
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    ts0 = 1752105600.0
    for venue in ("binance", "okx", "hl"):
        _write_skew_day(tmp_path, venue, "BTC", "2025-07-10", [
            {"ts": ts0, "bids": [{"price": 100.0, "size": 1.0}], "asks": [{"price": 102.0, "size": 1.0}]}])

    calls = []
    real = cvs.stream_imbalance_and_mid

    def counting(venue, coin, dates, depth_n=cvs.IMBALANCE_DEPTH_N):
        calls.append((venue, coin))
        return real(venue, coin, dates, depth_n)
    monkeypatch.setattr(cvs, "stream_imbalance_and_mid", counting)

    em._select_basis_pairs()

    # BASIS_VENUE_PAIRS = [(binance,okx),(binance,hl),(okx,hl)] -> 3 distinct venues,
    # 캐시 없으면 6번(각 페어가 venue_a/venue_b 둘 다 로드) 호출됨. ETH는 데이터 없어 스킵.
    assert sorted(calls) == [("binance", "BTC"), ("hl", "BTC"), ("okx", "BTC")]
```

같은 파일에서 `test_load_venue_snapshots_cached_clips_to_lookback_window`를 찾아 전체 교체:

```python
def test_load_venue_series_cached_clips_to_lookback_window(tmp_path, monkeypatch):
    """collector가 날마다 파일 계속 쌓음(2026-09-13 I/O 폭주 원인) — 캐시가 있어도
    로드 윈도가 무한하면 데이터 늘수록 I/O 계속 증가. 최근 SKEW_LOOKBACK_DAYS일로
    클립되는지, _MIN_DAYS=30 통계 게이트 넘는 날짜수가 실제로 남는지 확인."""
    monkeypatch.setattr(em, "_SKEW_DIR", tmp_path)
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    all_dates = [f"2025-06-{d:02d}" if d <= 30 else f"2025-07-{d - 30:02d}" for d in range(1, 61)]
    assert len(all_dates) == 60  # _MIN_DAYS(30) + SKEW_LOOKBACK_DAYS(45) 둘 다 넉넉히 넘는 픽스처
    for date in all_dates:
        _write_skew_day(tmp_path, "binance", "BTC", date, [
            {"ts": 1752105600.0, "bids": [{"price": 100.0, "size": 1.0}], "asks": [{"price": 102.0, "size": 1.0}]}])

    captured = {}
    real = cvs.stream_imbalance_and_mid

    def spy(venue, coin, dates, depth_n=cvs.IMBALANCE_DEPTH_N):
        captured["dates"] = dates
        return real(venue, coin, dates, depth_n)
    monkeypatch.setattr(cvs, "stream_imbalance_and_mid", spy)

    em._load_venue_series_cached("binance", "BTC")

    assert len(captured["dates"]) == em.SKEW_LOOKBACK_DAYS
    assert captured["dates"] == all_dates[-em.SKEW_LOOKBACK_DAYS:]
    assert len(captured["dates"]) >= em._MIN_DAYS  # 클립 후에도 통계 유효성 게이트 통과 가능
```

파일 상단 import 블록(`import gzip` / `import json as _json` / `import pytest` / `from research.autoresearch import engines_microstructure as em` 근처)에 `cross_venue_skew` 모듈 import가 없다면 추가:

```python
import research.hypotheses.cross_venue_skew as cvs
```

(이미 있으면 스킵 — `_write_skew_day` 헬퍼가 이미 이 모듈을 쓰고 있을 가능성이 높으니 파일 상단을 먼저 확인할 것.)

메모리 회귀 방지용 신규 테스트를 파일 끝에 추가:

```python
import tracemalloc


def test_load_venue_series_cached_peak_memory_far_below_dataframe_snapshot(tmp_path, monkeypatch):
    """_load_venue_series_cached가 스트리밍(스칼라만 보관)을 쓰므로, 같은 파일을
    DataFrame으로 통째로 적재하는 경로(load_venue_snapshots+build_imbalance)보다
    피크 메모리가 확연히 작아야 한다. 절대 바이트 임계값은 플랫폼/파이썬 버전마다
    흔들리므로 비교로 검증(2026-09-14: okx_BTC 실측 1파일 46MB gz -> 2.99GB 해제,
    이 배율을 테스트에서 재현할 필요는 없고 '커지지 않는다'만 확인하면 충분)."""
    monkeypatch.setattr(em, "_SKEW_DIR", tmp_path)
    monkeypatch.setattr(cvs, "_DATA_DIR", tmp_path)
    rows = [
        {"ts": float(i), "bids": [{"price": 100.0 - j, "size": 1.0} for j in range(5)],
         "asks": [{"price": 101.0 + j, "size": 1.0} for j in range(5)]}
        for i in range(20_000)
    ]
    _write_skew_day(tmp_path, "binance", "BTC", "2025-07-10", rows)

    tracemalloc.start()
    df = cvs.load_venue_snapshots("binance", "BTC", ["2025-07-10"])
    cvs.build_imbalance(df)
    _current, dataframe_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del df

    em._snapshot_cache.clear()
    tracemalloc.start()
    em._load_venue_series_cached("binance", "BTC")
    _current, stream_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert stream_peak < dataframe_peak * 0.5
```

- [ ] **Step 3: 테스트 실행 — 재작성한 테스트가 실패하는지 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_engines_microstructure.py -q`
Expected: FAIL — `AttributeError: module 'research.autoresearch.engines_microstructure' has no attribute '_load_venue_series_cached'` 등(구현 전이라 `_load_venue_snapshots_cached`만 있고 `_load_venue_series_cached` 없음, `cvs.stream_imbalance_and_mid` monkeypatch 대상도 아직 안 쓰임).

- [ ] **Step 4: `_load_venue_snapshots_cached` -> `_load_venue_series_cached` 교체**

`research/autoresearch/engines_microstructure.py`의 `_load_venue_snapshots_cached` 함수 전체(현재 `_snapshot_cache: dict = {}` 바로 아래)를 다음으로 교체:

```python
def _load_venue_series_cached(venue: str, coin: str) -> tuple[pd.Series, pd.Series] | None:
    """venue×coin 오더북 스냅샷을 스트리밍 집계(imbalance, mid)로 로드, 프로세스
    생존 동안 (venue,coin) 단위 캐시.

    basis(_select_basis_pairs)와 skew(_skew_divergence_result)가 SKEW_VENUES/
    BASIS_VENUE_PAIRS에서 같은 (venue,coin) 조합을 각자 따로 로드하던 것을 공유.
    cross_venue_skew.stream_imbalance_and_mid()가 bids/asks 원본을 DataFrame에
    안 올리고 줄마다 스칼라만 뽑아 피크 메모리를 파일 크기(GB)가 아니라 날짜수×
    스냅샷수에 비례하는 수준으로 낮춘다(2026-09-14: 원본 DataFrame 캐시가 45일
    윈도로도 배치 1시간 만에 물리메모리 70.6GB, GC 스래싱 — 강제종료 재현 확인).
    dates도 최근 SKEW_LOOKBACK_DAYS일로 클립 — collector가 매일 데이터 누적해서
    캐시만으로는 I/O가 무한 증가함(_MIN_DAYS=30 통계 유효성 게이트 위에 15일 버퍼)."""
    key = (venue, coin)
    if key not in _snapshot_cache:
        dates = jsonl_dates.list_dates(_SKEW_DIR, glob_prefix=f"{venue}_{coin}_")[-SKEW_LOOKBACK_DAYS:]
        if not dates:
            _snapshot_cache[key] = None
        else:
            from research.hypotheses.cross_venue_skew import stream_imbalance_and_mid
            imbalance, mid = stream_imbalance_and_mid(venue, coin, dates)
            _snapshot_cache[key] = None if mid.empty else (imbalance, mid)
    return _snapshot_cache[key]
```

- [ ] **Step 5: `_daily_mid` 재작성**

`_daily_mid` 함수 전체를 다음으로 교체:

```python
def _daily_mid(venue: str, coin: str) -> dict:
    """venue×coin 오더북 스냅샷 -> 날짜별 평균 mid((best_bid+best_ask)/2).
    UTC 날짜 경계 사용(dt.timezone.utc 대신 pd.to_datetime(unit="s", utc=True) —
    Python 3.14 대상, utcfromtimestamp 미사용). 출력 스키마·값은 기존과 동일."""
    series = _load_venue_series_cached(venue, coin)
    if series is None:
        return {}
    _imbalance, mid = series
    valid = mid.notna()
    if not valid.any():
        return {}
    mid = mid[valid]
    dates = pd.to_datetime(mid.index.to_numpy(), unit="s", utc=True).strftime("%Y-%m-%d")
    return pd.Series(mid.to_numpy(), index=dates).groupby(level=0).mean().to_dict()
```

- [ ] **Step 6: `_skew_divergence_result` 로딩부 재작성**

`_skew_divergence_result` 함수 상단 import 블록을:

```python
    from research.hypotheses.cross_venue_skew import (
        align_venues, build_imbalance, build_labels_multi_horizon,
        build_price_series, build_skew_divergence, build_spike_signal,
    )
```

다음으로 교체(`build_imbalance`/`build_price_series` 더는 안 씀):

```python
    from research.hypotheses.cross_venue_skew import (
        align_venues, build_labels_multi_horizon, build_skew_divergence, build_spike_signal,
    )
```

그 아래:

```python
    raw_by_venue = {v: df for v in SKEW_VENUES if (df := _load_venue_snapshots_cached(v, coin)) is not None}
    if len(raw_by_venue) < 2:
        return None

    imbalance_by_venue = {v: build_imbalance(df) for v, df in raw_by_venue.items()}
    aligned = align_venues(imbalance_by_venue)
    divergence = build_skew_divergence(aligned)
    spikes = build_spike_signal(divergence)
    price = build_price_series(raw_by_venue)
```

를 다음으로 교체:

```python
    series_by_venue = {v: s for v in SKEW_VENUES if (s := _load_venue_series_cached(v, coin)) is not None}
    if len(series_by_venue) < 2:
        return None

    imbalance_by_venue = {v: imb for v, (imb, _mid) in series_by_venue.items()}
    mid_by_venue = {v: mid for v, (_imb, mid) in series_by_venue.items()}
    aligned = align_venues(imbalance_by_venue)
    divergence = build_skew_divergence(aligned)
    spikes = build_spike_signal(divergence)
    price = align_venues(mid_by_venue).mean(axis=1, skipna=True)
```

(`price` 계산은 `build_price_series`가 내부에서 하던 것과 동일 — `align_venues` 그리드 정렬 후 컬럼 평균.)

- [ ] **Step 7: 테스트 실행 — 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_engines_microstructure.py tests/test_cross_venue_skew.py tests/test_autoresearch_engine.py -q`
Expected: PASS (전건).

- [ ] **Step 8: 커밋**

```bash
git add research/autoresearch/engines_microstructure.py tests/test_engines_microstructure.py
git commit -m "$(cat <<'EOF'
fix: engines_microstructure 스냅샷 캐시를 스트리밍 imbalance/mid로 교체

_load_venue_snapshots_cached(DataFrame 통째로 캐시)를 _load_venue_series_cached
(스트리밍 imbalance/mid Series만 캐시)로 교체. _daily_mid/_skew_divergence_result가
새 캐시를 직접 소비 — bids/asks 원본 DataFrame이 더는 이 경로에 안 올라온다.
45일 윈도로도 배치가 물리메모리 70.6GB 찍고 GC 스래싱하던 문제(2026-09-14 재현,
강제종료 확인)의 근본원인 수정. load_venue_snapshots/validate.py 무수정.
EOF
)"
```

---

### Task 3: 전체 회귀 + 실배치 규모 메모리 검증 → 최종 확정

**Files:**
- 없음(코드 수정 없음, 검증 전용). 결과에 따라 `docs/progress.md`만 갱신.

**Interfaces:**
- Consumes: Task 1+2가 만든 전체 구현.
- Produces: 없음(검증 결과 보고 + progress.md 기록).

- [ ] **Step 1: 전체 테스트 스위트 그린 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: 전건 PASS, pre-existing failure 없음(CLAUDE.md 기준).

- [ ] **Step 2: 실배치 규모 데이터로 메모리 재현 검증**

아래 스크립트를 백그라운드로 실행(실제 `research/data/cross_venue_skew/` 데이터, 6조합×45일 규모 — SIGKILL 재현에 썼던 것과 동일 시나리오):

```bash
cd /Users/seokhun/seokminal/seokminal-multi-venue
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -c "
from research.autoresearch import engines_microstructure as em
em.microstructure_candidates()
print('DONE')
" > /tmp/micro_timing_streaming.log 2>&1 &
echo $!
```

`echo $!`로 나온 PID를 기록해두고, 완료될 때까지 `/usr/bin/sample <PID> 1 -file /tmp/sample_streaming.txt`를 주기적으로 실행해 "Physical footprint" 값을 추적한다(이번 세션에서 `ps -o rss`가 실제 물리 메모리를 과소평가한다고 확인됐으므로 `ps` 대신 `sample`을 신뢰 지표로 쓸 것).

Expected: 프로세스가 완주(`DONE` 출력)하고, `sample` "Physical footprint (peak)"이 수 GB 이내(이전 70.6GB 대비 최소 한 자릿수 개선)로 유지됨.

- [ ] **Step 3: 결과에 따라 분기**

- **통과(수 GB 이내로 완주)**: Task 1/2 커밋은 이미 완료된 상태 — 추가 커밋 불필요. `docs/progress.md`(이번 세션 진행 기록 upsert 컨벤션)에 최상단 새 엔트리로 (a) 원래 45일 윈도 fix가 불충분했던 이유(파일 1개가 이미 GB 스케일), (b) 스트리밍 재설계로 교체한 내용, (c) 재현 검증 결과(피크 물리메모리 수치) 기록.
- **미통과(여전히 크거나 GC 스래싱)**: 커밋된 Task 1/2를 되돌리지 말고, 새 발견을 `docs/progress.md`에 기록 후 사용자에게 보고 — 이 경우 근본원인이 추가로 남아있다는 뜻(예: `align_venues`의 1초 그리드 자체가 45일치 tick 수만큼 큰 DataFrame을 만드는 것일 수 있음 — 후속 조사 필요, 이 플랜 범위 밖).

- [ ] **Step 4: (통과 시) progress.md 커밋**

```bash
git add docs/progress.md
git commit -m "$(cat <<'EOF'
docs: skew 로더 스트리밍 재설계 완료 — 실배치 규모 메모리 재검증 기록
EOF
)"
```
