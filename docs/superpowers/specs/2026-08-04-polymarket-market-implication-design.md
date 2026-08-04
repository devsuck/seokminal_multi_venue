# Polymarket 크로스이벤트 함의관계 위반 — Design Spec

**작성:** 2026-08-04. 브레인스토밍 중 섹션별 확정, 사용자 승인 완료.

## 1. 배경

sharp_wallet 워크포워드 하락 원인 조사(300s 호라이즌만 진짜 엣지, 30s/120s는
비용이 엣지 잡아먹음) 후, "트레이더 행동패턴 추정" 계열 가설(whale, sharp_wallet,
cross_venue_skew)이 반복적으로 비용/노이즈 벽에 부딪힌다는 게 확인됐다. 사용자
요청으로 완전히 다른 축의 아이디어를 브레인스토밍 — 이번엔 **구조적/논리적
비효율**을 노린다: 트레이더 행동과 무관하게, 서로 논리적으로 연관된 두 마켓의
가격이 그 관계를 위반하면 그 자체가 신호다.

기존 `research/polymarket_event_divergence/`는 **같은 이벤트 안** 상호배타
마켓(예: "누가 당선?" 안의 여러 후보)의 YES 가격 합이 1에서 벗어나는지만 본다.
이번 가설은 **다른 이벤트끼리** 걸친 함의관계(예: "X 예선 승리" → "X 본선 승리")
— 코드 겹침 없음, 완전 신규 영역.

**목표 성향:** 한방 큰 수익 아니라 "냅두면 야금야금" — 저빈도, 저분산, 만기
비슷한 쌍으로 좁혀 헤지형(양다리) 포지션만 취급한다.

## 2. 가설

Polymarket 활성 마켓 중 논리적으로 연관된 두 마켓 쌍(A, B)이 존재하고, 그 관계가
가격에 강제하는 부등식(예: P(B) ≥ P(A))을 현재 가격이 위반하면, 그 위반폭이
왕복 거래비용을 넘어설 때 헤지 포지션(위반 방향 양다리)의 만기 시점 pnl이
양수인가.

기존 가설들과 달리 확률적 상관관계 검정이 아니라 **결정론적 논리 위반** 탐지다
— 통계적 유의성 개념 자체가 다르게 적용된다(§6 참고).

## 3. 관계 패턴 (2종류, 독립 태그)

- **A타입 — 계층형(hierarchical)**: 한 마켓 YES가 다른 마켓 YES를 논리적으로
  함의. 예: "X 예선 승리" → "X 본선 승리" (P(본선)≥P(예선)). 오탐 리스크 낮음.
- **B타입 — 배타형(cross-event exclusive)**: 같은 엔티티가 서로 다른 이벤트에
  걸쳐 나타나 확률합 제약을 만드는 경우(예: 같은 인물이 서로 다른 두 직책
  마켓에 동시 출마). 오탐 리스크 A보다 높음.
- 모든 판정 레코드에 `pattern_type: "A" | "B"` 태그 필수 — B타입만 언제든 독립
  적으로 끌 수 있어야 함(사용자 명시 요구). BH-FDR 대신 쓰는 오탐률/포워드
  로깅 집계(§6)도 pattern_type별로 분리 집계한다.

## 4. 아키텍처

```
polymarket/client.py (기존)                              ← get_markets() 재사용, 신규 코드 없음
research/run_polymarket_market_implication_collect.py    ← 일 1회 마켓 전체 스냅샷 + 엔티티태깅 + 쌍판정
research/polymarket_market_implication/entity_tags.py    ← 엔티티 추출/캐시(순수함수 + 로컬 저장)
research/polymarket_market_implication/pairing.py        ← 엔티티 공유 + 만기근접 후보쌍 필터(순수함수)
research/hypotheses/polymarket_market_implication.py     ← LLM 함의판정 + 위반폭 계산(가설 모듈)
research/run_polymarket_market_implication_watch.py      ← 시간당 가격 재조회(LLM 호출 없음) + 위반 로깅
research/run_polymarket_market_implication_report.py     ← §6 리포트(통계 아니라 QA율/포워드pnl 집계)
```

## 5. 모듈 상세

### 5.1 수집 (`run_polymarket_market_implication_collect.py`)

```python
SCAN_INTERVAL_S = 86400.0        # 일 1회
MIN_VOLUME_USD = 500.0           # 죽은 마켓 컷 (임계값은 조정 가능, v1 잠정치)
MATURITY_WINDOW_DAYS = 14        # 후보쌍 만기 차이 허용폭
LLM_DAILY_CALL_CAP = 500         # 세이프티, 엔티티태깅+쌍판정 합산
```

- `polymarket/client.py`의 `get_markets()`로 활성마켓 전체 폴링(기존 100cap
  버그 이미 수정된 상태 — 페이지네이션 그대로 신뢰).
- `MIN_VOLUME_USD` 미만 컷 후 daily jsonl 스냅샷:
  `research/data/polymarket_market_implication/YYYY-MM-DD.jsonl`.
- 신규/변경(question 텍스트 변경) 마켓만 `entity_tags.py`로 엔티티 추출 LLM
  호출 — 이미 태깅된 `condition_id`는 캐시 재사용(비용 절감).
