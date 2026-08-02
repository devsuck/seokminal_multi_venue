# Polymarket sharp_wallet Paper 라이브 집행 봇 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 검증된(BH-FDR+walk-forward) Polymarket sharp_wallet 컨버전스 신호 중 라이브 실행 가능한 그룹만 골라 paper 포지션을 자동 진입/청산하는 서버측 봇을 만든다.

**Architecture:** 기존 `api_server/polymarket_bot.py`(다각화 봇) 패턴 그대로 재사용(JSON 설정 + JSONL 로그 + FastAPI 라우터 + 백그라운드 `_loop()`). 다른 점은 신호 소스(`build_convergence_count` 롤링 재사용)와 청산 방식(hold-to-resolution 대신 horizon 마크아웃), 비용모델(고정 200bps 대신 CLOB 실측 스프레드).

**Tech Stack:** Python, FastAPI, pandas(`research/hypotheses/polymarket_sharp_wallet.py` 재사용), requests, pytest.

## Global Constraints

이 값들은 `docs/superpowers/specs/2026-08-02-polymarket-sharp-wallet-execution-design.md`에서 그대로 가져왔다. 모든 태스크에 암묵적으로 적용된다.

- **v1 진입 허용 그룹은 딱 둘뿐:** `convergence_bucket=1`(horizon 30/120/300s 전부), `convergence_bucket=3`(horizon 300s만). `bucket=2`와 score-tercile(`low`/`mid`/`high`)은 전부 v1 진입 금지 — score의 `liquidity` 컴포넌트가 미래 300s 윈도우라 라이브 진입판정이 청산시점보다 늦게 확정되는 순서모순 때문(스펙 §진입신호).
- **그룹별 병렬 포지션:** 같은 anchor가 여러 horizon을 동시에 충족하면(예: bucket1 anchor → 30/120/300s) 그 수만큼 독립 paper 포지션을 각각 연다. 그룹별 서브버짓 없음 — flat `trade_size_usd`, 전역 `max_concurrent_positions` 캡 하나로만 노출 제한.
- **청산은 horizon 마크아웃:** `exit_at = entry_ts + horizon_s`, 그 시점 시장가로 강제청산. 손익식은 검증기(`research/run_polymarket_sharp_wallet_validate.py::_score_horizons`)와 동일하게 `pnl = direction * (exit_price - entry_price) * shares - cost_usd`.
- **비용모델은 CLOB 실측 스프레드로 대체:** 검증 당시 `polymarket_effective_cost_bps()`는 고정 `POLYMARKET_SPREAD_BPS=200.0`("미검증 근사치") 하나만 썼다. 라이브 봇은 포지션 진입/청산 시점 CLOB 오더북 1회 조회로 실측 `spread_bps`를 구해 같은 함수에 넘긴다. 실측치가 없으면(조회 실패/빈 오더북/역전) 기본값(인자 생략)으로 폴백. **진입 게이트(어느 그룹이 유효한가)는 건드리지 않는다** — 이미 통과한 walk-forward 검증을 실시간 신호로 무효화하면 안 됨.
- **Positions API는 로그 전용:** `data-api.polymarket.com/positions`는 통계검증 안 된 신호라 진입/사이징/청산 게이트 어디에도 관여 안 함. 실패해도 포지션 진입/청산 로직 자체는 안 막힘.
- **저장공간/RAM 제약:** CLOB/positions 호출은 포지션 이벤트당 1회(상시 폴링 없음). 신규 상시 프로세스/tmux 세션 없음 — 기존 봇 `_loop()` 패턴에 얹는다. 신규 대용량 캐시 없음 — 전부 기존 JSONL 이벤트 로그에 필드 추가.
- **Out of Scope:** 실집행(paper만), 그룹별 서브버짓, positions API 게이팅, CLOB 상시수집, score-tercile v1 실집행.

---

## Task 1: CLOB 오더북 읽기전용 클라이언트

**Files:**
- Create: `polymarket/clob_client.py`
- Test: `tests/test_polymarket_clob_client.py`

**Interfaces:**
- Consumes: `research.net_utils.call_with_hard_timeout(fn: Callable[[], T], timeout_s: float) -> T` (기존 유틸, DNS/connect 행 방어).
- Produces: `get_order_book(token_id: str) -> dict | None` (`{"best_bid": float, "best_ask": float}` 또는 실패 시 `None`). `spread_bps_from_book(book: dict | None) -> float | None` (Task 3/4가 이 두 함수를 씀).

- [ ] **Step 1: Write the failing test**

`tests/test_polymarket_clob_client.py`:
```python
"""Polymarket CLOB 오더북 읽기전용 클라이언트 테스트."""
from unittest.mock import patch

import pytest

from polymarket import clob_client


def _book(bids, asks):
    return {"bids": bids, "asks": asks}


def test_get_order_book_returns_best_bid_ask():
    raw = _book(
        [{"price": "0.48", "size": "100"}, {"price": "0.50", "size": "50"}],
        [{"price": "0.53", "size": "80"}, {"price": "0.55", "size": "20"}],
    )
    with patch.object(clob_client, "_get", return_value=raw):
        book = clob_client.get_order_book("tok1")
    assert book == {"best_bid": 0.50, "best_ask": 0.53}


def test_get_order_book_empty_book_returns_none():
    with patch.object(clob_client, "_get", return_value=_book([], [])):
        assert clob_client.get_order_book("tok1") is None


def test_get_order_book_request_failure_returns_none():
    with patch.object(clob_client, "_get", side_effect=Exception("boom")):
        assert clob_client.get_order_book("tok1") is None


def test_spread_bps_from_book():
    book = {"best_bid": 0.50, "best_ask": 0.53}
    assert clob_client.spread_bps_from_book(book) == pytest.approx((0.53 - 0.50) / 0.515 * 10_000.0)


def test_spread_bps_from_book_none_input_returns_none():
    assert clob_client.spread_bps_from_book(None) is None


def test_spread_bps_from_book_inverted_market_returns_none():
    assert clob_client.spread_bps_from_book({"best_bid": 0.6, "best_ask": 0.5}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_clob_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'polymarket.clob_client'`

- [ ] **Step 3: Write minimal implementation**

