# 실거래 실행 라우터(live_router) — 설계

2026-08-26. 08-25/26 밤샘 세션에서 배선한 `jarvis/execution/broker_bridge.py` +
`jarvis/execution/arm.py`/`arm_criteria.py`(동결) 게이트 스택을, 이미 존재하는
검증된 신호융합 파이프라인(`jarvis/fusion/`)과 연결하는 마지막 커넥터.

## 배경

어젯밤 `jarvis/execution/ensemble.py`(Tier A/B 투표, 자체 구현)를 만들었으나,
오늘 재탐색 중 `jarvis/fusion/`에 이미 완성·검증된 리스크조정 가중투표 엔진이
있음을 발견(`fusion.py` v1_risk_adjusted, `providers.py`의 4개 전략 어댑터,
`weighting.py`, `normalize.py` 전부 테스트 통과 상태). 사용자 확인 후 결정:
**ensemble.py는 fusion.py로 대체.** arm 게이트(Tier A=armed 필수, Tier B 단독
트리거 금지) 개념만 새 커넥터에 남기고, 신호결합 로직 자체는 재구현하지 않는다.

또한 이 과정에서 `jarvis/execution/gateway.py`(기존, 미변경)에 문서화된
이중게이트("①사람 arm() ②autonomy level≥`MIN_LIVE_LEVEL`(6)")를 `broker_bridge.py`가
지키고 있지 않음을 발견 — `route_order()`가 `AUTONOMY_LEVEL` 체크 없이 바로
실브로커를 호출함(`ExecutionGateway.execute()`는 원래 mock/paper dry-run 전용이라
이 체크를 실제로 실행하는 코드가 없었음). 이번 스펙에 수정 포함.

## 불변식(변경 없음, 재확인)

- `jarvis/execution/arm_criteria.py` — 동결(2026-07-04). 수정 금지.
- Tier B(draft 상태 + 실데이터)는 **단독으로 절대 트리거 불가.** armed+GO 전략이
  최소 1개 같은 방향으로 기여해야만 트레이드 성립.
- `arm()`은 사람 ADMIN 전용. 이 작업에서 자동화하지 않음 — 방아쇠는 여전히 사람.
- `AUTONOMY_LEVEL(기본5) < MIN_LIVE_LEVEL(6)`이면 무장됐어도 실행 BLOCK.

## 컴포넌트

### 1. `jarvis/execution/edge_providers.py` (신규)
`fusion.providers.PROVIDER_REGISTRY` 패턴을 그대로 베낀 레지스트리.

```python
EdgeProviderFn = Callable[[], tuple[dict, float]]  # -> (edge_dict, paper_months)
EDGE_PROVIDERS: dict[str, EdgeProviderFn] = {}

def _buyback_edge_provider() -> tuple[dict, float]:
    from research.paper.buyback_edge import edge_status
    from research.paper import buyback_config as CFG
    import datetime as _dt
    s = edge_status()
    months = (_dt.date.today() - _dt.date.fromisoformat(CFG.FROZEN_AT)).days / 30.0
    return s, round(months, 1)

EDGE_PROVIDERS["kr_dart_buyback_drift_v1"] = _buyback_edge_provider

# venue는 registry.asset_class로 안 뗌 — 현재 전부 None(아무도 안 채움, 확인함).
# fusion/adapters의 "암묵 매칭 금지, 명시적 매핑" 관례 따라 여기도 명시 딕셔너리.
EDGE_PROVIDER_VENUE: dict[str, str] = {"kr_dart_buyback_drift_v1": "KR"}

def edge_go(strategy_id: str) -> bool:
    """arm_criteria GO 여부. edge provider 없는 전략은 항상 False(정직한 기본값)."""
    fn = EDGE_PROVIDERS.get(strategy_id)
    if fn is None:
        return False
    from jarvis.execution.arm_criteria import evaluate
    edge, months = fn()
    return evaluate(edge, months).get("decision") == "GO"
```

tsmom/tom은 arm_criteria 호환 edge 함수가 아직 없어 자동 배제(추후 provider
추가하면 바로 편입 — 재작업 없음).

### 2. `jarvis/execution/live_router.py` (신규, ensemble.py 대체)

```python
BOOST_MULTIPLIER = 1.3  # 기존 ensemble.py에서 유지

def _sign(x: float) -> int: ...  # fusion._sign과 동일 로직 재사용 불가(private) — 로컬 재정의

def route_all(as_of: str = "") -> dict:
    from jarvis.fusion.providers import collect_signals
    from jarvis.fusion.performance import perf_for
    from jarvis.fusion.fusion import FusionEngine
    from jarvis.execution.arm import is_armed, arm_state
    from jarvis.execution.edge_providers import edge_go
    from jarvis.execution import broker_bridge

    signals, skipped = collect_signals(as_of)
    if not signals:
        return {"as_of": as_of, "routed": [], "skipped": skipped, "note": "fusion-eligible 신호 없음"}
    perfs = {s.strategy_id: perf_for(s.strategy_id) for s in signals}
    fused = FusionEngine().fuse(signals, perfs, as_of)

    routed, blocked = [], []
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
        base_capital = min(arm_state(b.strategy_id)["capital_limit"] for b in armed_backers)
        size_mult = (BOOST_MULTIPLIER if fs.n_strategies >= 2 else 1.0) * fs.confidence
        order = _build_order(fs, base_capital * size_mult)
        try:
            result = broker_bridge.route_order(order)
            routed.append({"instrument": fs.instrument, "result": result})
        except broker_bridge.BrokerOrderRejected as exc:
            blocked.append({"instrument": fs.instrument, "reason": str(exc)})
    return {"as_of": as_of, "routed": routed, "blocked": blocked, "skipped": skipped}
```

