# 폴리마켓 이벤트 내 후보군 합산 괴리 탐지 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 같은 이벤트(`event_id`)로 묶인 폴리마켓 후보 마켓들의 YES가격 합이 이론상 수렴해야 할 100%에서 얼마나 벗어났는지(괴리) 폴링으로 수집해 `research/data/polymarket_event_divergence/*.jsonl`에 쌓는다.

**Architecture:** `research/polymarket_event_divergence/collector.py`에 순수함수(`group_by_event`, `compute_divergence`)와 `get_markets()` 호출부(`run_once`)를 함께 둔다(단일 마켓 오더북까지 폴링하는 `polymarket_arb`와 달리 이 기능은 Gamma API의 `yes_price` 필드만으로 계산 가능해 별도 CLOB 호출이 없으므로 파일을 detector/collector로 안 쪼갠다). `research/run_polymarket_event_divergence_scan.py`가 무한루프로 돌며 스냅샷을 적재한다. 판단(어느 정도 괴리가 실제 시그널인지)은 이 플랜 스코프 밖 — 후속 검증 스크립트 몫.

**Tech Stack:** Python 3.14, pytest, 기존 `polymarket/client.py::get_markets()` 재사용(신규 API 없음).

## Global Constraints

- Python 인터프리터: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`
- 테스트: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest <path> -q`
- `asyncio_mode="auto"` — `@pytest.mark.asyncio` 절대 쓰지 않음 (이 플랜의 코드는 전부 동기라 해당 없음)
- `research/`는 다른 research 서브모듈의 상수를 import하지 않는다 — `MIN_LIQUIDITY`/`MIN_DAYS_TO_RESOLUTION`은 `polymarket_arb/collector.py`와 같은 값을 복제(import 금지 주석 필수)
- 라이브 API 호출은 테스트에서 하지 않음 — `get_markets`는 항상 mock
- **스펙 3.1절 의사코드는 `run_once`/`compute_divergence`에 `fee_buffer` 파라미터를 넣었지만, 4·9절은 "판단(시그널 여부)은 스캐너 책임이 아니다"라고 명시한다 — 이 플랜은 4·9절을 따라 `fee_buffer`/`FEE_BUFFER`를 이 모듈에 아예 두지 않는다(스펙 내부 불일치를 사용 안 하는 쪽으로 해소, YAGNI).** 스냅샷은 `divergence` raw 값만 담고, 임계치 판단은 후속 스크립트가 한다.
- 데이터 스키마는 스펙 4절 그대로: `ts, event_id, event_title, n_markets, yes_sum, divergence, total_liquidity, markets`

---

## Task 1: `research/polymarket_event_divergence/collector.py` — 그룹핑·괴리 계산·수집

**Files:**
- Create: `research/polymarket_event_divergence/__init__.py` (빈 파일)
- Create: `research/polymarket_event_divergence/collector.py`
- Test: `tests/test_polymarket_event_divergence_collector.py`

**Interfaces:**
- Consumes: `polymarket.client.get_markets(limit: int = 200, active: bool = True, closed: bool = False) -> list[dict]` — 각 dict는 `condition_id, question, event_id, event_title, end_date, liquidity, yes_price, active, closed, accepting_orders` 포함(기존 `_map_market` 필드).
- Produces: `group_by_event(markets: list[dict]) -> dict[str, list[dict]]`, `compute_divergence(event_markets: list[dict]) -> dict | None`, `run_once(top_n: int = 50) -> list[dict]`. 모듈 상수 `MIN_LIQUIDITY = 5000.0`, `MIN_DAYS_TO_RESOLUTION = 3`, `TOP_N_EVENTS = 50`, `POLL_INTERVAL_SEC = 30` — Task 2가 `TOP_N_EVENTS`/`POLL_INTERVAL_SEC`/`run_once`를 가져다 쓴다.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_polymarket_event_divergence_collector.py
import datetime as dt
from unittest.mock import patch

from research.polymarket_event_divergence import collector


def _market(condition_id, event_id="e1", event_title="이벤트", liquidity=10000.0,
            yes_price=0.5, end_date="2099-01-01", active=True, closed=False, accepting=True):
    return {
        "condition_id": condition_id, "question": f"q-{condition_id}", "event_id": event_id,
        "event_title": event_title, "end_date": end_date, "liquidity": liquidity,
        "yes_price": yes_price, "active": active, "closed": closed, "accepting_orders": accepting,
    }


