# IB 라이브 실행 고리 — 인프라 배지 · 멀티통화 · 게이트 매핑 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스펙의 섹션 2(재인증 UX)·3(멀티통화)·4(게이트 매핑) 중 코드로 구현 가능한 부분을 완성한다. 섹션 1(VM 배포)은 유저 선행 작업이라 이 계획엔 없음.

**Architecture:** (a) `api_server`에 `ibg-controller`의 `/health`를 프록시하는 새 라우터 추가 + `seokminal-dashboard`의 `SettingsDrawer`에 상태 배지 추가(VM 미배포 시 "연결 안 됨"으로 정상 폴백). (b) `backends/ib/order_client.py`·`backends/ib/client.py`의 `Stock()` 생성부에 `exchange`/`currency` 파라미터 추가(기본값 유지, 하위호환). (c) `jarvis/execution/agent_gate.py`의 `PROFILE_TO_STRATEGY` 하드코딩 딕셔너리를 `jarvis/execution/arm.py`와 동일한 패턴(append-only jsonl + 사람 ADMIN 게이트 + 감사로그)으로 교체.

**Tech Stack:** Python 3.14 / FastAPI / pytest(`asyncio_mode="auto"`) / `httpx` / Next.js(dashboard) / vitest / `ib_async`.

**Spec:** `docs/superpowers/specs/2026-09-18-ib-live-execution-design.md`

## Global Constraints

- `asyncio_mode="auto"` — `@pytest.mark.asyncio` 데코레이터 절대 금지 (백엔드 테스트).
- Python 실행: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`.
- 프론트: raw `fetch` 금지, 반드시 `lib/api.ts` 함수 경유. 디자인 토큰만 사용(`bg-bg/panel/panel-2`, `border-border`, `text-text-1/2/3`, `text-accent/pos/neg/warn/info`). `style={{}}` 금지.
- 새 `state_path`-backed 모듈은 그 모듈을 쓰는 **모든** 테스트 파일의 `_isolate_state` 픽스처에 빠짐없이 추가할 것 — 이전 세션에 이걸 빠뜨려 실제 production `jarvis/_state/capital_claims.jsonl`이 두 번 오염된 사고가 있었음. 이번 계획에서 새로 건드리는 상태 파일은 `jarvis/_state/agent_strategy_mapping.jsonl` 하나(Task 5).
- `jarvis/execution/agent_gate.py`의 `AUTONOMY_LEVEL`·`arm.py` 로직은 건드리지 않는다. 최종 라이브 트리거는 여전히 100% 사람 수동.
- CORS: API는 `localhost:3000`만 허용 — 새 엔드포인트도 기존 CORS 설정을 그대로 상속(추가 설정 불필요).

---

### Task 1: 백엔드 IB Gateway 상태 프록시 엔드포인트

**Files:**
- Create: `api_server/routers/ib_gateway.py`
- Modify: `api_server/main.py` (steward_router 등록부 바로 아래, 5415번 줄 부근에 등록 추가)
- Test: `tests/test_ib_gateway_router.py`

**Interfaces:**
- Produces: `GET /ib/gateway/status -> dict` with keys `connected: bool`, `last_auth_ts: str | None`, `next_reset_eta: str | None`, `needs_manual_action: bool`, optional `error: str`. Task 2's frontend consumes this exact shape.

`ibg-controller`의 실제 `/health` JSON 스키마는 VM에 배포되기 전까지 검증 불가(스펙에 명시된 알려진 한계) — 그래서 아래 구현은 여러 후보 필드명(`connected`/`authenticated`, `last_auth_ts`/`lastAuthTime`, `next_reset_eta`/`nextReset`)을 관대하게 매핑하고, 요청 자체가 실패하면(연결 거부·타임아웃·JSON 파싱 실패 등 무엇이든) 안전하게 "연결 안 됨"으로 폴백한다. VM 배포 후 실제 응답을 보고 필드 매핑을 좁히는 건 다음 세션 몫이다.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ib_gateway_router.py
from __future__ import annotations

from fastapi.testclient import TestClient

from api_server.main import app
from api_server.routers import ib_gateway


def _client():
    return TestClient(app, client=("127.0.0.1", 1))


def test_status_reports_connected_when_health_reachable(monkeypatch):
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"connected": True, "last_auth_ts": "2026-09-14T01:00:00Z",
                     "next_reset_eta": "2026-09-21T01:00:00Z"}

    monkeypatch.setattr(ib_gateway.httpx, "get", lambda url, timeout: FakeResp())

    r = _client().get("/ib/gateway/status")

    assert r.status_code == 200
    body = r.json()
    assert body == {
        "connected": True,
        "last_auth_ts": "2026-09-14T01:00:00Z",
        "next_reset_eta": "2026-09-21T01:00:00Z",
        "needs_manual_action": False,
    }


def test_status_falls_back_to_disconnected_when_unreachable(monkeypatch):
    def _raise(url, timeout):
        raise ConnectionError("VM not deployed yet")

    monkeypatch.setattr(ib_gateway.httpx, "get", _raise)

    r = _client().get("/ib/gateway/status")

    assert r.status_code == 200
    body = r.json()
    assert body["connected"] is False
    assert body["needs_manual_action"] is False
    assert body["error"] == "ib_gateway_unreachable"


def test_status_surfaces_needs_manual_action_flag(monkeypatch):
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"authenticated": False, "needs_manual_action": True}

    monkeypatch.setattr(ib_gateway.httpx, "get", lambda url, timeout: FakeResp())

    r = _client().get("/ib/gateway/status")

    body = r.json()
    assert body["connected"] is False
    assert body["needs_manual_action"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ib_gateway_router.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'api_server.routers.ib_gateway'`

