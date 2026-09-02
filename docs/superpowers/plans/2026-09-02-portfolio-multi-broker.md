# 멀티브로커 포트폴리오 뷰 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** HL/KIS 계좌를 live/paper 구분해서 합산 총자산·보유종목 파이·수익률
그래프·계좌별 거래내역으로 보여주는 백엔드 3개 엔드포인트 + iOS 2탭(Agents+Bots
통합, Portfolio 신설) 구현.

**Architecture:** `jarvis/broker_readonly/live_providers.py`(신규, HL/KIS 실계좌
어댑터) → `jarvis/broker_readonly/aggregator.py`(신규, 병렬 집계+FX 변환) →
`jarvis/broker_readonly/snapshot_job.py`(신규, 일일 스냅샷) → `api_server/main.py`
얇은 라우터 3개 → iOS `PortfolioView.swift`(신규) + `ContentView.swift`(탭 개편).

**Tech Stack:** FastAPI, asyncio(to_thread), SwiftUI Charts(iOS17 네이티브,
SectorMark/LineMark), pytest(asyncio_mode=auto).

**Spec:** `docs/superpowers/specs/2026-09-02-portfolio-multi-broker-design.md`

## Global Constraints

- 브로커 I/O(HL SDK, KIS HTTP)는 반드시 `asyncio.to_thread`로 이벤트루프 밖에서
  실행 — 절대 `async def` 라우트에서 직접 sync 브로커 호출 금지(오늘 겪은
  전체 서버 먹통 사고 재발 방지가 이 기능의 핵심 불변식).
- 계좌 하나 실패해도 `/portfolio/summary`는 항상 200 + 해당 계좌만
  `connected:false` — 절대 500 전체 실패 없음.
- `jarvis/broker_readonly/adapters.py`, `models.py`, `provider.py`는 **수정
  금지** — `tests/test_broker_readonly.py::test_no_execution_import`가 이
  파일들의 소스 문자열에 `"backends.kis"`/`"backends.ib"`/`"place_order"`가
  없음을 강제한다(집행 게이트웨이 미도달 불변식). 실계좌 연동 코드는 이 스캔
  대상이 아닌 새 파일 `live_providers.py`에 둔다.
- KIS 계좌 크레덴셜은 `KIS_{,MOCK_}APP_KEY/APP_SECRET/CANO` + 공통
  `KIS_ACNT_PRDT_CD` (실전: `KIS_` 접두사, 모의: `KIS_MOCK_` 접두사) — 이미
  `.env`에 존재, 새로 추가할 값 없음.
- 기본 통화 USD — KIS(KRW) equity는 `USDKRW=X`(yfinance) 환율로 나눠 합산.
- `oms.list_orders()`/`api_server/oms.py`는 **거래내역 소스로 쓰지 않음**
  (조사 결과 HL 주문은 애초에 안 거치고, KR 주문도 live/paper 구분이 없음 —
  스펙 작성 시점엔 몰랐던 사실). 대신 `api_server/order_audit.py:read_recent()`
  (venue + `request.paper` 필드로 필터)를 쓴다 — 아래 Task 1에서 상세.

---

### Task 1: `jarvis/broker_readonly/live_providers.py` — HL/KIS 실계좌 프로바이더

**Files:**
- Create: `jarvis/broker_readonly/live_providers.py`
- Test: `tests/test_broker_readonly_live.py`

**Interfaces:**
- Consumes: `jarvis.broker_readonly.provider.BrokerReadOnlyProvider`(ABC),
  `jarvis.broker_readonly.models.{AccountSnapshot,BrokerPosition,BrokerHealth}`
  (기존, 수정 없음) · `hyperliquid.trader.get_positions(paper: bool) -> dict`
  (기존) · `backends.kis.order_client.KISOrderClient(app_key, app_secret, cano,
  acnt_prdt_cd, mock: bool).get_balance() -> dict` / `.get_holdings() -> list[dict]`
  (기존) · `api_server.order_audit.read_recent(limit: int) -> list[dict]`(기존,
  엔트리 형태 `{"ts","venue","status","request","result"}`).
- Produces: `HLReadOnlyProvider(paper: bool)`, `KISReadOnlyProvider(paper: bool)`
  — 둘 다 `account_snapshot()/positions()/balances()/orders_history()/
  health_check()` 구현. `orders_history()`는 정규화된
  `{"ts","venue","status","symbol","side","quantity"}` dict 리스트를 반환
  (Task 2/3에서 그대로 소비).

- [ ] **Step 1: 실패 테스트 작성**

