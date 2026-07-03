# S1 — 이벤트 family 확장 (알파 사냥 로드맵 1/4)

**작성일:** 2026-07-03
**상태:** 설계 승인됨 → 구현 계획 대기
**로드맵 위치:** 알파 사냥 S1. 이후 S2(buyback 심화)·S3(새 데이터 연못)·S4(새 시장)는 각자 spec→plan 사이클.

## 목표 (한 줄)

경제적 근거 있는 새 이벤트 family 4개를 사전등록해 **한 배치**로 검증 파이프(event_study → BH-FDR → 레드팀 → classify)에 태우고, 새 *생존* 엣지가 있는지 정직하게 판정한다.

## 배경 / 왜 이벤트인가

지금까지 기각 패턴이 방향을 가리킨다:
- **가격 패턴**(TA·ICT·유동성웨이브·단타·잘못된 빈도 팩터) → 전멸.
- **이벤트/구조**(자본구조 공급·수요 이벤트) → **buyback만 생존**(전세계 buyback anomaly와 일치).

데이터가 말한다: "차트 파동은 죽고, 공시/구조 이벤트는 산다." 따라서 알파 사냥은 이벤트/구조 축을 더 판다. S1은 그 축에서 **미검증 이벤트 형제들**을 발굴한다.

방금(2026-07-03) 실배치로 기존 family는 전부 판정 완료: buyback·supply_contract·treasury_trust·capital_reduction=REJECT_REDTEAM, spinoff·turn_to_profit=REJECT_BH, buyback_cancel=UNDERPOWERED(데이터 없음). 즉 기존 연못은 소진 → 새 family가 S1의 실체.

## 핵심 원칙 — 인프라 재사용

`autoresearch.run_batch()`가 이미 `FAMILIES` 전체를 순회한다. FAMILIES에 family를 추가하면 배치 편입·BH-FDR·레드팀·registry 기록·lab reconcile·UI 표시까지 **전부 자동**. 신규 코드는 사실상 (1) family 정의 (2) DART 데이터 풀 (3) 레드팀 통제 확인뿐이다.

### 데이터 흐름
```
research/scanner/families.py  (FAMILIES +4 정의: 키워드·방향·피드)
        │
        ▼  run_scanner (FAMILIES 키워드 → DART pull)
events_{fam_id}.jsonl  (PIT·survivorship-free 캐시)
        │
        ▼  load_events(fam_id)
research/autoresearch/engine.py::run_batch()
   → event_study(익일진입·20거래일·매칭 random)
   → benjamini_hochberg(구+신 전체 family p값)   ← 다중검정 보정
   → review_strategy(redteam 통제)                ← confound/lookahead/생존편향
   → classify(단일 진실원) → leaderboard
        │
        ▼  (이미 배선됨) LabEngine.reconcile_from_batch → UI 판정피드
```

## 4 family 스펙 (사전등록·동결)

각 family는 `research/scanner/families.py`의 `FAMILIES` dict에 아래 형태로 추가한다:
`{"keywords": [...], "exclude": [...], "direction": ..., "pblntf_ty": ..., "event_type": None, "thesis": "..."}`.

| id | keywords | exclude | pblntf_ty | direction | thesis (경제 메커니즘) | kill (사망조건) |
|---|---|---|---|---|---|---|
| `treasury_disposal` | `자기주식처분` | `취득` | B | bearish | 자사주 처분=공급↑. buyback(공급↓ 호재)의 거울 — 방향축 확증 | 매칭 random 못 이기거나 드리프트가 bearish 아니면 폐기 |
| `control_change` | `최대주주변경`, `경영권` | `-` | B | bullish | 최대주주 이전=인수/경영권 프리미엄 기대 | random·레드팀 통과 실패 시 폐기 |
| `asset_transfer` | `자산양수도`, `영업양수도` | `-` | B | research | 구조조정 재평가(방향 불명 → 양방향 탐색) | 양방향 다 random과 무구분 시 폐기 |
| `rights_issue` | `유상증자` | `무상` | B | bearish | 신주 발행=희석. 이미 음드리프트로 알려짐(대조군) → 정식 회피신호로 확증 | 음드리프트 확증 실패(random과 무구분) 시 폐기 |

**주:** `rights_issue`는 `research/data/kr_dart_events.py`의 `EVENT_DEFS`에 이미 존재한다(유상증자, bearish). 이미 pull된 `events_rights_issue.jsonl`이 있으면 재사용해 pull 비용을 아낀다. 나머지 3개는 신규 pull.

**동결:** 위 키워드·exclude·방향·비용(40bps)·보유기간(20거래일)은 사전등록이며 **결과를 본 뒤 튜닝하지 않는다.** 조정하고 싶으면 별도 v2 family로 신규 등록(기존 v1 동결) — 기존 규율([[feedback_v2_shadow_only]]) 준수.

