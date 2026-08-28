# Live Execution Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `jarvis/fusion/`'s validated signal-fusion engine into the existing arm/AUTONOMY_LEVEL/broker_bridge gate stack so armed+GO strategies can route real orders — replacing the from-scratch `jarvis/execution/ensemble.py` — and close the `broker_bridge.py` gap where it never checked `AUTONOMY_LEVEL` before dispatching.

**Architecture:** New `jarvis/execution/edge_providers.py` maps strategy_id → arm_criteria-compatible edge function (explicit registry, no implicit matching — same convention as `jarvis/fusion/adapters/__init__.py`). New `jarvis/execution/live_router.py` calls `fusion.collect_signals()` → `FusionEngine.fuse()` → for each fused instrument, keeps only contributions from strategies that are both `is_armed()` and `edge_go()` (Tier B alone can never trigger, since only registered adapters produce signals and only armed+GO ones survive the filter) → builds an order sized by `capital_limit * confidence * (1.3 if n_strategies>=2)` → `broker_bridge.route_order()`. `broker_bridge.route_order()` gets a `live_execution_enabled()` check at its top (the gap fix). `research/lab/service.py` calls `live_router.route_all()` on the same 6h throttle pattern as `_warm_edge()`.

**Tech Stack:** Python 3.14, pytest (`asyncio_mode="auto"` — never use `@pytest.mark.asyncio`), existing `jarvis.fusion`/`jarvis.execution`/`backends.kis` modules (no new dependencies).

**Spec:** `docs/superpowers/specs/2026-08-26-live-execution-router-design.md`

## Global Constraints

- `jarvis/execution/arm_criteria.py` is frozen (2026-07-04) — do not modify it.
- Tier B (draft status + real data, no human arm) can never trigger a trade alone — at least one armed+GO contributor must share the fused direction.
- `arm()` stays human-ADMIN-only — this plan does not automate arming.
- `AUTONOMY_LEVEL` (default 5) `< MIN_LIVE_LEVEL` (6) must BLOCK `broker_bridge.route_order()` even when a strategy is armed.
- Python: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3` for all test runs.
- No new pip dependencies. Price lookups reuse `backends.kis.client.KISClient.get_daily_price` (the same pattern `place_test_order.py` already uses) — no new quote infra.

## Correction vs. the spec doc (found while reading the actual code — record here, not by re-editing the already-approved spec)

1. **Price lookup**: the spec assumed "재사용" of an existing broker-client price function but no live quote function exists anywhere in the repo (`grep` confirmed). The actual reusable pattern is `KISClient(app_key=KIS_APP_KEY, app_secret=KIS_APP_SECRET).get_daily_price(code, start, end)` → last row's `stck_clpr` field, exactly as `place_test_order.py:48-56` already does (quotation endpoints always use the real-domain key pair regardless of mock/live order routing). Task 3 implements this as `_kr_last_close()`.
2. **`order["paper"]` must be explicitly `False`**: `broker_bridge.route_order()` defaults `paper = bool(order.get("paper", True))` — if the new router omits this key, every order silently simulates forever even after all three gates (arm/AUTONOMY_LEVEL/arm_criteria GO) open. This is a real router, so `_build_order()` sets `"paper": False` explicitly.
3. **`jarvis.config.AUTONOMY_LEVEL` is a frozen module-level constant** (read from `os.environ` once at import), not re-read per call. Adding the gate check to `route_order()` will break all 5 existing `tests/test_broker_bridge.py` tests unless they explicitly allow it — Task 2 adds an autouse "allow by default" fixture to that test file so existing tests keep their original intent, and the one new regression test overrides it to prove the block.
4. **`RiskAdjustedVoting.weights()` returns weight 0 for every strategy when every strategy's `StrategyPerf.score` is 0** (`total <= 0` branch in `jarvis/fusion/weighting.py`) — which is the real state today for `kr_dart_buyback_drift_v1` (no closed trades yet in its paper ledger). When that happens `FusionEngine.fuse()` produces `direction=0` and `route_all()` skips the instrument *before* even checking `armed_backers` — so today, even once a strategy clears every other gate, it will not route until it has ≥2 closed paper trades. This isn't a bug (it's `fusion`'s intentional "no track record = no vote" design) but it's a fourth structural reason nothing routes yet, on top of the three human gates. Flagged for the user in the final summary, not something this plan changes.

---

### Task 1: `jarvis/execution/edge_providers.py` — explicit strategy_id → edge-provider registry

**Files:**
- Create: `jarvis/execution/edge_providers.py`
- Test: `tests/test_edge_providers.py`

**Interfaces:**
- Consumes: `jarvis.execution.arm_criteria.evaluate(edge: dict, paper_months: float) -> dict` (existing, frozen — returns `{"decision": "GO"|"WAIT"|"KILL", "reasons": [...]}`), `research.paper.buyback_edge.edge_status() -> dict` (existing), `research.paper.buyback_config.FROZEN_AT` (existing, `"2026-07-02"`).
- Produces: `EDGE_PROVIDERS: dict[str, Callable[[], tuple[dict, float]]]`, `EDGE_PROVIDER_VENUE: dict[str, str]`, `edge_go(strategy_id: str) -> bool` — consumed by Task 3's `live_router.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_edge_providers.py
"""edge_providers — 전략별 arm_criteria 호환 GO 판정. 미등록 전략은 항상 False(정직한 기본값)."""
from __future__ import annotations