`_build_order()`: venue는 `edge_providers.EDGE_PROVIDER_VENUE[armed_backers[0].strategy_id]`
로 명시 결정(KR/HL만 스코프 — [[project_active_venue_scope]]; armed_backers가
여러 전략을 걸치는 경우는 현재 provider 1개뿐이라 발생 안 함 — 나중에 provider
늘면 전부 같은 venue인지 검증 추가). side는 `direction`(1=BUY, -1=SELL).
quantity는 `base_capital*size_mult`를 현재가로 나눠 산출(가격 조회는 기존 broker
클라이언트 함수 재사용, 신규 안 만듦).

**포지션사이징 스코프 제한(ponytail 명시):** `jarvis/portfolio/`(allocator/
decision_engine/orchestrator, 역변동성+상관페널티 배분)는 이번 스코프에 안 넣음
— armed 전략의 `capital_limit`(사람이 arm() 때 지정한 값) 그대로 씀. 여러 armed
전략이 동시에 운용되기 시작하면 그때 portfolio 레이어 편입 검토.
`# ponytail: 단일-capital_limit 사이징, 배분 최적화는 armed 전략 2개+ 되면 추가.`

### 3. `jarvis/execution/broker_bridge.py` 수정 (기존 파일)

`route_order()` 최상단에 추가:
```python
from jarvis.config import live_execution_enabled, AUTONOMY_LEVEL, MIN_LIVE_LEVEL

def route_order(order: dict) -> dict:
    if not live_execution_enabled():
        raise BrokerOrderRejected(
            f"live execution disabled at autonomy level {AUTONOMY_LEVEL} (needs >= {MIN_LIVE_LEVEL})")
    ...  # 기존 로직 그대로
```

### 4. `research/lab/service.py` 통합 (기존 파일)

`_tick()`에 새 서브틱 추가(다른 것들과 동일한 throttle 패턴):
```python
def _execution_check(self) -> None:
    """6h 스로틀 — live_router 실행. armed 전략 없으면 사실상 항상 no-op."""
    if time.time() - self._last_execution_ts < 21600:
        return
    self._last_execution_ts = time.time()
    try:
        from jarvis.execution.live_router import route_all
        r = route_all(as_of=_now())
        self.last_execution_check = _now()
        self.execution_routed_total += len(r.get("routed", []))
        if r.get("routed"):
            from jarvis.watchdog import observe
            observe({"live_order_routed": True, "n": len(r["routed"])})
    except Exception:  # noqa: BLE001
        pass
```
`_tick()` 안 `_warm_edge()` 다음 줄에 `self._execution_check()` 추가.
`__init__`에 `_last_execution_ts`, `last_execution_check`, `execution_routed_total` 필드 추가.
`status()` dict에 노출.

**독스트링 수정(필수, 정직성):** 파일 최상단 "안전: live 절대 없음(Jarvis 강제)"
→ "안전: 실주문 경로 있음(live_router) — 단 arm()은 사람 전용, AUTONOMY_LEVEL 게이트
미달이면 broker_bridge가 자체 BLOCK. 구조적으로 이 두 게이트 다 열리기 전까진
여전히 무동작."로 갱신.

## 데이터 흐름 요약

```
research/lab/service.py 틱(6h)
  → live_router.route_all()
    → fusion.collect_signals()      [기존, 무수정]
    → fusion.FusionEngine.fuse()    [기존, 무수정]
    → per-instrument: armed+GO 기여자 있는지 확인
        → 없으면 skip (Tier B 단독트리거 금지 불변식)
        → 있으면 broker_bridge.route_order()
            → live_execution_enabled() 체크 [신규 — 이번에 추가하는 구멍 메우기]
            → risk_guard 이중체크          [기존, 무수정]
            → KIS/HL 실전송                [기존, 무수정]
```

## 에러 처리

- fusion 신호 없음 → 빈 결과, 정상 반환(에러 아님, 기존 fusion CLI 관례 따름).
- armed_backers 없음 → `blocked` 리스트에 사유 기록, 다음 틱 계속.
- `broker_bridge.BrokerOrderRejected`(리스크 위반/게이트 미달/크레덴셜 부재) → catch,
  `blocked`에 기록, 다른 instrument 처리는 계속(한 종목 실패가 전체 틱 안 죽임).
- `_execution_check()` 자체의 예외는 기존 `_tick()` 서브틱들과 동일하게 조용히 삼킴
  (research service 전체가 죽으면 안 됨 — 기존 패턴).

## 테스트

- `tests/test_edge_providers.py` — buyback provider가 GO/WAIT 반환 mock, 미등록
  전략은 항상 False.
- `tests/test_live_router.py` — armed_backers 없으면 항상 skip(회귀, 기존
  `test_tier_b_alone_never_triggers`의 후신), armed+GO 있으면 route, 2개 이상
  동의시 BOOST_MULTIPLIER 적용, broker_bridge 예외 시 blocked에 기록되고 계속 진행.
- `tests/test_broker_bridge.py`에 케이스 추가 — `AUTONOMY_LEVEL` 미달 시
  `BrokerOrderRejected` 발생 확인(신규 회귀 테스트, 오늘 발견한 구멍 고정).
- 삭제: `jarvis/execution/ensemble.py`, `tests/test_ensemble.py`.

## 스코프 밖(명시)

- `jarvis/portfolio/`(allocator/decision_engine/orchestrator) 편입 — armed 전략
  2개 이상 동시운용 시점에 재검토.
- tsmom/tom edge provider 작성 — 각 전략의 arm_criteria 호환 edge 함수 없음,
  별도 작업.
- 스케줄 주기(6h) 조정 — buyback `_warm_edge`와 동일 주기로 맞춘 것뿐, 실거래
  빈도 최적화는 미스코프.
