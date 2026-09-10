# 자본 청구 모델 (Live/Paper 이분법 폐지 → 전략별 자본 청구 + 배정금액 기준 PnL)

## 배경

기존: 전략은 Live 또는 Paper 둘 중 하나로 이분법 배정. `docs/progress.md` Phase 248에서
"전략이 필요 금액을 청구 → 배정금액 기준 PnL" 모델로 전환 필요 플래그됨. 18개월 무인 운영
(체크 주기 최대 1일) 조건에서 자금 흐름이 막히지 않아야 함.

## 범위

**포함:** 전략의 자본 청구 → (사전 설정된 엔벨로프 내) AI 자율 승인 또는 사람 승인 대기열 →
`allocated_capital` 확정 → 그 값 기준 PnL. 백엔드(`seokminal-multi-venue`) + 프론트(대시보드 UI)
둘 다.

**제외 (명시적으로 나중 작업):** 실제 브로커 자금 이동/주문 집행 연결. 이번 스펙의 산출물은
**배정 장부(bookkeeping)** 뿐 — `broker_bridge.py`, 실제 주문 실행 경로, `AUTONOMY_LEVEL` 게이트는
전혀 건드리지 않는다. `allocated_capital`이 "live"로 결정돼도 그 자체로 돈이 움직이지 않는다 —
기존 `arm.py`/`AUTONOMY_LEVEL` 이중 게이트가 여전히 실제 주문 실행의 유일한 문턱이다. 이 스펙의
모든 산출물은 `moves_real_capital: false`, `executes_broker_order: false`를 불변으로 갖는다
(investment_os의 `is_advisory`/`executes_allocation` 관례와 동일 계열).

## 기존 자산 재사용 (신규 설계 전 확인됨)

- **`jarvis/execution/arm.py`의 `capital_limit`**: LIVE_CANDIDATE/MICRO_LIVE 전략에 대해 사람
  ADMIN이 `arm()`으로 설정하는 자본 한도. 이게 이미 "사전 엔벨로프 + 그 안에서 자율 승인"의 LIVE
  버전이다. **새로 만들지 않는다.** LIVE 청구의 하드 상한 = `arm_state(strategy_id)["capital_limit"]`.
- **`jarvis/registry/lifecycle.py`의 `StrategyRegistry`/`Status`**: 전략이 PAPER_ACTIVE인지
  LIVE_CANDIDATE/MICRO_LIVE/CONSTRAINED_LIVE인지 — 이 상태가 청구의 `fulfillment_mode`를 결정.
- **`jarvis/audit/log.py`의 `record()`**: 모든 청구 결정(자동/사람) 기록.
- **`jarvis/permissions/policy.py`의 `Principal`/`Level`/`require()`**: 행위자 권한 게이트.
- **`jarvis/config.py`의 `state_path()`**: JSONL/JSON 저장 — SQL 도입 안 함(기존 컨벤션과 동일).
- **`jarvis/investment_os/portfolio_construction.py`의 `recommend_capital_allocation()`** +
  `api_server/ai_portfolio.py`의 `latest_recommendation()`: 청구액 제안 시 "상한 참고용" 근거.

## 아키텍처

```
[전략] --(자금 필요, 이벤트)--> submit_claim()
                                      │
                          propose_claim(): 제안액 산출
                          (ceiling_ref = 최신 AI 포트폴리오 빌더
                           weight × total_capital, 참고용 — soft)
                                      │
                                      ▼
                    fulfillment_mode 판정 (StrategyRegistry 상태)
                    ├─ PAPER_ACTIVE 이하           → mode=paper, 상한=신규 paper 엔벨로프
                    └─ LIVE_CANDIDATE 이상 + armed → mode=live,  상한=arm capital_limit
                                                     (armed 아니면 → paper로 취급)
                                      │
                              엔벨로프 검증
                    (전략별 상한 AND 전체 풀 상한 둘 다 이내?)
                                      │
                    ┌─────────────────┴─────────────────┐
                    │ 이내 → AI 자율 승인          │ 초과 → 대기열(queued)
                    ▼                                     ▼
        allocated_capital 확정                   사람 체크 시 승인/거부
        audit.record() 기록                       (approve_capital_claim,
                    │                               ADMIN_HUMAN_ONLY)
                    └─────────────┬─────────────────────┘
                                  ▼
                    PnL = pnl / allocated_capital
                    (기존 계좌잔고 기준 PnL과 별개 뷰로 병행 표시)
```

## 컴포넌트

### `jarvis/execution/capital_envelope.py` (신규)