- [ ] **Step 3: Write minimal implementation**

```python
# api_server/routers/ib_gateway.py
"""IB Gateway(VM 헤드리스, ibg-controller) 상태 프록시.

ibg-controller의 /health(기본 포트 8080)를 폴링해 대시보드가 읽기 쉬운 형태로
반환한다. VM에 아직 배포 전이거나 컨테이너가 죽어 있어도(연결 거부/타임아웃/
JSON 파싱 실패 등 무엇이든) 500을 내지 않고 connected=False로 정상 폴백한다 —
이 엔드포인트 자체는 인프라 전제 없이 항상 응답 가능해야 함.
"""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/ib", tags=["ib"])


def _health_url() -> str:
    return os.environ.get("IB_GATEWAY_HEALTH_URL", "http://127.0.0.1:8080/health")


@router.get("/gateway/status")
def get_gateway_status() -> dict:
    try:
        resp = httpx.get(_health_url(), timeout=2.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return {
            "connected": False,
            "last_auth_ts": None,
            "next_reset_eta": None,
            "needs_manual_action": False,
            "error": "ib_gateway_unreachable",
        }
    return {
        "connected": bool(data.get("connected", data.get("authenticated", False))),
        "last_auth_ts": data.get("last_auth_ts") or data.get("lastAuthTime"),
        "next_reset_eta": data.get("next_reset_eta") or data.get("nextReset"),
        "needs_manual_action": bool(data.get("needs_manual_action", False)),
    }
```

```python
# api_server/main.py — steward_router 등록부(5414-5415번 줄) 바로 아래에 추가
from api_server.routers.ib_gateway import router as ib_gateway_router
app.include_router(ib_gateway_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ib_gateway_router.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add api_server/routers/ib_gateway.py api_server/main.py tests/test_ib_gateway_router.py
git commit -m "feat: IB Gateway 상태 프록시 엔드포인트 추가 (VM 미배포시 폴백)"
```

---

### Task 2: 프론트엔드 — `lib/api.ts` 함수 + `SettingsDrawer` 배지

**Files:**
- Modify: `lib/api.ts` (파일 끝 근처, `getRiskStatus`/`setKillSwitch` 섹션 바로 아래에 새 섹션 추가)
- Modify: `components/console/SettingsDrawer.tsx`
- Test: `tests/lib/api-ib-gateway.test.ts`

**Interfaces:**
- Consumes: Task 1의 `GET /ib/gateway/status` 응답 형태 — `{connected, last_auth_ts, next_reset_eta, needs_manual_action, error?}`.
- Produces: `getIBGatewayStatus(signal?: AbortSignal): Promise<IBGatewayStatus>` — `SettingsDrawer`가 렌더링에 사용.

- [ ] **Step 1: Write the failing test**

```typescript
// tests/lib/api-ib-gateway.test.ts
import { describe, it, expect, vi, afterEach } from "vitest";
import { getIBGatewayStatus } from "@/lib/api";

describe("getIBGatewayStatus", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns the connected status from the API response", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        connected: true,
        last_auth_ts: "2026-09-14T01:00:00Z",
        next_reset_eta: "2026-09-21T01:00:00Z",
        needs_manual_action: false,
      }),
    } as Response);

    const status = await getIBGatewayStatus();

    expect(status.connected).toBe(true);
    expect(status.needs_manual_action).toBe(false);
  });

  it("surfaces needs_manual_action when reauth is required", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        connected: false,
        last_auth_ts: null,
        next_reset_eta: null,
        needs_manual_action: true,
      }),
    } as Response);

    const status = await getIBGatewayStatus();

    expect(status.connected).toBe(false);
    expect(status.needs_manual_action).toBe(true);
  });

  it("throws when the backend responds with an error", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: async () => ({ detail: "boom" }),
    } as Response);

    await expect(getIBGatewayStatus()).rejects.toThrow();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run tests/lib/api-ib-gateway.test.ts`
Expected: FAIL — `getIBGatewayStatus is not a function` / import error

