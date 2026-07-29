# Research OS Final Consolidation (P204–P208)

> Investment OS 확장 **전** 마지막 정리. 지능 추가 아님 — **더 작고·깨끗하고·안전하고·측정 가능하게.**
> 아키텍처 동결 · 원장 3개 불변 · 실행 없음 · 사람 거버넌스 필수 · 모든 신규 공개 API 는 facade-only.

## P204 Research Discovery Facade (완료)

단일 namespace `research_discovery`: `generate() · search() · expand() · criticize() · rank()` (+ `discover()`).
내부 재사용(유지·deprecated): hypothesis_generator · creative_hypothesis · hypothesis_discovery ·
research_search · research_expansion · research_critic · research_priority. **재작성 없음, 공개 API 유실 없음.**

## P204.5 Prediction Coverage Audit (`prediction_coverage_audit.py`) — 지표만

"무엇을 기록 중인가"를 점수보다 먼저. capture 완결성 · missing captures(invalidation/horizon/evidence) ·
confidence 분포 · source 분포·커버리지 · duplicate · pending/evaluated. **대시보드 없음.**

## P205 Research Validation Score (`research_validation_score.py`) — n<20 이면 숫자 없음

**graded(RIGHT/WRONG) >= 20 전에는 status=PROVISIONAL, score=None.** 데이터 5개로 "62점" 찍는 자기기만 차단.
구성(충분 시): Accuracy · Calibration · Baseline-relative · Sample confidence + composite.
INVALIDATED(리스크관리 성공)·INCONCLUSIVE(데이터 부족)는 채점 제외. 투자 추천 아님.

## P206 Governance Deprecation — 삭제 없음

중복 governance 모듈 11개(system/release/autonomy/autonomous_v3/operational/ops/agent/brain/
intelligence_validation·memory_audit·research_audit)에 `__deprecated__` 마커 + `governance.deprecations()`
레지스트리. **공개 API 는 `validate(domain)`/`validate_all()`.** 모듈은 ≥1 릴리스 유지(살아있음, forwarding·삭제는 이관 후).

## P207 Dashboard Consolidation Plan — 계획만(UI 없음)

21 → 5 페이지 마이그레이션 인벤토리(`dashboard_consolidation_plan_p207.md`). Brief · Discovery ·
Intelligence · Brain · Committee&Governance. 21/21 흡수, 엔드포인트 무변경. **UI 구현은 별도 승인.**

## P208 Meaning-preserving Golden 확장

Golden 3겹:
- **Meaning** (`research_meaning.json`) — 553건 연결 의미.
- **Call Graph: discovery** (`call_graph.json`) — 발견 파사드 조율 위상.
- **Call Graph: research workflow** (`call_graph_research_workflow.json`) — loop→cycle→gate→validation→selection 위상.

리팩터링이 의미(meaning)·발견 호출구조·연구워크플로 호출구조 **셋 다** 보존하는지 검증. 전부 통과.

## 성공 지표 (달성)

```
Governance:  12 modules → 1 facade (2 public + 5 domains), 11 deprecated (삭제 없음)
Discovery:   7 modules → 1 facade (5 methods), 내부 유지
Accountability: coverage audit + validation score(PROVISIONAL 게이트)
Goldens:     meaning + call-graph×2 = 3겹, 전부 통과
Behaviour/Meaning: 동일   Public APIs: 감소   Maintenance: 감소
회귀 319 통과 · governance COMPLIANT · ledger==3 · 실행/브로커/벡터DB 없음
```

**다음: Investment OS 확장 — 단, Research OS 는 이 상태로 동결.**