```python
"""jarvis/broker_readonly/live_providers.py 단위 테스트 — 실 네트워크 없음.
HL/KIS SDK 호출 지점을 monkeypatch로 가짜 응답으로 대체."""
from __future__ import annotations

from jarvis.broker_readonly.live_providers import HLReadOnlyProvider, KISReadOnlyProvider


def _fake_hl_positions(paper=False):
    return {
        "margin_summary": {"accountValue": "1000.5", "spotUsdcBalance": "50.0"},
        "asset_positions": [
            {"position": {"coin": "BTC", "szi": "0.1", "entryPx": "60000", "positionValue": "6500"}},
            {"position": {"coin": "ETH", "szi": "0", "entryPx": "0", "positionValue": "0"}},
        ],
        "open_orders": [],
    }


def test_hl_account_snapshot(monkeypatch):
    monkeypatch.setattr("hyperliquid.trader.get_positions", _fake_hl_positions)
    snap = HLReadOnlyProvider(paper=False).account_snapshot()
    assert snap.equity == 1000.5 and snap.cash == 50.0


def test_hl_positions_skips_zero_size(monkeypatch):
    monkeypatch.setattr("hyperliquid.trader.get_positions", _fake_hl_positions)
    positions = HLReadOnlyProvider(paper=False).positions()
    assert len(positions) == 1 and positions[0].symbol == "BTC"


def test_hl_health_check_reports_disconnected_on_error(monkeypatch):
    def _raise(paper=False):
        raise ValueError("HL_PRIVATE_KEY env var not set")
    monkeypatch.setattr("hyperliquid.trader.get_positions", _raise)
    h = HLReadOnlyProvider(paper=False).health_check()
    assert h.connected is False and "HL_PRIVATE_KEY" in h.error


def test_hl_orders_history_filters_by_venue_and_paper(monkeypatch):
    entries = [
        {"ts": "t1", "venue": "HL", "status": "submitted",
         "request": {"coin": "BTC", "is_buy": True, "size": 0.1, "paper": False}},
        {"ts": "t2", "venue": "HL", "status": "submitted",
         "request": {"coin": "ETH", "is_buy": False, "size": 1.0, "paper": True}},
        {"ts": "t3", "venue": "KR", "status": "submitted",
         "request": {"code": "005930", "side": "BUY", "quantity": 10, "paper": False}},
    ]
    monkeypatch.setattr("api_server.order_audit.read_recent", lambda limit=2000: entries)
    trades = HLReadOnlyProvider(paper=False).orders_history()
    assert len(trades) == 1 and trades[0]["symbol"] == "BTC" and trades[0]["side"] == "BUY"


def test_kis_missing_creds_raises_in_health_check(monkeypatch):
    for k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_CANO", "KIS_ACNT_PRDT_CD"):
        monkeypatch.delenv(k, raising=False)
    h = KISReadOnlyProvider(paper=False).health_check()
    assert h.connected is False and "미설정" in h.error


def test_kis_account_snapshot(monkeypatch):
    monkeypatch.setenv("KIS_APP_KEY", "k")
    monkeypatch.setenv("KIS_APP_SECRET", "s")
    monkeypatch.setenv("KIS_CANO", "12345678")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def get_balance(self):
            return {"deposit": 1000.0, "total_eval": 5000.0, "net_asset": 4900.0}

        def get_holdings(self):
            return [{"code": "005930", "qty": 10.0, "avg_price": 70000.0, "current": 72000.0}]

    monkeypatch.setattr("backends.kis.order_client.KISOrderClient", _FakeClient)
    p = KISReadOnlyProvider(paper=False)
    snap = p.account_snapshot()
    assert snap.cash == 1000.0 and snap.equity == 4900.0
    positions = p.positions()
    assert positions[0].symbol == "005930" and positions[0].market_value == 720000.0


def test_kis_mock_prefix_used_for_paper(monkeypatch):
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "mk")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "ms")
    monkeypatch.setenv("KIS_MOCK_CANO", "87654321")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")
    captured = {}

    class _FakeClient:
        def __init__(self, app_key, app_secret, cano, acnt_prdt_cd, mock=True):
            captured["mock"] = mock
            captured["cano"] = cano

        def get_balance(self):
            return {"deposit": 0.0, "total_eval": 0.0, "net_asset": 0.0}

    monkeypatch.setattr("backends.kis.order_client.KISOrderClient", _FakeClient)
    KISReadOnlyProvider(paper=True).account_snapshot()
    assert captured == {"mock": True, "cano": "87654321"}
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_broker_readonly_live.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jarvis.broker_readonly.live_providers'`

- [ ] **Step 3: 구현**

```python
"""HL/KIS 실계좌 read-only 프로바이더 (P8).

jarvis.broker_readonly.adapters와 분리된 파일인 이유: adapters.py는
tests/test_broker_readonly.py::test_no_execution_import 가 소스 문자열에
"backends.kis"/"backends.ib"/"place_order"가 없음을 강제하는 불변식 스캔
대상이라, 여기서 KISOrderClient(주문 가능 클래스)를 재사용하려면 별도
파일이 필요하다. 이 파일은 그 스캔 대상은 아니지만 규율은 동일하게 지킨다
— place_order/cancel_order는 호출하지 않고 get_balance/get_holdings 같은
읽기 메서드만 쓴다.
"""
from __future__ import annotations

import datetime as _dt
import os as _os

from jarvis.broker_readonly.models import AccountSnapshot, BrokerHealth, BrokerPosition
from jarvis.broker_readonly.provider import BrokerReadOnlyProvider


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class HLReadOnlyProvider(BrokerReadOnlyProvider):
    def __init__(self, paper: bool = False) -> None:
        self._paper = paper
        self.source_name = "hl_paper" if paper else "hl"

    def _raw(self) -> dict:
        from hyperliquid.trader import get_positions
        return get_positions(paper=self._paper)

    def account_snapshot(self) -> AccountSnapshot | None:
        ms = self._raw().get("margin_summary", {})
        equity = float(ms.get("accountValue", 0) or 0)
        cash = float(ms.get("spotUsdcBalance", 0) or 0)
        return AccountSnapshot(cash=cash, equity=equity, buying_power=equity, timestamp=_now())

    def positions(self) -> list[BrokerPosition]:
        now = _now()
        out = []
        for p in self._raw().get("asset_positions", []):
            pos = p.get("position", {})
            szi = float(pos.get("szi", 0) or 0)
            if szi == 0:
                continue
            out.append(BrokerPosition(
                symbol=pos.get("coin", ""), quantity=szi,
                avg_price=float(pos.get("entryPx", 0) or 0),
                market_value=float(pos.get("positionValue", 0) or 0),
                timestamp=now,
            ))
        return out

    def balances(self) -> dict:
        snap = self.account_snapshot()
        return snap.to_dict() if snap else {}

    def orders_history(self) -> list[dict]:
        from api_server.order_audit import read_recent
        out = []
        for e in read_recent(limit=2000):
            if e.get("venue") != "HL":
                continue
            req = e.get("request") or {}
            if bool(req.get("paper")) != self._paper:
                continue
            out.append({
                "ts": e.get("ts"), "venue": "HL", "status": e.get("status"),
                "symbol": req.get("coin"),
                "side": "BUY" if req.get("is_buy") else "SELL",
                "quantity": req.get("size"),
            })
        return out

    def health_check(self) -> BrokerHealth:
        try:
            self._raw()
            return BrokerHealth(connected=True, stale=False, error=None, timestamp=_now())
        except Exception as exc:
            return BrokerHealth(connected=False, stale=False, error=str(exc), timestamp=_now())


class KISReadOnlyProvider(BrokerReadOnlyProvider):
    def __init__(self, paper: bool = False) -> None:
        self._paper = paper
        self.source_name = "kis_paper" if paper else "kis"

    def _creds(self) -> tuple[str, str, str, str]:
        prefix = "KIS_MOCK_" if self._paper else "KIS_"
        app_key = _os.environ.get(f"{prefix}APP_KEY", "")
        app_secret = _os.environ.get(f"{prefix}APP_SECRET", "")
        cano = _os.environ.get(f"{prefix}CANO", "")
        acnt = _os.environ.get("KIS_ACNT_PRDT_CD", "")
        if not all([app_key, app_secret, cano, acnt]):
            raise ValueError(f"KIS {'모의' if self._paper else '실전'} 계좌 키 미설정")
        return app_key, app_secret, cano, acnt

    def _client(self):
        from backends.kis.order_client import KISOrderClient
        app_key, app_secret, cano, acnt = self._creds()
        return KISOrderClient(app_key, app_secret, cano, acnt, mock=self._paper)

    def account_snapshot(self) -> AccountSnapshot | None:
        bal = self._client().get_balance()
        return AccountSnapshot(cash=bal["deposit"], equity=bal["net_asset"],
                               buying_power=bal["deposit"], timestamp=_now())

    def positions(self) -> list[BrokerPosition]:
        now = _now()
        return [BrokerPosition(symbol=h["code"], quantity=h["qty"], avg_price=h["avg_price"],
                               market_value=h["qty"] * h["current"], timestamp=now)
                for h in self._client().get_holdings()]

    def balances(self) -> dict:
        return self._client().get_balance()

    def orders_history(self) -> list[dict]:
        from api_server.order_audit import read_recent
        out = []
        for e in read_recent(limit=2000):
            if e.get("venue") != "KR":
                continue
            req = e.get("request") or {}
            if bool(req.get("paper")) != self._paper:
                continue
            out.append({
                "ts": e.get("ts"), "venue": "KR", "status": e.get("status"),
                "symbol": req.get("code"), "side": req.get("side"),
                "quantity": req.get("quantity"),
            })
        return out

    def health_check(self) -> BrokerHealth:
        try:
            self._client().get_balance()
            return BrokerHealth(connected=True, stale=False, error=None, timestamp=_now())
        except Exception as exc:
            return BrokerHealth(connected=False, stale=False, error=str(exc), timestamp=_now())
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_broker_readonly_live.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: 기존 broker_readonly 불변식 테스트 회귀 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_broker_readonly.py -v`
Expected: PASS 그대로 (adapters.py 안 건드렸으므로 `test_no_execution_import` 포함 전부 그대로 통과)