`polymarket/clob_client.py`:
```python
"""Polymarket CLOB 오더북 읽기전용 클라이언트 — 공개 endpoint, 인증 불필요.

sharp_wallet 집행봇(api_server/polymarket_sharp_wallet_bot.py) paper 비용모델
(스프레드 실측)에만 쓴다. 실거래 주문은 안 함(polymarket/client.py와 동일
전제) — 상시 폴링/저장 없음, 포지션 진입/청산 시점 1회성 조회만.
docs/superpowers/specs/2026-08-02-polymarket-sharp-wallet-execution-design.md
"""
from __future__ import annotations

import requests

from research.net_utils import call_with_hard_timeout

_BASE = "https://clob.polymarket.com"
_TIMEOUT = 10
_HARD_TIMEOUT = _TIMEOUT + 5.0  # requests timeout이 못 막는 DNS/connect 단계 방어


def _get(token_id: str) -> dict:
    return call_with_hard_timeout(
        lambda: requests.get(f"{_BASE}/book", params={"token_id": token_id}, timeout=_TIMEOUT),
        _HARD_TIMEOUT,
    ).json()


def get_order_book(token_id: str) -> dict | None:
    """{"best_bid": float, "best_ask": float} 반환. 조회 실패/빈 오더북이면 None."""
    try:
        data = _get(token_id)
        bids = data.get("bids") or []
        asks = data.get("asks") or []
        if not bids or not asks:
            return None
        best_bid = max(float(b["price"]) for b in bids)
        best_ask = min(float(a["price"]) for a in asks)
        return {"best_bid": best_bid, "best_ask": best_ask}
    except Exception:
        return None


def spread_bps_from_book(book: dict | None) -> float | None:
    """(ask-bid)/mid*10000. book 없거나 mid<=0이거나 역전(ask<bid, 이상치)이면 None."""
    if not book:
        return None
    bid, ask = book["best_bid"], book["best_ask"]
    mid = (bid + ask) / 2.0
    if mid <= 0 or ask < bid:
        return None
    return (ask - bid) / mid * 10_000.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_clob_client.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add polymarket/clob_client.py tests/test_polymarket_clob_client.py
git commit -m "feat: CLOB 오더북 읽기전용 클라이언트 추가"
```

---

## Task 2: 지갑별 포지션 조회 클라이언트 (로그 전용)

**Files:**
- Create: `research/polymarket_sharp_wallet/positions.py`
- Test: `tests/test_polymarket_sharp_wallet_positions.py`

**Interfaces:**
- Consumes: 없음(단순 requests 호출, `research/polymarket_sharp_wallet/leaderboard.py`와 동일한 무인증 데이터API 패턴).
- Produces: `fetch_wallet_positions(wallet: str) -> list[dict]` (Task 3의 `_scan_and_enter`가 anchor의 `proxy_wallet`으로 호출).

- [ ] **Step 1: Write the failing test**

`tests/test_polymarket_sharp_wallet_positions.py`:
```python
from unittest.mock import Mock, patch

import research.polymarket_sharp_wallet.positions as pos


def test_fetch_wallet_positions_returns_list():
    fake_resp = Mock()
    fake_resp.json.return_value = [{"conditionId": "c1", "size": 10.0, "avgPrice": 0.5}]
    fake_resp.raise_for_status.return_value = None
    with patch.object(pos.requests, "get", return_value=fake_resp) as mock_get:
        result = pos.fetch_wallet_positions("0xabc")
    assert result == [{"conditionId": "c1", "size": 10.0, "avgPrice": 0.5}]
    args, kwargs = mock_get.call_args
    assert args[0] == "https://data-api.polymarket.com/positions"
    assert kwargs["params"] == {"user": "0xabc"}


def test_fetch_wallet_positions_non_list_response_returns_empty():
    fake_resp = Mock()
    fake_resp.json.return_value = {"error": "bad"}
    fake_resp.raise_for_status.return_value = None
    with patch.object(pos.requests, "get", return_value=fake_resp):
        assert pos.fetch_wallet_positions("0xabc") == []


def test_fetch_wallet_positions_request_failure_returns_empty():
    with patch.object(pos.requests, "get", side_effect=Exception("boom")):
        assert pos.fetch_wallet_positions("0xabc") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_sharp_wallet_positions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research.polymarket_sharp_wallet.positions'`

- [ ] **Step 3: Write minimal implementation**

`research/polymarket_sharp_wallet/positions.py`:
```python
"""Polymarket 지갑별 현재 포지션 조회 — data-api.polymarket.com/positions, 무인증.

sharp_wallet 집행봇이 포지션 진입 시점에 그 anchor를 낸 지갑의 순보유를
참고 필드로만 기록한다(게이트/사이징에 미반영 — 통계검증 안 된 신호이므로).
leaderboard.py와 동일하게 단순 requests, 재시도/하드타임아웃 없음 — 실패해도
포지션 진입 자체는 안 막는 참고필드라 호출부에서 통째로 흡수한다.
docs/superpowers/specs/2026-08-02-polymarket-sharp-wallet-execution-design.md
"""
from __future__ import annotations

import requests

POSITIONS_URL = "https://data-api.polymarket.com/positions"
_TIMEOUT = 15


def fetch_wallet_positions(wallet: str) -> list[dict]:
    """실패/비정상 응답이면 빈 리스트."""
    try:
        r = requests.get(POSITIONS_URL, params={"user": wallet}, timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_sharp_wallet_positions.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add research/polymarket_sharp_wallet/positions.py tests/test_polymarket_sharp_wallet_positions.py
git commit -m "feat: 지갑별 포지션 조회 클라이언트 추가(로그 전용)"
```

---

## Task 3: 봇 스캐폴딩 + 진입 로직 (`_scan_and_enter`)

**Files:**
- Create: `api_server/polymarket_sharp_wallet_bot.py`
- Test: `tests/test_polymarket_sharp_wallet_bot.py`

