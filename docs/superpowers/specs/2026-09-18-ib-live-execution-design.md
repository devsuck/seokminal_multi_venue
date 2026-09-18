# IB 라이브 실행 고리 — 브로커 인프라 + 게이트 매핑 설계

- 상태: 승인됨 (2026-09-18, 유저 섹션별 승인 완료)
- 관련 repo: `seokminal-multi-venue`(백엔드), `seokminal-dashboard`(프론트 — 섹션 2만)
- 범위: 아래 (1)~(4). 5번(게이트 전면 개방/승격 워크플로우)은 이번 스코프 제외, 다음 세션.

## 배경

`jarvis/execution/broker_bridge.py`의 `_gate()`는 세 조건(autonomy level ≥6, deadman
미만료, RiskConfig)을 통과하면 브로커에 바로 주문을 낸다 — 사전 승인 없이. 이 세
조건과 별도로 3중 게이트(AUTONOMY_LEVEL, `microlive_arms.jsonl`, `agent_gate.py`의
`PROFILE_TO_STRATEGY`)가 모두 닫혀 있어 실주문은 현재 불가능. 라이브 돌릴 가치가
있는 전략도 없음(god_mode 3조건 통과 0/5, paper_active 10개 전부 포워드 거래 0건 —
직전 세션 평가).

유저는 그럼에도 인프라(브로커 실행 경로 + 게이트 구조)를 먼저 정리하고 싶어함.
IB를 브로커로 확정, USD/EUR(+가능하면 JP/HK) 멀티마켓 지원 필요, 본인 컴퓨터를
상시 켜두지 않으므로 TWS 데스크톱 상시구동은 불가.

## 스코프 분해

| # | 항목 | 이번 스코프 |
|---|---|---|
| 1 | 브로커 실행 인프라 (TWS → 헤드리스) | 포함 |
| 2 | 재인증 UX (대시보드 통합) | 포함 |
| 3 | 멀티통화/멀티마켓 주문 처리 | 포함 |
| 4 | 3중 게이트 — 매핑 구조만 정리 | 포함 |
| 5 | 게이트 전면 개방/승격 워크플로우 | **제외, 별도 세션** |

---

## 섹션 1: 브로커 실행 인프라