- [ ] **Step 6: 커밋**

```bash
git add jarvis/broker_readonly/live_providers.py tests/test_broker_readonly_live.py
git commit -m "feat: HL/KIS 실계좌 read-only 프로바이더 추가"
```

---

### Task 2: `jarvis/broker_readonly/aggregator.py` — 병렬 집계 + FX 변환

**Files:**
- Create: `jarvis/broker_readonly/aggregator.py`
- Test: `tests/test_portfolio_aggregator.py`

**Interfaces:**
- Consumes: Task 1의 `HLReadOnlyProvider`, `KISReadOnlyProvider` (생성자
  `(paper: bool)`, 메서드 `account_snapshot()/positions()/health_check()/
  orders_history()`).
- Produces: `PortfolioAggregator(mode: str)` — `mode`는 `"live"` 또는
  `"paper"`. `async def summary() -> dict`(아래 스키마), `def trades(account:
  str | None = None) -> list[dict]`(Task 1의 정규화된 거래 dict 리스트,
  ts 내림차순).

`summary()` 반환 스키마 (Task 4의 `/portfolio/summary`가 그대로 리턴):
```json
{
  "mode": "live",
  "total_equity_usd": 12345.67,
  "fx_usdkrw": 1350.2,
  "accounts": [
    {"account": "hl", "connected": true, "error": null, "cash": 100.0,
     "equity": 5000.0, "equity_usd": 5000.0,
     "positions": [{"symbol": "BTC", "quantity": 0.1, "avg_price": 60000.0,
                     "market_value": 6000.0, "timestamp": "..."}]},
    {"account": "kis", "connected": false, "error": "KIS 실전 계좌 키 미설정",
     "cash": 0.0, "equity": 0.0, "equity_usd": 0.0, "positions": []}
  ],
  "holdings": [{"account": "hl", "symbol": "BTC", "value_usd": 6000.0}]
}
```
`accounts[]`는 성공/실패 관계없이 항상 같은 키 집합 — 실패해도 `cash/equity/
equity_usd/positions`가 0/빈 리스트로 채워짐(iOS Decodable이 옵셔널 없이
파싱 가능하게).

- [ ] **Step 1: 실패 테스트 작성**