from jarvis.execution import edge_providers as ep

_GOOD_EDGE = {"status": "ok", "oos_months": 6, "oos_in_envelope": 5}  # ratio 5/6 >= 2/3
_BAD_EDGE = {"status": "ok", "oos_months": 6, "oos_in_envelope": 1}   # ratio 1/6 < kill threshold


def test_unregistered_strategy_always_false():
    assert ep.edge_go("no_such_strategy") is False


def test_buyback_go_when_edge_and_paper_months_sufficient(monkeypatch):
    monkeypatch.setattr("research.paper.buyback_edge.edge_status", lambda: _GOOD_EDGE)
    monkeypatch.setattr("research.paper.buyback_config.FROZEN_AT", "2020-01-01")
    assert ep.edge_go("kr_dart_buyback_drift_v1") is True


def test_buyback_not_go_when_edge_bad(monkeypatch):
    monkeypatch.setattr("research.paper.buyback_edge.edge_status", lambda: _BAD_EDGE)
    monkeypatch.setattr("research.paper.buyback_config.FROZEN_AT", "2020-01-01")
    assert ep.edge_go("kr_dart_buyback_drift_v1") is False


def test_buyback_not_go_when_paper_months_insufficient():
    # FROZEN_AT 실제값 그대로 — 오늘(2026-08) 기준 6개월 구조적 미달([[project_live_execution_bridge_08-25]])
    assert ep.edge_go("kr_dart_buyback_drift_v1") is False


def test_venue_mapping_explicit():
    assert ep.EDGE_PROVIDER_VENUE["kr_dart_buyback_drift_v1"] == "KR"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_edge_providers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jarvis.execution.edge_providers'`

- [ ] **Step 3: Write the implementation**

```python
# jarvis/execution/edge_providers.py
"""전략별 arm_criteria 호환 edge 판정 프로바이더 — 명시 레지스트리.

fusion/adapters/__init__.py의 "암묵 매칭 금지, 명시적 매핑" 원칙과 동일.
edge provider 없는 전략은 항상 GO 거부(정직한 기본값) — tsmom/turn-of-month는
아직 arm_criteria 호환 edge 함수가 없어 자동 배제(provider 추가하면 재작업 없이 편입).
"""
from __future__ import annotations

import datetime as _dt
from typing import Callable

EdgeProviderFn = Callable[[], tuple[dict, float]]  # -> (edge_dict, paper_months)
EDGE_PROVIDERS: dict[str, EdgeProviderFn] = {}

# venue는 registry.asset_class로 못 뗌 — 전부 None(08-26 확인, 아무도 안 채움).
EDGE_PROVIDER_VENUE: dict[str, str] = {}


def _buyback_edge_provider() -> tuple[dict, float]:
    from research.paper import buyback_config as CFG
    from research.paper.buyback_edge import edge_status
    s = edge_status()
    months = (_dt.date.today() - _dt.date.fromisoformat(CFG.FROZEN_AT)).days / 30.0
    return s, round(months, 1)


EDGE_PROVIDERS["kr_dart_buyback_drift_v1"] = _buyback_edge_provider
EDGE_PROVIDER_VENUE["kr_dart_buyback_drift_v1"] = "KR"


def edge_go(strategy_id: str) -> bool:
    """arm_criteria GO 여부. provider 없는 전략은 항상 False."""
    fn = EDGE_PROVIDERS.get(strategy_id)
    if fn is None:
        return False
    from jarvis.execution.arm_criteria import evaluate
    edge, months = fn()
    return evaluate(edge, months).get("decision") == "GO"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_edge_providers.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add jarvis/execution/edge_providers.py tests/test_edge_providers.py
git commit -m "feat: edge_providers — arm_criteria 호환 GO 판정 명시 레지스트리"
```

---

### Task 2: `broker_bridge.py` — enforce the `AUTONOMY_LEVEL` gate `route_order()` was missing

**Files:**
- Modify: `jarvis/execution/broker_bridge.py:1-75` (add import + gate check at top of `route_order()`)
- Modify: `tests/test_broker_bridge.py` (add autouse "allow by default" fixture + one regression test)

**Interfaces:**
- Consumes: `jarvis.config.live_execution_enabled() -> bool`, `jarvis.config.AUTONOMY_LEVEL: int`, `jarvis.config.MIN_LIVE_LEVEL: int` (all existing, unchanged).
- Produces: `broker_bridge.route_order()` now raises `BrokerOrderRejected` immediately when `live_execution_enabled()` is False — consumed by Task 3's `live_router.route_all()` (already catches `BrokerOrderRejected` and records it in `blocked`).

- [ ] **Step 1: Write the failing regression test**

Add to `tests/test_broker_bridge.py` (after the existing fixtures, before `_kr_order`):

```python
@pytest.fixture(autouse=True)
def _allow_live_execution(monkeypatch):
    """기본값: 게이트 통과. 개별 테스트가 False로 덮어쓰면 그 테스트만 차단됨."""
    monkeypatch.setattr(bb, "live_execution_enabled", lambda: True)
```

