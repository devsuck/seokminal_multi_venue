# 멀티시그널 통합 (에이전트 판단 배선) — Design

**Status:** 사용자 승인 대기 (2026-09-06 초안, 사용자가 스펙 검토 후 확정).

## Background

`autopilot/CLAUDE.md`(실제 가동 중인 페이퍼트레이딩 에이전트, `claude --print` 사이클 스펙)의
STEP 3 종목분석은 현재 A(가치)·B(기술적)·C(뉴스)·D(내부자매매/DART공시) 4관점뿐.
`api_server/console_api.py`에는 100개 이상의 엔드포인트가 있으나 대부분 대시보드 표시용으로만
만들어졌고, 실제 매매 판단 경로(`autopilot`)로는 연결돼 있지 않음 — macro_intelligence·
insider-flow·dart-events 3건이 이번 세션에 이미 같은 패턴으로 배선 완료(커밋 `243b349`,
`3597da7` 외).

사용자 요청: "내가 만든 모든 기능들을 다 고려했으면 좋겠어. 뉴스, 경제지표, 회계장부,
발표하는 문서 등을 복합적으로 판단해서 AI가 에이전틱 트레이딩 하면 좋겠어." 100개 넘는
엔드포인트를 한번에 다 배선하는 건 비현실적 — 감사 후 우선순위 순차배선으로 결정(브레인스토밍
3안 중 1안 승인됨). 사용자가 명시적으로 지목한 항목: **회계장부(재무제표)**.

## Non-Goals

- 자본배분/PnL 모델 재설계(서브프로젝트 A) — 별도 스펙, 이 문서 범위 밖.
- 매매 실행경로(`broker_bridge`, `AUTONOMY_LEVEL` 게이트) 변경 없음.
- LLM 대신 코드가 매수/매도를 결정하는 로직 추가 없음 — 전부 참고용 컨텍스트, 최종 판단은
  `claude --print` 사이클의 LLM.
- 감사 대상에 없거나 실측 데이터소스 자체가 없는(순수 fabricated) 엔드포인트를 억지로 살리는
  작업 없음 — 그런 항목은 "배선 불가"로 감사 보고서에만 기록.
- HL/KR 등 미가동 에이전트 기동 없음(기존 보류 결정 유지).

## Architecture

두 단계.

### B-1. 감사 (읽기전용, 서브에이전트 위임)

`general-purpose` 서브에이전트에게 `console_api.py`의 엔드포인트 전수(약 100+)를 훑게 하고,
각 엔드포인트의 핸들러가 호출하는 실제 함수를 따라가 아래 표를 산출:

| 컬럼 | 설명 |
|---|---|
| endpoint | `/console/...` 경로 |
| backing_module | 실제 데이터를 만드는 `jarvis/research_workflow/*.py` 또는 `research/data/*.py` |
| data_source | `REAL`(FRED/DART/OpenInsider류 외부API·캐시 실측) / `DEMO`(하드코딩 상수) / `MIXED`(일부만 실측, macro 배선 전 상태) |
| symbol_scoped | 종목 단위 필터링 가능 여부(에이전트가 STEP 3에서 쓰려면 종목별이어야 함) |
| trading_relevant | 매수/매도 판단에 실제 의미 있는 정보인지(순수 운영 모니터링용 dashboard 엔드포인트는 제외) |
| notes | 배선 난이도/전제조건 |

이미 확인된 항목은 감사에서 제외(중복 조사 방지): `macro-intelligence`, `insider-flow-live`,
`dart-events-live`.

우선 확인 후보(이번 세션 grep으로 이미 실측 모듈 확인됨, 감사에서 최우선 검증):
`research/data/dart_financials.py`(재무제표, `parse_financials()`/`load_cached()`),
`jarvis/research_workflow/news_intelligence.py`, `company_analyst.py`, `ownership_pipeline.py`
(NPS/기관보유), `sector-intelligence`/`earnings-intel`/`supply-chain-impact` 엔드포인트.

### B-2. 순차배선 (표준 레시피, 3회 검증됨)

감사 결과 중 `trading_relevant=YES`이고 `data_source ∈ {REAL, MIXED}`인 항목을, **재무제표
최우선 → 이후 감사 결과 기반 리스크/임팩트 순**으로 하나씩:

1. **엔드포인트**: `DEMO`/`MIXED`면 `macro-intelligence` 때처럼 실측 우선·실패시 demo 폴백으로
   교체. 이미 전량 데이터인데 종목 필터링이 없으면 `insider-flow-live`/`dart-events-live`처럼
   `symbol`/`code` 쿼리파라미터로 필터링하는 새 `-live` 엔드포인트 추가.
2. **`autopilot/tools/<feature>.sh`**: 기존 `macro.sh`/`insider.sh`/`dart.sh`와 동일 형식
   (curl → python3 -c 요약 출력).
3. **`autopilot/CLAUDE.md`**: STEP 3에 새 관점(E, F, ...) 추가. 반드시 "참고용, 매수/매도
   신호 아님" 명시 + 구체적 조정 규칙 1줄(예: "부채비율 급증 시 신규진입 보류 검토").
4. **검증**: `pytest tests/ -q` 전체 그린 + 실제 종목(예: 005930, AAPL)으로 curl 스모크테스트
   해서 비어있지 않은 실측 응답 확인.
5. **커밋 + 기록**: `seokminal-multi-venue`와 `autopilot` 양쪽 레포 커밋, 양쪽
   `docs/progress.md`에 세션 로그/Phase 항목 추가.

### 가드레일 — 비용 체크포인트

기능 2개 배선할 때마다 STEP 3 하위 관점 개수를 재점검. 현재 A~D 4개, 재무제표 추가 시 5개.
**8개를 넘어가면 배선 중단, 사용자에게 2안(`/console/composite-signal` 서버측 집계)으로
전환할지 재확인** — 사이클당(`claude --print`) 도구 호출 수가 늘어날수록 실행시간·토큰비용이
선형 증가하기 때문.

## Error Handling

기존 `macro-intelligence`와 동일: 모든 실측 fetch는 `_safe()` 래퍼로 감싸 예외 시 `None`/빈
기본값 반환, 엔드포인트는 그 값을 demo/빈 리스트로 폴백. 에이전트 사이클(`claude --print`)이
도구 실패로 죽는 일은 없어야 함 — `tools/*.sh`는 항상 텍스트 출력(빈 상태 메시지 포함)으로
종료.

## Testing

각 기능 배선마다: `pytest tests/ -q`(현재 베이스라인 1975 passed, 회귀 없어야 함) +
실제 종목으로 curl 스모크테스트(빈 응답이면 배선 실패로 간주, 원인 규명 후 재시도 또는
"배선 불가"로 감사 보고서 갱신).

## Open Question (구현 계획 단계에서 결정)

B-1 감사 보고서가 나온 뒤에야 B-2의 정확한 기능 목록과 순서가 확정됨 — 즉 이 스펙은
"프로세스"를 확정하는 것이고, 구현 계획(`writing-plans`)의 Task 1은 감사 실행, Task 2부터는
감사 결과에 따라 동적으로 채워짐. 이는 통상적인 사전확정 태스크 목록과 다른 점 — 감사 완료 후
계획 문서를 감사 결과 반영해 갱신하고 사용자에게 다시 보여준 뒤 Task 2 이후를 진행한다.