**Interfaces:**
- Consumes:
  - `polymarket.client.get_market(condition_id: str) -> dict | None` (기존, `yes_price`/`no_price`/`active`/`closed`/`clob_token_ids` 포함).
  - `polymarket.clob_client.get_order_book(token_id: str) -> dict | None`, `spread_bps_from_book(book) -> float | None` (Task 1).
  - `research.polymarket_sharp_wallet.positions.fetch_wallet_positions(wallet: str) -> list[dict]` (Task 2).
  - `research.hypotheses.polymarket_sharp_wallet.load_sharp_wallet_trades(dates: list[str]) -> pd.DataFrame`, `build_convergence_count(trades: pd.DataFrame) -> pd.DataFrame`(반환 컬럼: `ts, condition_id, side, direction, notional_usd, proxy_wallet, convergence_count, convergence_bucket`) — 기존, 그대로 재사용.
- Produces: 모듈 전역 `_DEFAULT: dict`, 함수 `_load() -> dict`, `_save(cfg: dict) -> None`, `_log_event(ev: dict) -> None`, `_recent_log(n: int = 40) -> list[dict]`, `_spread_bps_for_market(m: dict) -> float | None`, `_wallet_snapshot_safe(wallet: str | None) -> list[dict]`, `_scan_and_enter(cfg: dict) -> int` — Task 4/5가 이 전부를 씀.

**설계 메모(구현자가 알아야 할 것):** anchor 하나가 bucket1이면 30/120/300s 세 포지션을 동시에 여는데, 셋 다 같은 순간(같은 `condition_id`, 같은 `entry_ts`)이라 CLOB 스프레드와 positions API 조회는 anchor당 딱 1번만 하고 그 결과를 세 포지션에 공유한다(스펙의 "저장공간/RAM 제약" — 동일 데이터를 3번 조회하는 건 낭비). 청산(Task 4)은 각 포지션마다 실제로 다른 시각에 일어나므로 거기서는 포지션마다 개별 조회한다.

- [ ] **Step 1: Write the failing test**

`tests/test_polymarket_sharp_wallet_bot.py`:
```python
"""sharp_wallet 컨버전스 신호 paper 집행봇 — 진입 로직 테스트."""
from unittest.mock import patch

import pandas as pd

from api_server import polymarket_sharp_wallet_bot as bot


def _cfg(**over):
    return {**bot._DEFAULT, "enabled": True, "positions": [], **over}


def _market(condition_id="c1", yes=0.5, no=0.5, active=True, closed=False, clob_token_ids=("t-yes", "t-no")):
    return {"condition_id": condition_id, "yes_price": yes, "no_price": no,
            "active": active, "closed": closed, "clob_token_ids": clob_token_ids}


def _anchors(rows):
    cols = ["ts", "condition_id", "side", "direction", "notional_usd",
            "proxy_wallet", "convergence_count", "convergence_bucket"]
    return pd.DataFrame(rows, columns=cols)


def _anchor_row(ts=100.0, cid="c1", bucket=1, direction=1.0, wallet="0xsharp"):
    return {"ts": ts, "condition_id": cid, "side": "BUY", "direction": direction,
            "notional_usd": 500.0, "proxy_wallet": wallet,
            "convergence_count": bucket, "convergence_bucket": bucket}


def test_scan_and_enter_bucket1_opens_three_parallel_positions():
    cfg = _cfg(trade_size_usd=10.0, budget=100.0, max_concurrent_positions=20)
    anchors = _anchors([_anchor_row(ts=100.0, bucket=1)])
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market", return_value=_market(yes=0.6)), \
         patch.object(bot, "_spread_bps_for_market", return_value=150.0), \
         patch.object(bot, "_wallet_snapshot_safe", return_value=[{"conditionId": "c1"}]), \
         patch.object(bot, "_log_event"):
        entered = bot._scan_and_enter(cfg)
    assert entered == 3
    horizons = sorted(p["horizon_s"] for p in cfg["positions"])
    assert horizons == [30, 120, 300]
    for p in cfg["positions"]:
        assert p["condition_id"] == "c1"
        assert p["convergence_bucket"] == 1
        assert p["entry_price"] == 0.6
        assert p["exit_at"] == 100.0 + p["horizon_s"]
        assert p["usd"] == 10.0
        assert p["entry_spread_bps"] == 150.0
        assert p["wallet_positions_snapshot"] == [{"conditionId": "c1"}]
    assert cfg["spent"] == 30.0
    assert cfg["last_anchor_ts"] == 100.0


def test_scan_and_enter_bucket3_opens_only_300s():
    cfg = _cfg(trade_size_usd=10.0, budget=100.0)
    anchors = _anchors([_anchor_row(ts=100.0, bucket=3)])
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market", return_value=_market()), \
         patch.object(bot, "_spread_bps_for_market", return_value=None), \
         patch.object(bot, "_wallet_snapshot_safe", return_value=[]), \
         patch.object(bot, "_log_event"):
        entered = bot._scan_and_enter(cfg)
    assert entered == 1
    assert cfg["positions"][0]["horizon_s"] == 300


def test_scan_and_enter_bucket2_skips_entirely():
    cfg = _cfg()
    anchors = _anchors([_anchor_row(ts=100.0, bucket=2)])
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market") as mock_market:
        entered = bot._scan_and_enter(cfg)
    assert entered == 0
    assert cfg["positions"] == []
    mock_market.assert_not_called()  # bucket2는 시장조회까지 갈 필요 없이 걸러짐
    assert cfg["last_anchor_ts"] == 100.0  # 그래도 재처리 방지용으로 진행은 시킴


def test_scan_and_enter_dedups_already_processed_anchors():
    cfg = _cfg(last_anchor_ts=100.0)
    anchors = _anchors([_anchor_row(ts=100.0, bucket=1), _anchor_row(ts=50.0, bucket=1)])
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market") as mock_market:
        entered = bot._scan_and_enter(cfg)
    assert entered == 0
    mock_market.assert_not_called()


def test_scan_and_enter_respects_max_concurrent_positions():
    cfg = _cfg(trade_size_usd=10.0, budget=1000.0, max_concurrent_positions=2)
    anchors = _anchors([_anchor_row(ts=100.0, bucket=1)])  # bucket1 = 3개 시도
    with patch.object(bot, "load_sharp_wallet_trades", return_value=pd.DataFrame()), \
         patch.object(bot, "build_convergence_count", return_value=anchors), \
         patch.object(bot, "get_market", return_value=_market()), \
         patch.object(bot, "_spread_bps_for_market", return_value=None), \
         patch.object(bot, "_wallet_snapshot_safe", return_value=[]), \
         patch.object(bot, "_log_event"):
        entered = bot._scan_and_enter(cfg)
    assert entered == 2  # 캡에서 멈춤


def test_scan_and_enter_no_slots_returns_zero_without_loading_trades():
    cfg = _cfg(max_concurrent_positions=1, positions=[{"condition_id": "x"}])
    with patch.object(bot, "load_sharp_wallet_trades") as mock_load:
        entered = bot._scan_and_enter(cfg)
    assert entered == 0
    mock_load.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_sharp_wallet_bot.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api_server.polymarket_sharp_wallet_bot'`