- [ ] **Step 3: Write minimal implementation**

`lib/api.ts`에 `getRiskStatus`/`setKillSwitch` 섹션(약 2308-2324번 줄) 바로 아래에 추가:

```typescript
// ── IB Gateway 상태 (헤드리스 VM, ibg-controller 프록시) ──────────────────────────

export interface IBGatewayStatus {
  connected: boolean;
  last_auth_ts?: string | null;
  next_reset_eta?: string | null;
  needs_manual_action: boolean;
  error?: string;
}
export async function getIBGatewayStatus(signal?: AbortSignal): Promise<IBGatewayStatus> {
  const r = await fetch(`${API_URL}/ib/gateway/status`, { signal });
  return handleResponse<IBGatewayStatus>(r);
}
```

`components/console/SettingsDrawer.tsx` 수정 — 기존 `getRiskStatus` 로드 로직 옆에 독립적인 IB 상태 로드(리스크 패널이 실패해도 IB 배지는 따로 동작해야 하므로 별도 state/ctrl):

```typescript
// import 줄 교체
import { ApiError, getRiskStatus, setKillSwitch, getIBGatewayStatus, type RiskStatus, type IBGatewayStatus } from "@/lib/api";
```

```typescript
// SettingsDrawer 함수 내부, 기존 useState 선언들 옆에 추가
const [ibStatus, setIbStatus] = useState<IBGatewayStatus | null>(null);
const ibCtrl = useRef<AbortController | null>(null);

const loadIB = useCallback(() => {
  ibCtrl.current?.abort(); const c = new AbortController(); ibCtrl.current = c;
  getIBGatewayStatus(c.signal)
    .then((d) => { if (!c.signal.aborted) setIbStatus(d); })
    .catch(() => { if (!c.signal.aborted) setIbStatus(null); });
}, []);
```

```typescript
// 기존 useEffect(open일 때 load() + 30초 interval) 안에 loadIB()도 같이 호출하도록 확장
useEffect(() => {
  if (!open) return;
  load();
  loadIB();
  const iv = setInterval(() => { load(); loadIB(); }, 30_000);
  return () => { clearInterval(iv); ctrl.current?.abort(); ibCtrl.current?.abort(); };
}, [open, load, loadIB]);
```

```tsx
// 기존 "주문 한도" ApPanel 바로 아래(129번 줄 부근)에 새 패널 추가
<ApPanel>
  <ApPanelHead title="IB Gateway 연결" />
  <div className="p-4">
    {!ibStatus ? (
      <div className="text-[13px] text-ap-ink-3">상태 조회 중…</div>
    ) : (
      <div className="flex items-center gap-2">
        <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${ibStatus.connected ? "bg-ap-up" : "bg-ap-down"}`} />
        <div className="text-[13px]">
          <span className={ibStatus.connected ? "text-ap-up font-semibold" : "text-ap-down font-semibold"}>
            {ibStatus.connected ? "연결됨" : "연결 안 됨"}
          </span>
          {ibStatus.last_auth_ts && (
            <span className="text-ap-ink-3 ml-2">마지막 인증: {ibStatus.last_auth_ts}</span>
          )}
        </div>
      </div>
    )}
    {ibStatus?.needs_manual_action && (
      <p className="text-ap-down text-[11px] mt-2">
        IBKR Mobile 앱에서 재인증 승인 필요
      </p>
    )}
  </div>
</ApPanel>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run tests/lib/api-ib-gateway.test.ts`
Expected: PASS (3 passed)

Then start the dev server and manually verify in the browser (per project convention — no component-level test harness exists for `SettingsDrawer`):

```bash
cd ~/seokminal/seokminal-multi-venue && uvicorn api_server.main:app --timeout-graceful-shutdown 10 &
cd ~/seokminal/seokminal-dashboard && npm run dev &
```

Open `http://localhost:3000/hud/summary` → 설정 아이콘 클릭 → "IB Gateway 연결" 패널이 "연결 안 됨"(빨간 배지, VM 미배포 상태이므로 정상)으로 뜨는지 확인.

- [ ] **Step 5: Commit**

```bash
git add lib/api.ts components/console/SettingsDrawer.tsx tests/lib/api-ib-gateway.test.ts
git commit -m "feat: SettingsDrawer에 IB Gateway 연결 상태 배지 추가"
```

---

### Task 3: `backends/ib/order_client.py` — `exchange`/`currency` 파라미터화

**Files:**
- Modify: `backends/ib/order_client.py:24-39` (`place_order`), `:41-65` (`place_option_order`), `:88-109` (`get_intraday_bars`)
- Test: `tests/test_ib_order_client.py`