```python
"""PortfolioAggregator 단위 테스트 — HL/KIS 프로바이더를 monkeypatch로 대체."""
from __future__ import annotations

import pytest

from jarvis.broker_readonly import aggregator
from jarvis.broker_readonly.models import AccountSnapshot, BrokerHealth, BrokerPosition


class _FakeHL:
    def __init__(self, paper=False):
        self.paper = paper

    def account_snapshot(self):
        return AccountSnapshot(cash=100.0, equity=5000.0, buying_power=5000.0, timestamp="t")

    def positions(self):
        return [BrokerPosition(symbol="BTC", quantity=0.1, avg_price=60000.0, market_value=6000.0)]

    def health_check(self):
        return BrokerHealth(connected=True, stale=False, error=None, timestamp="t")

    def orders_history(self):
        return [{"ts": "t2", "venue": "HL", "status": "submitted", "symbol": "BTC",
                  "side": "BUY", "quantity": 0.1}]


class _FakeKISBroken:
    def __init__(self, paper=False):
        self.paper = paper

    def account_snapshot(self):
        raise RuntimeError("KIS unreachable")

    def positions(self):
        raise RuntimeError("KIS unreachable")

    def health_check(self):
        return BrokerHealth(connected=False, stale=False, error="KIS unreachable", timestamp="t")

    def orders_history(self):
        return []


@pytest.fixture(autouse=True)
def _patch_providers(monkeypatch):
    monkeypatch.setattr(aggregator, "HLReadOnlyProvider", _FakeHL)
    monkeypatch.setattr(aggregator, "KISReadOnlyProvider", _FakeKISBroken)
    monkeypatch.setattr(aggregator, "_usdkrw_rate", lambda: 1350.0)


async def test_summary_reports_partial_failure_not_500():
    result = await aggregator.PortfolioAggregator("live").summary()
    accounts = {a["account"]: a for a in result["accounts"]}
    assert accounts["hl"]["connected"] is True
    assert accounts["kis"]["connected"] is False
    assert accounts["kis"]["equity_usd"] == 0.0
    assert accounts["kis"]["positions"] == []


async def test_summary_totals_and_holdings():
    result = await aggregator.PortfolioAggregator("live").summary()
    assert result["total_equity_usd"] == 5000.0
    assert result["holdings"] == [{"account": "hl", "symbol": "BTC", "value_usd": 6000.0}]


def test_trades_merges_and_sorts_by_ts_desc():
    trades = aggregator.PortfolioAggregator("live").trades()
    assert trades == [{"ts": "t2", "venue": "HL", "status": "submitted", "symbol": "BTC",
                        "side": "BUY", "quantity": 0.1}]


def test_trades_filters_by_account():
    assert aggregator.PortfolioAggregator("live").trades(account="kis") == []
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_portfolio_aggregator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jarvis.broker_readonly.aggregator'`

- [ ] **Step 3: 구현**

```python
"""HL+KIS(live/paper) 계좌 병렬 집계 (P8)."""
from __future__ import annotations

import asyncio
import time as _time

from jarvis.broker_readonly.live_providers import HLReadOnlyProvider, KISReadOnlyProvider

_FX_CACHE: dict = {}
_FX_TTL = 60.0
_FX_FALLBACK = 1350.0  # ponytail: yfinance 실패+캐시 없음 시 대략치. 화면은 뜨게.


def _usdkrw_rate() -> float:
    now = _time.time()
    cached = _FX_CACHE.get("rate")
    if cached and now - cached[0] < _FX_TTL:
        return cached[1]
    try:
        import yfinance as yf
        hist = yf.Ticker("USDKRW=X").history(period="1d", interval="1d")
        rate = float(hist["Close"].dropna().iloc[-1])
    except Exception:
        rate = cached[1] if cached else _FX_FALLBACK
    _FX_CACHE["rate"] = (now, rate)
    return rate


def _empty_account(name: str, error: str) -> dict:
    return {"account": name, "connected": False, "error": error,
            "cash": 0.0, "equity": 0.0, "equity_usd": 0.0, "positions": []}


class PortfolioAggregator:
    def __init__(self, mode: str) -> None:
        self._mode = mode
        paper = mode == "paper"
        self._providers = {
            "hl": HLReadOnlyProvider(paper=paper),
            "kis": KISReadOnlyProvider(paper=paper),
        }

    async def summary(self) -> dict:
        fx = await asyncio.to_thread(_usdkrw_rate)
        results = await asyncio.gather(
            *[asyncio.to_thread(self._one, name, p, fx) for name, p in self._providers.items()]
        )
        accounts = []
        total_usd = 0.0
        holdings: list[dict] = []
        for name, account in results:
            accounts.append(account)
            total_usd += account["equity_usd"]
            for pos in account["positions"]:
                if pos["market_value"] == 0:
                    continue
                value_usd = pos["market_value"] / fx if name == "kis" else pos["market_value"]
                holdings.append({"account": name, "symbol": pos["symbol"],
                                  "value_usd": round(value_usd, 2)})
        return {"mode": self._mode, "total_equity_usd": round(total_usd, 2), "fx_usdkrw": fx,
                "accounts": accounts, "holdings": holdings}

    def _one(self, name: str, provider, fx: float) -> tuple[str, dict]:
        try:
            snap = provider.account_snapshot()
            positions = provider.positions()
            health = provider.health_check()
        except Exception as exc:
            return name, _empty_account(name, str(exc))
        if snap is None:
            return name, _empty_account(name, health.error or "계좌 정보 없음")
        equity_usd = snap.equity / fx if name == "kis" else snap.equity
        return name, {
            "account": name, "connected": health.connected, "error": health.error,
            "cash": snap.cash, "equity": snap.equity, "equity_usd": round(equity_usd, 2),
            "positions": [p.to_dict() for p in positions],
        }

    def trades(self, account: str | None = None) -> list[dict]:
        providers = self._providers if account is None else {account: self._providers[account]}
        out: list[dict] = []
        for p in providers.values():
            out.extend(p.orders_history())
        out.sort(key=lambda t: t.get("ts") or "", reverse=True)
        return out
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_portfolio_aggregator.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add jarvis/broker_readonly/aggregator.py tests/test_portfolio_aggregator.py
git commit -m "feat: 포트폴리오 집계기(PortfolioAggregator) 추가 — 부분 실패 허용"
```

---

### Task 3: `jarvis/broker_readonly/snapshot_job.py` — 일일 스냅샷

**Files:**
- Create: `jarvis/broker_readonly/snapshot_job.py`
- Test: `tests/test_portfolio_snapshot_job.py`

**Interfaces:**
- Consumes: Task 2의 `PortfolioAggregator(mode).summary() -> dict`(키
  `total_equity_usd` 사용).
- Produces: `async def snapshot_loop() -> None`(Task 4가 startup에서
  `asyncio.create_task`), `async def _snapshot_once() -> None`, `def
  _append_snapshot(mode: str, total_equity_usd: float, path: Path | None =
  None) -> dict`. 파일: `data/portfolio_snapshots.jsonl`, 한 줄 =
  `{"ts","mode","total_equity_usd"}`.

- [ ] **Step 1: 실패 테스트 작성**

