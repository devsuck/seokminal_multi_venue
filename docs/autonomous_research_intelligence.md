# Autonomous Research Intelligence Enhancement (P171–P180)

> v2.0 아키텍처는 **동결**됐다. 이 단계는 **새 아키텍처가 아니라 지능 향상**이다.
> 새 패키지·엔진·원장·DB·벡터스토어·메모리·실행계층 없음. **기존 Research OS 조율·확장만.**

기존 엔진을 조합해 4가지 능력을 강화한다: ① 더 나은 아이디어 생성 ② 지속적 기회 발굴
③ 유망 아이디어 자동 확장 ④ 완료 사이클로부터 학습. 모두 **결정적·자문 전용·사람 거버넌스**.

## 모듈 (모두 `jarvis/research_workflow/`, 기존 엔진 재사용)

| 단계 | 모듈 | 하는 일 | 재사용 |
|---|---|---|---|
| P171 | `creative_hypothesis` | 다중 지식원 결정적 조합 → **다양한 가설** + novelty/근거체인/유사연구/상충증거/불확실성/확신도/필요검증 | hypothesis_generator·regime·macro/sector_intelligence·semantic_recall·conflict_detection |
| P172 | `research_search` | 가설 1건 → 탐색 트리(차원별 변형) → 스코어·프루닝·중복병합 → 최고가치 표면화 | research_similarity·sector_intelligence |
| P173 | `continuous_queue` | 다중 소스 백로그, 새 정보 시 자기 재우선순위화 (**큐만**) | creative_hypothesis·opportunity_discovery·conflict_detection·research_ingestion·research_prioritizer |
| P174 | `experiment_prioritization` | 7요인 + **3요인 확장**(검증복잡도·커버리지·지식갭) → 다음 실험 추천 | research_prioritizer·knowledge_graph |
| P175 | `research_expansion` | 가설 → 수백 후보(**계층적 프루닝** + 중복탐지), 브루트포스 아님 | research_search·research_similarity |
| P176 | `self_reflection` | 사이클 후 실패/생존/놀람/부족/강화/다음/금지 성찰, 교훈은 **기존 메모리에만** 저장 | learning_engine·research_ingestion |
| P177 | `research_planning` | 일/주/월 아젠다 + **분기 로드맵** (**계획만**) | research_scheduler·continuous_queue·experiment_prioritization·regime |
| P178 | `collaborative_research` | 고정 파이프라인 → **협업 라운드**(challenge/refine/split/merge/reject/request_evidence), Director 조율, **자율 승인 없음** | multi_agent_workflow·semantic_recall |
| P179 | `productivity_optimization` | 8지표 측정 + 운영 개선 **추천만**(코드 자동 수정 없음) | research_ingestion·knowledge_quality·operational_metrics |
| P180 | `autonomy_validation` | 안전·재사용 감사(실행/브로커/거래/배분/승인/새원장/중복 없음) + 전 능력 스모크 | governance·ledger |

## 안전 불변식 (P180 검증)

- **실행 없음** — `execute()`/`trade()`/`place_order()`/`allocate()`/`approve()`/`deploy_strategy()` 정의 0개 (AST 강제)
- **브로커/집행 import 없음** — `jarvis.execution|broker|live_execution|live_trading|portfolio_execution` 0개
- **새 원장 없음** — `ALL_LEDGERS == 3` 유지
- **중복 로직 0** — 새 `*Engine` 클래스·새 `append_*` 원장 함수 정의 0개
- **재사용 19개** 기존 모듈 조율 (P180 reuse audit)
- **자문 전용** — 모든 산출 `is_advisory=True, is_decision=False, requires_human_review=True`
- **자율 승인 없음** — 협업 Director 는 조율만, `autonomous_approval=False`
- **연구 자동 실행 없음** — 가설/큐/확장은 제안일 뿐, 백테스트는 사람 체크포인트에서만

## 콘솔 (READ ONLY)

`GET /console/research-intelligence?q=<질문>` — 위 10개 능력을 한 번에 집계.
자문만, 연구 자동 실행 없음, 새 아키텍처 없음.

## 남은 한계 (정직)

- 가설 생성은 **결정론적 다중원 조합** — LLM 창발 아님(재현성 우선).
- 커버리지/지식갭 지표는 축적된 지식그래프에 의존.
- 매크로/레짐 라벨은 주입 값 없으면 UNKNOWN.
- 협업 액션은 결정적 휴리스틱 — 사람 검토 결과와 대조해 가중 보정 여지.

## 향후 (아키텍처 동결 유지)

데이터 소스 확대 → 커버리지 정확도 · 완전 검증 세트 백필 → 판정 품질 · 협업 액션 학습 보정.
**신규 기능 패밀리 추가 금지.** operations·data quality·model improvement·research outcomes 에 집중.