```python
def get_envelope() -> dict:
    """{'pool_limit': float, 'per_strategy_paper_limit': {sid: float}, 'default_paper_limit': float}.
    파일 없으면 전부 0 — 엔벨로프 미설정 = 자율승인 전면 불가(fail-safe)."""

def set_envelope(human: Principal, pool_limit: float,
                  per_strategy_paper_limit: dict[str, float] | None = None,
                  default_paper_limit: float = 0.0) -> dict:
    """require(human, "modify_capital_envelope"). 덮어쓰기 저장(auto_execution_approval.json 패턴)."""
```

### `jarvis/execution/capital_claims.py` (신규)

```python
def propose_claim(strategy_id: str, requested_amount: float | None = None) -> dict:
    """requested_amount 없으면 최신 AI 포트폴리오 빌더 weight × total_capital로 제안.
    반환에 ceiling_ref 포함(참고용, 14일 이상 stale이면 stale=True 플래그만, 블로킹 아님)."""

def submit_claim(strategy_id: str, requested_amount: float | None = None,
                  ai: Principal = ...) -> dict:
    """require(ai, "submit_capital_claim"). 동일 전략에 이미 pending/queued 청구 있으면 거부
    (idempotency). propose_claim() 호출 후 _decide()로 즉시 판정. JSONL append."""

def _fulfillment_mode(strategy_id: str) -> tuple[str, float]:
    """(mode, hard_limit). registry status 기반. live인데 not is_armed()면 paper로 강등."""

def _decide(claim: dict) -> dict:
    """엔벨로프(전략별 + 풀) 검증. 이내면 status=approved, decided_by='AI',
    audit.record(). 초과면 status=queued. 둘 다 반환값에 envelope_check 상세 포함."""

def approve_queued(claim_id: str, human: Principal, approve: bool, note: str = "") -> dict:
    """require(human, "approve_capital_claim"). status를 approved/rejected로 전이. audit 기록."""

def pending_queue() -> list[dict]:
    """status=='queued' 전체."""

def claim_history(strategy_id: str | None = None, limit: int = 50) -> list[dict]:
    """감사/조회용."""

def allocated_capital(strategy_id: str) -> float:
    """해당 전략의 최신 approved 청구의 allocated_capital. 없으면 0.0.
    PnL 계산(`pnl / allocated_capital`)이 여기 의존."""
```

**청구 레코드 (JSONL, `state_path("capital_claims.jsonl")`)**:
```json
{
  "claim_id": "uuid4",
  "strategy_id": "str",
  "requested_amount": 0.0,
  "proposed_amount": 0.0,
  "ceiling_ref": {"weight": 0.0, "total_capital_basis": 0.0, "capital_amount": 0.0,
                  "as_of": "iso8601|null", "stale": false},
  "fulfillment_mode": "paper|live",
  "envelope_check": {"strategy_limit": 0.0, "pool_limit": 0.0,
                      "strategy_used_before": 0.0, "pool_used_before": 0.0,
                      "within_strategy": true, "within_pool": true},
  "status": "approved|queued|rejected",
  "allocated_capital": 0.0,
  "decided_by": "AI|<human principal name>",
  "created_at": "iso8601",
  "decided_at": "iso8601|null",
  "reason": "str",
  "is_decision": true,
  "executes_broker_order": false,
  "moves_real_capital": false,
  "note": "Capital Claim — 배정 장부 기록만. 실제 브로커 자금이동/주문 아님."
}
```

### `jarvis/permissions/policy.py` 추가 (기존 표에 항목만 추가, 로직 변경 없음)

```python
"submit_capital_claim": "LIVE_PROPOSAL_ONLY",     # propose_allocation과 동급
"auto_fulfill_capital_claim": "LIVE_PROPOSAL_ONLY",
"approve_capital_claim": "ADMIN_HUMAN_ONLY",       # approve_live_promotion과 동급
"modify_capital_envelope": "ADMIN_HUMAN_ONLY",     # modify_risk_limit과 동급
```

### `api_server/console_api.py` 추가 엔드포인트

- `POST /capital-claims` — body `{strategy_id, requested_amount?}` → `submit_claim()`
- `GET /capital-claims/queue` — `pending_queue()`
- `POST /capital-claims/{claim_id}/decide` — body `{approve: bool, note?}` → `approve_queued()`
  (human principal은 세션/헤더에서 기존 인증 미들웨어 방식 그대로 사용 — 신규 인증 체계 안 만듦)
- `GET /capital-claims/history?strategy_id=&limit=` — `claim_history()`
- `GET /capital-envelope` / `POST /capital-envelope` — `get_envelope()`/`set_envelope()`

모두 기존 `console_api.py`의 다른 investment_os 엔드포인트와 동일한 응답 래핑/에러 처리 패턴 따름.