```python
"""portfolio_snapshots.jsonl append + 실패 삼킴 테스트."""
from __future__ import annotations

import json

from jarvis.broker_readonly import snapshot_job


def test_append_snapshot_writes_jsonl_line(tmp_path):
    path = tmp_path / "snap.jsonl"
    snapshot_job._append_snapshot("live", 1234.5, path=path)
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["mode"] == "live" and row["total_equity_usd"] == 1234.5 and "ts" in row


async def test_snapshot_once_swallows_aggregator_errors(monkeypatch):
    class _Boom:
        def __init__(self, mode):
            pass

        async def summary(self):
            raise RuntimeError("kis timeout")

    monkeypatch.setattr(snapshot_job, "PortfolioAggregator", _Boom)
    await snapshot_job._snapshot_once()  # 예외 안 남으면 통과


async def test_snapshot_once_writes_both_modes(monkeypatch, tmp_path):
    monkeypatch.setattr(snapshot_job, "_SNAPSHOT_PATH", tmp_path / "snap.jsonl")

    class _Fake:
        def __init__(self, mode):
            self.mode = mode

        async def summary(self):
            return {"total_equity_usd": 100.0 if self.mode == "live" else 50.0}

    monkeypatch.setattr(snapshot_job, "PortfolioAggregator", _Fake)
    await snapshot_job._snapshot_once()
    lines = (tmp_path / "snap.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    modes = {json.loads(line)["mode"] for line in lines}
    assert modes == {"live", "paper"}
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_portfolio_snapshot_job.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jarvis.broker_readonly.snapshot_job'`

- [ ] **Step 3: 구현**

```python
"""일일 포트폴리오 스냅샷 (P8) — equity curve 데이터 소스.
alert_push_loop과 동일 패턴: 실패해도 다음 주기 재시도, 서버 안 죽임."""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
from pathlib import Path

from jarvis.broker_readonly.aggregator import PortfolioAggregator

_SNAPSHOT_PATH = Path("data/portfolio_snapshots.jsonl")
_INTERVAL_SEC = 24 * 3600


def _append_snapshot(mode: str, total_equity_usd: float, path: Path | None = None) -> dict:
    entry = {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(), "mode": mode,
              "total_equity_usd": total_equity_usd}
    target = path if path is not None else _SNAPSHOT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


async def _snapshot_once() -> None:
    for mode in ("live", "paper"):
        try:
            summary = await PortfolioAggregator(mode).summary()
            _append_snapshot(mode, summary["total_equity_usd"])
        except Exception:
            pass


async def snapshot_loop() -> None:
    while True:
        await _snapshot_once()
        await asyncio.sleep(_INTERVAL_SEC)
```

주의: `test_snapshot_once_writes_both_modes`가 `monkeypatch.setattr(snapshot_job,
"_SNAPSHOT_PATH", ...)`로 모듈 전역을 바꿔치기하므로, `_snapshot_once`
내부에서 `_append_snapshot`을 호출할 때 `path` 인자를 안 넘기면(기본값
`None`) 함수 안에서 **호출 시점에** `snapshot_job._SNAPSHOT_PATH`를
다시 읽어야 monkeypatch가 반영된다 — 위 구현처럼 `target = path if path is
not None else _SNAPSHOT_PATH`로 함수 바디에서 참조할 것 (default 인자값으로
바인딩하면 monkeypatch 적용 전 값이 고정되어버림).

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_portfolio_snapshot_job.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 커밋**

```bash
git add jarvis/broker_readonly/snapshot_job.py tests/test_portfolio_snapshot_job.py
git commit -m "feat: 포트폴리오 일일 스냅샷 잡 추가"
```

---

### Task 4: `api_server/main.py` — 엔드포인트 3개 + 스냅샷 잡 등록

**Files:**
- Modify: `api_server/main.py` (새 섹션 삽입, `@app.on_event("startup")`
  블록 직전 — 기존 5496번째 줄 근방; 정확한 줄번호는 Task 1-3 커밋 이후
  달라질 수 있으니 `@app.on_event("startup")` 문자열로 찾을 것)
- Modify: `api_server/main.py` startup 블록 — `asyncio.create_task(alert_push_loop())`
  다음 줄에 스냅샷 루프 등록 추가
- Test: `tests/test_portfolio_api.py`

**Interfaces:**
- Consumes: Task 2의 `PortfolioAggregator(mode).summary()`/`.trades()`,
  Task 3의 `snapshot_loop()`.
- Produces: `GET /portfolio/summary?mode=live|paper`, `GET
  /portfolio/history?mode=live|paper&days=N`, `GET /portfolio/trades?mode=
  live|paper&account=hl|kis`(account 생략 가능).

- [ ] **Step 1: 실패 테스트 작성**

```python
"""GET /portfolio/* 라우트 테스트 — PortfolioAggregator를 patch로 대체."""
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api_server.main import app

client = TestClient(app)


@patch("jarvis.broker_readonly.aggregator.PortfolioAggregator")
def test_portfolio_summary_returns_aggregator_result(mock_cls):
    mock_inst = mock_cls.return_value
    mock_inst.summary = AsyncMock(return_value={"mode": "live", "total_equity_usd": 1.0,
                                                  "fx_usdkrw": 1350.0, "accounts": [], "holdings": []})
    r = client.get("/portfolio/summary", params={"mode": "live"})
    assert r.status_code == 200
    assert r.json()["total_equity_usd"] == 1.0
    mock_cls.assert_called_once_with("live")


def test_portfolio_summary_rejects_invalid_mode():
    r = client.get("/portfolio/summary", params={"mode": "bogus"})
    assert r.status_code == 422


def test_portfolio_history_returns_empty_when_no_snapshot_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # data/portfolio_snapshots.jsonl 없는 cwd
    r = client.get("/portfolio/history", params={"mode": "live", "days": 30})
    assert r.status_code == 200
    assert r.json() == {"mode": "live", "points": []}


@patch("jarvis.broker_readonly.aggregator.PortfolioAggregator")
def test_portfolio_trades_filters_by_account(mock_cls):
    mock_inst = mock_cls.return_value
    mock_inst.trades.return_value = [{"ts": "t", "venue": "HL", "status": "submitted",
                                        "symbol": "BTC", "side": "BUY", "quantity": 0.1}]
    r = client.get("/portfolio/trades", params={"mode": "live", "account": "hl"})
    assert r.status_code == 200
    assert r.json()["trades"][0]["symbol"] == "BTC"
    mock_inst.trades.assert_called_once_with(account="hl")
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_portfolio_api.py -v`
Expected: FAIL — 404 (라우트 없음)