**중간에 뒤집힌 결정**: 처음엔 IB Client Portal Web API(REST, CPAPI)로 마이그레이션
검토했으나, 웹 검색으로 확인한 결과 CPAPI는 세션이 24시간마다 만료되고 재인증
안정성 문제로 커뮤니티에서 "showstopper"로 불릴 정도로 불안정함
([IBKR 공식 FAQ](https://www.interactivebrokers.com/docs/web-api/authentication/faq)).

반대로 classic **IB Gateway**(TWS 아닌 경량 버전, socket API — 지금 쓰는
`ib_async` 그대로 호환)를 헤드리스 Docker로 돌리면 세션 만료가 **주 1회**(일요일
01:00 ET IBKR 강제 리셋)뿐. 따라서:

- **코드 변경 없음**: `backends/ib/order_client.py`, `backends/ib/client.py`는
  `ib_async` 그대로 유지. 이미 `IB_HOST`/`IB_PORT` env로 호스트 분리 설계돼 있음
  (원래 WSL 대응 목적).
- **인프라만 이전**: IB Gateway를 유저 데스크톱 → Vultr VM(진행 중인 클라우드
  이전 작업의 그 VM)에 `gnzsnz/ib-gateway-docker` 이미지로 헤드리스 배포.
- **재인증 자동화**: `IBC`가 2026-09-01자로 공식 폐지됨. 후계자
  [`ibg-controller`](https://github.com/code-hustler-ft3d/ibg-controller) 사용.
  - 계좌 2FA를 IBKR Mobile 푸시 → **TOTP(인증앱) 방식으로 전환**하면 주 1회
    재인증까지 완전 자동(사람 개입 0). TOTP 자격요건은 지역별이라 유저가 IBKR
    계정 보안설정에서 직접 확인/전환해야 함 (Claude가 대신 못 함 — 계정 자격
    증명 변경은 사람 액션).
  - TOTP 불가하면 IBKR Mobile 푸시 유지 — 주 1회 폰 승인 필요(섹션 2에서 알림).
- `IB_PORT`는 계속 페이퍼(7497)/라이브(7496) 구분 — Gateway 컨테이너 설정으로
  결정, 코드 무관.

**유저 액션 항목** (Claude가 실행 못 하는 부분, 명시):
- Vultr VM에 `gnzsnz/ib-gateway-docker` + `ibg-controller` 배포
- IBKR 계정 2FA를 TOTP로 전환 시도(자격 확인)
- IB API 자격증명(암호화된 계좌 로그인 정보)을 VM 환경변수로 등록

## 섹션 2: 재인증 UX (대시보드 통합)

- 백엔드(`api_server`)에 엔드포인트 추가: VM 내부 `ibg-controller`의
  `/health`(포트 8080)를 폴링해 `{connected, last_auth_ts, next_reset_eta,
  needs_manual_action}` 형태로 반환.
- 프론트(`seokminal-dashboard`)의 기존 `SettingsDrawer`(설정 · 리스크 가드,
  현재 홈 화면 우상단 아이콘으로 진입)에 "IB Gateway 상태" 섹션 추가.
  - 평소: 초록 배지(연결됨, 마지막 인증 시각).
  - TOTP 실패 또는 push-fallback으로 재인증 필요 시: 빨간 배지 + "IBKR Mobile
    앱에서 승인 필요" 안내.
- 대시보드는 2FA 승인 자체를 대신할 수 없음(폰 앱 필수) — "지금 필요함"을
  보여주는 게 전부. TOTP 전환되면 이 배지는 사실상 상시 초록.

## 섹션 3: 멀티통화/멀티마켓

- `live_engine/risk_guard.py`의 `RiskConfig.from_env(venue=...)`는 이미 통화별
  분리 지원(`MAX_ORDER_NOTIONAL_KR` 식 접미사 패턴) — EUR/JPY도 `venue="IB_EUR"`
  등만 넘기면 코드 변경 없이 동작.
- `backends/ib/order_client.py`/`client.py`의 `Stock(symbol, "SMART", "USD")`
  하드코딩을 `exchange`/`currency` 파라미터로 교체(기본값 `"SMART"`/`"USD"` 유지,
  하위호환). **심볼→거래소 매핑 테이블은 만들지 않음** — 유럽 거래소가
  파리/암스테르담/프랑크푸르트마다 코드가 다르고 잘못 매핑하면 오발주 위험이 커서,
  호출부(전략 설정)가 명시적으로 `exchange`/`currency`를 넘기도록 강제.
- `jarvis/execution/capital_envelope.py`의 `pool_limit`은 단일 숫자라 여러 통화가
  섞이면 암묵적으로 단일 통화(현재 USD) 가정임. 이번엔 그대로 둠 —
  `ponytail: 크로스통화 풀 합산 단순화(단일 통화 가정), 실제 EUR/JPY 라이브 돌릴
  때 FX 정규화 재검토`로 명시.

## 섹션 4: 3중 게이트 — 매핑 구조만 정리

`jarvis/execution/agent_gate.py`의 `PROFILE_TO_STRATEGY`를 하드코딩된 빈
딕셔너리에서, `jarvis/execution/arm.py`와 동일한 패턴(append-only jsonl, 사람
ADMIN 게이트, 감사로그)으로 바꾼다.

- 새 상태 파일: `jarvis/_state/agent_strategy_mapping.jsonl`. 각 행:
  `{profile_name, strategy_id, action: "register"|"unregister", registered_by,
  ts}`. 최신 행이 유효 상태(= `arm.py`의 `arm_state()`와 동일한 latest-wins 방식).
- 새 함수 (agent_gate.py):
  - `register_validated_strategy(profile_name: str, strategy_id: str, human:
    Principal) -> dict` — 사람 ADMIN만(`Level.ADMIN_HUMAN_ONLY` 체크,
    `arm.py`의 패턴 그대로). 감사로그 남김. `strategy_id`가 실제 registry에
    존재하는지 정도만 sanity-check(상태값 검증은 안 함 — `validation_of()`가
    호출 시점마다 실시간으로 재검증하므로 등록 시점엔 존재 여부만).
  - `unregister_strategy(profile_name: str, human: Principal) -> dict` — 대칭
    롤백.
  - `_current_mapping() -> dict[str, str]` — jsonl 읽어 latest-wins 매핑 반환,
    파일 없으면 빈 딕셔너리(기존 fail-safe 동작 그대로).
- `validation_of()`는 `PROFILE_TO_STRATEGY.get(...)` 대신
  `_current_mapping().get(...)` 사용하도록 한 줄 교체.
- **AUTONOMY_LEVEL·arm.py는 이번엔 건드리지 않음** — 사람이 env 직접 수정 /
  `arm()` 직접 호출하는 기존 수동 절차 그대로 유지. 실제로 라이브를 트리거하는
  최종 액션은 여전히 100% 사람.

## 테스트

- 섹션 3: `IBOrderClient.place_order`에 `exchange`/`currency` 기본값 테스트
  (기존 동작 불변 확인) + 명시적 EUR/JPY 파라미터 전달 시 올바른 `Stock` 생성
  확인.
- 섹션 4: `register_validated_strategy`/`unregister_strategy`의 권한 게이트(비
  ADMIN 거부), latest-wins 매핑 정확성, `validation_of()` 통합 테스트. 기존
  `tests/test_jarvis.py` 등의 `_isolate_state` 픽스처에 새 상태 파일도 반드시
  포함(이전 세션에 발견된 실제 상태 파일 오염 버그와 동일한 패턴 — 빠뜨리면
  재발).
- 섹션 1/2는 인프라·프론트 작업이라 유닛테스트보다 수동 검증(VM 배포 후 `/health`
  응답 확인, 대시보드 배지 렌더링).

## 다음 세션 (스코프 밖, 명시적으로 미룸)

- 5번: 3중 게이트 실제 개방(전면 vs 단계적 승인 워크플로우) — god_mode 통과
  전략이 실제로 나온 뒤에나 의미 있는 작업이라 유보.
- `agent_gate.py`에 전략을 등록해도 god_mode 3조건을 통과하는 전략이 아직 없어
  이번 스코프 자체는 "구조만 준비, 실제 라이브 트리거는 여전히 0건" 상태로 끝남
  — 의도된 결과.