## 데이터 커버리지 처리

- 각 family를 pull 후 `load_events(fam_id)` 이벤트 수 확인.
- **n ≥ 30**: 배치에서 event_study 판정.
- **n < 30**: `UNDERPOWERED`로 정직히 표기(buyback_cancel n=0 선례). 커버리지 부족은 실패가 아니라 데이터 게이트 — 억지로 판정하지 않는다.
- 키워드가 실제 DART `report_nm`과 안 맞으면 커버리지 0 가능. 구현 시 소량 윈도우로 커버리지 프로브 먼저(스캐너 refill 방식) → report_nm 실측 후 키워드 확정.

## 규율 — p-해킹 방지

- **사전등록·동결:** 4개 방향·키워드 고정. 결과 후 튜닝 금지.
- **한 배치·BH-FDR:** 구 생존자 포함 전체 family p값으로 다중검정 보정. family를 무한정 늘리면 BH 임계가 빡세져 진짜 엣지도 탈락 → 4개로 제한.
- **레드팀 통제 필수:** survivorship·lookahead·cost_stress·entry_confound·multiple_testing. classify에서 candidate = BH 생존 AND 레드팀 CLEARED AND net>0 AND wf 양쪽 양수.
- **죽은연못 자동생성 금지:** 경제 메커니즘 없는 family는 넣지 않는다([[feedback_kr_validation_lessons]]).

## 성공 기준 (정직)

- **1차(반드시 달성):** 4개 family가 파이프를 완주해 정직한 판정(candidate/watchlist/reject_*/underpowered)을 산출한다. 엣지 발견이 아니라 **판정 산출**이 1차 목표.
- **승리:** ≥1개 family가 candidate 또는 watchlist로 생존(BH+레드팀+wf 통과).
- **정당한 비승리:** 전부 REJECT여도 유효한 과학 결과다. 특히 `treasury_disposal`가 bearish로 확증되면 buyback의 공급/수요 축을 **양방향으로 검증**(호재↓공급 / 악재↑공급) — 메커니즘 이해 획득. `rights_issue` 음드리프트 확증도 회피신호로 가치.
- **실패로 간주하는 것:** 커버리지를 못 만들어 4개 다 underpowered이거나, 규율을 어겨(튜닝·과다 family) p-해킹으로 흐르는 것.

## 범위

**포함:** 4 family 정의 + DART pull + 레드팀 통제 확인 + 배치 실행 + 정직 판정.
**불포함(YAGNI):**
- 곁가지 UI/기능 정리 — S1엔 불필요(검증면 이미 통합·정결). 별도 작업.
- S2~S4(buyback 심화·새 데이터 연못·새 시장) — 각자 spec.
- 라이브 집행 — 엣지 생존 후 페이퍼→forward 거쳐야 하며 사람 arm 필요. S1은 연구·판정까지만.

## 파일

| 파일 | 변경 |
|---|---|
| `research/scanner/families.py` | `FAMILIES`에 4 family 추가. 필요 시 `redteam_spec` 통제 특성 보강 |
| `research/data/kr_dart_events.py` | 신규 3 family pull 경로(스캐너가 FAMILIES 키워드 사용). `rights_issue`는 기존 EVENT_DEFS 재사용 |
| `research/scanner/` (run_scanner) | 4 family 데이터 pull 실행(커버리지 프로브 → 확정 pull) |
| 배치·registry·reconcile·UI | 무변경(자동 편입) |
| `tests/` | family 정의·키워드 필터 단위 테스트 + 배치 편입 스모크 |

## 테스트 전략

- **단위:** 4 family가 FAMILIES에 정의되고 keywords/exclude/direction 스키마가 올바른지. exclude 필터가 반대 신호를 거르는지(예: rights_issue가 무상증자 제외).
- **커버리지:** pull 후 각 family 이벤트 수 리포트(n≥30 여부). 실데이터라 CI 불가 → 수동 검증 스크립트 + 결과 로그.
- **배치 스모크:** run_batch가 4 신규 family를 leaderboard 또는 underpowered에 포함하는지(monkeypatch로 event_study 대체한 결정 로직 테스트).
- **정직성:** underpowered/reject가 정확히 분류되는지(가짜 candidate 없음).

## 미결(구현 계획에서 확정)

- 각 family 실제 DART `report_nm` 키워드 정합성(프로브로 실측).
- `control_change`가 B피드(주요사항)에 있는지 vs 지분공시(D, 새 피드 필요) — B에 없으면 UNDERPOWERED 예상, 이는 정직한 결과이며 S3(새 데이터 연못)로 이관 후보.