Add at the end of the file:

```python
def test_blocked_when_autonomy_level_insufficient(monkeypatch):
    monkeypatch.setattr(bb, "live_execution_enabled", lambda: False)
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "k")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "s")
    monkeypatch.setenv("KIS_MOCK_CANO", "c")
    monkeypatch.setenv("KIS_ACNT_PRDT_CD", "01")
    with pytest.raises(bb.BrokerOrderRejected, match="live execution disabled"):
        bb.route_order(_kr_order())
```

- [ ] **Step 2: Run tests to verify the new test fails**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_broker_bridge.py -v`
Expected: `test_blocked_when_autonomy_level_insufficient` FAILS (no exception raised — the order actually goes through since the gate doesn't exist yet). The other 5 pre-existing tests still PASS (the autouse fixture is a no-op until the gate exists).

- [ ] **Step 3: Add the gate check to `route_order()`**

In `jarvis/execution/broker_bridge.py`, change:

```python
from backends.kis.order_client import KISOrderClient
from jarvis.audit import record
from live_engine.risk_guard import DailyLossLimitBreached, RiskConfig, RiskViolation, validate_order
```

to:

```python
from backends.kis.order_client import KISOrderClient
from jarvis.audit import record
from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
from live_engine.risk_guard import DailyLossLimitBreached, RiskConfig, RiskViolation, validate_order
```

And change the top of `route_order()` from:

```python
def route_order(order: dict) -> dict:
    """order: {venue: KR|HL, symbol, side, quantity, order_type, price, paper,
    client_order_id}. 반환: place_order 결과 dict. 실패 시 BrokerOrderRejected."""
    venue = order["venue"]
```

to:

```python
def route_order(order: dict) -> dict:
    """order: {venue: KR|HL, symbol, side, quantity, order_type, price, paper,
    client_order_id}. 반환: place_order 결과 dict. 실패 시 BrokerOrderRejected."""
    if not live_execution_enabled():
        reason = f"AUTONOMY_LEVEL={AUTONOMY_LEVEL} < MIN_LIVE_LEVEL={MIN_LIVE_LEVEL}"
        record({"layer": "broker_bridge", "action": "route_order", "venue": order.get("venue"),
                "symbol": order.get("symbol"), "result": "autonomy_blocked", "reason": reason})
        raise BrokerOrderRejected(f"live execution disabled ({reason})")
    venue = order["venue"]
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_broker_bridge.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add jarvis/execution/broker_bridge.py tests/test_broker_bridge.py
git commit -m "fix: broker_bridge.route_order() — AUTONOMY_LEVEL 게이트 미체크 구멍 메움"
```

---

### Task 3: `jarvis/execution/live_router.py` — replace `ensemble.py` with the fusion-based router

**Files:**
- Create: `jarvis/execution/live_router.py`
- Test: `tests/test_live_router.py`
- Delete: `jarvis/execution/ensemble.py`, `tests/test_ensemble.py` (confirmed via `grep` — referenced nowhere else in the repo)

**Interfaces:**
- Consumes: `jarvis.fusion.providers.collect_signals(as_of: str) -> tuple[list[StrategySignal], list[dict]]`, `jarvis.fusion.performance.perf_for(strategy_id: str) -> StrategyPerf`, `jarvis.fusion.fusion.FusionEngine(scheme=...).fuse(signals, perfs, as_of) -> list[FusionSignal]` (all existing, unchanged), `jarvis.execution.arm.is_armed(strategy_id) -> bool`, `jarvis.execution.arm.arm_state(strategy_id) -> dict | None` (existing), `jarvis.execution.edge_providers.edge_go(strategy_id) -> bool`, `jarvis.execution.edge_providers.EDGE_PROVIDER_VENUE: dict[str, str]` (Task 1), `jarvis.execution.broker_bridge.route_order(order: dict) -> dict` / `broker_bridge.BrokerOrderRejected` (Task 2).
- Produces: `live_router.route_all(as_of: str = "") -> dict` (`{"as_of", "routed": [...], "blocked": [...], "skipped": [...]}`) — consumed by Task 4's `research/lab/service.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_live_router.py
"""live_router.route_all — armed+GO 기여자 없으면 절대 트리거 안 함(Tier B 단독금지
회귀, ensemble.py의 test_tier_b_alone_never_triggers 후신). armed+GO 있으면 route,
2개 이상 동일방향 동의시 부스트, broker_bridge 예외는 blocked에 기록하고 계속 진행."""
from __future__ import annotations

import os

import pytest

from jarvis.agents import HUMAN_ADMIN
from jarvis.execution import arm as arm_mod
from jarvis.execution import live_router
from jarvis.fusion import providers as fusion_providers
from jarvis.fusion.types import StrategyPerf, StrategySignal
from jarvis.registry import Status, StrategyRegistry

SID = "kr_dart_buyback_drift_v1"
SID2 = "kr_turn_of_month_v1_PORTFOLIO"


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import importlib
    for mod in ("jarvis.audit.log", "jarvis.registry.lifecycle", "jarvis.execution.arm"):
        monkeypatch.setattr(importlib.import_module(mod), "state_path", sp)
    fusion_providers.PROVIDER_REGISTRY.clear()
    yield tmp_path
    fusion_providers.PROVIDER_REGISTRY.clear()