def test_group_by_event_groups_and_drops_singletons():
    markets = [
        _market("a1", event_id="e1"), _market("a2", event_id="e1"),
        _market("b1", event_id="e2"),
        _market("c1", event_id="e3"), _market("c2", event_id="e3"), _market("c3", event_id="e3"),
    ]
    groups = collector.group_by_event(markets)
    assert set(groups.keys()) == {"e1", "e3"}
    assert len(groups["e1"]) == 2
    assert len(groups["e3"]) == 3


def test_group_by_event_skips_markets_without_event_id():
    markets = [_market("a1", event_id=""), _market("a2", event_id="")]
    assert collector.group_by_event(markets) == {}


def test_compute_divergence_calculates_yes_sum_and_divergence():
    markets = [_market("a", yes_price=0.55, liquidity=6000.0),
               _market("b", yes_price=0.52, liquidity=6000.0)]
    snap = collector.compute_divergence(markets)
    assert snap["yes_sum"] == 1.07
    assert snap["divergence"] == 0.07
    assert snap["event_id"] == "e1"
    assert snap["event_title"] == "이벤트"
    assert snap["n_markets"] == 2
    assert snap["total_liquidity"] == 12000.0
    assert [m["condition_id"] for m in snap["markets"]] == ["a", "b"]
    assert "ts" in snap


def test_compute_divergence_returns_none_for_single_market():
    assert collector.compute_divergence([_market("a")]) is None


def test_compute_divergence_returns_none_when_liquidity_sum_below_min():
    markets = [_market("a", liquidity=2000.0), _market("b", liquidity=2000.0)]
    assert collector.compute_divergence(markets) is None


def test_compute_divergence_returns_none_when_any_market_inactive():
    markets = [_market("a"), _market("b", active=False)]
    assert collector.compute_divergence(markets) is None


def test_compute_divergence_returns_none_when_any_market_not_accepting_orders():
    markets = [_market("a"), _market("b", accepting=False)]
    assert collector.compute_divergence(markets) is None


def test_compute_divergence_returns_none_when_any_market_missing_yes_price():
    markets = [_market("a"), _market("b", yes_price=None)]
    assert collector.compute_divergence(markets) is None


def test_compute_divergence_returns_none_when_end_date_malformed():
    markets = [_market("a"), _market("b", end_date="not-a-date")]
    assert collector.compute_divergence(markets) is None


def test_compute_divergence_returns_none_when_any_market_too_close_to_resolution():
    near_date = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    markets = [_market("a"), _market("b", end_date=near_date)]
    assert collector.compute_divergence(markets) is None


def test_run_once_sorts_by_absolute_divergence_and_respects_top_n():
    markets = [
        _market("a1", event_id="e1", yes_price=0.50),
        _market("a2", event_id="e1", yes_price=0.48),
        _market("b1", event_id="e2", yes_price=0.50),
        _market("b2", event_id="e2", yes_price=0.70),
    ]
    with patch.object(collector, "get_markets", return_value=markets):
        snaps = collector.run_once(top_n=1)
    assert len(snaps) == 1
    assert snaps[0]["event_id"] == "e2"


def test_run_once_skips_events_that_fail_filters():
    markets = [_market("a1", event_id="e1"), _market("a2", event_id="e1", active=False)]
    with patch.object(collector, "get_markets", return_value=markets):
        snaps = collector.run_once()
    assert snaps == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_event_divergence_collector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.polymarket_event_divergence'`

- [ ] **Step 3: Write minimal implementation**

```python
# research/polymarket_event_divergence/__init__.py
```