### 프론트 (`seokminal-dashboard`)

- `app/(console)/investment-os/capital-claims/page.tsx` (신규): 대기열 목록(승인/거부 버튼),
  엔벨로프 설정 폼(풀 한도 + 전략별 paper 한도), 최근 청구 히스토리 테이블. 기존
  `ai-portfolio/page.tsx`와 동일한 `(console)` 라우트 그룹 컨벤션(`--c-*` 토큰, `bg-[var(--c-bg)]`) 따름 — `ap-*` 라이트 테마 아님.
- `lib/console-api.ts` 추가: `getCapitalClaimQueue()`, `decideCapitalClaim(id, approve, note?)`,
  `getCapitalClaimHistory(params?)`, `getCapitalEnvelope()`, `setCapitalEnvelope(payload)`.
- 기존 포트폴리오 PnL 뷰(`app/portfolio/page.tsx` `PnlTab`)는 변경하지 않음 — 배정금액 기준 PnL은
  새 `/investment-os/capital-claims` 페이지에 추가 뷰로만 표시(병행, 대체 아님).

## 에러 처리 / 엣지케이스 (자는 동안 직접 판단한 것들)

- 엔벨로프 미설정 → `pool_limit=0` 기본값 → 모든 청구 자동으로 대기열行 (fail-safe: 설정 없으면
  자율성 없음).
- 동일 전략에 이미 pending/queued 청구 존재 → 새 `submit_claim()` 거부(중복 방지).
- `ceiling_ref`(AI 포트폴리오 빌더 최신값) 14일 초과 stale → `stale: true` 플래그만, 청구 처리는
  안 막음(비중은 상한 참고용이지 하드 제약 아니라고 이미 확정됨).
- LIVE_CANDIDATE 이상인데 `arm.py`에 armed 기록 없음 → `fulfillment_mode="paper"`로 강등(아직
  실제 사람이 live 자본한도를 정하지 않은 전략은 paper 취급).
- 등록 안 된 `strategy_id` → 즉시 `status="rejected"`, 대기열에 안 들어감.
- 한도 초과 청구는 **부분 승인 없음** — 전액 대기열, 사람 체크 시 처리(이미 확정된 답변).

## 테스트

- `capital_envelope.py`: 파일 없을 때 기본값, `set_envelope` 권한 거부(비인간/저레벨), 덮어쓰기 동작.
- `capital_claims.py`:
  - 엔벨로프 이내 → 자동 승인, `allocated_capital` 정확, audit 항목 1건.
  - 전략별 한도는 이내인데 풀 한도 초과 → 대기열.
  - LIVE_CANDIDATE armed → live 모드, `arm capital_limit` 하드상한 적용.
  - LIVE_CANDIDATE not armed → paper로 강등.
  - 중복 pending 청구 거부.
  - `approve_queued`: 사람 아닌 principal 거부(`PermissionDenied`).
  - `ceiling_ref` stale 플래그 14일 경계값.
- API 계층: 4개 엔드포인트 각 happy-path 1개 + 권한거부 1개.
- 프론트: 큐 렌더링, 승인/거부 버튼 호출, 엔벨로프 폼 유효성(음수 불가, 전략별 ≤ 풀).

## 자는 동안 처리 방침

이 스펙 작성 후: 백엔드 모듈(`capital_envelope.py`, `capital_claims.py`, policy.py 추가, 테스트) +
API 엔드포인트 + 프론트 페이지까지 구현 진행. **실제 브로커 연결(주문 실행)은 만들지 않음** — 위
"범위" 절 그대로. 구현 중 추가로 판단 필요한 세부사항 생기면 이 방침(재사용 우선, fail-safe 기본값,
기존 관례 일치)대로 직접 결정하고 아래 "결정 로그"에 추가.

### 결정 로그

- 엔벨로프 단위: 전략별 + 전체 풀 둘 다 (사용자 확정).
- 한도 초과 시: 부분승인 없이 전액 대기 (사용자 확정).
- LIVE 엔벨로프 = 신규 개념 아님, 기존 `arm.py capital_limit` 재사용 (설계 중 발견, 별도 확인 없이 채택 — 기존 코드와 중복 방지가 명백히 옳은 선택이라 판단).
- ceiling_ref staleness 임계값 14일: AI 포트폴리오 빌더가 주 1회(launchd) 실행되므로 2회 누락까지 허용하는 여유값으로 직접 결정.
- 중복 pending 청구 거부(전략당 동시 1건): 사용자 미확인, 레이스/중복 방지 목적으로 직접 결정. 필요시 나중에 조정 가능.
