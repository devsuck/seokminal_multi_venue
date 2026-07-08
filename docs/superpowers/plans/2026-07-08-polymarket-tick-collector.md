# Polymarket 실시간 틱 수집기 (1단계: 데이터만) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 라이브 인플레이 스포츠 마켓과 단기 뉴스/정치 마켓의 확률을 Polymarket CLOB WSS로 실시간 구독해 틱 단위로 `research/data/polymarket_tick/*.jsonl`에 적재하는 수집기를 만든다. 전략/판정 로직 없음 — 데이터 축적만.

**Architecture:** `research/polymarket_tick/market_selector.py`(순수함수 — 대상 마켓 선정 + token_id 메타 매핑)와 `research/polymarket_tick/ws_collector.py`(I/O — CLOB WSS 클라이언트 + 틱 파싱)로 분리. `research/run_polymarket_tick_collect.py`가 5분마다 마켓 재선정 → WSS 재구독을 반복하는 무한루프 진입점. `polymarket/client.py`는 스포츠 마켓 식별용 필드 2개만 최소 확장. 프로덕션 `api_server/polymarket_bot.py`, 기존 `research/polymarket_arb/` 트랙은 전혀 건드리지 않는다.

**Tech Stack:** Python 3.14, `websockets`(CLOB WSS 클라이언트), pytest, 기존 `polymarket/client.py`(Gamma API) 재사용.

## Global Constraints

- Python 인터프리터: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`
- 테스트: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest <path> -q`
- `asyncio_mode="auto"` — `@pytest.mark.asyncio` 절대 쓰지 않음
- WSS 클라이언트는 `backends/kis/ws_client.py`의 패턴을 그대로 따른다: 생성자에 `connect_fn: Callable[[str], Any] = websockets.connect` 주입, `async def stream_X(...) -> AsyncIterator[str]`가 `async with self._connect_fn(url) as connection: ... async for message in connection: yield message`. 테스트는 `tests/test_ws_client.py`의 `FakeConnection`/`FakeConnect` 패턴을 그대로 재사용.
- CLOB WSS 실제 검증된 페이로드 (문서 `https://docs.polymarket.com/developers/CLOB/websocket/market-channel`에서 확인):
  - 구독 메시지: `{"assets_ids": [...], "type": "market"}` (필드명 `assets_ids`, 복수형 오타 아님 — 공식 스펙)
  - `book` 이벤트: `{"event_type": "book", "asset_id": "...", "bids": [{"price","size"}...], "asks": [{"price","size"}...], ...}` — asset_id 하나당 스냅샷 1건
  - `price_change` 이벤트: `{"event_type": "price_change", "market": "...", "price_changes": [{"asset_id","price","size","side":"BUY|SELL","best_bid","best_ask"}, ...], ...}` — 마켓당 1메시지, 배열 안에 asset별 변경사항 여러 건
  - 위 두 event_type 외(`tick_size_change`, `last_trade_price` 등)는 1단계에서 무시
- `research/`는 `api_server/`를 import하지 않음 (기존 컨벤션, `polymarket_arb`와 동일) — 필터 상수는 값만 복제, import 금지
- `min_liquidity` 하한값 `5000.0`은 `polymarket_arb/collector.py`의 `MIN_LIQUIDITY`와 동일 값을 복제(import 금지, 별도 상수로 선언)
- `pyproject.toml`의 `[tool.setuptools.packages.find]` include 리스트에는 `research*`가 없지만 기존 `research/polymarket_arb`도 같은 상태로 테스트/실행이 정상 동작 중(패키지 설치가 아니라 `pytest`/`python -m`이 저장소 루트를 `sys.path`에 넣어 동작) — 이 플랜에서도 include 리스트를 건드리지 않는다.
- `websockets` 라이브러리는 이미 설치돼 있으나(`backends/kis/ws_client.py`가 이미 사용 중) `pyproject.toml` dependencies에 선언 누락 상태 — 이 플랜에서 처음 선언 추가.
- 실주문 체결, 전략/판정(모멘텀 vs 오버리액션) 로직은 이 플랜 스코프 밖.
- **스펙 대비 의도적 단순화 2건** (계획 작성 중 확인된 사실 기반):
  1. "news" family의 "거래량 급증" 조건은 뺀다 — Gamma API 응답 전체 필드를 curl로 확인한 결과 24h 거래량 델타를 계산할 수 있는 필드가 없음(`volume`/`volumeNum`은 누적 총량, `oneWeekPriceChange`는 가격 변화지 거래량 아님). news family는 `sports_market_type` null + 잔여기간 3일 미만 + 유동성 하한만으로 판정.
  2. WSS 구독 해제는 마켓별 명시적 unsubscribe 메시지 대신, 5분마다 전체 재연결(새 asset_ids로 재구독)로 대체 — 공개 문서에 unsubscribe 메시지 스펙이 없어 전체 재연결이 더 확실하고 단순하다. 결과적으로 종료된 마켓은 다음 재선정 사이클에서 자연히 구독 목록에서 빠진다(스펙의 "다음 5분 재선정 사이클에서 자연히 빠짐" 문장과 동일한 효과).