- [ ] **Step 3: 구현 — 라우트 3개 추가**

`@app.on_event("startup")` 정의 바로 위에 새 섹션 삽입:

```python
# ── Portfolio (멀티브로커 계좌 뷰, P8) ────────────────────────────────────────
@app.get("/portfolio/summary")
async def portfolio_summary(mode: Literal["live", "paper"] = "live") -> dict:
    from jarvis.broker_readonly.aggregator import PortfolioAggregator
    return await PortfolioAggregator(mode).summary()


@app.get("/portfolio/history")
def portfolio_history(mode: Literal["live", "paper"] = "live", days: int = 30) -> dict:
    path = Path("data/portfolio_snapshots.jsonl")
    if not path.exists():
        return {"mode": mode, "points": []}
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    points = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("mode") != mode:
                continue
            if dt.datetime.fromisoformat(row["ts"]) >= cutoff:
                points.append(row)
    return {"mode": mode, "points": points}


@app.get("/portfolio/trades")
def portfolio_trades(mode: Literal["live", "paper"] = "live",
                      account: Literal["hl", "kis"] | None = None) -> dict:
    from jarvis.broker_readonly.aggregator import PortfolioAggregator
    return {"trades": PortfolioAggregator(mode).trades(account=account)}
```

`Literal`, `Path`, `dt`, `json`은 파일 상단에 이미 import돼있음(각각
`typing.Literal`, `pathlib.Path`, `datetime as dt`, `json`) — 추가 import
불필요.

- [ ] **Step 4: 구현 — 스냅샷 루프 startup 등록**

`asyncio.create_task(alert_push_loop())` 다음 줄에 추가:

```python
    from jarvis.broker_readonly.snapshot_job import snapshot_loop
    asyncio.create_task(snapshot_loop())
```

- [ ] **Step 5: 테스트 실행해서 통과 확인**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_portfolio_api.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: 회귀 확인 (pre-existing 94건 실패 제외)**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ -q`
Expected: 이전과 동일한 94건만 실패(프로젝트 CLAUDE.md에 문서화된 기존
실패, 오늘 변경분과 무관), 신규 실패 없음.

- [ ] **Step 7: 서버 재기동 + 수동 확인**

```bash
bash scripts/restart_api.sh
curl -s -H "X-Api-Key: $MOBILE_API_KEY" "http://127.0.0.1:8000/portfolio/summary?mode=live" | python3 -m json.tool
curl -s -H "X-Api-Key: $MOBILE_API_KEY" "http://127.0.0.1:8000/portfolio/history?mode=live&days=30" | python3 -m json.tool
curl -s -H "X-Api-Key: $MOBILE_API_KEY" "http://127.0.0.1:8000/portfolio/trades?mode=live" | python3 -m json.tool
```
Expected: 셋 다 200 + 위 스키마. KIS/HL 크레덴셜 미설정이어도 `connected:false`
로 채워진 200 응답(500 아님)이면 정상.

- [ ] **Step 8: 커밋**

```bash
git add api_server/main.py tests/test_portfolio_api.py
git commit -m "feat: /portfolio/summary,history,trades 엔드포인트 + 스냅샷 잡 등록"
```

---

### Task 5: iOS `APIClient.swift` + `Models.swift` — 쿼리 파라미터 지원 + 타입

**Files:**
- Modify: `~/seokminal/ios-remote/Seokminal/APIClient.swift`
- Modify: `~/seokminal/ios-remote/Seokminal/Models.swift`

**Interfaces:**
- Consumes: Task 4의 3개 엔드포인트 JSON 스키마(위 참조).
- Produces: `APIClient.get<T: Decodable>(_ path: String, query: [String:
  String] = [:]) async throws -> T`(기존 시그니처에 `query` 추가, 하위
  호환 — 기존 호출부 안 건드림). `PortfolioSummary`, `PortfolioHistory`,
  `PortfolioTrades` Decodable 구조체(Task 6이 소비).

기존 `APIClient.get`은 `baseURL.appendingPathComponent(path)`를 쓰는데,
`path`에 `?mode=live` 같은 쿼리 문자열을 그대로 붙이면 `?`가 percent-encode
되어 버려 쿼리로 동작하지 않는다 — `URLComponents`로 바꿔야 함.

- [ ] **Step 1: `APIClient.swift`의 `get<T>` 수정**

```swift
static func get<T: Decodable>(_ path: String, query: [String: String] = [:]) async throws -> T {
    var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
    if !query.isEmpty {
        components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
    }
    var req = URLRequest(url: components.url!)
    req.setValue(apiKey, forHTTPHeaderField: "X-Api-Key")
    let (data, resp) = try await URLSession.shared.data(for: req)
    guard let http = resp as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
        throw APIError.badStatus((resp as? HTTPURLResponse)?.statusCode ?? -1)
    }
    do { return try JSONDecoder().decode(T.self, from: data) }
    catch { throw APIError.decode }
}
```

- [ ] **Step 2: `Models.swift`에 타입 추가**

```swift
// GET /portfolio/summary
struct PortfolioSummary: Decodable {
    struct Position: Decodable, Identifiable {
        var id: String { symbol }
        let symbol: String
        let quantity: Double
        let avg_price: Double
        let market_value: Double
    }
    struct Account: Decodable, Identifiable {
        var id: String { account }
        let account: String
        let connected: Bool
        let error: String?
        let cash: Double
        let equity: Double
        let equity_usd: Double
        let positions: [Position]
    }
    struct Holding: Decodable, Identifiable {
        var id: String { "\(account):\(symbol)" }
        let account: String
        let symbol: String
        let value_usd: Double
    }
    let mode: String
    let total_equity_usd: Double
    let fx_usdkrw: Double
    let accounts: [Account]
    let holdings: [Holding]
}

