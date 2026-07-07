# Polymarket 합가격 차익거래 수집·검증 파이프라인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polymarket 이진 마켓의 YES+NO 합가격 차익거래 기회를 라이브 CLOB 오더북으로 수집하고, 지속성·순마진·빈도 3축으로 go/no-go를 판정하는 리서치 파이프라인을 만든다.

**Architecture:** `research/polymarket_arb/`에 순수함수 판정 로직(`detector.py`)과 I/O 로직(`collector.py`)을 분리. `research/run_polymarket_arb_scan.py`가 무한루프로 돌며 `research/data/polymarket_arb/*.jsonl`에 스냅샷을 적재하고, `research/run_polymarket_arb_validation.py`가 사후에 그 데이터를 읽어 판정 리포트를 출력한다. `polymarket/client.py`는 CLOB 토큰ID를 추출하도록 최소 확장만 한다. 프로덕션 `api_server/polymarket_bot.py`는 전혀 건드리지 않는다.

**Tech Stack:** Python 3.14, `requests`(CLOB HTTP), pytest, 기존 `polymarket/client.py`(Gamma API 클라이언트) 재사용.

## Global Constraints

- Python 인터프리터: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`
- 테스트: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest <path> -q`
- `asyncio_mode="auto"` — `@pytest.mark.asyncio` 절대 쓰지 않음 (이 플랜의 코드는 전부 동기라 해당 없음)
- `research/`는 기존 컨벤션상 `api_server/`를 import하지 않음 (grep으로 기존 코드 확인 완료) — 필터 상수는 값만 복제, import 금지
- 실주문 체결(CLOB 서명 주문) 코드는 이 플랜 스코프 밖 — 전부 읽기전용 오더북 조회만
- `api_server/polymarket_bot.py`, `data/polymarket_bot*.json(l)` 등 프로덕션 페이퍼봇 관련 파일은 이 플랜에서 수정하지 않음

---

## Task 1: `polymarket/client.py` — CLOB 토큰ID 추출

**Files:**
- Modify: `polymarket/client.py:44-67` (`_map_market` 함수)
- Test: `tests/test_polymarket_client.py` (신규)

**Interfaces:**
- Produces: `_map_market(raw: dict) -> dict | None` 반환 dict에 `"clob_token_ids": tuple[str | None, str | None]` 필드 추가. 정상 케이스는 `("<yes_token_id>", "<no_token_id>")`, 누락/개수불일치는 `(None, None)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_polymarket_client.py
from polymarket.client import _map_market


def _raw_market(**over):
    base = {
        "conditionId": "c1", "question": "q", "events": [{"id": "e1", "title": "t"}],
        "endDateIso": "2099-01-01", "volumeNum": 100.0, "liquidityNum": 5000.0,
        "outcomes": ["Yes", "No"], "outcomePrices": ["0.6", "0.4"],
        "active": True, "closed": False, "acceptingOrders": True,
    }
    base.update(over)
    return base


def test_map_market_extracts_clob_token_ids():
    mapped = _map_market(_raw_market(clobTokenIds='["111", "222"]'))
    assert mapped["clob_token_ids"] == ("111", "222")


def test_map_market_missing_clob_token_ids_defaults_to_none_pair():
    mapped = _map_market(_raw_market())
    assert mapped["clob_token_ids"] == (None, None)


def test_map_market_malformed_clob_token_ids_defaults_to_none_pair():
    mapped = _map_market(_raw_market(clobTokenIds='["only-one"]'))
    assert mapped["clob_token_ids"] == (None, None)


def test_map_market_still_returns_none_for_non_binary_outcomes():
    mapped = _map_market(_raw_market(outcomes=["A", "B", "C"], outcomePrices=["0.3", "0.3", "0.4"]))
    assert mapped is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_client.py -v`