```python
# research/polymarket_event_divergence/collector.py
"""Polymarket 이벤트 내 후보군 YES가격 합산 괴리 탐지 — 폴링 스캐너.

polymarket_arb는 단일 마켓의 YES+NO 합가격만 보지만, 여긴 같은 event_id로
묶인 여러 후보 마켓들의 YES가격 합을 본다(후보군이 상호배타적이므로 이론상
합이 ~100%에 수렴해야 함). 어느 정도 괴리가 실제 시그널인지 판단하는 로직은
이 모듈 스코프 밖 — 수집만 한다.
"""
from __future__ import annotations

import datetime as dt

from polymarket.client import get_markets

# polymarket_arb/collector.py와 동일값(복제, import 금지)
MIN_LIQUIDITY = 5000.0
MIN_DAYS_TO_RESOLUTION = 3

TOP_N_EVENTS = 50
POLL_INTERVAL_SEC = 30


def group_by_event(markets: list[dict]) -> dict[str, list[dict]]:
    """event_id 기준 그룹핑. 소속 마켓 1개뿐인 이벤트는 제외(비교 대상 없음)."""
    groups: dict[str, list[dict]] = {}
    for m in markets:
        event_id = m.get("event_id")
        if not event_id:
            continue
        groups.setdefault(event_id, []).append(m)
    return {eid: ms for eid, ms in groups.items() if len(ms) >= 2}


def compute_divergence(event_markets: list[dict]) -> dict | None:
    """단일 이벤트 소속 마켓들의 YES가격 합산 괴리 스냅샷.

    필터(활성/주문가능/yes_price 존재/잔여기간/유동성 합) 불통과 시 None.
    """
    if len(event_markets) < 2:
        return None
    today = dt.date.today()
    total_liquidity = 0.0
    for m in event_markets:
        if not m["active"] or m["closed"] or not m["accepting_orders"]:
            return None
        if m.get("yes_price") is None:
            return None
        try:
            end = dt.date.fromisoformat(m["end_date"])
        except (ValueError, TypeError):
            return None
        if (end - today).days < MIN_DAYS_TO_RESOLUTION:
            return None
        total_liquidity += m["liquidity"]
    if total_liquidity < MIN_LIQUIDITY:
        return None

    yes_sum = round(sum(m["yes_price"] for m in event_markets), 4)
    first = event_markets[0]
    return {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "event_id": first["event_id"],
        "event_title": first["event_title"],
        "n_markets": len(event_markets),
        "yes_sum": yes_sum,
        "divergence": round(yes_sum - 1.0, 4),
        "total_liquidity": round(total_liquidity, 2),
        "markets": [
            {"condition_id": m["condition_id"], "question": m["question"],
             "yes_price": m["yes_price"], "liquidity": m["liquidity"]}
            for m in event_markets
        ],
    }


def run_once(top_n: int = TOP_N_EVENTS) -> list[dict]:
    markets = get_markets(limit=300)
    groups = group_by_event(markets)
    snapshots = []
    for event_markets in groups.values():
        snap = compute_divergence(event_markets)
        if snap is not None:
            snapshots.append(snap)
    snapshots.sort(key=lambda s: abs(s["divergence"]), reverse=True)
    return snapshots[:top_n]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_event_divergence_collector.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add research/polymarket_event_divergence/__init__.py research/polymarket_event_divergence/collector.py tests/test_polymarket_event_divergence_collector.py
git commit -m "feat: add polymarket event-divergence collector (same-event candidate YES-sum spread)"
```

---

## Task 2: `research/run_polymarket_event_divergence_scan.py` — 상시 수집 진입점