def _register_paper_active(sid):
    reg = StrategyRegistry()
    reg.register(sid, name=sid, config={})
    for s in (Status.DATA_AUDIT_PASSED, Status.BACKTESTED, Status.WATCHLIST,
              Status.PAPER_CANDIDATE, Status.PAPER_ACTIVE):
        reg.transition(sid, s, "t")
    return reg


def _arm(sid, capital=1_000_000):
    arm_mod.arm(sid, HUMAN_ADMIN, capital_limit=capital, paper_months=12)


def _signal(sid, direction, instrument="005930", strength=1.0):
    fusion_providers.PROVIDER_REGISTRY[sid] = lambda as_of="": [
        StrategySignal(strategy_id=sid, instrument=instrument, direction=direction, strength=strength)
    ]


def _flat_perf(monkeypatch):
    """모든 전략에 동일 양(+) 점수 부여 — weighting.py는 전 전략 score=0이면
    weight=0/net=0/direction=0이 되어 armed_backers 체크까지 못 감(실서비스에서도
    실제로 그런 상태 — 이건 fusion 로직 검증이 아니라 armed 필터 검증이 목적이므로 고정값으로 우회)."""
    monkeypatch.setattr(live_router, "perf_for", lambda sid: StrategyPerf(
        strategy_id=sid, score=1.0, sharpe=1.0, volatility=0.1,
        observation_count=30, underpowered=False, source="test"))


def test_no_armed_backer_never_routes(monkeypatch):
    _register_paper_active(SID)
    _signal(SID, 1)
    _flat_perf(monkeypatch)
    monkeypatch.setattr(live_router, "edge_go", lambda sid: True)
    r = live_router.route_all()
    assert r["routed"] == []
    assert r["blocked"][0]["reason"] == "no_armed_go_backer"


def test_armed_but_not_go_never_routes(monkeypatch):
    _register_paper_active(SID)
    _arm(SID)
    _signal(SID, 1)
    _flat_perf(monkeypatch)
    monkeypatch.setattr(live_router, "edge_go", lambda sid: False)
    r = live_router.route_all()
    assert r["routed"] == []
    assert r["blocked"][0]["reason"] == "no_armed_go_backer"


def test_armed_and_go_routes_with_paper_false(monkeypatch):
    _register_paper_active(SID)
    _arm(SID, capital=1_000_000)
    _signal(SID, 1)
    _flat_perf(monkeypatch)
    monkeypatch.setattr(live_router, "edge_go", lambda sid: True)
    monkeypatch.setattr(live_router, "_kr_last_close", lambda code: 70000.0)
    calls = []
    monkeypatch.setattr(live_router.broker_bridge, "route_order",
                         lambda o: calls.append(o) or {"status": "submitted"})
    r = live_router.route_all()
    assert len(r["routed"]) == 1
    assert calls[0] == {"venue": "KR", "symbol": "005930", "side": "BUY",
                         "quantity": 14, "order_type": "MARKET", "price": 70000.0,
                         "paper": False, "strategy_id": SID}


def test_broker_rejection_recorded_in_blocked_and_continues(monkeypatch):
    _register_paper_active(SID)
    _arm(SID, capital=1_000_000)
    _signal(SID, 1)
    _flat_perf(monkeypatch)
    monkeypatch.setattr(live_router, "edge_go", lambda sid: True)
    monkeypatch.setattr(live_router, "_kr_last_close", lambda code: 70000.0)

    def _reject(o):
        raise live_router.broker_bridge.BrokerOrderRejected("risk violation")
    monkeypatch.setattr(live_router.broker_bridge, "route_order", _reject)
    r = live_router.route_all()
    assert r["routed"] == []
    assert r["blocked"][0]["reason"] == "risk violation"


def test_two_agreeing_strategies_boost_size(monkeypatch):
    _register_paper_active(SID)
    _arm(SID, capital=1_000_000)
    _register_paper_active(SID2)
    _arm(SID2, capital=1_000_000)
    _signal(SID, 1)
    fusion_providers.PROVIDER_REGISTRY[SID2] = lambda as_of="": [
        StrategySignal(strategy_id=SID2, instrument="005930", direction=1, strength=1.0)
    ]
    _flat_perf(monkeypatch)
    monkeypatch.setattr(live_router, "edge_go", lambda sid: True)
    monkeypatch.setattr(live_router, "_kr_last_close", lambda code: 70000.0)
    monkeypatch.setitem(live_router.EDGE_PROVIDER_VENUE, SID2, "KR")
    calls = []
    monkeypatch.setattr(live_router.broker_bridge, "route_order",
                         lambda o: calls.append(o) or {"status": "submitted"})
    r = live_router.route_all()
    assert len(r["routed"]) == 1
    assert calls[0]["quantity"] > 14  # boosted (1.3x) vs single-strategy baseline of 14


def test_capital_too_small_for_one_share_is_blocked(monkeypatch):
    _register_paper_active(SID)
    _arm(SID, capital=100)  # 100원 / 70000원 주가 = 0주
    _signal(SID, 1)
    _flat_perf(monkeypatch)
    monkeypatch.setattr(live_router, "edge_go", lambda sid: True)
    monkeypatch.setattr(live_router, "_kr_last_close", lambda code: 70000.0)
    r = live_router.route_all()
    assert r["routed"] == []
    assert r["blocked"][0]["reason"] == "unpriceable_or_too_small"