// GET /portfolio/history
struct PortfolioHistory: Decodable {
    struct Point: Decodable, Identifiable {
        var id: String { ts }
        let ts: String
        let mode: String
        let total_equity_usd: Double
    }
    let mode: String
    let points: [Point]
}

// GET /portfolio/trades
struct PortfolioTrades: Decodable {
    struct Trade: Decodable, Identifiable {
        var id: String { ts + (symbol ?? "") + (side ?? "") }
        let ts: String
        let venue: String
        let status: String
        let symbol: String?
        let side: String?
        let quantity: Double?
    }
    let trades: [Trade]
}
```

- [ ] **Step 3: 커밋**

```bash
cd ~/seokminal/ios-remote
git add Seokminal/APIClient.swift Seokminal/Models.swift 2>/dev/null || true
```

(이 레포가 git 저장소가 아니면 이 스텝은 스킵 — Task 7에서 빌드 검증 후
전체를 한 번에 커밋)

---

### Task 6: iOS `PortfolioView.swift` (신규) — Portfolio 탭

**Files:**
- Create: `~/seokminal/ios-remote/Seokminal/PortfolioView.swift`

**Interfaces:**
- Consumes: Task 5의 `APIClient.get<T>(_:query:)`, `PortfolioSummary`,
  `PortfolioHistory`, `PortfolioTrades`. `ContentView.swift`의 `RefreshingList<T,
  Content>`(기존, 10초 자동새로고침 뼈대 — import 없이 같은 타겟 내에서
  바로 쓸 수 있음).
- Produces: `struct PortfolioTab: View`(Task 7이 `ContentView`의 `TabView`
  안에 배치).

- [ ] **Step 1: 구현**

```swift
import SwiftUI
import Charts

private let portfolioISOFormatter: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return f
}()

struct PortfolioTab: View {
    @State private var mode: String = "live"

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("모드", selection: $mode) {
                    Text("Live").tag("live")
                    Text("Paper").tag("paper")
                }
                .pickerStyle(.segmented)
                .padding()

                RefreshingList(fetch: {
                    try await APIClient.get("/portfolio/summary", query: ["mode": mode]) as PortfolioSummary
                }) { summary in
                    PortfolioSummaryBody(summary: summary, mode: mode)
                }
                .id(mode)
            }
            .navigationTitle("Portfolio")
        }
    }
}

private struct PortfolioSummaryBody: View {
    let summary: PortfolioSummary
    let mode: String

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 4) {
                    Text("총자산 (USD)").font(.caption).foregroundStyle(.secondary)
                    Text(String(format: "$%.2f", summary.total_equity_usd))
                        .font(.system(size: 34, weight: .bold))
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            if !summary.holdings.isEmpty {
                Section("보유 종목") {
                    Chart(summary.holdings) { h in
                        SectorMark(angle: .value("금액", h.value_usd), innerRadius: .ratio(0.6))
                            .foregroundStyle(by: .value("종목", "\(h.account):\(h.symbol)"))
                    }
                    .frame(height: 200)
                }
            }

            Section("수익률") {
                EquityCurveChart(mode: mode)
                    .frame(height: 160)
            }

            Section("계좌") {
                ForEach(summary.accounts) { account in
                    NavigationLink(value: account.account) {
                        AccountCardView(account: account)
                    }
                }
            }
        }
        .navigationDestination(for: String.self) { accountId in
            TradeHistoryView(mode: mode, account: accountId)
        }
    }
}

private struct AccountCardView: View {
    let account: PortfolioSummary.Account

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Circle().fill(account.connected ? .green : .red).frame(width: 8, height: 8)
                Text(account.account.uppercased()).bold()
            }
            Text("현금 \(String(format: "%.0f", account.cash))  평가금액 \(String(format: "%.0f", account.equity))")
                .font(.caption).foregroundStyle(.secondary)
            if let error = account.error {
                Text(error).font(.caption2).foregroundStyle(.red)
            }
        }
    }
}

private struct EquityCurveChart: View {
    let mode: String
    @State private var points: [PortfolioHistory.Point] = []

    var body: some View {
        Chart(points) { p in
            if let date = portfolioISOFormatter.date(from: p.ts) {
                LineMark(x: .value("날짜", date), y: .value("총자산", p.total_equity_usd))
            }
        }
        .task(id: mode) {
            if let history: PortfolioHistory = try? await APIClient.get(
                "/portfolio/history", query: ["mode": mode, "days": "30"]
            ) {
                points = history.points
            }
        }
    }
}

private struct TradeHistoryView: View {
    let mode: String
    let account: String
    @State private var trades: [PortfolioTrades.Trade] = []

    var body: some View {
        List(trades) { t in
            VStack(alignment: .leading) {
                Text("\(t.symbol ?? "?") \(t.side ?? "")").bold()
                Text("\(t.status) · qty \(t.quantity.map { String(format: "%.2f", $0) } ?? "-")")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("\(account.uppercased()) 거래내역")
        .task {
            if let result: PortfolioTrades = try? await APIClient.get(
                "/portfolio/trades", query: ["mode": mode, "account": account]
            ) {
                trades = result.trades
            }
        }
    }
}
```

- [ ] **Step 2: 커밋**

Task 7에서 xcodegen/빌드 검증 후 전체 한 번에 커밋(아래 Task 7 Step 5).

---

### Task 7: iOS `ContentView.swift` — 탭 개편 (Agents+Bots 통합, Portfolio 배치)

**Files:**
- Modify: `~/seokminal/ios-remote/Seokminal/ContentView.swift`

**Interfaces:**
- Consumes: Task 6의 `PortfolioTab`. 기존 `RefreshingList<T, Content>`(안
  건드림), 기존 `AgentsOverview`/`AllBotsStatus`(안 건드림).
- Produces: 최종 `ContentView` — 2탭(Agents, Portfolio). `PnLTab`/`HLTab`은
  Portfolio로 흡수되어 삭제(죽은 코드 방치 안 함).

- [ ] **Step 1: 전체 교체**

```swift
import SwiftUI

struct ContentView: View {
    var body: some View {
        TabView {
            AgentsBotsTab().tabItem { Label("Agents", systemImage: "chart.bar") }
            PortfolioTab().tabItem { Label("Portfolio", systemImage: "chart.pie") }
        }
    }
}

/// 2개 탭 공통: 로딩/에러/자동새로고침(10초) 뼈대. 화면마다 fetch 클로저만 다르게 줌.
struct RefreshingList<T, Content: View>: View {
    let fetch: () async throws -> T
    @ViewBuilder let content: (T) -> Content

    @State private var data: T?
    @State private var errorText: String?

    var body: some View {
        Group {
            if let data { content(data) }
            else if let errorText { Text(errorText).foregroundStyle(.red).padding() }
            else { ProgressView() }
        }
        .task { await loop() }
    }

    private func loop() async {
        while !Task.isCancelled {
            do { data = try await fetch(); errorText = nil }
            catch { errorText = "\(error)" }
            try? await Task.sleep(nanoseconds: 10_000_000_000)
        }
    }
}

struct AgentsBotsTab: View {
    @State private var segment = 0

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("", selection: $segment) {
                    Text("에이전트").tag(0)
                    Text("봇").tag(1)
                }
                .pickerStyle(.segmented)
                .padding()

                if segment == 0 { OverviewList() } else { BotsList() }
            }
            .navigationTitle(segment == 0 ? "Agents" : "Bots")
        }
    }
}