**Interfaces:**
- Produces: `place_order(symbol, side, quantity, order_type, limit_price=None, wait_fill=False, exchange="SMART", currency="USD") -> dict`; `place_option_order(..., exchange="SMART", currency="USD") -> dict`; `get_intraday_bars(symbol, bar_size="5 mins", duration="2 D", exchange="SMART", currency="USD") -> list[dict]`. 기본값 동작은 기존과 동일(하위호환) — Task 5·live_router 등 기존 호출부는 수정 불필요.

- [ ] **Step 1: Write the failing test**

`tests/test_ib_order_client.py` 끝에 추가:

```python
async def test_place_order_default_exchange_currency_is_smart_usd():
    fake_ib = FakeIB()
    client = _client(fake_ib)

    await client.place_order(symbol="AAPL", side="BUY", quantity=1, order_type="MARKET")

    assert fake_ib.qualify_calls == [("AAPL", "SMART", "USD")]


async def test_place_order_explicit_eur_currency():
    fake_ib = FakeIB()
    client = _client(fake_ib)

    await client.place_order(symbol="SAP", side="BUY", quantity=1, order_type="MARKET",
                              exchange="IBIS", currency="EUR")

    assert fake_ib.qualify_calls == [("SAP", "IBIS", "EUR")]


async def test_get_intraday_bars_explicit_exchange_currency():
    fake_ib = FakeIB()
    fake_ib._bars = []
    client = _client(fake_ib)

    await client.get_intraday_bars("SAP", exchange="IBIS", currency="EUR")

    assert fake_ib.qualify_calls == [("SAP", "IBIS", "EUR")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ib_order_client.py -q`
Expected: FAIL — `TypeError: place_order() got an unexpected keyword argument 'exchange'`

- [ ] **Step 3: Write minimal implementation**

`backends/ib/order_client.py`의 `place_order` 시그니처와 본문 수정:

```python
    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str,
        limit_price: float | None = None,
        wait_fill: bool = False,
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> dict:
        """Place an order. When ``wait_fill`` is True, wait (briefly) for the
        order to reach a terminal state so the returned dict carries the real
        ``avg_fill_price`` — needed for accurate live P&L on market orders."""
        await self._ensure_connected()
        contract = Stock(symbol, exchange, currency)
        await self._ib.qualifyContractsAsync(contract)
        return await self._place(contract, side, quantity, order_type, limit_price, wait_fill)
```

`place_option_order` 시그니처와 본문 수정:

```python
    async def place_option_order(
        self,
        symbol: str,
        expiry: str,
        strike: float,
        right: str,
        side: str,
        quantity: int,
        order_type: str,
        limit_price: float | None = None,
        wait_fill: bool = False,
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> dict:
        """Place a single-leg option order. ``quantity`` is contract count
        (1 contract = 100 shares of the underlying)."""
        await self._ensure_connected()
        contract = Option(
            symbol=symbol,
            lastTradeDateOrContractMonth=expiry,
            strike=strike,
            right=right,
            exchange=exchange,
            currency=currency,
        )
        await self._ib.qualifyContractsAsync(contract)
        return await self._place(contract, side, quantity, order_type, limit_price, wait_fill)
```

`get_intraday_bars` 시그니처와 본문 수정:

```python
    async def get_intraday_bars(
        self, symbol: str, bar_size: str = "5 mins", duration: str = "2 D",
        exchange: str = "SMART", currency: str = "USD",
    ) -> list[dict]:
        """Recent intraday bars as intraday_score-shaped dicts (t/o/h/l/c/v).
        Reuses this client's IB connection so a live day-trade tick reads data
        and executes over a single session (no source mismatch)."""
        await self._ensure_connected()
        contract = Stock(symbol, exchange, currency)
        await self._ib.qualifyContractsAsync(contract)
        bars = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,
        )
        return [
            {"t": b.date, "o": float(b.open), "h": float(b.high),
             "l": float(b.low), "c": float(b.close), "v": float(b.volume)}
            for b in bars
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ib_order_client.py -q`
Expected: PASS (all tests, existing + 3 new)

- [ ] **Step 5: Commit**

```bash
git add backends/ib/order_client.py tests/test_ib_order_client.py
git commit -m "feat: IBOrderClient에 exchange/currency 파라미터 추가 (EUR/JPY 등 멀티통화 대비, 기본값 SMART/USD 유지)"
```

---

### Task 4: `backends/ib/client.py` — `get_daily_bars`의 `exchange`/`currency` 파라미터화

**Files:**
- Modify: `backends/ib/client.py:109-116` (`get_daily_bars`)
- Test: `tests/test_ib_client.py`

**Interfaces:**
- Produces: `get_daily_bars(symbol, end_date, duration, bar_size=DEFAULT_BAR_SIZE, exchange="SMART", currency="USD") -> list[BarData]`. 기본값 동작 불변.
- 스코프 밖: `get_daily_bars_option`/`get_option_chain`/`get_daily_bars_crypto`는 이번엔 건드리지 않음(옵션/크립토는 EUR/JPY 현물주식 요구사항과 무관 — 실제로 필요해지면 그때 같은 패턴으로 확장).