def test_no_signals_returns_empty_note():
    r = live_router.route_all()
    assert r["routed"] == [] and r["blocked"] == []
    assert "note" in r
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_live_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jarvis.execution.live_router'`

- [ ] **Step 3: Write the implementation**

```python
# jarvis/execution/live_router.py
"""fusion 합성신호 → armed+GO 필터 → broker_bridge 실주문. ensemble.py 대체
(신호결합 로직은 재구현하지 않고 이미 검증된 jarvis/fusion/을 그대로 소비).

불변식: armed+GO 기여자가 최소 1개, 같은 방향으로 있어야만 트레이드 성립
(Tier B — draft 상태 후보 — 단독 트리거 절대 불가. 애초에 fusion PROVIDER_REGISTRY에
adapter가 등록된 전략만 신호를 내므로 draft 후보는 신호 자체가 안 생김).
포지션사이징은 armed 전략의 capital_limit(사람이 arm() 때 지정)만 사용 —
jarvis/portfolio/(역변동성+상관페널티 배분)는 미편입. armed 전략 2개+가 동시에
운용되기 시작하면 그때 편입 검토.
# ponytail: 단일-capital_limit 사이징. 배분 최적화는 armed 전략 2개+ 되면 추가.
"""
from __future__ import annotations

from jarvis.execution import broker_bridge
from jarvis.execution.arm import arm_state, is_armed
from jarvis.execution.edge_providers import EDGE_PROVIDER_VENUE, edge_go
from jarvis.fusion.fusion import FusionEngine
from jarvis.fusion.performance import perf_for
from jarvis.fusion.providers import collect_signals

BOOST_MULTIPLIER = 1.3


def _kr_last_close(code: str) -> float | None:
    """최근 종가(quotation 엔드포인트는 mock/실전 구분 없이 실전 앱키 사용 —
    place_test_order.py와 동일 패턴). 크레덴셜 없거나 데이터 없으면 None."""
    import datetime as _dt
    import os
    from backends.kis.client import KISClient

    app_key = os.environ.get("KIS_APP_KEY", "")
    app_secret = os.environ.get("KIS_APP_SECRET", "")
    if not app_key or not app_secret:
        return None
    client = KISClient(app_key=app_key, app_secret=app_secret)
    today = _dt.date.today()
    start = (today - _dt.timedelta(days=10)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    rows = client.get_daily_price(code, start, end)
    if not rows:
        return None
    return float(rows[-1]["stck_clpr"])


def _build_order(fs, capital: float, backer_strategy_id: str) -> dict | None:
    """가격 못 구하거나 1주도 못 사면 None(호출부가 blocked 처리).
    paper=False 명시 — broker_bridge.route_order 기본값이 True라, 생략하면
    게이트가 다 열려도 계속 페이퍼로만 나감(실거래 라우터의 핵심 전제)."""
    venue = EDGE_PROVIDER_VENUE.get(backer_strategy_id)
    side = "BUY" if fs.direction == 1 else "SELL"
    if venue != "KR":
        return None  # HL 등 다른 venue의 edge provider 생기면 그때 분기 추가
    price = _kr_last_close(fs.instrument)
    if price is None or price <= 0:
        return None
    quantity = int(capital // price)
    if quantity < 1:
        return None
    return {"venue": "KR", "symbol": fs.instrument, "side": side, "quantity": quantity,
            "order_type": "MARKET", "price": price, "paper": False,
            "strategy_id": backer_strategy_id}


def route_all(as_of: str = "") -> dict:
    """fusion 합성신호 전체를 armed+GO 필터 후 라우팅. 반환: {as_of, routed, blocked, skipped}."""
    signals, skipped = collect_signals(as_of)
    if not signals:
        return {"as_of": as_of, "routed": [], "blocked": [], "skipped": skipped,
                "note": "fusion-eligible 신호 없음"}
    perfs = {s.strategy_id: perf_for(s.strategy_id) for s in signals}
    fused = FusionEngine().fuse(signals, perfs, as_of)

    routed: list[dict] = []
    blocked: list[dict] = []
    for fs in fused:
        if fs.direction == 0:
            continue
        armed_backers = [c for c in fs.contributions
                          if c.direction == fs.direction
                          and is_armed(c.strategy_id)
                          and edge_go(c.strategy_id)]
        if not armed_backers:
            blocked.append({"instrument": fs.instrument, "reason": "no_armed_go_backer",
                             "n_strategies": fs.n_strategies})
            continue
        lead = armed_backers[0]
        base_capital = min(arm_state(b.strategy_id)["capital_limit"] for b in armed_backers)
        size_mult = (BOOST_MULTIPLIER if fs.n_strategies >= 2 else 1.0) * fs.confidence
        order = _build_order(fs, base_capital * size_mult, lead.strategy_id)
        if order is None:
            blocked.append({"instrument": fs.instrument, "reason": "unpriceable_or_too_small"})
            continue
        try:
            result = broker_bridge.route_order(order)
            routed.append({"instrument": fs.instrument, "result": result})
        except broker_bridge.BrokerOrderRejected as exc:
            blocked.append({"instrument": fs.instrument, "reason": str(exc)})
    return {"as_of": as_of, "routed": routed, "blocked": blocked, "skipped": skipped}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_live_router.py -v`
