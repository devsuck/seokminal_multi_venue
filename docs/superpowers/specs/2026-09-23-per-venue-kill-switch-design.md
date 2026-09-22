# Venue별 독립 MDD 킬스위치 설계

- 상태: 승인됨 (2026-09-23, 유저 섹션별 승인 완료 — 채팅으로 구두 승인, 이 문서가 최종 확정본)
- 관련 repo: `seokminal-multi-venue`(백엔드만, 프론트 변경 없음)

## 배경

`api_server/risk_state.py`의 킬스위치는 이름은 "통합"이지만 실제론 Alpaca-paper
계좌 equity curve만 관측한다(`_current_drawdown_pct()`가
`TradingClient(paper=True).get_portfolio_history()` 호출). `is_killed()`는
단일 글로벌 불린값이라 dart_autobot(KR), vrp_bot(US_IB) 두 봇의 진입 게이트로도
쓰이는데, 이 두 봇의 실제 venue와는 무관한 계좌의 드로다운으로 차단 여부가
결정된다.

퀀트 근거(유저 승인): 각 venue/자본풀은 서로 상관관계가 1이 아니므로, 한 계좌
proxy로 전체를 판단하면 (a) 실제로 터진 venue를 못 잡거나 (b) 무관한 noise로
엉뚱한 venue를 막는 이중 오류가 생긴다. 프랍데스크 표준 구조인 "개별 book
stop + firm-wide aggregate stop" 2계층으로 간다.

추가로 코드 조사 중 스코프가 커짐: 현재 킬스위치는 Alpaca 자신의 실제
에이전트-주도 주문 경로(`broker_bridge.route_order()`/`route_order_ib()`)조차
게이팅 안 한다 — dart_autobot/vrp_bot 두 독립 봇만 자체적으로 `is_killed()`를
수동 호출할 뿐. 5개 실제 게이팅 지점을 모두 커버해야 함.