- [ ] **Step 3: Write minimal implementation**

`api_server/polymarket_sharp_wallet_bot.py`:
```python
"""Polymarket sharp_wallet 컨버전스 신호 paper 라이브 집행 봇.

검증 통과(BH-FDR+walk-forward) 그룹 중 라이브 실행 가능한 것만 진입 —
bucket1(30/120/300s), bucket3(300s). score-tercile(mid/high)은 score의
liquidity 컴포넌트가 미래 300s 윈도우라 라이브 진입판정이 청산시점보다
늦게 확정되는 순서모순이라 v1 제외. 청산은 hold-to-resolution이 아니라
entry_ts+horizon_s 시점 마크아웃. 비용은 검증 당시 고정 200bps 대신 CLOB
실측 스프레드로 대체(진입 게이트는 안 건드림).

api_server/polymarket_bot.py(다각화 봇)와 동일한 JSON 설정 + JSONL 로그 패턴.
docs/superpowers/specs/2026-08-02-polymarket-sharp-wallet-execution-design.md
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
import time as _time
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from polymarket.client import get_market
from polymarket.clob_client import get_order_book, spread_bps_from_book
from research.hypotheses.polymarket_sharp_wallet import build_convergence_count, load_sharp_wallet_trades
from research.polymarket_sharp_wallet.positions import fetch_wallet_positions
from research.validation.cost_model import polymarket_effective_cost_bps

router = APIRouter(prefix="/polymarket-sharp-wallet-bot", tags=["polymarket-sharp-wallet-bot"])

_DATA = Path(os.environ.get("POLYMARKET_SHARP_WALLET_BOT_DIR", "data"))
_CFG = _DATA / "polymarket_sharp_wallet_bot.json"
_LOG = _DATA / "polymarket_sharp_wallet_bot_log.jsonl"

# v1 라이브 실행 허용 그룹 — bucket2/score-tercile(low/mid/high) 전부 제외
# (스펙 §진입신호 — score의 liquidity 컴포넌트가 미래 300s 윈도우라 순서모순).
_HORIZONS_BY_BUCKET = {1: (30, 120, 300), 3: (300,)}

_DEFAULT = {
    "enabled": False, "interval_sec": 15,
    "budget": 300.0, "trade_size_usd": 15.0, "max_concurrent_positions": 30,
    "spent": 0.0, "realized_pnl": 0.0,
    "positions": [],  # [{condition_id, convergence_bucket, horizon_s, direction, entry_price,
                       #   entry_ts, exit_at, usd, shares, entry_spread_bps, wallet_positions_snapshot}]
    "last_anchor_ts": 0.0,
    "last_run": None,
}


def _load() -> dict:
    try:
        return {**_DEFAULT, **json.loads(_CFG.read_text())}
    except Exception:
        return dict(_DEFAULT)


def _save(cfg: dict) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    _CFG.write_text(json.dumps(cfg))


def _log_event(ev: dict) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    ev["ts"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    with _LOG.open("a") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def _recent_log(n: int = 40) -> list[dict]:
    try:
        lines = _LOG.read_text().strip().splitlines()
        return [json.loads(x) for x in lines[-n:]][::-1]
    except Exception:
        return []


def _spread_bps_for_market(m: dict) -> float | None:
    token_ids = m.get("clob_token_ids")
    if not token_ids or not token_ids[0]:
        return None
    book = get_order_book(token_ids[0])
    return spread_bps_from_book(book) if book else None


def _wallet_snapshot_safe(wallet: str | None) -> list[dict]:
    if not wallet:
        return []
    return fetch_wallet_positions(wallet)


def _scan_and_enter(cfg: dict) -> int:
    remaining_slots = cfg["max_concurrent_positions"] - len(cfg.get("positions", []))
    remaining_budget = cfg["budget"] - cfg.get("spent", 0.0)
    if remaining_slots <= 0 or remaining_budget < cfg["trade_size_usd"]:
        return 0

    today = _dt.datetime.now(_dt.timezone.utc).date()
    yesterday = today - _dt.timedelta(days=1)
    try:
        trades = load_sharp_wallet_trades([yesterday.isoformat(), today.isoformat()])
        anchors = build_convergence_count(trades)
    except Exception as e:  # noqa: BLE001
        _log_event({"kind": "scan_fail", "msg": str(e)[:100]})
        return 0
    if anchors.empty:
        return 0

    last_ts = cfg.get("last_anchor_ts", 0.0)
    new_anchors = anchors[anchors["ts"] > last_ts].sort_values("ts")
    if new_anchors.empty:
        return 0

    entered = 0
    max_ts_seen = last_ts
    for _, row in new_anchors.iterrows():
        max_ts_seen = max(max_ts_seen, float(row["ts"]))
        if entered >= remaining_slots or remaining_budget < cfg["trade_size_usd"]:
            continue  # 슬롯/예산 소진 — 그래도 last_anchor_ts는 갱신해 재처리 방지
        horizons = _HORIZONS_BY_BUCKET.get(int(row["convergence_bucket"]))
        if not horizons:
            continue  # bucket2/미분류 — v1 진입 금지 그룹
        m = get_market(row["condition_id"])
        if m is None or not m["active"] or m["closed"]:
            continue
        entry_price = m["yes_price"]
        if entry_price <= 0:
            continue

        # anchor당 1회만 조회(3개 horizon이 같은 순간·같은 마켓이라 공유) — 저장공간/RAM 제약.
        entry_spread_bps = _spread_bps_for_market(m)
        wallet_snapshot = _wallet_snapshot_safe(row["proxy_wallet"])

        for h in horizons:
            if entered >= remaining_slots or remaining_budget < cfg["trade_size_usd"]:
                break
            usd = min(cfg["trade_size_usd"], remaining_budget)
            shares = round(usd / entry_price, 4)
            pos = {
                "condition_id": row["condition_id"],
                "convergence_bucket": int(row["convergence_bucket"]),
                "horizon_s": h, "direction": float(row["direction"]),
                "entry_price": entry_price, "entry_ts": float(row["ts"]),
                "exit_at": float(row["ts"]) + h,
                "usd": usd, "shares": shares,
                "entry_spread_bps": entry_spread_bps,
                "wallet_positions_snapshot": wallet_snapshot,
            }
            cfg.setdefault("positions", []).append(pos)
            cfg["spent"] = round(cfg.get("spent", 0.0) + usd, 2)
            remaining_budget -= usd
            _log_event({"kind": "entry", **pos})
            entered += 1

    cfg["last_anchor_ts"] = max_ts_seen
    return entered
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_sharp_wallet_bot.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add api_server/polymarket_sharp_wallet_bot.py tests/test_polymarket_sharp_wallet_bot.py
git commit -m "feat: sharp_wallet 집행봇 스캐폴딩 + 진입로직(bucket1/3 그룹별 병렬 포지션)"
```