- [ ] **Step 1: Write the failing test**

`tests/test_ib_client.py`에서 기존 `get_daily_bars` 테스트 블록(약 100-111번 줄) 아래에 추가:

```python
async def test_get_daily_bars_explicit_eur_exchange_currency():
    bar = BarData(date=dt.date(2024, 6, 1), open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0)
    fake_ib = FakeIB(historical_bars=[bar])
    client = IBClient(host="127.0.0.1", port=7497, client_id=1, ib=fake_ib)

    bars = await client.get_daily_bars("SAP", end_date="20240601 23:59:59", duration="1 Y",
                                        exchange="IBIS", currency="EUR")

    assert bars == [bar]
    assert fake_ib.qualify_calls == [("SAP", "IBIS", "EUR")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ib_client.py -q`
Expected: FAIL — `TypeError: get_daily_bars() got an unexpected keyword argument 'exchange'`

- [ ] **Step 3: Write minimal implementation**

```python
    async def get_daily_bars(
        self, symbol: str, end_date: str, duration: str, bar_size: str = DEFAULT_BAR_SIZE,
        exchange: str = "SMART", currency: str = "USD",
    ) -> list[BarData]:
        contract = Stock(symbol, exchange, currency)
        return await self._fetch_bars(
            contract, end_date, duration, bar_size, DAILY_WHAT_TO_SHOW, True,
            f"{symbol} (end_date={end_date!r}, duration={duration!r}, bar_size={bar_size!r})",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_ib_client.py -q`
Expected: PASS (all tests, existing + 1 new)

- [ ] **Step 5: Commit**

```bash
git add backends/ib/client.py tests/test_ib_client.py
git commit -m "feat: IBClient.get_daily_bars에 exchange/currency 파라미터 추가"
```

---

### Task 5: `jarvis/execution/agent_gate.py` — `arm.py` 패턴으로 리팩터

**Files:**
- Modify: `jarvis/execution/agent_gate.py` (전체 재작성)
- Modify: `jarvis/execution/tests/test_agent_gate.py` (전체 재작성 — 기존 `monkeypatch.setitem(ag.PROFILE_TO_STRATEGY, ...)` 3곳을 새 API 호출로 교체)
- Create state file (런타임 생성, 커밋 대상 아님): `jarvis/_state/agent_strategy_mapping.jsonl`

**Interfaces:**
- Consumes: `jarvis.audit.record`, `jarvis.config.state_path`, `jarvis.permissions.{Level, PermissionDenied, Principal, require}`, `jarvis.registry.StrategyRegistry` (`.state(strategy_id) -> dict | None`, `.all_current() -> list[dict]`), `jarvis.agents.{HUMAN_ADMIN, BACKTEST_AGENT}` (테스트에서만).
- Produces: `register_validated_strategy(profile_name: str, strategy_id: str, human: Principal) -> dict`, `unregister_strategy(profile_name: str, human: Principal) -> dict`, `_current_mapping() -> dict[str, str]`. `validation_of(agent: dict) -> dict`와 `enforce_paper(agent: dict) -> tuple[bool, str | None]`는 기존 시그니처·반환 형태 그대로 유지(내부 구현만 교체) — `jarvis/execution/broker_bridge.py` 등 기존 호출부는 수정 불필요.

- [ ] **Step 1: Write the failing test**

`jarvis/execution/tests/test_agent_gate.py` 전체를 아래로 교체:

```python
"""에이전트 ↔ registry 전략 매핑 게이트 테스트.

핵심 계약: profile_name 조회는 agent["type"]만 씀(과거 profile.name/style/
profile_name은 죽은 필드였음) · 매핑 미등록이면 무조건 미검증 ·
등록돼도 registry 상태가 _VALIDATED_STATUSES 밖이면 미검증 ·
매핑 등록/해제는 사람 ADMIN만(arm.py와 동일 패턴, jsonl latest-wins).
"""
from __future__ import annotations

import os

import pytest

from jarvis.agents import BACKTEST_AGENT, HUMAN_ADMIN
from jarvis.execution import agent_gate as ag
from jarvis.permissions import PermissionDenied
from jarvis.registry import StrategyRegistry


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import importlib
    for mod in ("jarvis.audit.log", "jarvis.registry.lifecycle", "jarvis.execution.agent_gate"):
        monkeypatch.setattr(importlib.import_module(mod), "state_path", sp)
    return tmp_path


def _register(sid="kr_dart_buyback_drift_v1"):
    StrategyRegistry().register(sid, name=sid, config={"x": 1})
    return sid


def test_unmapped_type_is_unvalidated():
    v = ag.validation_of({"type": "kr_daytrade"})
    assert v["validated"] is False
    assert v["strategy_id"] is None


def test_profile_name_key_is_type_not_dead_fields(monkeypatch):
    sid = _register()
    ag.register_validated_strategy("kr_daytrade", sid, HUMAN_ADMIN)
    monkeypatch.setattr(
        "jarvis.registry.StrategyRegistry.all_current",
        lambda self: [{"strategy_id": sid, "status": "paper_active"}],
    )
    # profile.name/style/profile_name 세팅해도 무시되고 type만 봐야 함(회귀 방지).
    agent = {
        "type": "kr_daytrade",
        "profile": {"label": "데이트레이딩 (한국주식)", "name": "wrong"},
        "style": "also_wrong",
        "profile_name": "still_wrong",
    }
    v = ag.validation_of(agent)
    assert v["validated"] is True
    assert v["strategy_id"] == sid


def test_mapped_but_registry_status_not_validated(monkeypatch):
    sid = _register()
    ag.register_validated_strategy("kr_daytrade", sid, HUMAN_ADMIN)
    monkeypatch.setattr(
        "jarvis.registry.StrategyRegistry.all_current",
        lambda self: [{"strategy_id": sid, "status": "draft"}],
    )
    v = ag.validation_of({"type": "kr_daytrade"})
    assert v["validated"] is False
    assert "검증 상태 아님" in v["reason"]


def test_enforce_paper_forces_paper_when_unvalidated():
    paper, reason = ag.enforce_paper({"type": "kr_daytrade", "paper": False})
    assert paper is True
    assert reason is not None


def test_enforce_paper_allows_live_when_validated(monkeypatch):
    sid = _register()
    ag.register_validated_strategy("kr_daytrade", sid, HUMAN_ADMIN)
    monkeypatch.setattr(
        "jarvis.registry.StrategyRegistry.all_current",
        lambda self: [{"strategy_id": sid, "status": "paper_active"}],
    )
    paper, reason = ag.enforce_paper({"type": "kr_daytrade", "paper": False})
    assert paper is False
    assert reason is None


def test_already_paper_short_circuits_without_registry_lookup():
    paper, reason = ag.enforce_paper({"type": "kr_daytrade", "paper": True})
    assert paper is True and reason is None


def test_god_mode_bypasses_unvalidated_registry():
    # god_mode=1은 별도 3조건 실적 심사(god_mode.py)를 이미 통과한 것 —
    # registry 미등록이어도(매핑 비어있음) live 허용돼야 함.
    paper, reason = ag.enforce_paper({"type": "kr_daytrade", "paper": False, "god_mode": True})
    assert paper is False and reason is None


def test_register_validated_strategy_requires_human_admin():
    sid = _register()
    with pytest.raises(PermissionDenied):
        ag.register_validated_strategy("kr_daytrade", sid, BACKTEST_AGENT)
    assert ag._current_mapping() == {}


def test_register_validated_strategy_rejects_unregistered_strategy_id():
    r = ag.register_validated_strategy("kr_daytrade", "no_such_strategy", HUMAN_ADMIN)
    assert r["registered"] is False
    assert r["reason"] == "strategy_not_registered"
    assert ag._current_mapping() == {}


def test_unregister_strategy_removes_mapping():
    sid = _register()
    ag.register_validated_strategy("kr_daytrade", sid, HUMAN_ADMIN)
    assert ag._current_mapping() == {"kr_daytrade": sid}

    ag.unregister_strategy("kr_daytrade", HUMAN_ADMIN)

    assert ag._current_mapping() == {}


def test_current_mapping_latest_wins():
    sid1 = _register("strat_a")
    sid2 = _register("strat_b")
    ag.register_validated_strategy("kr_daytrade", sid1, HUMAN_ADMIN)
    ag.register_validated_strategy("kr_daytrade", sid2, HUMAN_ADMIN)

    assert ag._current_mapping() == {"kr_daytrade": sid2}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest jarvis/execution/tests/test_agent_gate.py -q`
Expected: FAIL — `AttributeError: module 'jarvis.execution.agent_gate' has no attribute 'register_validated_strategy'`

- [ ] **Step 3: Write minimal implementation**

`jarvis/execution/agent_gate.py` 전체를 아래로 교체:

```python
"""트레이딩 에이전트 ↔ 전략 registry 게이트.

시스템 최대 모순 해소: 연구 트랙은 BH-FDR·레드팀 통과해야 페이퍼로 가는데,
트레이딩 에이전트는 registry 무관한 교과서 신호(intraday_score·모멘텀)로
실계좌 매매 가능했음. 규칙:

  - 에이전트 전략이 registry 검증 상태가 아니면 → live 주문 차단, 페이퍼 강제.
  - 매핑은 명시적으로만(register_validated_strategy) — 암묵 매칭 금지.
  - 사람 ADMIN만 매핑을 등록/해제할 수 있다(arm.py와 동일 게이트) — append-only
    jsonl(jarvis/_state/agent_strategy_mapping.jsonl)에 latest-wins로 기록.
  - 지금은 매핑이 비어 있음 = 모든 에이전트 미검증 = live 전부 차단(정직한 현주소).
    검증된 전략을 에이전트로 돌리려면 register_validated_strategy 호출 + registry
    상태가 증명해야 함.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from jarvis.audit import record
from jarvis.config import state_path
from jarvis.permissions import Level, PermissionDenied, Principal, require
from jarvis.registry import StrategyRegistry

_MAPPING = "agent_strategy_mapping.jsonl"

# registry에서 "검증됨"으로 인정하는 상태 — paper 단계 이상(사전등록 게이트 통과분)
_VALIDATED_STATUSES = {
    "paper_candidate", "paper_candidate_forward_test_required",
    "paper_active", "micro_live", "live",
}


def _rows() -> list[dict]:
    p = state_path(_MAPPING)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _append(row: dict) -> None:
    os.makedirs(os.path.dirname(state_path(_MAPPING)), exist_ok=True)
    with open(state_path(_MAPPING), "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _current_mapping() -> dict[str, str]:
    """최신 register/unregister 반영한 profile_name → strategy_id 매핑(latest-wins).
    상태 파일이 없으면 빈 딕셔너리 — 기존 PROFILE_TO_STRATEGY={}의 fail-safe 동작 그대로."""
    mapping: dict[str, str] = {}
    for r in _rows():
        name = r.get("profile_name")
        if r.get("action") == "register":
            mapping[name] = r.get("strategy_id")
        elif r.get("action") == "unregister":
            mapping.pop(name, None)
    return mapping


def register_validated_strategy(profile_name: str, strategy_id: str, human: Principal) -> dict:
    """사람 ADMIN만: 에이전트 profile 이름 → registry 전략 매핑 등록.

    등록 시점엔 registry에 strategy_id가 존재하는지만 확인한다(상태값 검증은
    안 함) — validation_of()가 호출 시점마다 실시간으로 상태를 재검증하므로."""
    if not human.is_human or human.level < Level.ADMIN_HUMAN_ONLY:
        record({"layer": "agent_gate", "action": "register_validated_strategy",
                "profile_name": profile_name, "strategy_id": strategy_id,
                "agent": human.name, "result": "denied", "reason": "not_human_admin"})
        raise PermissionDenied("register_validated_strategy는 사람 ADMIN만 가능")
    require(human, "approve_live_promotion", strategy_id)
    if StrategyRegistry().state(strategy_id) is None:
        record({"layer": "agent_gate", "action": "register_validated_strategy",
                "profile_name": profile_name, "strategy_id": strategy_id,
                "result": "denied", "reason": "strategy_not_registered"})
        return {"profile_name": profile_name, "strategy_id": strategy_id,
                "registered": False, "reason": "strategy_not_registered"}
    row = {"profile_name": profile_name, "strategy_id": strategy_id, "action": "register",
           "registered_by": human.name,
           "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    _append(row)
    record({"layer": "agent_gate", "action": "register_validated_strategy",
            "profile_name": profile_name, "strategy_id": strategy_id,
            "registered_by": human.name, "result": "registered"})
    return {"profile_name": profile_name, "strategy_id": strategy_id, "registered": True}


def unregister_strategy(profile_name: str, human: Principal) -> dict:
    """사람만: 매핑 해제(대칭 롤백, arm.py의 disarm()과 동일하게 가벼운 게이트)."""
    if not human.is_human:
        raise PermissionDenied("unregister_strategy는 사람만")
    row = {"profile_name": profile_name, "strategy_id": None, "action": "unregister",
           "registered_by": human.name,
           "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    _append(row)
    record({"layer": "agent_gate", "action": "unregister_strategy",
            "profile_name": profile_name, "registered_by": human.name, "result": "unregistered"})
    return {"profile_name": profile_name, "registered": False}


def validation_of(agent: dict) -> dict:
    """에이전트의 전략 검증 상태. 반환: {validated, strategy_id, reason}."""
    # agent["type"]이 유일한 실제 키(AGENT_PROFILES 인덱스와 동일) — profile.name/style/
    # profile_name은 어디서도 채워지지 않는 죽은 필드였음(항상 빈 문자열 → 매핑 영구 미스).
    profile_name = str(agent.get("type") or "")
    sid = _current_mapping().get(profile_name)
    if not sid:
        return {"validated": False, "strategy_id": None,
                "reason": "registry 미등록 전략(교과서 신호) — 검증 트랙 통과 이력 없음"}
    try:
        for r in StrategyRegistry().all_current():
            if r["strategy_id"] == sid:
                ok = r["status"] in _VALIDATED_STATUSES
                return {"validated": ok, "strategy_id": sid,
                        "reason": f"registry {r['status']}" + ("" if ok else " — 검증 상태 아님")}
    except Exception as exc:  # noqa: BLE001
        return {"validated": False, "strategy_id": sid, "reason": f"registry 조회 실패: {exc}"}
    return {"validated": False, "strategy_id": sid, "reason": "registry에 없음"}


def enforce_paper(agent: dict) -> tuple[bool, str | None]:
    """live 요청 에이전트가 미검증이면 페이퍼 강제.

    God Mode(agent["god_mode"]) 승급 에이전트는 registry 트랙과 무관한 별도
    3조건 실적 심사(api_server/god_mode.py)를 이미 통과했으므로 여기서 면제.

    반환: (paper 최종값, 차단 사유 또는 None). 감사 로그는 호출부가 남김.
    """
    paper = bool(agent.get("paper", True))
    if paper:
        return True, None
    if agent.get("god_mode"):
        return False, None
    v = validation_of(agent)
    if v["validated"]:
        return False, None
    return True, f"live 차단 → 페이퍼 강제: {v['reason']}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest jarvis/execution/tests/test_agent_gate.py -q`