- 엔티티 공유 마켓끼리 `pairing.py`로 그룹핑 → `MATURITY_WINDOW_DAYS` 안 드는
  쌍만 후보로 남김.
- 후보쌍 중 미판정 쌍만 `polymarket_market_implication.py`의 LLM 함의판정
  호출 → `pattern_type`, 방향, 부등식 저장(`research/data/polymarket_market_implication/pairs.jsonl`,
  append-only, `condition_id_a+condition_id_b` 키로 재판정 스킵).
- `LLM_DAILY_CALL_CAP` 넘으면 그날은 큐잉만 하고 다음날 이어서 처리.
- LLM 클라이언트: `ai_strategy/advisor.py`와 동일 배선(`openai.OpenAI`,
  `base_url=groq`, `GROQ_API_KEY`) 재사용 — 신규 의존성 추가 안 함. 단, 함의
  판정은 오탐 비용이 커서(§3 B타입 특히) advisor.py의 `llama-3.1-8b-instant`보다
  큰 모델 사용 권장(예: `llama-3.3-70b-versatile`, Groq 제공) — 정확한 모델명은
  구현 시점 Groq 가용 모델 확인 후 확정.

### 5.2 가격 워치 (`run_polymarket_market_implication_watch.py`)

```python
WATCH_INTERVAL_S = 3600.0        # 시간당 1회, LLM 호출 없음
```

- `pairs.jsonl`의 확정 쌍만 대상, `polymarket/clob_client.py`의
  `get_order_book`/`spread_bps_from_book`로 현재 best_bid/ask만 재조회.
- 위반폭 = 부등식 위반량(가격 기준) − 왕복비용(`cost_model.py`의
  `polymarket_effective_cost_bps` 양다리분 재사용, 신규 비용모델 불필요).
- 비용 넘는 위반 발생 시 `research/data/polymarket_market_implication/violations.jsonl`에
  기록(감지시각, pair_id, pattern_type, 위반폭, 당시 가격) — **v1은 로깅만,
  실주문 없음**(§7).

## 6. 검증 방법론 — 기존 BH-FDR 파이프라인과 다름

논리 위반은 확률적 패턴이 아니라 결정론적 부등식이라 랜덤셔플 베이스라인
대비 유의성 검정이 성립하지 않는다. 2단계로 분리:

1. **탐지 정확도 QA (정성적)**: `violations.jsonl` 상위 30~50건을 사람이
   직접 훑어 LLM의 관계판정(방향/부등식)이 실제로 맞는지 확인, 오탐률 산출.
   pattern_type(A/B)별로 분리 집계 — B타입 오탐률이 임계치 넘으면 B타입만
   판정 파이프라인에서 끔(§3).
2. **포워드 페이퍼 로깅**: 실집행 없이 위반 기록만 계속 쌓다가, 쌍의 마켓들이
   resolve되면 헤지 양다리(위반 방향)의 사후 pnl을 계산해 `violations.jsonl`에
   갱신. **최소 N=20~30건** 쌓이기 전엔 결론 내지 않음(sharp_wallet 표본부족
   보류 반복 방지 — 처음부터 명시).
3. **리포트**(`run_polymarket_market_implication_report.py`): 기존
   `compute_report`(survivors/no_edge 포맷)와 다른 새 리포트 함수 —
   pattern_type별 {오탐률, 포워드 건수, 평균 pnl, 승률} 출력.

## 7. 실행모드 / Out of scope

- v1은 **paper-only**. 라이브 전환 조건: §6-1 QA 오탐률 통과 **AND** §6-2
  포워드 N≥20~30건 누적 + 평균 pnl 양수. 미충족 시 sharp_wallet과 동일하게
  paper 무기한 유지 — 프로젝트 전역 컨벤션.
- 실주문/지갑 서명/실집행 — v1 전부 제외(§6 조건 충족 전까지).
- 만기 차이 큰 쌍(방향성 단일다리 구조) — 자본 lock 리스크로 v1 범위 밖,
  매칭만기 헤지형만 다룬다.
- 카테고리 제한 없이 엔티티 기반으로만 후보 좁힘 — tag 기반 사전필터(정치 등)
  는 v1에서 안 씀.

## 8. 테스트 계획

- `tests/test_polymarket_market_implication_entity_tags.py`: 캐시 히트/미스,
  신규 vs 변경 마켓 판정, 빈 응답 처리.
- `tests/test_polymarket_market_implication_pairing.py`: 엔티티 공유 그룹핑,
  `MATURITY_WINDOW_DAYS` 경계값(포함/제외), 자기 자신 페어 제외.
- `tests/test_polymarket_market_implication.py`: 부등식 위반폭 계산(A/B
  타입별), 비용 차감 후 순위반폭, pattern_type 태그 보존.
- `tests/test_run_polymarket_market_implication_collect.py`: `LLM_DAILY_CALL_CAP`
  도달 시 큐잉, 재판정 스킵(캐시 히트).
- `tests/test_run_polymarket_market_implication_watch.py`: 위반 로깅 트리거
  조건(비용 넘는 경우만), resolve 후 pnl 갱신 로직.