Expected: 7 passed

- [ ] **Step 5: Delete `ensemble.py` and its test**

```bash
git rm jarvis/execution/ensemble.py tests/test_ensemble.py
```

- [ ] **Step 6: Run the full execution test directory to confirm nothing else referenced ensemble.py**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_live_router.py tests/test_edge_providers.py tests/test_broker_bridge.py tests/test_arm.py -v`
Expected: all pass (no `ModuleNotFoundError: jarvis.execution.ensemble` anywhere)

- [ ] **Step 7: Commit**

```bash
git add jarvis/execution/live_router.py tests/test_live_router.py
git commit -m "feat: live_router — fusion 기반 실행 라우터로 ensemble.py 대체"
```

---

### Task 4: `research/lab/service.py` — wire `live_router.route_all()` into the 6h tick

**Files:**
- Modify: `research/lab/service.py` (docstring, `__init__`, new `_execution_check()` method, `_tick()`, `status()`)
- Test: `tests/test_lab_service_execution_check.py`

**Interfaces:**
- Consumes: `jarvis.execution.live_router.route_all(as_of: str = "") -> dict` (Task 3), `jarvis.watchdog.observe(dict) -> list[dict]` (existing).
- Produces: `ResearchService._execution_check() -> None`, new instance fields `last_execution_check: str | None`, `execution_routed_total: int`, `last_execution_result: dict | None` — surfaced via `status()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lab_service_execution_check.py
"""_execution_check — 6h 스로틀로 live_router.route_all() 호출, 결과를 status에 반영.
예외는 다른 _tick 서브틱과 동일하게 조용히 삼킴(research service 전체가 안 죽어야 함)."""
from __future__ import annotations

import os

import pytest

from research.lab.service import ResearchService


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import importlib
    for mod in ("jarvis.audit.log", "jarvis.registry.lifecycle", "jarvis.watchdog"):
        monkeypatch.setattr(importlib.import_module(mod), "state_path", sp)
    return tmp_path


def test_first_call_runs_and_records_routed_total(monkeypatch):
    svc = ResearchService()
    monkeypatch.setattr(
        "jarvis.execution.live_router.route_all",
        lambda as_of="": {"as_of": as_of, "routed": [{"instrument": "005930", "result": {}}],
                           "blocked": [], "skipped": []},
    )
    svc._execution_check()
    assert svc.execution_routed_total == 1
    assert svc.last_execution_check is not None
    assert svc.last_execution_result["routed"] == [{"instrument": "005930", "result": {}}]


def test_throttled_within_6h_window(monkeypatch):
    svc = ResearchService()
    calls = []

    def _route_all(as_of=""):
        calls.append(1)
        return {"as_of": as_of, "routed": [], "blocked": [], "skipped": []}
    monkeypatch.setattr("jarvis.execution.live_router.route_all", _route_all)
    svc._execution_check()
    svc._execution_check()
    assert len(calls) == 1


def test_exception_is_swallowed(monkeypatch):
    svc = ResearchService()

    def _boom(as_of=""):
        raise RuntimeError("route_all boom")
    monkeypatch.setattr("jarvis.execution.live_router.route_all", _boom)
    svc._execution_check()  # 예외로 죽지 않음
    assert svc.execution_routed_total == 0


def test_status_exposes_execution_fields():
    svc = ResearchService()
    s = svc.status()
    assert "last_execution_check" in s
    assert "execution_routed_total" in s
    assert "last_execution_result" in s
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_lab_service_execution_check.py -v`
Expected: FAIL — `AttributeError: 'ResearchService' object has no attribute '_execution_check'`

- [ ] **Step 3: Update the module docstring (honesty fix — "안전: live 절대 없음" is about to become false)**

In `research/lab/service.py`, change:

```python
안전: live 절대 없음(Jarvis 강제). $0(맥·무료 데이터). 아이디어 생성 = 우리 대화($0).
```

to:

```python
안전: 실주문 경로 있음(live_router, 6h 스로틀) — 단 arm()은 사람 ADMIN 전용,
AUTONOMY_LEVEL<MIN_LIVE_LEVEL이면 broker_bridge가 자체 BLOCK. 구조적으로 이
두 게이트(+arm_criteria GO)가 다 열리기 전까진 여전히 무동작. $0(맥·무료 데이터).
아이디어 생성 = 우리 대화($0).
```

- [ ] **Step 4: Add the new fields to `__init__`**

After the existing `self.watchdog_new_total = 0` line, add:

```python
        self._last_execution_ts = 0.0
        self.last_execution_check: str | None = None
        self.execution_routed_total = 0
        self.last_execution_result: dict | None = None