Expected: PASS (13 passed)

Then confirm no other test file still references the removed `PROFILE_TO_STRATEGY` module attribute:

Run: `grep -rn "PROFILE_TO_STRATEGY" --include="*.py" .`
Expected: no matches (if any turn up outside `agent_gate.py`'s own docstring history, update that call site to use `register_validated_strategy`/`_current_mapping` instead before proceeding).

Then run the full test suite once to confirm no other regression (this module is imported by `broker_bridge.py`/`live_router.py`):

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/ jarvis/ -q`
Expected: same pass/fail counts as the pre-existing baseline, plus these new passes — no new failures introduced by this task.

- [ ] **Step 5: Commit**

```bash
git add jarvis/execution/agent_gate.py jarvis/execution/tests/test_agent_gate.py
git commit -m "refactor: agent_gate.py를 arm.py 패턴(jsonl+ADMIN게이트+감사로그)으로 전환"
```

---

## Self-Review

**Spec coverage:**
- 섹션 2 (재인증 UX) → Task 1(백엔드 프록시) + Task 2(프론트 배지). 커버됨.
- 섹션 3 (멀티통화/멀티마켓) → Task 3(`order_client.py`) + Task 4(`client.py`). 스펙이 명시적으로 스코프 밖에 둔 심볼→거래소 매핑 테이블은 만들지 않음(계획에도 없음, 의도된 누락). `capital_envelope.pool_limit`의 단일통화 가정은 스펙이 이번 라운드에서 그대로 두기로 명시한 known ceiling — 이 계획에도 태스크 없음(의도된 누락).
- 섹션 4 (게이트 매핑) → Task 5. `AUTONOMY_LEVEL`/`arm.py`는 스펙 지시대로 건드리지 않음.
- 섹션 1 (VM 배포) → 계획에 태스크 없음, 아래 "유저 선행 작업" 체크리스트로만 명시(의도된 스코프 제외).

**Placeholder scan:** "TBD"/"나중에"/"적절히 처리" 패턴 없음. 모든 스텝에 실행 가능한 실제 코드·명령어 포함.

**Type consistency:** `IBGatewayStatus`(TypeScript)와 `get_gateway_status()`(Python dict)의 키가 정확히 일치(`connected`/`last_auth_ts`/`next_reset_eta`/`needs_manual_action`/`error`). `place_order`/`place_option_order`/`get_intraday_bars`/`get_daily_bars`의 `exchange`/`currency` 파라미터명·기본값이 Task 3·4 전체에서 일관됨. `register_validated_strategy`/`unregister_strategy`/`_current_mapping`의 시그니처가 Task 5 코드 블록과 테스트 블록 사이에서 일치함.

---

## 유저 선행 작업 체크리스트 (이 계획의 범위 밖 — Claude가 실행 불가)

스펙 섹션 1의 인프라 이전 작업. 아래가 완료되기 전까지 Task 1의 엔드포인트는 `connected: false`로 정상 동작(폴백)하며, 이는 의도된 동작이다:

- [ ] Vultr VM에 `gnzsnz/ib-gateway-docker` + `ibg-controller`(https://github.com/code-hustler-ft3d/ibg-controller) 배포
- [ ] IBKR 계정 2FA를 IBKR Mobile 푸시 → TOTP(인증앱)로 전환 시도(지역별 자격요건 직접 확인)
- [ ] IB API 자격증명을 VM 환경변수(`IB_HOST`/`IB_PORT` 등)로 등록, `api_server`가 그 VM을 바라보도록 `IB_GATEWAY_HEALTH_URL` 환경변수 설정
- [ ] VM 배포 후 `ibg-controller`의 실제 `/health` 응답 스키마를 확인 → Task 1의 관대한 필드 매핑(`connected`/`authenticated` 등 후보들)을 실제 스키마에 맞게 좁히는 후속 작업 필요할 수 있음(다음 세션)