---

## Task 4: 청산 로직 (`_process_exits`) — horizon 마크아웃

**Files:**
- Modify: `api_server/polymarket_sharp_wallet_bot.py` (Task 3 파일에 함수 추가)
- Test: `tests/test_polymarket_sharp_wallet_bot.py` (Task 3 파일에 테스트 추가)

**Interfaces:**
- Consumes: Task 3의 `get_market`, `_spread_bps_for_market`, `_log_event`. `research.validation.cost_model.polymarket_effective_cost_bps(spread_bps: float = 200.0) -> float`(기존).
- Produces: `_process_exits(cfg: dict) -> int` (Task 5의 `tick()`이 씀).

**손익식 근거:** 검증기(`research/run_polymarket_sharp_wallet_validate.py::_score_horizons`)의 `cost = (abs(entry_px)+abs(exit_px)) * TRADE_SIZE * COST_BPS / 10_000.0`, `pnl = direction*(exit_px-entry_px)*TRADE_SIZE - cost`를 그대로 따르되 `TRADE_SIZE=1.0` 고정 대신 실제 `shares`를 쓴다. `COST_BPS`는 검증기처럼 전역 상수 하나가 아니라 진입/청산 두 스프레드 실측치 평균을 `polymarket_effective_cost_bps(spread_bps=...)`에 넘겨 포지션마다 계산한다. 둘 다 없으면(조회 실패) 인자 생략 — 함수 기본값(200bps)으로 자동 폴백.

- [ ] **Step 1: Write the failing test**

`tests/test_polymarket_sharp_wallet_bot.py`에 추가:
```python
def _pos(**over):
    base = {"condition_id": "c1", "convergence_bucket": 1, "horizon_s": 30,
            "direction": 1.0, "entry_price": 0.50, "entry_ts": 100.0, "exit_at": 130.0,
            "usd": 10.0, "shares": 20.0, "entry_spread_bps": 100.0,
            "wallet_positions_snapshot": []}
    base.update(over)
    return base


def test_process_exits_marks_out_at_exit_at_with_real_spread():
    cfg = _cfg()
    cfg["positions"] = [_pos()]
    cfg["spent"] = 10.0
    with patch.object(bot, "_time") as mock_time, \
         patch.object(bot, "get_market", return_value=_market(yes=0.60)), \
         patch.object(bot, "_spread_bps_for_market", return_value=120.0), \
         patch.object(bot, "_log_event"):
        mock_time.time.return_value = 200.0  # exit_at(130) 지남
        closed = bot._process_exits(cfg)
    assert closed == 1
    assert cfg["positions"] == []
    assert cfg["spent"] == 0.0
    # cost_bps = polymarket_effective_cost_bps(spread_bps=(100+120)/2) = 0 + 110/2 = 55
    expected_cost = (0.50 + 0.60) * 20.0 * 55.0 / 10_000.0
    expected_pnl = round(1.0 * (0.60 - 0.50) * 20.0 - expected_cost, 2)
    assert cfg["realized_pnl"] == expected_pnl


def test_process_exits_keeps_position_before_exit_at():
    cfg = _cfg()
    cfg["positions"] = [_pos(exit_at=130.0)]
    with patch.object(bot, "_time") as mock_time:
        mock_time.time.return_value = 129.0
        closed = bot._process_exits(cfg)
    assert closed == 0
    assert len(cfg["positions"]) == 1


def test_process_exits_retries_on_market_fetch_failure():
    cfg = _cfg()
    cfg["positions"] = [_pos(exit_at=130.0)]
    with patch.object(bot, "_time") as mock_time, \
         patch.object(bot, "get_market", return_value=None):
        mock_time.time.return_value = 200.0
        closed = bot._process_exits(cfg)
    assert closed == 0
    assert len(cfg["positions"]) == 1  # 다음 tick 재시도


def test_process_exits_falls_back_to_default_cost_when_no_spread_data():
    cfg = _cfg()
    cfg["positions"] = [_pos(entry_spread_bps=None)]
    cfg["spent"] = 10.0
    with patch.object(bot, "_time") as mock_time, \
         patch.object(bot, "get_market", return_value=_market(yes=0.55)), \
         patch.object(bot, "_spread_bps_for_market", return_value=None), \
         patch.object(bot, "_log_event"):
        mock_time.time.return_value = 200.0
        closed = bot._process_exits(cfg)
    assert closed == 1
    # 실측 스프레드 전무 -> polymarket_effective_cost_bps() 기본값(200bps 절반=100)
    from research.validation.cost_model import polymarket_effective_cost_bps
    expected_cost = (0.50 + 0.55) * 20.0 * polymarket_effective_cost_bps() / 10_000.0
    expected_pnl = round(1.0 * (0.55 - 0.50) * 20.0 - expected_cost, 2)
    assert cfg["realized_pnl"] == expected_pnl
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_sharp_wallet_bot.py -v -k process_exits`
Expected: FAIL with `AttributeError: module 'api_server.polymarket_sharp_wallet_bot' has no attribute '_process_exits'`