```

- [ ] **Step 5: Add the `_execution_check()` method** (after `_warm_tsmom`, before `_tick`)

```python
    def _execution_check(self) -> None:
        """6h 스로틀 — live_router 실행. armed+GO 전략 없으면 사실상 항상 no-op."""
        if time.time() - self._last_execution_ts < 21600:
            return
        self._last_execution_ts = time.time()
        try:
            from jarvis.execution.live_router import route_all
            r = route_all(as_of=_now())
            self.last_execution_check = _now()
            self.last_execution_result = r
            self.execution_routed_total += len(r.get("routed", []))
            if r.get("routed"):
                from jarvis.watchdog import observe
                observe({"live_order_routed": True, "n": len(r["routed"])})
        except Exception:  # noqa: BLE001
            pass
```

- [ ] **Step 6: Wire into `_tick()`**

Change:

```python
    def _tick(self) -> None:
        self.ticks += 1
        self._refresh_buyback()
        self._autoresearch_batch()
        self._warm_edge()
        self._warm_tsmom()
```

to:

```python
    def _tick(self) -> None:
        self.ticks += 1
        self._refresh_buyback()
        self._autoresearch_batch()
        self._warm_edge()
        self._execution_check()
        self._warm_tsmom()
```

- [ ] **Step 7: Expose the new fields in `status()`**

Change:

```python
            "arm_decision": self.arm_decision,
            "tsmom_last_month": self.tsmom_last_month, "tsmom_in_envelope": self.tsmom_in_envelope,
            "watchdog": self._watchdog_summary(),
            "pull_queue": self._pull_queue_summary(),
            "note": "pending 큐 + buyback 24h 갱신 + Auto-Research 24h 배치 + lab 되먹임 + jarvis 감사큐 브릿지 + 엣지 6h 워밍 + 감시견. live 불가. $0.",
```

to:

```python
            "arm_decision": self.arm_decision,
            "tsmom_last_month": self.tsmom_last_month, "tsmom_in_envelope": self.tsmom_in_envelope,
            "last_execution_check": self.last_execution_check,
            "execution_routed_total": self.execution_routed_total,
            "last_execution_result": self.last_execution_result,
            "watchdog": self._watchdog_summary(),
            "pull_queue": self._pull_queue_summary(),
            "note": "pending 큐 + buyback 24h 갱신 + Auto-Research 24h 배치 + lab 되먹임 + jarvis 감사큐 브릿지 + 엣지 6h 워밍 + 실행체크 6h + 감시견. 실주문 경로 있음(게이트 미달시 무동작). $0.",
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -m pytest tests/test_lab_service_execution_check.py tests/test_lab_service_jarvis_bridge.py tests/test_lab_service_reconcile.py -v`
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add research/lab/service.py tests/test_lab_service_execution_check.py
git commit -m "feat: research service — live_router 6h 실행체크 배선, 정직성 갱신"
```

---

### Task 5: Docs — close out roadmap item 10 and add the progress.md handoff entry

**Files:**
- Modify: `docs/roadmap.md` (item 10 under `## 다음 세션 최우선` — currently references `ensemble.py` as the completed piece)
- Modify: `docs/progress.md` (append a dated session entry, per the global CLAUDE.md handoff convention)

**Interfaces:** None (docs only).

- [ ] **Step 1: Update `docs/roadmap.md` item 10**

Find the item 10 entry (starts `10. **실거래 완전자동 실행 배선(08-25/26 밤샘, 완료)**`) and replace its body with:

```
10. **실거래 완전자동 실행 배선(08-25/26 밤샘 + 08-26, 완료)** — jarvis/execution/broker_bridge.py(KIS+HL 라우팅, risk_guard 이중체크, 알림) + jarvis/execution/live_router.py(fusion 기반 신호결합 — ensemble.py는 08-26 대체 후 삭제, armed+arm_criteria GO 기여자 없으면 Tier B 단독 절대 트리거 안 함) + jarvis/execution/edge_providers.py(전략별 arm_criteria 호환 edge 명시 레지스트리) 신규. live_engine/risk_guard.py venue별 리밋 + 파일기반 kill switch 배선(08-25/26). broker_bridge.route_order()가 AUTONOMY_LEVEL 게이트를 체크 안 하던 구멍(08-26 발견) 수정. research/lab/service.py가 6h 스로틀로 live_router.route_all() 자동 호출 — 실행루프 완성. 테스트 전부 통과. 남은 건: 사람 3게이트(arm/AUTONOMY_LEVEL/arm_criteria GO) 전부 잠긴 채 유지(의도적) + fusion v1_risk_adjusted가 track record 없는 전략엔 0표를 주므로 buyback이 closed 트레이드 2개 이상 쌓이기 전까진 그마저도 무의미(구조적, 코드 결함 아님). 상세: docs/superpowers/specs/2026-08-26-live-execution-router-design.md, docs/superpowers/plans/2026-08-26-live-execution-router.md.
```

- [ ] **Step 2: Append the `docs/progress.md` session entry**

Append (after the existing final `### 막힌 부분/결정사항` section, following the same header format used throughout the file):