private struct OverviewList: View {
    var body: some View {
        RefreshingList(fetch: { try await APIClient.get("/agents/overview/all") as AgentsOverview }) { o in
            List {
                Section("합계") {
                    LabeledContent("실행중", value: "\(o.totals.running)/\(o.totals.count)")
                    LabeledContent("실현손익", value: String(format: "%.0f", o.totals.realized_pnl))
                    LabeledContent("수익률", value: String(format: "%.2f%%", o.totals.return_pct))
                }
                Section("에이전트") {
                    ForEach(o.agents) { a in
                        VStack(alignment: .leading) {
                            Text(a.name).bold()
                            Text("\(a.status) · \(a.type) · 손익 \(String(format: "%.0f", a.realized_pnl)) (\(String(format: "%.2f", a.return_pct))%)")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
    }
}

private struct BotsList: View {
    var body: some View {
        RefreshingList(fetch: { try await APIClient.get("/bots/all-live-status") as AllBotsStatus }) { s in
            List(s.bots) { b in
                VStack(alignment: .leading) {
                    HStack {
                        Circle().fill(b.running ? .green : .gray).frame(width: 8, height: 8)
                        Text(b.name).bold()
                    }
                    Text("\(b.position) qty=\(String(format: "%.2f", b.qty))" +
                         (b.unrealized_pnl.map { " · 미실현 \($0)" } ?? ""))
                        .font(.caption).foregroundStyle(.secondary)
                    if let err = b.error {
                        Text(err).font(.caption2).foregroundStyle(.red)
                    }
                }
            }
        }
    }
}
```

- [ ] **Step 2: xcodegen으로 새 파일(`PortfolioView.swift`) 프로젝트에 반영**

```bash
cd ~/seokminal/ios-remote
xcodegen generate
```

- [ ] **Step 3: 시뮬레이터 빌드로 컴파일 검증** (테스트 타겟 없음 — 이게
  이 프로젝트의 최소 검증 수단. 실제 동작 확인은 사용자가 저녁에 폰에
  설치해서 확인)

```bash
xcodebuild -project Seokminal.xcodeproj -scheme Seokminal \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' build
```
Expected: `** BUILD SUCCEEDED **`. 실패 시 에러 메시지 보고 Task 5/6/7의
타입 불일치(특히 Decodable 키 이름, `RefreshingList` 제네릭 사용법) 수정.

- [ ] **Step 4: 커밋**

```bash
cd ~/seokminal/ios-remote
git status  # 이 레포가 git 저장소인지 먼저 확인
git add Seokminal/ContentView.swift Seokminal/PortfolioView.swift \
        Seokminal/APIClient.swift Seokminal/Models.swift project.yml \
        Seokminal.xcodeproj
git commit -m "feat: 탭 개편(Agents+Bots 통합) + Portfolio 탭 추가(라이브/페이퍼, 계좌별 카드, 파이/라인 차트)"
```

(git 저장소가 아니면 커밋 스킵하고 사용자에게 보고 — 이 레포의 버전관리
여부는 이번 조사에서 확인 안 됨)

---

## Self-Review 완료 사항

- **스펙 커버리지:** 스펙의 6개 섹션(아키텍처/컴포넌트/엔드포인트/에러처리/
  iOS/테스트) 전부 Task 1-7에 매핑됨. 단 2곳 스펙 대비 조사 후 변경:
  (1) `jarvis/portfolio/aggregator.py` → `jarvis/broker_readonly/aggregator.py`
  (기존 `jarvis/portfolio`는 이미 다른 도메인(전략배분)이 쓰고 있어 이름
  충돌·경계 혼동 방지), (2) 거래내역 소스를 `oms.list_orders()` → provider별
  `orders_history()`(`order_audit.read_recent` 기반, venue+paper 필터) —
  oms가 HL을 아예 안 쌓고 KR도 live/paper 구분이 없다는 사실을 계획 단계에서
  발견.
- **플레이스홀더 스캔:** TBD/TODO 없음. 모든 스텝에 실행 가능한 실제 코드.
- **타입 일관성:** `HLReadOnlyProvider`/`KISReadOnlyProvider`(Task 1) →
  `PortfolioAggregator`(Task 2, 동일 클래스명으로 import) →
  `snapshot_job`(Task 3, `summary()["total_equity_usd"]` 키 일치) →
  `main.py` 라우트(Task 4, `PortfolioAggregator(mode).summary()`/`.trades
  (account=...)` 시그니처 일치) → iOS `PortfolioSummary`/`PortfolioHistory`/
  `PortfolioTrades`(Task 5, JSON 키 스네이크케이스 그대로 대응) → `PortfolioView.swift`
  (Task 6, 위 타입 그대로 소비) 전 구간 확인.
