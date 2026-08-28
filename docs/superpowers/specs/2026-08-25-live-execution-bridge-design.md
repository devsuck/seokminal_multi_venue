# 실거래 브릿지 설계 — Execution Gateway → 실브로커

**Date:** 2026-08-25
**Status:** Approved (async — user asleep, "스펙쓰고 개발까지 다 해줘" 하에 self-review 후 진행)
**Driver:** [[project-vps-migration-timeline]] — 2026-10-19 입대, 18개월 무인 운영 필요

## 배경 — 재조사로 뒤집힌 전제

브레인스토밍 중 "`jarvis/live_execution/` 신규 패키지 필요"로 approach 1을 승인받았으나,
스펙 작성 직전 재조사에서 **이미 완성된 거버넌스 스택**을 발견:

- `jarvis/registry/lifecycle.py` — `LIVE_CANDIDATE→MICRO_LIVE→CONSTRAINED_LIVE` FSM, human-approver 강제
- `jarvis/execution/arm_criteria.py` — **동결된(FROZEN_AT 2026-07-04)** GO/WAIT/KILL 기준: OOS≥3개월 AND envelope 2/3 AND 페이퍼≥6개월. 파일 수정 금지, 기준 변경은 v2 신규 등록만 허용.
- `jarvis/execution/arm.py` — 사람 ADMIN 전용 arm(), `check_micro_live_eligible()`
- `jarvis/risk/governor.py` — `RiskGovernor.check()` → `risk_status` APPROVED/REJECTED
- `jarvis/execution/gateway.py` — `ExecutionGateway.execute()`. autonomy<6 → BLOCKED, micro_live인데 미무장 → REJECTED, 그 외 전부 **"SIMULATED — mock/paper dry-run" 고정 반환. 실브로커 호출 코드 자체가 없음.**
- `jarvis/config.py` — `AUTONOMY_LEVEL=5`(env override), `MIN_LIVE_LEVEL=6`. 이게 진짜 마스터 스위치.

즉 **`AUTO_EXECUTION_ENABLED`(jarvis/investment_os)는 이 스택과 무관한 별개 장식용 플래그** — Investment OS는 애초에 execute()를 정의하지 않고, `separation.py`가 `jarvis.execution`/`jarvis.live_execution` import 자체를 금지(AST 검증)해서 건드릴 수도 없음. 진짜 게이트는 `AUTONOMY_LEVEL`.

**결론: 신규 병렬 시스템을 만들지 않는다. 기존 스택의 빠진 한 조각 — Gateway의 "SIMULATED" 종점을 실브로커 호출로 확장 — 만 추가한다.** Ponytail 룰 2(이미 있으면 재사용) 그대로 적용.

## 핵심 발견 — 오늘 밤 실전 발동은 구조적으로 불가능

`arm_criteria.py`는 페이퍼 ≥6개월을 요구. 현재 KIS paper_active 중 가장 오래된 `kr_turn_of_month_v1_PORTFOLIO`는 2026-07-16 시작, 약 40일. HL은 paper_active 자체가 0개.
**어떤 전략도 오늘 GO를 받을 수 없다** — 코드를 완성해도 마찬가지. 이건 버그가 아니라 이 파일의 설계 목적 그 자체(자기합리화로 사후에 기준 낮추는 것 차단, arm_criteria.py 상단 docstring).

→ 이번 스코프는 "실행 파이프라인을 완성해서, 정직하게 아직 아무것도 못 쏘는 상태로 대기시킨다"이다. 브레인스토밍에서 논의한 Tier A/B(paper_active 90일 vs draft 2-3주)는 **진입 문턱을 낮추는 용도로 쓰지 않는다** — 대신 이미 arm된 Tier A 전략의 사이징 부스터(+30% 상한)로만 계층화한다. arm_criteria.py는 원문 그대로 둔다(수정 금지 원칙 존중).

## 범위

**포함:**
1. `jarvis/execution/broker_bridge.py` — Gateway의 SIMULATED 종점 다음 단계. mode가 진짜 실행(live/micro_live)이고 4중 게이트(레벨·무장·리스크·registry) 전부 통과했을 때만 실제 KIS/HL 주문 함수 호출.
2. `live_engine/risk_guard.py` — venue별 통화 단위 분리(KRW/USD). 현재 단일 글로벌 한도가 두 통화에 동일 숫자로 적용되는 버그 수정. 실자본(KIS ₩100,000 + 지속 입금, HL $170) 기준 값 설정.
3. Kill switch — env var(`TRADING_KILL_SWITCH`, 재시작 필요) → 파일 플래그 병행 확인으로 전환. 재시작 없이 즉시 발동.
4. `jarvis/execution/ensemble.py` — 복수 전략 합의 판단. Tier A(armed, arm_criteria GO) 신호를 베이스로, Tier B(draft+실데이터+2주 이상 forward, sanity_only 아님) 중 ≥2개가 같은 방향이면 사이즈 +30%(상한), Tier A 신호 자체가 없으면 아무것도 안 함, Tier A끼리 방향 불일치면 skip.
5. `jarvis/investment_os` — `AUTO_EXECUTION_ENABLED=True` 전환(사용자 명시 요청, 무해함 — 이 플래그는 실제로 아무것도 게이트하지 않음). `separation.py`의 `auto_execution_permanently_disabled` 체크를 "True거나, 승인 아티팩트 파일 존재" 조건으로 갱신.
6. 알림 — `notify_live_trade()` 재사용, 브로커 호출 성공/실패 각각 사후 통보.