**Files:**
- Create: `research/run_polymarket_event_divergence_scan.py`
- Test: `tests/test_run_polymarket_event_divergence_scan.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `research.polymarket_event_divergence.collector.run_once(top_n) -> list[dict]`, `TOP_N_EVENTS`, `POLL_INTERVAL_SEC` from Task 1.
- Produces: `append_snapshots(snapshots: list[dict]) -> None`, `run_forever(poll_interval_sec: float = POLL_INTERVAL_SEC, max_iterations: int | None = None) -> None`. 매일 `research/data/polymarket_event_divergence/YYYY-MM-DD.jsonl`에 append.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_polymarket_event_divergence_scan.py
import datetime as dt
import json
from unittest.mock import patch

import research.run_polymarket_event_divergence_scan as scan


def test_append_snapshots_writes_jsonl_to_dated_file(tmp_path):
    with patch.object(scan, "_DATA_DIR", tmp_path):
        scan.append_snapshots([{"event_id": "a"}, {"event_id": "b"}])
        path = tmp_path / f"{dt.date.today().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event_id"] == "a"
    assert json.loads(lines[1])["event_id"] == "b"


def test_append_snapshots_skips_write_when_empty(tmp_path):
    with patch.object(scan, "_DATA_DIR", tmp_path):
        scan.append_snapshots([])
    assert list(tmp_path.iterdir()) == []


def test_append_snapshots_appends_to_existing_file(tmp_path):
    with patch.object(scan, "_DATA_DIR", tmp_path):
        scan.append_snapshots([{"event_id": "a"}])
        scan.append_snapshots([{"event_id": "b"}])
        path = tmp_path / f"{dt.date.today().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 2


def test_run_forever_stops_after_max_iterations_and_sleeps_between_not_after():
    with patch.object(scan, "run_once", return_value=[{"event_id": "a"}]) as mock_run, \
         patch.object(scan, "append_snapshots") as mock_append, \
         patch.object(scan.time, "sleep") as mock_sleep:
        scan.run_forever(poll_interval_sec=1, max_iterations=3)
    assert mock_run.call_count == 3
    assert mock_append.call_count == 3
    assert mock_sleep.call_count == 2


def test_run_forever_skips_cycle_on_exception_and_keeps_looping():
    with patch.object(scan, "run_once", side_effect=[Exception("api down"), [{"event_id": "a"}]]) as mock_run, \
         patch.object(scan, "append_snapshots") as mock_append, \
         patch.object(scan.time, "sleep") as mock_sleep:
        scan.run_forever(poll_interval_sec=1, max_iterations=2)
    assert mock_run.call_count == 2
    assert mock_append.call_count == 1  # 첫 사이클은 예외로 스킵, append 안 됨
    assert mock_sleep.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_event_divergence_scan.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.run_polymarket_event_divergence_scan'`

- [ ] **Step 3: Write minimal implementation**

```python
# research/run_polymarket_event_divergence_scan.py
"""폴리마켓 이벤트 내 후보군 YES가격 합산 괴리 스캐너 — 상시 실행 진입점.

tmux/systemd로 계속 돌려서 research/data/polymarket_event_divergence/*.jsonl
에 스냅샷을 쌓는다. 어느 정도 괴리가 실제 시그널인지 판단하는 로직은 이 파일
스코프 밖 — 수집만 한다.

Usage: python -m research.run_polymarket_event_divergence_scan
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path

from research.polymarket_event_divergence.collector import POLL_INTERVAL_SEC, TOP_N_EVENTS, run_once

_DATA_DIR = Path("research/data/polymarket_event_divergence")


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
        try:
            append_snapshots(run_once(top_n=TOP_N_EVENTS))
        except Exception:
            logging.exception("이벤트 괴리 스캔 실패 — 이번 사이클 스킵")
        i += 1
        if max_iterations is None or i < max_iterations:
            time.sleep(poll_interval_sec)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
```

Also add to `.gitignore` right after the existing `research/data/polymarket_arb/*.jsonl` line (line 18):

```gitignore

# 폴리마켓 이벤트 내 후보군 합산 괴리 원자재 수집(재생성 불가) — 로컬 전용
research/data/polymarket_event_divergence/*.jsonl
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_event_divergence_scan.py -v`
Expected: 5 passed

- [ ] **Step 5: Run full backend test suite to confirm no regressions**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: same pass count as before this plan started, plus 18 new tests from Tasks 1-2 (13 + 5). Pre-existing failures (`test_auth.py` x3-4, `test_backtest_happy_path`) are expected and unrelated.

- [ ] **Step 6: Commit**

```bash
git add research/run_polymarket_event_divergence_scan.py tests/test_run_polymarket_event_divergence_scan.py .gitignore
git commit -m "feat: add always-on entrypoint for polymarket event-divergence collection"
```

---

## After This Plan

Not part of this plan (deliberately deferred, see spec's "Out of scope" section):
- 판단/검증 로직(어느 `divergence` 크기가 실제 차익거래로 유효한지) — 데이터 쌓인 뒤 사람이 보고 후속 스크립트로 발전
- 크로스 *이벤트* 논리적 상관관계 분석
- WSS 실시간화
- 페이퍼 포지션 자동 진입/저널링
- `research/run_polymarket_event_divergence_scan.py`를 tmux 상시구동으로 올리는 것 — 이 플랜은 코드만, 실제 장시간 구동/관찰은 별도 작업