---

## Task 1: `polymarket/client.py` — 스포츠 마켓 식별 필드 추가

**Files:**
- Modify: `polymarket/client.py:56-70` (`_map_market` 함수 반환 dict)
- Test: `tests/test_polymarket_client.py` (기존 파일에 테스트 추가)

**Interfaces:**
- Produces: `_map_market(raw: dict) -> dict | None` 반환 dict에 `"sports_market_type": str | None`, `"game_start_time": str | None` 필드 추가. 원본 raw 문자열 그대로 보존(파싱은 Task 2에서 소비 시점에 함).

- [ ] **Step 1: Write the failing test**

`tests/test_polymarket_client.py` 파일 맨 아래에 추가:

```python
def test_map_market_extracts_sports_market_type_and_game_start_time():
    mapped = _map_market(_raw_market(
        sportsMarketType="soccer_halftime_result",
        gameStartTime="2026-07-08 17:00:00+00",
    ))
    assert mapped["sports_market_type"] == "soccer_halftime_result"
    assert mapped["game_start_time"] == "2026-07-08 17:00:00+00"


def test_map_market_defaults_sports_fields_to_none():
    mapped = _map_market(_raw_market())
    assert mapped["sports_market_type"] is None
    assert mapped["game_start_time"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_client.py -v`
Expected: FAIL — `KeyError: 'sports_market_type'` on both new tests.

- [ ] **Step 3: Write minimal implementation**

`polymarket/client.py`의 `_map_market` 반환 dict(현재 55번째 줄 근처, `"clob_token_ids": clob_token_ids,` 바로 다음)에 두 줄 추가:

```python
        "clob_token_ids": clob_token_ids,
        "sports_market_type": m.get("sportsMarketType"),
        "game_start_time": m.get("gameStartTime"),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_client.py -v`
Expected: PASS (all tests including pre-existing ones).

- [ ] **Step 5: Commit**

```bash
git add polymarket/client.py tests/test_polymarket_client.py
git commit -m "feat: map sports_market_type/game_start_time in polymarket client"
```

---

## Task 2: `research/polymarket_tick/market_selector.py` — 대상 마켓 선정 (순수함수)

**Files:**
- Create: `research/polymarket_tick/__init__.py` (빈 파일)
- Create: `research/polymarket_tick/market_selector.py`
- Test: `tests/test_polymarket_tick_selector.py`