Expected: FAIL — `KeyError: 'clob_token_ids'` on the first two tests (field doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

In `polymarket/client.py`, inside `_map_market`, right before the `return {` block (currently around line 54, right after `event = (m.get("events") or [{}])[0]`), add:

```python
    clob_ids = _parse_json_list(m.get("clobTokenIds") or [])
    clob_token_ids = (clob_ids[0], clob_ids[1]) if len(clob_ids) == 2 else (None, None)
```

Then add `"clob_token_ids": clob_token_ids,` as a new key in the returned dict (any position, e.g. right after `"accepting_orders": bool(m.get("acceptingOrders")),`).

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_client.py -v`
Expected: 4 passed

- [ ] **Step 5: Run existing polymarket bot tests to confirm no regression**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_bot.py -v`
Expected: all previously-passing tests still pass (they patch `get_markets`/`get_market` directly and never exercise `_map_market`, so this is a pure addition).

- [ ] **Step 6: Commit**

```bash
git add polymarket/client.py tests/test_polymarket_client.py
git commit -m "feat: polymarket client extracts CLOB token IDs from market payload"
```

---

## Task 2: `research/polymarket_arb/detector.py` — 차익 판정 순수함수

**Files:**
- Create: `research/polymarket_arb/__init__.py` (빈 파일)
- Create: `research/polymarket_arb/detector.py`
- Test: `tests/test_polymarket_arb_detector.py`

**Interfaces:**
- Produces: `evaluate_snapshot(yes_ask: float, no_ask: float, fee_buffer: float = 0.01) -> dict` returning `{"sum_ask": float, "is_opportunity": bool}`. Used by Task 3's `collector.snapshot_market`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_polymarket_arb_detector.py
from research.polymarket_arb.detector import evaluate_snapshot


def test_evaluate_snapshot_detects_opportunity_below_buffer():
    r = evaluate_snapshot(yes_ask=0.45, no_ask=0.50)
    assert r["sum_ask"] == 0.95
    assert r["is_opportunity"] is True


def test_evaluate_snapshot_no_opportunity_above_one():
    r = evaluate_snapshot(yes_ask=0.52, no_ask=0.50)
    assert r["sum_ask"] == 1.02
    assert r["is_opportunity"] is False


def test_evaluate_snapshot_respects_fee_buffer_boundary():
    # sum_ask=0.99, buffer=1% -> threshold=0.99, 0.99 < 0.99 is False (경계는 기회 아님)
    r = evaluate_snapshot(yes_ask=0.49, no_ask=0.50, fee_buffer=0.01)
    assert r["sum_ask"] == 0.99
    assert r["is_opportunity"] is False


def test_evaluate_snapshot_zero_buffer_only_needs_under_one():
    r = evaluate_snapshot(yes_ask=0.499, no_ask=0.50, fee_buffer=0.0)
    assert r["is_opportunity"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_arb_detector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.polymarket_arb'`

- [ ] **Step 3: Write minimal implementation**

```python
# research/polymarket_arb/__init__.py
```

```python
# research/polymarket_arb/detector.py
"""합가격 차익거래 판정 — 순수함수, I/O 없음. collector.py가 오더북에서
best ask를 뽑아 여기 넘긴다."""
from __future__ import annotations


def evaluate_snapshot(yes_ask: float, no_ask: float, fee_buffer: float = 0.01) -> dict:
    """YES ask + NO ask 합가격 계산 후 차익기회 여부 판정.

    fee_buffer: 수수료/가스비 감안 버퍼(기본 1%) — sum_ask가 (1 - fee_buffer)
    미만이어야 기회로 카운트한다.
    """
    sum_ask = round(yes_ask + no_ask, 4)
    return {"sum_ask": sum_ask, "is_opportunity": sum_ask < (1.0 - fee_buffer)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_arb_detector.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add research/polymarket_arb/__init__.py research/polymarket_arb/detector.py tests/test_polymarket_arb_detector.py
git commit -m "feat: add pure arbitrage-detection function for polymarket YES+NO sum"
```

---

## Task 3: `research/polymarket_arb/collector.py` — 마켓 선정 + CLOB 오더북 폴링

**Files:**
- Create: `research/polymarket_arb/collector.py`
- Test: `tests/test_polymarket_arb_collector.py`

**Interfaces:**
- Consumes: `polymarket.client.get_markets(limit: int = 200, active: bool = True, closed: bool = False) -> list[dict]` (each dict includes `condition_id, question, liquidity, yes_price, no_price, end_date, active, closed, accepting_orders, clob_token_ids` per Task 1). `research.polymarket_arb.detector.evaluate_snapshot(yes_ask, no_ask, fee_buffer=0.01) -> dict` from Task 2.
- Produces: `select_liquid_markets(top_n: int = 50) -> list[dict]`, `fetch_book(token_id: str, retries: int = 3) -> dict | None`, `best_levels(book: dict) -> dict` (keys `bid, bid_size, ask, ask_size`), `snapshot_market(market: dict, fee_buffer: float = 0.01) -> dict | None`, `run_once(top_n: int = 50, fee_buffer: float = 0.01) -> list[dict]`. Module constants `TOP_N = 50`, `POLL_INTERVAL_SEC = 10`, `FEE_BUFFER = 0.01` consumed by Task 4.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_polymarket_arb_collector.py
from unittest.mock import MagicMock, patch

from research.polymarket_arb import collector


def _market(condition_id="c1", liquidity=10000.0, yes_price=0.5, no_price=0.5,
            end_date="2099-01-01", clob_token_ids=("y1", "n1"), active=True,
            closed=False, accepting=True):
    return {
        "condition_id": condition_id, "question": f"q-{condition_id}", "event_id": "e1",
        "event_title": "", "end_date": end_date, "volume": 1000.0, "liquidity": liquidity,
        "yes_price": yes_price, "no_price": no_price, "active": active, "closed": closed,
        "accepting_orders": accepting, "clob_token_ids": clob_token_ids,
    }


def _book(bids, asks):
    return {"bids": [{"price": str(p), "size": str(s)} for p, s in bids],
            "asks": [{"price": str(p), "size": str(s)} for p, s in asks]}


def test_select_liquid_markets_filters_and_sorts_by_liquidity():
    markets = [
        _market(condition_id="low_liquidity", liquidity=3000.0),
        _market(condition_id="extreme_price", yes_price=0.95),
        _market(condition_id="no_clob", clob_token_ids=(None, None)),
        _market(condition_id="inactive", active=False),
        _market(condition_id="b", liquidity=8000.0),
        _market(condition_id="a", liquidity=20000.0),
    ]
    with patch.object(collector, "get_markets", return_value=markets):
        picked = collector.select_liquid_markets(top_n=10)
    assert [m["condition_id"] for m in picked] == ["a", "b"]


def test_select_liquid_markets_respects_top_n():
    markets = [_market(condition_id=str(i), liquidity=float(1000 * i)) for i in range(10, 20)]
    with patch.object(collector, "get_markets", return_value=markets):
        picked = collector.select_liquid_markets(top_n=3)
    assert len(picked) == 3
    assert picked[0]["condition_id"] == "19"


def test_best_levels_picks_best_bid_and_ask_with_size():
    book = _book(bids=[(0.40, 5), (0.45, 8)], asks=[(0.55, 12), (0.60, 3)])
    levels = collector.best_levels(book)
    assert levels == {"bid": 0.45, "bid_size": 8.0, "ask": 0.55, "ask_size": 12.0}


def test_best_levels_handles_empty_book():
    levels = collector.best_levels({"bids": [], "asks": []})
    assert levels == {"bid": None, "bid_size": None, "ask": None, "ask_size": None}


def test_fetch_book_returns_json_on_200():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"bids": [], "asks": []}
    resp.raise_for_status.return_value = None
    with patch.object(collector.requests, "get", return_value=resp):
        book = collector.fetch_book("tok1")
    assert book == {"bids": [], "asks": []}


def test_fetch_book_returns_none_after_retries_exhausted():
    with patch.object(collector.requests, "get", side_effect=Exception("boom")), \
         patch.object(collector.time, "sleep"):
        book = collector.fetch_book("tok1", retries=2)
    assert book is None


def test_snapshot_market_builds_full_record():
    market = _market(condition_id="c1", liquidity=9000.0, clob_token_ids=("y1", "n1"))
    yes_book = _book(bids=[(0.40, 10)], asks=[(0.45, 20)])
    no_book = _book(bids=[(0.48, 15)], asks=[(0.50, 25)])
    with patch.object(collector, "fetch_book", side_effect=[yes_book, no_book]):
        snap = collector.snapshot_market(market)
    assert snap["condition_id"] == "c1"
    assert snap["yes_ask"] == 0.45
    assert snap["yes_ask_size"] == 20.0
    assert snap["no_ask"] == 0.50
    assert snap["no_ask_size"] == 25.0
    assert snap["sum_ask"] == 0.95
    assert snap["is_opportunity"] is True
    assert snap["liquidity"] == 9000.0
    assert "ts" in snap


def test_snapshot_market_returns_none_when_book_fetch_fails():
    market = _market(clob_token_ids=("y1", "n1"))
    with patch.object(collector, "fetch_book", side_effect=[None, _book([(0.5, 1)], [(0.55, 1)])]):
        snap = collector.snapshot_market(market)
    assert snap is None


def test_run_once_collects_snapshots_for_selected_markets():
    markets = [_market(condition_id="a", liquidity=10000.0), _market(condition_id="b", liquidity=9000.0)]
    fake_snap = {"condition_id": "x"}
    with patch.object(collector, "select_liquid_markets", return_value=markets), \
         patch.object(collector, "snapshot_market", return_value=fake_snap):
        snaps = collector.run_once()
    assert snaps == [fake_snap, fake_snap]


def test_run_once_skips_markets_where_snapshot_fails():
    markets = [_market(condition_id="a"), _market(condition_id="b")]
    with patch.object(collector, "select_liquid_markets", return_value=markets), \
         patch.object(collector, "snapshot_market", side_effect=[None, {"condition_id": "b"}]):
        snaps = collector.run_once()
    assert snaps == [{"condition_id": "b"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_arb_collector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.polymarket_arb.collector'`

- [ ] **Step 3: Write minimal implementation**

```python
# research/polymarket_arb/collector.py
"""Polymarket CLOB 오더북 폴링 — 유동성 상위 마켓 선정 + 스냅샷 1틱 생성.

I/O 계층. 차익 판정 로직은 detector.py로 분리해서 순수함수로 테스트한다.
"""
from __future__ import annotations

import datetime as dt
import time

import requests

from polymarket.client import get_markets
from research.polymarket_arb.detector import evaluate_snapshot

_CLOB_BASE = "https://clob.polymarket.com"
_TIMEOUT = 10

# api_server/polymarket_bot.py 다각화봇 기본 필터와 동일값. research/는 기존
# 컨벤션상 api_server를 import하지 않으므로 값만 복제한다 (import 금지).
MIN_LIQUIDITY = 5000.0
MIN_PRICE = 0.10
MAX_PRICE = 0.90
MIN_DAYS_TO_RESOLUTION = 3

TOP_N = 50
POLL_INTERVAL_SEC = 10
FEE_BUFFER = 0.01


def select_liquid_markets(top_n: int = TOP_N) -> list[dict]:
    """유동성 상위 top_n개 이진마켓 선정 (다각화봇과 동일 필터 기준 + 오더북 조회 가능한 마켓만)."""
    today = dt.date.today()
    candidates = []
    for m in get_markets(limit=300):
        if not m["active"] or m["closed"] or not m["accepting_orders"]:
            continue
        if m["liquidity"] < MIN_LIQUIDITY:
            continue
        if not (MIN_PRICE <= m["yes_price"] <= MAX_PRICE):
            continue
        try:
            end = dt.date.fromisoformat(m["end_date"])
        except ValueError:
            continue
        if (end - today).days < MIN_DAYS_TO_RESOLUTION:
            continue
        if m.get("clob_token_ids") in (None, (None, None)):
            continue
        candidates.append(m)
    candidates.sort(key=lambda x: x["liquidity"], reverse=True)
    return candidates[:top_n]


def fetch_book(token_id: str, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        try:
            r = requests.get(f"{_CLOB_BASE}/book", params={"token_id": token_id}, timeout=_TIMEOUT)
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def best_levels(book: dict) -> dict:
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    best_bid = max(bids, key=lambda b: float(b["price"]), default=None)
    best_ask = min(asks, key=lambda a: float(a["price"]), default=None)
    return {
        "bid": float(best_bid["price"]) if best_bid else None,
        "bid_size": float(best_bid["size"]) if best_bid else None,
        "ask": float(best_ask["price"]) if best_ask else None,
        "ask_size": float(best_ask["size"]) if best_ask else None,
    }


def snapshot_market(market: dict, fee_buffer: float = FEE_BUFFER) -> dict | None:
    yes_id, no_id = market["clob_token_ids"]
    yes_book = fetch_book(yes_id)
    no_book = fetch_book(no_id)
    if yes_book is None or no_book is None:
        return None
    yes_levels = best_levels(yes_book)
    no_levels = best_levels(no_book)
    if yes_levels["ask"] is None or no_levels["ask"] is None:
        return None
    evald = evaluate_snapshot(yes_levels["ask"], no_levels["ask"], fee_buffer)
    return {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "condition_id": market["condition_id"],
        "question": market["question"],
        "yes_bid": yes_levels["bid"], "yes_ask": yes_levels["ask"], "yes_ask_size": yes_levels["ask_size"],
        "no_bid": no_levels["bid"], "no_ask": no_levels["ask"], "no_ask_size": no_levels["ask_size"],
        "sum_ask": evald["sum_ask"],
        "liquidity": market["liquidity"],
        "is_opportunity": evald["is_opportunity"],
    }


def run_once(top_n: int = TOP_N, fee_buffer: float = FEE_BUFFER) -> list[dict]:
    snapshots = []
    for market in select_liquid_markets(top_n):
        snap = snapshot_market(market, fee_buffer)
        if snap is not None:
            snapshots.append(snap)
    return snapshots
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_arb_collector.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add research/polymarket_arb/collector.py tests/test_polymarket_arb_collector.py
git commit -m "feat: add polymarket CLOB order-book collector with liquidity-based market selection"
```

---

## Task 4: `research/run_polymarket_arb_scan.py` — 상시 수집 진입점

**Files:**
- Create: `research/run_polymarket_arb_scan.py`
- Test: `tests/test_run_polymarket_arb_scan.py`
- Modify: `.gitignore` (raw 수집 데이터 커밋 방지)

**Interfaces:**
- Consumes: `research.polymarket_arb.collector.run_once(top_n, fee_buffer) -> list[dict]`, `TOP_N`, `POLL_INTERVAL_SEC`, `FEE_BUFFER` from Task 3.
- Produces: `append_snapshots(snapshots: list[dict]) -> None`, `run_forever(poll_interval_sec: float = POLL_INTERVAL_SEC, max_iterations: int | None = None) -> None`. Writes to `research/data/polymarket_arb/YYYY-MM-DD.jsonl`, one file per day — consumed by Task 5's `load_snapshots`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_polymarket_arb_scan.py
import datetime as dt
import json
from unittest.mock import patch

import research.run_polymarket_arb_scan as scan


def test_append_snapshots_writes_jsonl_to_dated_file(tmp_path):
    with patch.object(scan, "_DATA_DIR", tmp_path):
        scan.append_snapshots([{"condition_id": "a"}, {"condition_id": "b"}])
        path = tmp_path / f"{dt.date.today().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["condition_id"] == "a"
    assert json.loads(lines[1])["condition_id"] == "b"


def test_append_snapshots_skips_write_when_empty(tmp_path):
    with patch.object(scan, "_DATA_DIR", tmp_path):
        scan.append_snapshots([])
    assert list(tmp_path.iterdir()) == []


def test_append_snapshots_appends_to_existing_file(tmp_path):
    with patch.object(scan, "_DATA_DIR", tmp_path):
        scan.append_snapshots([{"condition_id": "a"}])
        scan.append_snapshots([{"condition_id": "b"}])
        path = tmp_path / f"{dt.date.today().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 2


def test_run_forever_stops_after_max_iterations_and_sleeps_between_not_after():
    with patch.object(scan, "run_once", return_value=[{"condition_id": "a"}]) as mock_run, \
         patch.object(scan, "append_snapshots") as mock_append, \
         patch.object(scan.time, "sleep") as mock_sleep:
        scan.run_forever(poll_interval_sec=1, max_iterations=3)
    assert mock_run.call_count == 3
    assert mock_append.call_count == 3
    assert mock_sleep.call_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_arb_scan.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.run_polymarket_arb_scan'`

- [ ] **Step 3: Write minimal implementation**

```python
# research/run_polymarket_arb_scan.py
"""폴리마켓 합가격 차익거래 오더북 수집기 — 상시 실행 진입점.

tmux/systemd로 계속 돌려서 research/data/polymarket_arb/*.jsonl 에 스냅샷을
쌓는다. 판정(go/no-go)은 run_polymarket_arb_validation.py 가 사후에 한다.

Usage: python -m research.run_polymarket_arb_scan
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from research.polymarket_arb.collector import FEE_BUFFER, POLL_INTERVAL_SEC, TOP_N, run_once

_DATA_DIR = Path("research/data/polymarket_arb")


def append_snapshots(snapshots: list[dict]) -> None:
    if not snapshots:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{dt.date.today().isoformat()}.jsonl"
    with path.open("a") as f:
        for snap in snapshots:
            f.write(json.dumps(snap, ensure_ascii=False) + "\n")


def run_forever(poll_interval_sec: float = POLL_INTERVAL_SEC, max_iterations: int | None = None) -> None:
    i = 0
    while max_iterations is None or i < max_iterations:
        append_snapshots(run_once(top_n=TOP_N, fee_buffer=FEE_BUFFER))
        i += 1
        if max_iterations is None or i < max_iterations:
            time.sleep(poll_interval_sec)


if __name__ == "__main__":
    run_forever()
```

Also append to `.gitignore` (after the existing `research/paper/buyback_forward_report.md` line):

```gitignore

# 폴리마켓 차익거래 오더북 원자재 수집(용량 크고 재생성 불가) — 데스크탑/맥에 로컬로만 쌓임
research/data/polymarket_arb/*.jsonl
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_arb_scan.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add research/run_polymarket_arb_scan.py tests/test_run_polymarket_arb_scan.py .gitignore
git commit -m "feat: add always-on entrypoint for polymarket arb order-book collection"
```

---

## Task 5: `research/run_polymarket_arb_validation.py` — go/no-go 판정

**Files:**
- Create: `research/run_polymarket_arb_validation.py`
- Test: `tests/test_run_polymarket_arb_validation.py`

**Interfaces:**
- Consumes: jsonl files written by Task 4's `append_snapshots`, each row matching Task 3's `snapshot_market` schema (`ts, condition_id, question, yes_bid, yes_ask, yes_ask_size, no_bid, no_ask, no_ask_size, sum_ask, liquidity, is_opportunity`).
- Produces: `load_snapshots(data_dir: Path) -> list[dict]`, `find_opportunity_runs(snapshots: list[dict]) -> list[dict]` (each run: `condition_id, start_ts, end_ts, duration_sec, min_sum_ask, ticks, max_capturable_margin_usd`), `evaluate_runs(runs: list[dict], min_duration_sec: float = 3.0) -> dict` (`persistent_runs, runs_per_week, best_min_sum_ask, verdict`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_polymarket_arb_validation.py
import json

from research.run_polymarket_arb_validation import evaluate_runs, find_opportunity_runs, load_snapshots


def _row(condition_id, ts, is_opportunity, sum_ask=0.97, yes_ask_size=50.0, no_ask_size=40.0):
    return {
        "ts": ts, "condition_id": condition_id, "question": f"q-{condition_id}",
        "yes_bid": 0.45, "yes_ask": sum_ask / 2, "yes_ask_size": yes_ask_size,
        "no_bid": 0.45, "no_ask": sum_ask / 2, "no_ask_size": no_ask_size,
        "sum_ask": sum_ask, "liquidity": 9000.0, "is_opportunity": is_opportunity,
    }


def test_load_snapshots_reads_all_jsonl_files_in_dir(tmp_path):
    (tmp_path / "2026-07-01.jsonl").write_text(
        json.dumps(_row("a", "2026-07-01T00:00:00+00:00", True)) + "\n"
    )
    (tmp_path / "2026-07-02.jsonl").write_text(
        json.dumps(_row("a", "2026-07-02T00:00:00+00:00", False)) + "\n"
    )
    rows = load_snapshots(tmp_path)
    assert len(rows) == 2


def test_find_opportunity_runs_groups_consecutive_ticks_per_market():
    rows = [
        _row("a", "2026-07-01T00:00:00+00:00", True, sum_ask=0.95),
        _row("a", "2026-07-01T00:00:10+00:00", True, sum_ask=0.93),
        _row("a", "2026-07-01T00:00:20+00:00", False),
        _row("a", "2026-07-01T00:00:30+00:00", True, sum_ask=0.98),
    ]
    runs = find_opportunity_runs(rows)
    assert len(runs) == 2
    first = runs[0]
    assert first["condition_id"] == "a"
    assert first["ticks"] == 2
    assert first["duration_sec"] == 10.0
    assert first["min_sum_ask"] == 0.93
    second = runs[1]
    assert second["ticks"] == 1
    assert second["duration_sec"] == 0.0


def test_find_opportunity_runs_computes_capturable_margin():
    rows = [_row("a", "2026-07-01T00:00:00+00:00", True, sum_ask=0.90,
                  yes_ask_size=30.0, no_ask_size=50.0)]
    runs = find_opportunity_runs(rows)
    # capturable size = min(30, 50) = 30, margin = 30 * (1 - 0.90) = 3.0
    assert runs[0]["max_capturable_margin_usd"] == 3.0


def test_find_opportunity_runs_ignores_non_opportunity_ticks():
    rows = [_row("a", "2026-07-01T00:00:00+00:00", False)]
    assert find_opportunity_runs(rows) == []


def test_evaluate_runs_rejects_when_no_run_meets_min_duration():
    runs = [{"condition_id": "a", "start_ts": "2026-07-01T00:00:00+00:00",
             "end_ts": "2026-07-01T00:00:00+00:00", "duration_sec": 0.0,
             "min_sum_ask": 0.95, "ticks": 1, "max_capturable_margin_usd": 1.0}]
    report = evaluate_runs(runs, min_duration_sec=3.0)
    assert report["verdict"] == "REJECT_NO_PERSISTENT_RUNS"
    assert report["persistent_runs"] == 0


def test_evaluate_runs_candidate_when_persistent_runs_exist():
    runs = [
        {"condition_id": "a", "start_ts": "2026-07-01T00:00:00+00:00",
         "end_ts": "2026-07-01T00:00:10+00:00", "duration_sec": 10.0,
         "min_sum_ask": 0.93, "ticks": 2, "max_capturable_margin_usd": 3.0},
        {"condition_id": "b", "start_ts": "2026-07-03T00:00:00+00:00",
         "end_ts": "2026-07-03T00:00:20+00:00", "duration_sec": 20.0,
         "min_sum_ask": 0.90, "ticks": 3, "max_capturable_margin_usd": 5.0},
    ]
    report = evaluate_runs(runs, min_duration_sec=3.0)
    assert report["verdict"] == "CANDIDATE"
    assert report["persistent_runs"] == 2
    assert report["best_min_sum_ask"] == 0.90
    assert report["runs_per_week"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_arb_validation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.run_polymarket_arb_validation'`

- [ ] **Step 3: Write minimal implementation**

```python
# research/run_polymarket_arb_validation.py
"""수집된 오더북 스냅샷(research/data/polymarket_arb/*.jsonl)으로 폴리마켓
합가격 차익거래 기회의 go/no-go를 판정한다.

기존 하우스 방식(랜덤 베이스라인 p-value)과 다른 3축 게이트:
지속성(연속 유지시간) x 순마진(사이즈 감안 캡처가능액) x 빈도(주당 발생건수).

Usage: python -m research.run_polymarket_arb_validation [--data-dir DIR] [--min-duration-sec N]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path


def load_snapshots(data_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(Path(data_dir).glob("*.jsonl")):
        for line in path.read_text().strip().splitlines():
            if line:
                rows.append(json.loads(line))
    return rows


def _capturable_margin_usd(row: dict) -> float:
    capturable_size = min(row["yes_ask_size"], row["no_ask_size"])
    return round(capturable_size * (1.0 - row["sum_ask"]), 4)


def _summarize_run(condition_id: str, rows: list[dict]) -> dict:
    start = dt.datetime.fromisoformat(rows[0]["ts"])
    end = dt.datetime.fromisoformat(rows[-1]["ts"])
    return {
        "condition_id": condition_id,
        "start_ts": rows[0]["ts"],
        "end_ts": rows[-1]["ts"],
        "duration_sec": (end - start).total_seconds(),
        "min_sum_ask": min(r["sum_ask"] for r in rows),
        "ticks": len(rows),
        "max_capturable_margin_usd": max(_capturable_margin_usd(r) for r in rows),
    }


def find_opportunity_runs(snapshots: list[dict]) -> list[dict]:
    """condition_id별 시간순 정렬 후 연속된 is_opportunity=True 구간(run)을 찾는다."""
    by_market: dict[str, list[dict]] = defaultdict(list)
    for row in snapshots:
        by_market[row["condition_id"]].append(row)

    runs: list[dict] = []
    for condition_id, rows in by_market.items():
        rows.sort(key=lambda r: r["ts"])
        current: list[dict] = []
        for row in rows:
            if row["is_opportunity"]:
                current.append(row)
            else:
                if current:
                    runs.append(_summarize_run(condition_id, current))
                    current = []
        if current:
            runs.append(_summarize_run(condition_id, current))
    return runs


def evaluate_runs(runs: list[dict], min_duration_sec: float = 3.0) -> dict:
    persistent = [r for r in runs if r["duration_sec"] >= min_duration_sec]
    if not persistent:
        return {"persistent_runs": 0, "runs_per_week": 0.0, "verdict": "REJECT_NO_PERSISTENT_RUNS"}

    start_times = [dt.datetime.fromisoformat(r["start_ts"]) for r in persistent]
    span_days = max((max(start_times) - min(start_times)).total_seconds() / 86400, 1.0)
    runs_per_week = round(len(persistent) / span_days * 7, 2)

    return {
        "persistent_runs": len(persistent),
        "runs_per_week": runs_per_week,
        "best_min_sum_ask": min(r["min_sum_ask"] for r in persistent),
        "verdict": "CANDIDATE",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="research/data/polymarket_arb")
    parser.add_argument("--min-duration-sec", type=float, default=3.0)
    args = parser.parse_args()

    snapshots = load_snapshots(Path(args.data_dir))
    runs = find_opportunity_runs(snapshots)
    report = evaluate_runs(runs, min_duration_sec=args.min_duration_sec)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_arb_validation.py -v`
Expected: 7 passed

- [ ] **Step 5: Run full backend test suite to confirm no regressions**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: same pass count as before this plan started, plus all new tests from Tasks 1-5. Pre-existing failures (`test_auth.py` x3-4, `test_backtest_happy_path`) are expected and unrelated.

- [ ] **Step 6: Commit**

```bash
git add research/run_polymarket_arb_validation.py tests/test_run_polymarket_arb_validation.py
git commit -m "feat: add go/no-go validation report for polymarket arb opportunity runs"
```

---

## After This Plan

Not part of this plan (deliberately deferred, see spec's "스코프 밖" section):
- Running `research/run_polymarket_arb_scan.py` continuously for the ~2-week collection window and eyeballing `runs_per_week` / `best_min_sum_ask` in practice.
- Deciding the final `min_duration_sec` / frequency bar based on real collected data (spec explicitly leaves this open, not a placeholder — it's a judgment call after seeing real numbers).
- Cross-platform (Polymarket vs Kalshi) arbitrage — separate spec/plan cycle.
- Real order execution (wallet signing) — deferred until back in Korea, separate track.