**제외 (스코프 아님, 명시적 결정):**
- `arm_criteria.py` 수정 또는 v2 등록 — 실자본 리스크 감수 판단은 사람 전용, 자는 동안 결정 안 함
- `AUTONOMY_LEVEL` 기본값 상향(5→6) — 이게 진짜 스위치. 코드 기본값은 그대로, 배포 시 env var로 사람이 올림
- 텔레그램 인바운드(kill 명령 수신) — 인프라 전무, YAGNI
- Alpaca/IB 배선 — 사용자가 명시 제외
- 대시보드 kill switch 버튼 — 이번 세션 앞부분에서 대시보드를 읽기전용으로 확정(`e66f8a1`). API/CLI로만 제어, 이 결정 뒤집지 않음
- DCF/목표주가 밸류에이션 모델 — 별도 브레인스토밍으로 이미 분리 합의됨

## 컴포넌트 상세

### broker_bridge.py
```
route_order(order: dict, venue: Literal["KR","HL"]) -> dict
```
- `venue="KR"`: `backends.kis.order_client.KISOrderClient.place_order()` 호출, `api_server/main.py`의 `/orders/kr` 패턴 그대로 재사용(멱등성 캐시 → risk_guard → place_order → record_order → idempotency.store → oms.record_event)
- `venue="HL"`: `hyperliquid.trader.place_order()` 호출 — 이미 `_check_risk()` 관통 확인(내 이전 조사가 틀렸음, `/hl/order`는 진작 risk_guard 탄다)
- Gateway.execute()에서 mode가 live/micro_live이고 SIMULATED 대신 진짜 집행을 원할 때만 이 함수를 호출 — 기존 mock/paper 테스트 계약(BLOCKED/REJECTED/SIMULATED)은 그대로 보존, 새 브랜치만 추가
- 실패 시 `notify_live_trade`로 실패 사후 통보, 예외는 audit에 기록 후 상위로

### risk_guard venue 분리
- `RiskConfig.from_env(venue: str)` — `MAX_ORDER_NOTIONAL_{KR,HL}` 형태 env var 우선 조회, 없으면 기존 `MAX_ORDER_NOTIONAL`로 폴백(하위호환)
- 실자본 기준 기본값: KR ₩500,000(현재 ₩100,000 + 입금 여유), HL $500(현재 $170 + 여유) — 자본 대비 과도한 단일 주문을 막는 게 목적이지 정상 거래를 막는 게 아님
- `daily_loss_limit`도 동일 패턴으로 분리

### kill switch
- `live_engine/risk_guard.py::RiskConfig.from_env()`에 파일 체크 추가: `jarvis.config.state_path("KILL_SWITCH")` 존재하면 `kill_switch=True`(env var와 OR)
- API: `POST /admin/kill-switch {on: bool}` — CLI로도 동일 파일 조작 가능. 대시보드에는 추가 안 함(위 제외 항목)

### ensemble.py
```
def evaluate(base_strategy_id: str, tier_b_candidates: list[str]) -> dict
```
- base: `jarvis.execution.arm.is_armed(base_strategy_id)` 이고 `arm_criteria.evaluate(...)["decision"] == "GO"` 인 것만 base 신호로 인정
- tier_b_candidates: registry status=="draft", data_version이 "unknown"/"" 아님, flags에 "sanity_only" 없음 — 필터는 이 함수가 직접 안 하고 호출부가 명시 리스트로 전달(코드 내 암묵 매칭 금지 — `agent_gate.py`와 동일 원칙)
- ≥2개 tier_b가 base와 같은 방향 신호 → size_multiplier=1.3(상한 고정), 아니면 1.0
- Tier B는 절대 단독 트리거 불가 — base 신호 없으면 evaluate()는 즉시 {"action": "none"} 반환

## 테스트 (ponytail — 로직 경로당 최소 1개 실행가능 체크)
- `tests/test_broker_bridge.py` — mock KIS/HL 클라이언트로 route_order 성공/실패 경로
- `tests/test_risk_guard_venue.py` — venue별 env var 분리 확인(KRW/USD 다른 값)
- `tests/test_kill_switch_file.py` — 파일 존재 시 kill_switch=True
- `tests/test_ensemble.py` — base 없음→none, base만→1.0, base+2 tier_b 동방향→1.3, tier_b만→none

## 안전 결론 (사용자에게 최종 보고 시 그대로 전달)
코드는 오늘 밤 전부 완성. 그러나 실제 주문 발사는:
1. `AUTONOMY_LEVEL` 5→6 (사람이 env var로), AND
2. 해당 전략이 `arm_criteria.py`의 동결된 GO(페이퍼 6개월+OOS 3개월 envelope 2/3) 통과 AND
3. 사람 ADMIN이 `arm()` 명시 호출

세 가지 다 사람의 의식적 행동 없이는 절대 안 열림. 오늘 밤 어떤 전략도 조건 2를 못 채움(가장 오래된 게 40일) — 그러니 코드를 다 짜도 "자는 동안 실탄 발사"는 구조적으로 불가능. 이건 이번 세션에서 방어한 그 rigor(16x walk-forward decay 발견)와 정합적인 결과다.