- [ ] **Step 3: Write minimal implementation**

`api_server/polymarket_sharp_wallet_bot.py`에 (`_scan_and_enter` 함수 뒤에) 추가:
```python
def _process_exits(cfg: dict) -> int:
    """entry_ts + horizon_s 지난 포지션을 그 순간 시장가로 강제청산."""
    now = _time.time()
    keep: list[dict] = []
    closed = 0
    for pos in cfg.get("positions", []):
        if now < pos["exit_at"]:
            keep.append(pos)
            continue
        m = get_market(pos["condition_id"])
        if m is None:
            keep.append(pos)  # 조회 실패 — 다음 tick 재시도
            continue
        exit_price = m["yes_price"]
        exit_spread_bps = _spread_bps_for_market(m)
        spreads = [s for s in (pos.get("entry_spread_bps"), exit_spread_bps) if s is not None]
        cost_bps = (polymarket_effective_cost_bps(spread_bps=sum(spreads) / len(spreads))
                    if spreads else polymarket_effective_cost_bps())
        cost_usd = (pos["entry_price"] + exit_price) * pos["shares"] * cost_bps / 10_000.0
        pnl = round(pos["direction"] * (exit_price - pos["entry_price"]) * pos["shares"] - cost_usd, 2)
        cfg["spent"] = round(max(cfg.get("spent", 0.0) - pos["usd"], 0.0), 2)
        cfg["realized_pnl"] = round(cfg.get("realized_pnl", 0.0) + pnl, 2)
        _log_event({"kind": "exit", "condition_id": pos["condition_id"],
                     "convergence_bucket": pos["convergence_bucket"], "horizon_s": pos["horizon_s"],
                     "entry_price": pos["entry_price"], "exit_price": exit_price,
                     "cost_bps": round(cost_bps, 2), "pnl": pnl})
        closed += 1
    cfg["positions"] = keep
    return closed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_sharp_wallet_bot.py -v`
Expected: PASS (10 tests — Task 3의 6개 + 이번 4개)

- [ ] **Step 5: Commit**

```bash
git add api_server/polymarket_sharp_wallet_bot.py tests/test_polymarket_sharp_wallet_bot.py
git commit -m "feat: sharp_wallet 집행봇 horizon 마크아웃 청산 + CLOB 실측비용"
```

---

## Task 5: tick/loop/라우터 + main.py 등록

**Files:**
- Modify: `api_server/polymarket_sharp_wallet_bot.py` (Task 3/4 파일에 `tick`/`_loop`/`start_loop`/라우터 추가)
- Modify: `api_server/main.py:5140` 부근 (라우터 등록), `api_server/main.py:5173` 부근 (startup 훅 호출)
- Test: `tests/test_polymarket_sharp_wallet_bot.py` (Task 3 파일에 테스트 추가)

**Interfaces:**
- Consumes: Task 3의 `_load`/`_save`/`_recent_log`, Task 4의 `_process_exits`, Task 3의 `_scan_and_enter`, 기존 `api_server.risk_state.is_killed() -> bool`.
- Produces: `tick() -> dict`, `_loop() -> None`(async), `start_loop() -> None`, FastAPI `router`(`GET /status`, `POST /config`, `POST /run-now`) — `main.py`가 등록.

- [ ] **Step 1: Write the failing test**

`tests/test_polymarket_sharp_wallet_bot.py`에 추가:
```python
def test_tick_disabled_skips():
    with patch.object(bot, "_load", return_value=dict(bot._DEFAULT)):
        result = bot.tick()
    assert result == {"skipped": "disabled"}


def test_tick_runs_exits_then_entries_and_saves():
    cfg = _cfg()
    with patch.object(bot, "_load", return_value=cfg), \
         patch.object(bot, "_save") as mock_save, \
         patch.object(bot, "_process_exits", return_value=1) as mock_exits, \
         patch.object(bot, "_scan_and_enter", return_value=2) as mock_enter:
        result = bot.tick()
    mock_exits.assert_called_once_with(cfg)
    mock_enter.assert_called_once_with(cfg)
    assert mock_save.call_count == 2  # 청산 저장 -> 진입 저장(다각화 봇과 동일 2단계 flush)
    assert result == {"entered": 2, "closed": 1, "positions": 0,
                       "spent": cfg["spent"], "realized_pnl": cfg["realized_pnl"]}


def test_status_endpoint_shape():
    with patch.object(bot, "_load", return_value=dict(bot._DEFAULT)), \
         patch.object(bot, "_recent_log", return_value=[]):
        result = bot.status()
    assert result["enabled"] is False
    assert result["interval_sec"] == 15
    assert result["positions"] == []
    assert "note" in result


def test_run_now_calls_tick():
    with patch.object(bot, "tick", return_value={"ok": True}) as mock_tick:
        result = bot.run_now()
    mock_tick.assert_called_once()
    assert result == {"ok": True}


def test_set_config_clamps_interval_sec_min_5():
    with patch.object(bot, "_load", return_value=dict(bot._DEFAULT)), \
         patch.object(bot, "_save"), patch.object(bot, "_log_event"):
        result = bot.set_config(bot.BotConfig(interval_sec=1))
    assert result["interval_sec"] == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_sharp_wallet_bot.py -v -k "tick or status_endpoint or run_now or set_config"`
Expected: FAIL with `AttributeError: module 'api_server.polymarket_sharp_wallet_bot' has no attribute 'tick'`

- [ ] **Step 3: Write minimal implementation**