킬스위치 기존 철학(유지): 신규 매수만 차단, 매도/청산은 절대 막지 않음
(`dart_autobot.py` 자체 주석: "킬스위치는 매도는 막지 않음... 신규 매수만
차단하는 게 브레이크의 목적"). `copytrade_autobot.py`(청산 전용 봇)가
`is_killed`를 아예 참조 안 하는 것도 이 철학과 일치 — 회귀테스트
(`test_copytrade_autobot.py::test_kill_switch_does_not_block_autoliquidation`)
가 이미 이걸 못박아둠.

## 아키텍처

`api_server/venue_risk.py`(신규) — venue별 NAV 조회 + 스냅샷 적립 +
peak/드로다운 계산 + kill 판정 + 백그라운드 루프. `api_server/risk_state.py`
(기존)는 kill 상태 저장/조회 + API 라우터로 역할 축소, 판정 로직은
venue_risk.py로 이동. 단일 책임 분리 — 기존 파일이 이미 "저장+판정+API"
세 역할을 섞고 있던 걸 이번에 분리하는 것도 겸함.

## 컴포넌트

### `api_server/venue_risk.py` (신규)

```python
VENUES = ("KR", "HL", "US_IB", "US_ALPACA")
```

- `_equity_usd(venue: str) -> float | None` — venue별 NAV, USD 환산까지 끝낸 값.
  실패시 None(그 venue만 스킵, 다른 venue/루프는 계속). 조회 방법:
  - `KR`: `jarvis.broker_readonly.live_providers.KISReadOnlyProvider(paper=True).account_snapshot().equity` (KRW) → `jarvis.broker_readonly.aggregator._usdkrw_rate()`로 환산
  - `HL`: `jarvis.broker_readonly.live_providers.HLReadOnlyProvider(paper=?).account_snapshot().equity` (이미 USD)
  - `US_IB`: `backends.ib.client.IBClient().get_account_summary()["net_liquidation"]` (이미 USD, 비동기라 `asyncio.run` 또는 루프 내 await)
  - `US_ALPACA`: `alpaca.trading.client.TradingClient(paper=True).get_account().equity` (이미 USD) — **읽기 전용 사용, `risk_state.py`에서 이미 하던 일 이동**
- `_append_snapshot(venue: str, equity_usd: float) -> None` — `data/venue_risk_snapshots.jsonl`에 `{ts, venue, equity_usd}` append. venue별 독립 파일 대신 단일 jsonl에 venue 필드로 구분(`snapshot_job.py` 기존 패턴과 동일 스타일).
- `_history(venue: str) -> list[float]` — 위 jsonl에서 해당 venue의 `equity_usd` 값만 시간순으로 읽음.
- `_drawdown_pct(venue: str, current: float) -> float` — 히스토리 + 현재값 기준 running peak 대비 dd%. 히스토리가 비어있으면(첫 실행) dd=0.
- `_max_dd_limit(venue: str) -> float` — `MAX_DRAWDOWN_PCT_{VENUE}` env, 없으면 기존 `MAX_DRAWDOWN_PCT`(기본 "15") fallback.
- `_check_and_kill(venue: str, dd: float) -> None` — dd가 `-limit` 이하면 `risk_state.set_kill(venue, True, reason)`. 이미 killed면 재호출 안 함(sticky, 자동해제 없음).
- `async def tick() -> None` — 4 venue 순회(각 venue 실패는 격리) → snapshot append → dd 계산 → `_check_and_kill` → 마지막에 4개 equity_usd(fetch 실패시 jsonl의 최근값 재사용) 합산해 `_AGGREGATE`도 동일하게 드로다운 계산 + kill 판정.
- `async def venue_risk_loop() -> None` — `while True: await tick(); await asyncio.sleep(300)`. `snapshot_job.py::snapshot_loop()`와 동일 패턴.
- `main.py` 앱 시작시 기존 백그라운드 루프들(`snapshot_loop`, alert_push_loop 등)과 같은 자리에 `asyncio.create_task(venue_risk_loop())` 등록.

**AST 체크포인트 대응(`tests/test_execution_chokepoint.py`)**: `alpaca.trading.client`
직접 import는 `FORBIDDEN_IMPORT_PREFIXES`에 걸림 → `ALLOWLIST`에
`"api_server/venue_risk.py"` 추가, 주석은 기존 `risk_state.py` 항목과 동일 문구
("get_account()만 — 읽기 전용")로. 동시에 `risk_state.py`는 이 로직을 넘겨주고
나면 더는 `alpaca.trading.client`를 안 쓰므로 **기존 ALLOWLIST 항목 제거**.
KR/HL(`jarvis.broker_readonly.live_providers` 경유)과 IB(`backends.ib.client`,
주문 API 없는 파일)는 원래 금지 목록에 없어 추가 조치 불필요.

### `api_server/risk_state.py` (수정)

- `risk_kill.json` 구조 변경: `{"KR": {...}, "HL": {...}, "US_IB": {...}, "US_ALPACA": {...}, "_AGGREGATE": {...}}`, 각 값은 기존과 동일한 `{engaged, reason, ts}`.
- `set_kill(venue: str, engaged: bool, reason: str = "") -> None` — 시그니처에 `venue` 추가, 해당 venue 키만 갱신(파일 전체 재작성이지만 다른 venue 값은 보존).
- `is_killed(venue: str) -> bool` — `venue` 키 engaged OR `_AGGREGATE` engaged.
- `_current_drawdown_pct()` 및 그 안의 Alpaca 직접 조회 로직 **삭제**(venue_risk.py로 이동).
- `GET /risk/status` — 응답을 4 venue + `_AGGREGATE` 전체 dict로 확장(`RiskStatus` 모델 재설계, venue별 kill/dd/limit 포함). 평가 로직 호출 없이 `risk_kill.json` + 최신 snapshot만 읽어서 반환(평가는 이제 루프가 담당, 이 엔드포인트는 순수 조회).
- `POST /risk/kill` — `KillRequest`에 `venue: str` 필드 추가(수동 오버라이드용, `"_AGGREGATE"`도 유효값).

## 게이팅 5곳

| 파일 | 위치 | 변경 |
|---|---|---|
| `api_server/dart_autobot.py` | :370 | `is_killed()` → `is_killed("KR")` |
| `api_server/vrp_bot.py` | :443 | `is_killed()` → `is_killed("US_IB")` |
| `jarvis/execution/broker_bridge.py` | `route_order()` 진입부 | venue 분기 전에 `is_killed(order["venue"])` 체크 추가 (KR/HL/US_ALPACA 커버) |
| `jarvis/execution/broker_bridge.py` | `route_order_ib()` 진입부 | `is_killed("US_IB")` 체크 추가 |
| `api_server/copytrade_autobot.py` | - | **변경 없음** — 청산 전용, 킬스위치 무관이 설계 의도 |

`route_close()`는 변경 없음(청산 경로, 원래도 킬스위치와 무관해야 함).

## 데이터 흐름

```
tick() 매 300초
  → 4 venue 순회:
      equity fetch (실패시 skip+로그, 마지막 알려진 값은 jsonl에 남아있음)
      → snapshot append
      → peak 갱신(히스토리 기준) → dd 계산
      → dd ≤ -limit(venue) → set_kill(venue, True, reason)
  → aggregate = sum(각 venue 최신 equity_usd, fetch 실패분은 최근 알려진 값)
  → aggregate dd 계산 → 초과시 set_kill("_AGGREGATE", True, reason)
```

봇/브릿지 쪽 신규 진입 요청 → `is_killed(자기 venue)` → 자기 venue 또는
`_AGGREGATE` 둘 중 하나라도 True면 차단.

## 에러 처리

- kill은 sticky — 자동 해제 없음, `POST /risk/kill {venue, engaged: false}`로만 해제(기존 철학 유지, 사람이 원인 파악 후 명시적으로 풀어야 함).
- 한 venue의 equity fetch 실패(브로커 다운, 네트워크 등)가 다른 venue 판정이나 루프 자체를 막지 않음 — try/except로 venue 단위 격리.
- 루프 자체가 죽으면(사실상 발생 안 해야 함, 각 venue try/except로 격리했으므로) `main.py`의 다른 백그라운드 루프와 동일하게 그냥 로그만 남기고 앱은 계속 뜸(기존 관례).
- IB `get_account_summary()`는 TWS/Gateway 연결이 매 호출마다 필요(15초 timeout) — 300초 간격이면 부담 없음, 더 짧게 당기지 않음.

## 테스트

`tests/test_venue_risk.py`(신규):
- 각 venue provider mock 후 `_equity_usd` 정상값/실패(None) 케이스
- `_drawdown_pct` — 히스토리 없음(0), peak 갱신, 낙폭 계산
- venue별 `MAX_DRAWDOWN_PCT_{VENUE}` env override, 없으면 공통값 fallback
- 한 venue 실패해도 나머지 3개 + aggregate는 정상 진행
- `_AGGREGATE` FX 환산 포함 합산 정확성
- kill 한번 걸리면 dd 회복해도 sticky(재호출 안 함, 즉 set_kill 재호출 없음을 mock으로 확인)

`tests/test_risk_state.py`(신규 또는 기존 확장):
- `set_kill(venue, ...)` / `is_killed(venue)` — 자기 venue OR `_AGGREGATE` OR 로직
- `risk_kill.json` 구조 마이그레이션(기존 단일 dict 파일 읽었을 때 깨지지 않게 — 실제 운영 파일이 구버전 구조일 수 있음, 최초 실행시 없는 venue 키는 `{engaged: False}`로 기본값 처리)

`tests/test_dart_autobot_exits.py`, `tests/test_vrp_bot.py` 기존 kill-switch
테스트: `patch("api_server.risk_state.is_killed", return_value=True)` →
`patch("api_server.risk_state.is_killed")`로 바꾸고 인자 무관하게 True 반환하도록
(`side_effect=lambda v: True`) 조정.

`tests/test_broker_bridge.py`(기존 확장): `route_order()`/`route_order_ib()`에
venue별 kill 상태일 때 차단되는 테스트 추가, kill 안 걸린 다른 venue는 정상
진입되는 것도 확인(교차 오염 없음 검증).

`tests/test_execution_chokepoint.py`: `ALLOWLIST`에 `api_server/venue_risk.py`
추가 + `risk_state.py` 항목 제거만 하면 기존 두 테스트(`test_only_chokepoint_imports_broker_sdks`, `test_allowlist_entries_still_exist`) 그대로 통과해야 함.

## 마이그레이션 노트

운영 중인 `data/risk_kill.json`이 구버전 단일 dict 구조(`{engaged, reason, ts}`)로
남아있을 수 있음 — `_kill_meta()`류 함수가 이 구조를 읽을 때 venue 키가 없으면
예외 없이 `{engaged: False}` 취급하도록 방어(신규 배포 시점에 기존 파일 삭제/
마이그레이션 스크립트 불필요, 자연히 다음 tick에서 새 구조로 덮어써짐).