```markdown

## 2026-08-26: live_router — ensemble.py를 fusion 엔진으로 대체, broker_bridge AUTONOMY_LEVEL 구멍 수정, 실행루프 배선

배경: "그러면 이제 에이전틱 트레이딩 플랫폼 급이라 생각해?" 질문에 "아니다 — 실행루프 없고, 몇 달간 arm 가능 전략도 0개"로 직답. "1,2 문제 해결해보자"(1=실행루프)로 착수. superpowers:brainstorming(architectural) 진행 — 재탐색 중 어젯밤 만든 ensemble.py가 이미 존재하던 검증된 jarvis/fusion/과 중복임을 발견, 유저 승인 후 fusion으로 대체.

### 완료된 작업
- `jarvis/execution/edge_providers.py`(신규): 전략별 arm_criteria 호환 edge 판정 명시 레지스트리(암묵 매칭 금지, fusion/adapters 관례 따름). 현재 buyback 하나만 등록.
- `jarvis/execution/live_router.py`(신규, `ensemble.py` 대체): fusion.collect_signals→FusionEngine.fuse→armed+GO 필터→broker_bridge.route_order. Tier B(draft) 단독 트리거 절대 불가(회귀테스트로 고정). 가격조회는 KISClient.get_daily_price 재사용(신규 quote 인프라 안 만듦).
- `jarvis/execution/broker_bridge.py`: route_order() 최상단에 AUTONOMY_LEVEL 게이트 체크 추가 — 어젯밤 배선에서 빠져있던 구멍(08-25 발견, 08-26 수정). 이전엔 무장+arm_criteria GO만 통과하면 AUTONOMY_LEVEL 무관하게 실주문 나갈 뻔했음.
- `research/lab/service.py`: `_execution_check()` 6h 스로틀 서브틱 추가, `_tick()`에 배선 — 리서치 서비스가 이미 상시 가동 중이므로 이게 곧 실행루프. 정직성: "안전: live 절대 없음" 독스트링을 실제 상태로 갱신.
- 삭제: `jarvis/execution/ensemble.py`, `tests/test_ensemble.py`.
- 신규 테스트: `tests/test_edge_providers.py`, `tests/test_live_router.py`, `tests/test_lab_service_execution_check.py` + `tests/test_broker_bridge.py`에 AUTONOMY_LEVEL 회귀 케이스 1개 추가. 전부 pass.

### 변경된 파일
- 신규: `jarvis/execution/edge_providers.py`, `jarvis/execution/live_router.py`, `tests/test_edge_providers.py`, `tests/test_live_router.py`, `tests/test_lab_service_execution_check.py`, `docs/superpowers/specs/2026-08-26-live-execution-router-design.md`, `docs/superpowers/plans/2026-08-26-live-execution-router.md`
- 수정: `jarvis/execution/broker_bridge.py`, `research/lab/service.py`, `tests/test_broker_bridge.py`, `docs/roadmap.md`
- 삭제: `jarvis/execution/ensemble.py`, `tests/test_ensemble.py`

### 다음 할 일
- 없음(이번 요청 "1번 실행루프" 완료). 2번(arm 가능 전략 0개)은 코드로 해결 불가 — arm_criteria.py(동결) 요구치를 buyback 전략이 채우는 데 몇 주~몇 달 필요, 재조사 불필요([[project_live_execution_bridge_08-25]]).
- tsmom/turn-of-month용 edge provider는 미착수(스코프 밖, 각 전략의 arm_criteria 호환 edge 함수 자체가 아직 없음) — provider 추가되면 edge_providers.py에 등록만 하면 바로 편입.
- jarvis/portfolio/(allocator/decision_engine) 편입은 armed 전략 2개 이상 동시운용 시점까지 보류.

### 막힌 부분/결정사항
- fusion v1_risk_adjusted 가중치 스킴은 track record(score>0) 없는 전략에 0표를 준다 — buyback이 closed 포지션 2개 이상(observation_count 늘어남) 쌓이기 전엔 armed+GO를 받아도 fused direction이 0으로 나와 트레이드가 안 나감. 코드 결함 아님(fusion의 의도된 "무트랙레코드=무표" 설계) — 다음 세션에서 "왜 여전히 안 나가지" 질문 나오면 이 문단 먼저 참조.
```

- [ ] **Step 3: Commit**

```bash
git add docs/roadmap.md docs/progress.md
git commit -m "docs: live_router 완료 반영 — roadmap 항목10 갱신, progress.md 세션 기록"
```

---

## Self-Review Notes (fixed inline while writing this plan)

- **Spec coverage:** all 4 components (edge_providers, live_router, broker_bridge gate, service.py integration) + tests + ensemble.py deletion are covered (Tasks 1-4). The spec's "스코프 밖" items (portfolio/ integration, tsmom/tom providers, schedule tuning) are correctly left undone and are called out in Task 5's doc entries rather than silently dropped.
- **Placeholder scan:** none found — every step has real code, real file paths, real assertions.
- **Type/name consistency:** `EDGE_PROVIDER_VENUE`, `edge_go`, `route_all`, `_kr_last_close`, `_build_order`, `BOOST_MULTIPLIER` are spelled identically everywhere they're referenced across Tasks 1/3/4 and their tests.
- **Deviation from the spec doc, recorded above rather than by re-editing the already-approved spec:** module-level imports in `live_router.py` instead of the spec's function-local imports (needed so tests can `monkeypatch.setattr(live_router, "perf_for", ...)` etc. without patching three different modules' internals), the price-lookup implementation (spec had no concrete function), and the explicit `paper=False`/`AUTONOMY_LEVEL`-frozen-constant fixes described above.