`api_server/polymarket_sharp_wallet_bot.py`에 (`_process_exits` 함수 뒤에) 추가:
```python
def tick() -> dict:
    cfg = _load()
    if not cfg["enabled"]:
        return {"skipped": "disabled"}
    try:
        from api_server.risk_state import is_killed
        if is_killed():
            _log_event({"kind": "kill", "msg": "리스크 킬스위치 — 매매 중단"})
            return {"skipped": "kill_switch"}
    except Exception:
        pass

    closed = _process_exits(cfg)
    _save(cfg)
    entered = _scan_and_enter(cfg)
    cfg["last_run"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    _save(cfg)
    return {"entered": entered, "closed": closed, "positions": len(cfg.get("positions", [])),
            "spent": cfg["spent"], "realized_pnl": cfg["realized_pnl"]}


async def _loop() -> None:
    while True:
        try:
            cfg = _load()
            interval = int(cfg.get("interval_sec", 15))
            if cfg.get("enabled"):
                await asyncio.to_thread(tick)
        except Exception:  # noqa: BLE001
            interval = 15
        await asyncio.sleep(max(interval, 5))


def start_loop() -> None:
    try:
        asyncio.get_event_loop().create_task(_loop())
    except RuntimeError:
        pass


# ── API ──────────────────────────────────────────────────────────────────────
class BotConfig(BaseModel):
    enabled: bool | None = None
    interval_sec: int | None = None
    budget: float | None = None
    trade_size_usd: float | None = None
    max_concurrent_positions: int | None = None
    reset_spent: bool | None = None


@router.get("/status")
def status() -> dict:
    cfg = _load()
    return {
        "enabled": cfg["enabled"], "interval_sec": cfg["interval_sec"],
        "budget": cfg["budget"], "trade_size_usd": cfg["trade_size_usd"],
        "max_concurrent_positions": cfg["max_concurrent_positions"],
        "spent": cfg.get("spent", 0.0), "realized_pnl": cfg.get("realized_pnl", 0.0),
        "remaining": max(cfg["budget"] - cfg.get("spent", 0.0), 0.0),
        "positions": cfg.get("positions", []), "last_run": cfg.get("last_run"),
        "log": _recent_log(40),
        "note": "sharp_wallet 컨버전스 신호 paper 집행 — v1은 bucket1/bucket3만"
                "(score-tercile mid/high 제외, 순서모순으로 라이브 진입불가). paper 전용.",
    }


@router.post("/config")
def set_config(body: BotConfig) -> dict:
    cfg = _load()
    if body.enabled is not None:
        cfg["enabled"] = body.enabled
    if body.interval_sec is not None:
        cfg["interval_sec"] = max(int(body.interval_sec), 5)
    if body.budget is not None:
        cfg["budget"] = max(float(body.budget), 0.0)
    if body.trade_size_usd is not None:
        cfg["trade_size_usd"] = max(float(body.trade_size_usd), 1.0)
    if body.max_concurrent_positions is not None:
        cfg["max_concurrent_positions"] = max(int(body.max_concurrent_positions), 1)
    if body.reset_spent:
        cfg["spent"] = 0.0
    _save(cfg)
    _log_event({"kind": "config", "enabled": cfg["enabled"], "budget": cfg["budget"]})
    return {"ok": True, **{k: cfg[k] for k in (
        "enabled", "interval_sec", "budget", "trade_size_usd", "max_concurrent_positions")}}


@router.post("/run-now")
def run_now() -> dict:
    return tick()
```

`api_server/main.py:5140` 다음 줄(`app.include_router(polymarket_bot_router)` 바로 뒤)에 삽입:
```python
# ── Polymarket sharp_wallet 컨버전스 신호 paper 집행 봇 (서버측) ────────────────────
from api_server.polymarket_sharp_wallet_bot import (
    router as polymarket_sharp_wallet_bot_router,
    start_loop as _polymarket_sharp_wallet_bot_start,
)
app.include_router(polymarket_sharp_wallet_bot_router)
```

`api_server/main.py:5173`(`_polymarket_bot_start()` 줄) 바로 다음 줄에 삽입:
```python
    _polymarket_sharp_wallet_bot_start()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_polymarket_sharp_wallet_bot.py -v`
Expected: PASS (15 tests — 누적)

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -c "import api_server.main"`
Expected: 에러 없이 임포트 성공(라우터 등록 구문오류 없는지 확인)

- [ ] **Step 5: Commit**

```bash
git add api_server/polymarket_sharp_wallet_bot.py api_server/main.py tests/test_polymarket_sharp_wallet_bot.py
git commit -m "feat: sharp_wallet 집행봇 tick/loop/라우터 배선 + main.py 등록"
```

---

## Task 6: 회계 정합성 불변식 (`/lab/health` 연동)

이 프로젝트의 모든 paper 매매 봇(dart_autobot, vrp_bot, polymarket_bot)은 `api_server/invariants.py`에 "조용한 회계 버그" 런타임 검증 함수를 갖고 있고 `/lab/health`가 주기적으로 돈다(과거 실제로 `spent` 드리프트·정산 큐 멈춤이 몇 주 방치된 전례가 있어 생긴 안전장치, 파일 docstring 참고). 신규 봇도 같은 패턴을 따른다.

**Files:**
- Modify: `api_server/invariants.py` (상수 + `check_polymarket_sharp_wallet_bot` 함수 추가)
- Modify: `api_server/lab_api.py:408` 부근 (`/lab/health`에 위반 체크 배선)
- Test: `tests/test_invariants.py` (테스트 추가)

**Interfaces:**
- Consumes: Task 3의 `_DEFAULT`가 정의한 포지션 스키마(`condition_id, convergence_bucket, horizon_s, direction, entry_price, entry_ts, exit_at, usd, shares`).
- Produces: `check_polymarket_sharp_wallet_bot(cfg: dict, *, now: float | None = None) -> list[dict]` (`/lab/health`가 씀).

- [ ] **Step 1: Write the failing test**

`tests/test_invariants.py`에 추가:
```python
from api_server.invariants import check_polymarket_sharp_wallet_bot


def _sw_pos(**over):
    base = {
        "condition_id": "c1", "convergence_bucket": 1, "horizon_s": 30,
        "direction": 1.0, "entry_price": 0.5, "entry_ts": 1000.0, "exit_at": 1030.0,
        "usd": 15.0, "shares": 30.0,
    }
    base.update(over)
    return base