**Interfaces:**
- Consumes: Task 1이 확장한 `polymarket/client.py::get_markets()`가 반환하는 마켓 dict 리스트 — 각 dict는 `condition_id, question, end_date, liquidity, clob_token_ids, sports_market_type, game_start_time` 키를 가짐(값 없으면 `None`/기본값).
- Produces:
  - `select_target_markets(markets: list[dict], now: datetime) -> list[dict]` — 입력 마켓 중 조건 충족한 것만, 각 dict에 `"family": "sports" | "news"` 키를 추가해 반환. `now`는 tz-aware UTC.
  - `build_meta_by_token(markets: list[dict]) -> dict[str, dict]` — `select_target_markets()`의 출력을 받아 `token_id -> {"condition_id", "question", "family", "outcome"}` 매핑 반환 (`outcome`은 `"yes"` 또는 `"no"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_polymarket_tick_selector.py
import datetime as dt

from research.polymarket_tick.market_selector import build_meta_by_token, select_target_markets

NOW = dt.datetime(2026, 7, 8, 12, 0, tzinfo=dt.timezone.utc)


def _market(condition_id="c1", liquidity=10000.0, end_date="2026-07-09",
            sports_market_type=None, game_start_time=None, clob_token_ids=("y1", "n1")):
    return {
        "condition_id": condition_id, "question": f"q-{condition_id}", "event_id": "e1",
        "event_title": "", "end_date": end_date, "volume": 1000.0, "liquidity": liquidity,
        "yes_price": 0.5, "no_price": 0.5, "active": True, "closed": False,
        "accepting_orders": True, "clob_token_ids": clob_token_ids,
        "sports_market_type": sports_market_type, "game_start_time": game_start_time,
    }


def test_sports_market_in_progress_included():
    m = _market(sports_market_type="soccer_halftime_result", game_start_time="2026-07-08 11:50:00+00")
    picked = select_target_markets([m], now=NOW)
    assert len(picked) == 1
    assert picked[0]["family"] == "sports"


def test_sports_market_upcoming_within_window_included():
    m = _market(sports_market_type="soccer_halftime_result", game_start_time="2026-07-08 15:00:00+00")
    picked = select_target_markets([m], now=NOW)
    assert len(picked) == 1
    assert picked[0]["family"] == "sports"


def test_sports_market_before_window_excluded():
    m = _market(sports_market_type="soccer_halftime_result", game_start_time="2026-07-08 08:00:00+00")
    assert select_target_markets([m], now=NOW) == []


def test_sports_market_after_window_excluded():
    m = _market(sports_market_type="soccer_halftime_result", game_start_time="2026-07-08 17:00:00+00")
    assert select_target_markets([m], now=NOW) == []


def test_sports_market_missing_game_start_time_excluded():
    m = _market(sports_market_type="soccer_halftime_result", game_start_time=None)
    assert select_target_markets([m], now=NOW) == []


def test_news_market_short_resolution_included():
    m = _market(end_date="2026-07-10")
    picked = select_target_markets([m], now=NOW)
    assert len(picked) == 1
    assert picked[0]["family"] == "news"


def test_news_market_long_resolution_excluded():
    m = _market(end_date="2026-12-31")
    assert select_target_markets([m], now=NOW) == []


def test_low_liquidity_excluded_even_if_otherwise_eligible():
    m = _market(liquidity=1000.0, end_date="2026-07-10")
    assert select_target_markets([m], now=NOW) == []


def test_build_meta_by_token_maps_yes_and_no_with_family():
    m = _market(condition_id="c1", end_date="2026-07-10", clob_token_ids=("y1", "n1"))
    picked = select_target_markets([m], now=NOW)
    meta = build_meta_by_token(picked)
    assert meta["y1"] == {"condition_id": "c1", "question": "q-c1", "family": "news", "outcome": "yes"}
    assert meta["n1"] == {"condition_id": "c1", "question": "q-c1", "family": "news", "outcome": "no"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_tick_selector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.polymarket_tick'`

- [ ] **Step 3: Write minimal implementation**

`research/polymarket_tick/__init__.py`: 빈 파일 생성.

```python
# research/polymarket_tick/market_selector.py
"""대상 마켓 선정 — 순수함수, I/O 없음."""
from __future__ import annotations

import datetime as dt

MIN_LIQUIDITY = 5000.0  # polymarket_arb/collector.py의 MIN_LIQUIDITY와 같은 값(복제, import 금지)
SPORTS_WINDOW_BEFORE = dt.timedelta(minutes=30)
SPORTS_WINDOW_AFTER = dt.timedelta(hours=4)
NEWS_MAX_DAYS_TO_RESOLUTION = 3


def _parse_game_start(raw: str | None) -> dt.datetime | None:
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw.replace(" ", "T"))
    except ValueError:
        return None


def _classify(market: dict, now: dt.datetime) -> str | None:
    if market["liquidity"] < MIN_LIQUIDITY:
        return None
    if market.get("sports_market_type"):
        start = _parse_game_start(market.get("game_start_time"))
        if start is None:
            return None
        if now - SPORTS_WINDOW_BEFORE <= start <= now + SPORTS_WINDOW_AFTER:
            return "sports"
        return None
    try:
        end = dt.date.fromisoformat(market["end_date"])
    except ValueError:
        return None
    if (end - now.date()).days < NEWS_MAX_DAYS_TO_RESOLUTION:
        return "news"
    return None


def select_target_markets(markets: list[dict], now: dt.datetime) -> list[dict]:
    """수집 대상 마켓 선정. 유동성 하한 미달, 스포츠 경기시간 범위 밖,
    뉴스 잔여기간 조건 미충족은 제외. 통과한 마켓엔 family 키를 추가한다."""
    out = []
    for m in markets:
        family = _classify(m, now)
        if family is None:
            continue
        out.append({**m, "family": family})
    return out


def build_meta_by_token(markets: list[dict]) -> dict[str, dict]:
    """select_target_markets() 출력에서 token_id -> 메타 매핑을 만든다."""
    meta: dict[str, dict] = {}
    for m in markets:
        yes_id, no_id = m["clob_token_ids"]
        for token_id, outcome in ((yes_id, "yes"), (no_id, "no")):
            if token_id:
                meta[token_id] = {
                    "condition_id": m["condition_id"],
                    "question": m["question"],
                    "family": m["family"],
                    "outcome": outcome,
                }
    return meta
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_tick_selector.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add research/polymarket_tick/__init__.py research/polymarket_tick/market_selector.py tests/test_polymarket_tick_selector.py
git commit -m "feat: add polymarket tick market selector"
```

---

## Task 3: `research/polymarket_tick/ws_collector.py` — WSS 클라이언트 + 틱 파싱

**Files:**
- Create: `research/polymarket_tick/ws_collector.py`
- Modify: `pyproject.toml` (dependencies에 `websockets` 선언 추가)
- Test: `tests/test_polymarket_tick_collector.py`

**Interfaces:**
- Consumes: Task 2의 `build_meta_by_token()`이 만드는 `dict[str, dict]` (키: token_id, 값: `{"condition_id", "question", "family", "outcome"}`).
- Produces:
  - `class PolymarketTickWSClient`: 생성자 `(base_url: str = MARKET_WS_URL, connect_fn: Callable[[str], Any] = websockets.connect)`. 메서드 `async def stream_ticks(self, asset_ids: list[str]) -> AsyncIterator[str]` — 구독 메시지 전송 후 수신 raw 문자열을 그대로 yield.
  - `parse_tick_message(raw: str, meta_by_token: dict[str, dict]) -> list[dict]` — raw WSS 메시지(JSON 문자열)를 저장용 틱 dict 리스트로 변환. 각 dict 스키마: `{"ts": str(ISO), "condition_id": str, "question": str, "family": str, "token_id": str, "outcome": "yes"|"no", "event_type": "book"|"price_change", "price": float|None, "size": float|None, "side": "BUY"|"SELL"|None, "best_bid": float|None, "best_ask": float|None}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_polymarket_tick_collector.py
import json

from research.polymarket_tick.ws_collector import PolymarketTickWSClient, parse_tick_message

META = {
    "y1": {"condition_id": "c1", "question": "q1", "family": "sports", "outcome": "yes"},
    "n1": {"condition_id": "c1", "question": "q1", "family": "sports", "outcome": "no"},
}


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


async def test_stream_ticks_sends_subscribe_message_and_yields_raw_messages():
    fake_connect = FakeConnect(["msg1", "msg2"])
    client = PolymarketTickWSClient(connect_fn=fake_connect)
    received = [msg async for msg in client.stream_ticks(["y1", "n1"])]
    assert received == ["msg1", "msg2"]
    assert fake_connect.called_with == client._base_url


def test_subscribe_message_has_expected_shape():
    client = PolymarketTickWSClient(connect_fn=FakeConnect([]))
    assert client._subscribe_message(["y1", "n1"]) == {"assets_ids": ["y1", "n1"], "type": "market"}


def test_parse_tick_message_book_event_computes_best_bid_ask():
    raw = json.dumps({
        "event_type": "book", "asset_id": "y1",
        "bids": [{"price": "0.40", "size": "100"}, {"price": "0.45", "size": "50"}],
        "asks": [{"price": "0.55", "size": "80"}, {"price": "0.50", "size": "60"}],
    })
    rows = parse_tick_message(raw, META)
    assert len(rows) == 1
    row = rows[0]
    assert row["token_id"] == "y1"
    assert row["outcome"] == "yes"
    assert row["condition_id"] == "c1"
    assert row["event_type"] == "book"
    assert row["best_bid"] == 0.45
    assert row["best_ask"] == 0.50
    assert row["price"] is None
    assert row["size"] is None
    assert row["side"] is None


def test_parse_tick_message_price_change_event_expands_array():
    raw = json.dumps({
        "event_type": "price_change", "market": "0xabc",
        "price_changes": [
            {"asset_id": "y1", "price": "0.52", "size": "10", "side": "BUY", "best_bid": "0.51", "best_ask": "0.53"},
            {"asset_id": "n1", "price": "0.48", "size": "10", "side": "SELL", "best_bid": "0.47", "best_ask": "0.49"},
        ],
    })
    rows = parse_tick_message(raw, META)
    assert len(rows) == 2
    assert rows[0]["token_id"] == "y1"
    assert rows[0]["outcome"] == "yes"
    assert rows[0]["price"] == 0.52
    assert rows[0]["side"] == "BUY"
    assert rows[1]["token_id"] == "n1"
    assert rows[1]["outcome"] == "no"


def test_parse_tick_message_unknown_token_id_dropped():
    raw = json.dumps({"event_type": "book", "asset_id": "unknown", "bids": [], "asks": []})
    assert parse_tick_message(raw, META) == []


def test_parse_tick_message_unknown_event_type_ignored():
    raw = json.dumps({"event_type": "tick_size_change", "asset_id": "y1"})
    assert parse_tick_message(raw, META) == []


def test_parse_tick_message_invalid_json_returns_empty_list():
    assert parse_tick_message("not json", META) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_tick_collector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.polymarket_tick.ws_collector'`

- [ ] **Step 3: Add `websockets` to pyproject.toml**

`pyproject.toml`의 `dependencies` 리스트(`"pandas>=2.0",` 다음 줄)에 추가:

```toml
    "pandas>=2.0",
    "websockets>=15.0",
]
```

- [ ] **Step 4: Write minimal implementation**

```python
# research/polymarket_tick/ws_collector.py
"""CLOB WSS market 채널 구독 + 틱 파싱 (I/O)."""
from __future__ import annotations

import datetime as dt
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets

MARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


class PolymarketTickWSClient:
    def __init__(
        self,
        base_url: str = MARKET_WS_URL,
        connect_fn: Callable[[str], Any] = websockets.connect,
    ) -> None:
        self._base_url = base_url
        self._connect_fn = connect_fn

    async def stream_ticks(self, asset_ids: list[str]) -> AsyncIterator[str]:
        async with self._connect_fn(self._base_url) as connection:
            await connection.send(json.dumps(self._subscribe_message(asset_ids)))
            async for message in connection:
                yield message

    def _subscribe_message(self, asset_ids: list[str]) -> dict:
        return {"assets_ids": asset_ids, "type": "market"}


def _to_float(v) -> float | None:
    return float(v) if v is not None else None


def _base_row(meta: dict, token_id: str, event_type: str) -> dict:
    return {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "condition_id": meta["condition_id"],
        "question": meta["question"],
        "family": meta["family"],
        "token_id": token_id,
        "outcome": meta["outcome"],
        "event_type": event_type,
        "price": None,
        "size": None,
        "side": None,
        "best_bid": None,
        "best_ask": None,
    }


def parse_tick_message(raw: str, meta_by_token: dict[str, dict]) -> list[dict]:
    """CLOB WSS raw 메시지(JSON 문자열) 1건을 저장용 틱 dict 리스트로 변환.
    book/price_change 외 event_type, 대상 목록에 없는 token_id는 버린다."""
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(msg, dict):
        return []

    event_type = msg.get("event_type")
    if event_type == "book":
        token_id = msg.get("asset_id")
        meta = meta_by_token.get(token_id)
        if meta is None:
            return []
        bids = msg.get("bids") or []
        asks = msg.get("asks") or []
        best_bid = max((float(b["price"]) for b in bids), default=None)
        best_ask = min((float(a["price"]) for a in asks), default=None)
        row = _base_row(meta, token_id, "book")
        row["best_bid"] = best_bid
        row["best_ask"] = best_ask
        return [row]

    if event_type == "price_change":
        rows = []
        for change in msg.get("price_changes") or []:
            token_id = change.get("asset_id")
            meta = meta_by_token.get(token_id)
            if meta is None:
                continue
            row = _base_row(meta, token_id, "price_change")
            row["price"] = _to_float(change.get("price"))
            row["size"] = _to_float(change.get("size"))
            row["side"] = change.get("side")
            row["best_bid"] = _to_float(change.get("best_bid"))
            row["best_ask"] = _to_float(change.get("best_ask"))
            rows.append(row)
        return rows

    return []
```

- [ ] **Step 5: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_tick_collector.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add research/polymarket_tick/ws_collector.py tests/test_polymarket_tick_collector.py pyproject.toml
git commit -m "feat: add polymarket tick WSS client and message parser"
```

---

## Task 4: `research/run_polymarket_tick_collect.py` — 무한루프 진입점

**Files:**
- Create: `research/run_polymarket_tick_collect.py`
- Test: `tests/test_run_polymarket_tick_collect.py`

**Interfaces:**
- Consumes:
  - `polymarket.client.get_markets(limit: int = 200) -> list[dict]`
  - `research.polymarket_tick.market_selector.select_target_markets(markets, now) -> list[dict]`
  - `research.polymarket_tick.market_selector.build_meta_by_token(markets) -> dict[str, dict]`
  - `research.polymarket_tick.ws_collector.PolymarketTickWSClient.stream_ticks(asset_ids) -> AsyncIterator[str]`
  - `research.polymarket_tick.ws_collector.parse_tick_message(raw, meta_by_token) -> list[dict]`
- Produces:
  - `append_ticks(ticks: list[dict]) -> None` — jsonl 날짜별 파일에 append.
  - `async def run_forever(*, client=None, get_markets_fn=None, append_fn=append_ticks, reselect_interval_sec: float = RESELECT_INTERVAL_SEC, max_cycles: int | None = None) -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_polymarket_tick_collect.py
import datetime as dt
import json
from unittest.mock import patch

import research.run_polymarket_tick_collect as runner


def _market(condition_id="c1", end_date="2026-07-10", clob_token_ids=("y1", "n1")):
    return {
        "condition_id": condition_id, "question": f"q-{condition_id}", "event_id": "e1",
        "event_title": "", "end_date": end_date, "volume": 1000.0, "liquidity": 10000.0,
        "yes_price": 0.5, "no_price": 0.5, "active": True, "closed": False,
        "accepting_orders": True, "clob_token_ids": clob_token_ids,
        "sports_market_type": None, "game_start_time": None,
    }


class FakeClient:
    def __init__(self, behaviors: list):
        self._behaviors = behaviors
        self.calls: list[list[str]] = []

    async def stream_ticks(self, asset_ids):
        self.calls.append(asset_ids)
        behavior = self._behaviors[len(self.calls) - 1]
        if isinstance(behavior, Exception):
            raise behavior
        for msg in behavior:
            yield msg


def test_append_ticks_writes_jsonl_to_dated_file(tmp_path):
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_ticks([{"token_id": "y1"}, {"token_id": "n1"}])
        path = tmp_path / f"{dt.date.today().isoformat()}.jsonl"
        lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["token_id"] == "y1"


def test_append_ticks_skips_write_when_empty(tmp_path):
    with patch.object(runner, "_DATA_DIR", tmp_path):
        runner.append_ticks([])
    assert list(tmp_path.iterdir()) == []


async def test_run_forever_skips_cycle_when_no_target_markets():
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_forever(
            get_markets_fn=lambda: [],
            client=FakeClient([]),
            append_fn=lambda ticks: None,
            max_cycles=1,
        )
    mock_sleep.assert_called_once_with(runner.RESELECT_INTERVAL_SEC)


async def test_run_forever_parses_and_appends_ticks_from_stream():
    raw_book = json.dumps({"event_type": "book", "asset_id": "y1", "bids": [{"price": "0.4", "size": "10"}], "asks": []})
    client = FakeClient([[raw_book]])
    appended = []
    await runner.run_forever(
        get_markets_fn=lambda: [_market()],
        client=client,
        append_fn=appended.append,
        max_cycles=1,
    )
    assert client.calls == [["y1", "n1"]]
    assert len(appended) == 1
    assert appended[0][0]["token_id"] == "y1"


async def test_run_forever_backs_off_and_doubles_delay_on_repeated_failure():
    client = FakeClient([ConnectionError("boom"), ConnectionError("boom")])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_forever(
            get_markets_fn=lambda: [_market()],
            client=client,
            append_fn=lambda ticks: None,
            max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY, runner.RECONNECT_BASE_DELAY * 2]


async def test_run_forever_resets_delay_after_success():
    client = FakeClient([ConnectionError("boom"), []])
    with patch("asyncio.sleep") as mock_sleep:
        await runner.run_forever(
            get_markets_fn=lambda: [_market()],
            client=client,
            append_fn=lambda ticks: None,
            max_cycles=2,
        )
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [runner.RECONNECT_BASE_DELAY]


async def test_run_forever_reuses_last_markets_when_reselect_fails():
    def flaky_get_markets():
        flaky_get_markets.calls += 1
        if flaky_get_markets.calls == 1:
            return [_market()]
        raise RuntimeError("gamma down")
    flaky_get_markets.calls = 0

    client = FakeClient([[], []])
    appended = []
    await runner.run_forever(
        get_markets_fn=flaky_get_markets,
        client=client,
        append_fn=appended.append,
        max_cycles=2,
    )
    assert client.calls == [["y1", "n1"], ["y1", "n1"]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_tick_collect.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'research.run_polymarket_tick_collect'`

- [ ] **Step 3: Write minimal implementation**

```python
# research/run_polymarket_tick_collect.py
"""폴리마켓 실시간 틱 수집기 진입점 — tmux로 상시 실행.

5분마다 대상 마켓을 재선정해 WSS를 재구독한다. 내부 상태 없음 —
재시작해도 market_selector로 매번 새로 계산되므로 유실 구간만 생기고 꼬이지 않는다.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from pathlib import Path

from polymarket.client import get_markets
from research.polymarket_tick.market_selector import build_meta_by_token, select_target_markets
from research.polymarket_tick.ws_collector import PolymarketTickWSClient, parse_tick_message

_DATA_DIR = Path("research/data/polymarket_tick")

RESELECT_INTERVAL_SEC = 300.0
RECONNECT_BASE_DELAY = 2.0
RECONNECT_MAX_DELAY = 60.0


def append_ticks(ticks: list[dict]) -> None:
    if not ticks:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{dt.date.today().isoformat()}.jsonl"
    with path.open("a") as f:
        for t in ticks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


def _default_get_markets() -> list[dict]:
    return get_markets(limit=300)


async def run_forever(
    *,
    client: PolymarketTickWSClient | None = None,
    get_markets_fn=None,
    append_fn=append_ticks,
    reselect_interval_sec: float = RESELECT_INTERVAL_SEC,
    max_cycles: int | None = None,
) -> None:
    client = client or PolymarketTickWSClient()
    get_markets_fn = get_markets_fn or _default_get_markets
    cycle = 0
    delay = RECONNECT_BASE_DELAY
    last_meta_by_token: dict[str, dict] | None = None
    while max_cycles is None or cycle < max_cycles:
        now = dt.datetime.now(dt.timezone.utc)
        try:
            markets = select_target_markets(get_markets_fn(), now=now)
            meta_by_token = build_meta_by_token(markets)
            last_meta_by_token = meta_by_token
        except Exception:
            # Gamma REST 재선정 실패 → 기존 구독(직전 사이클의 meta) 유지, 다음 주기에 재시도
            meta_by_token = last_meta_by_token or {}
        if not meta_by_token:
            await asyncio.sleep(reselect_interval_sec)
            cycle += 1
            continue
        asset_ids = list(meta_by_token.keys())
        try:
            async with asyncio.timeout(reselect_interval_sec):
                async for raw in client.stream_ticks(asset_ids):
                    append_fn(parse_tick_message(raw, meta_by_token))
            delay = RECONNECT_BASE_DELAY
        except TimeoutError:
            delay = RECONNECT_BASE_DELAY
        except Exception:
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)
        cycle += 1


if __name__ == "__main__":
    asyncio.run(run_forever())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_run_polymarket_tick_collect.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Run full test suite to check no regressions**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: same pre-existing failures as before this plan (`test_auth.py` ×3~4, `test_backtest_happy_path`), no new failures.

- [ ] **Step 6: Commit**

```bash
git add research/run_polymarket_tick_collect.py tests/test_run_polymarket_tick_collect.py
git commit -m "feat: add polymarket tick collector runner loop"
```

---

## Post-Implementation Note

이 플랜 완료 후 `tmux`로 `run_polymarket_tick_collect.py`를 상시 실행해 데이터 축적 시작. 모멘텀/오버리액션 가설 검증(random baseline p-value + walk-forward + cost-robust)은 데이터가 몇 주 쌓인 뒤 별도 spec→plan 사이클로 진행 — 이 플랜 스코프 밖.