def _sw_cfg(**over):
    base = {"budget": 300.0, "max_concurrent_positions": 30, "spent": 15.0, "positions": [_sw_pos()]}
    base.update(over)
    return base


def test_sharp_wallet_clean_state_no_violations():
    assert check_polymarket_sharp_wallet_bot(_sw_cfg(), now=1030.0) == []


def test_sharp_wallet_spent_mismatch_flagged():
    out = check_polymarket_sharp_wallet_bot(_sw_cfg(spent=100.0), now=1030.0)
    codes = {v["code"] for v in out}
    assert "SPENT_MISMATCH" in codes
    assert any(v["severity"] == "error" for v in out)


def test_sharp_wallet_stuck_exit_flagged():
    # exit_at=1030, now=1030+3601 -> STUCK_EXIT_SECONDS(3600) 초과
    out = check_polymarket_sharp_wallet_bot(_sw_cfg(), now=1030.0 + 3601.0)
    codes = {v["code"] for v in out}
    assert "STUCK_EXIT" in codes


def test_sharp_wallet_missing_field_flagged():
    bad_pos = _sw_pos()
    del bad_pos["exit_at"]
    out = check_polymarket_sharp_wallet_bot(_sw_cfg(positions=[bad_pos], spent=15.0), now=1030.0)
    codes = {v["code"] for v in out}
    assert "POSITION_SCHEMA" in codes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_invariants.py -v -k sharp_wallet`
Expected: FAIL with `ImportError: cannot import name 'check_polymarket_sharp_wallet_bot'`

- [ ] **Step 3: Write minimal implementation**

`api_server/invariants.py` 상단 import에 `import time as _time` 추가(기존 `import datetime as _dt` 바로 아래):
```python
import datetime as _dt
import time as _time
```

상수 블록(`STUCK_RESOLUTION_DAYS` 옆)에 추가:
```python
# horizon 30~300s 집행봇이 이만큼 늦게까지 안 청산되면 청산루프 멈춤 의심
STUCK_EXIT_SECONDS = 3600
```

`check_polymarket_bot` 함수(91번째 줄 `return out`) 바로 뒤, `check_agent` 함수 앞에 추가:
```python
_SHARP_WALLET_POSITION_REQUIRED_KEYS = (
    "condition_id", "convergence_bucket", "horizon_s", "direction",
    "entry_price", "entry_ts", "exit_at", "usd", "shares",
)


def check_polymarket_sharp_wallet_bot(cfg: dict, *, now: float | None = None) -> list[dict]:
    """sharp_wallet 집행봇 상태(data/polymarket_sharp_wallet_bot.json) 정합성 검증.

    now는 테스트 주입용(기본 현재 unix ts). 반환: 위반 리스트(빈 리스트면 정상)."""
    now = now if now is not None else _time.time()
    entity = "polymarket_sharp_wallet_bot"
    out: list[dict] = []

    positions = cfg.get("positions") or []
    budget = float(cfg.get("budget", 0.0))
    spent = float(cfg.get("spent", 0.0))
    max_positions = int(cfg.get("max_concurrent_positions", 0))

    # 1) 포지션 스키마 붕괴
    for i, pos in enumerate(positions):
        missing = [k for k in _SHARP_WALLET_POSITION_REQUIRED_KEYS if k not in pos]
        if missing:
            cid = pos.get("condition_id", f"#{i}")
            out.append(_v("error", entity, "POSITION_SCHEMA",
                          f"포지션 '{cid}' 필수 필드 결손: {missing}"))

    # 2) spent 회계 불일치
    pos_usd_sum = round(sum(float(p.get("usd", 0.0)) for p in positions), 2)
    if abs(spent - pos_usd_sum) > TOL:
        out.append(_v("error", entity, "SPENT_MISMATCH",
                      f"spent={spent} != 오픈 포지션 usd 합={pos_usd_sum} "
                      f"(차이 {round(spent - pos_usd_sum, 2)})"))

    # 3) spent가 예산 초과
    if spent > budget + TOL:
        out.append(_v("error", entity, "SPENT_OVER_BUDGET",
                      f"spent={spent} > budget={budget}"))

    # 4) 슬롯 초과
    if max_positions and len(positions) > max_positions:
        out.append(_v("error", entity, "SLOTS_EXCEEDED",
                      f"오픈 포지션 {len(positions)} > max_concurrent_positions {max_positions}"))

    # 5) 청산 멈춤 — horizon 지나고도 오래 미청산
    for pos in positions:
        exit_at = pos.get("exit_at")
        if exit_at is None:
            continue
        overdue = now - float(exit_at)
        if overdue > STUCK_EXIT_SECONDS:
            cid = pos.get("condition_id", "?")
            out.append(_v("error", entity, "STUCK_EXIT",
                          f"포지션 '{cid}' exit_at({exit_at}) 후 {round(overdue)}초째 미청산 "
                          f"(>{STUCK_EXIT_SECONDS}s) — 청산루프 멈춤 의심"))

    return out
```

`api_server/lab_api.py`의 `lab_health()` 안, 기존 폴리마켓 다각화 봇 체크 블록(407~408번째 줄) 바로 뒤에 추가:
```python
    # Polymarket sharp_wallet 집행봇
    try:
        from api_server.polymarket_sharp_wallet_bot import _load as _psw_load
        violations += invariants.check_polymarket_sharp_wallet_bot(_psw_load())
    except Exception as exc:  # noqa: BLE001
        violations.append({"severity": "warn", "entity": "polymarket_sharp_wallet_bot",
                           "code": "CHECK_FAILED", "detail": f"검사 실패: {exc}"[:200]})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_invariants.py -v`
Expected: PASS (기존 테스트 전부 + 신규 4개)

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -c "import api_server.lab_api"`
Expected: 에러 없이 임포트 성공

- [ ] **Step 5: Commit**

```bash
git add api_server/invariants.py api_server/lab_api.py tests/test_invariants.py
git commit -m "feat: sharp_wallet 집행봇 회계 정합성 불변식 + /lab/health 연동"
```

---

## Final Check

전체 스위트 1회 실행:

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: 전부 PASS, pre-existing failure 없음(CLAUDE.md 기준 2026-07-30 이후 0건 유지).
