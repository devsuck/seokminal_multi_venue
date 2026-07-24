# 7. Integration Proposal & Roadmap (통합 제안·로드맵)

## 통합 제안(계열별, 결정적)

| Family | Category | Action | Members | Rationale |
|---|---|---|---|---|
| agent_* | Agents | **KEEP** | 2 | 소규모 계열 — 현행 유지, 통합 이득 낮음 |
| autonomous_research_* | Research | **INTEGRATE** | 3 | 3개 동일계열 — 공용 파사드로 통합 검토(중복 축소) |
| data_* | MIXED | **REVIEW** | 2 | 다중 카테고리 계열 — 책임 경계 재정의 후 결정 |
| execution_* | Execution | **INTEGRATE** | 8 | 8개 동일계열 — 공용 파사드로 통합 검토(중복 축소) |
| experiment_* | Simulation | **INTEGRATE** | 3 | 3개 동일계열 — 공용 파사드로 통합 검토(중복 축소) |
| governance_* | MIXED | **REVIEW** | 4 | 다중 카테고리 계열 — 책임 경계 재정의 후 결정 |
| knowledge_* | Knowledge | **INTEGRATE** | 3 | 3개 동일계열 — 공용 파사드로 통합 검토(중복 축소) |
| model_* | MIXED | **REVIEW** | 2 | 다중 카테고리 계열 — 책임 경계 재정의 후 결정 |
| operations_* | System | **KEEP** | 2 | 소규모 계열 — 현행 유지, 통합 이득 낮음 |
| paper_* | MIXED | **REVIEW** | 2 | 다중 카테고리 계열 — 책임 경계 재정의 후 결정 |
| portfolio_* | Execution | **KEEP** | 2 | 소규모 계열 — 현행 유지, 통합 이득 낮음 |
| production_* | System | **INTEGRATE** | 3 | 3개 동일계열 — 공용 파사드로 통합 검토(중복 축소) |
| research_* | MIXED | **REVIEW** | 29 | 다중 카테고리 계열 — 책임 경계 재정의 후 결정 |
| research_agent_* | Agents | **KEEP** | 2 | 소규모 계열 — 현행 유지, 통합 이득 낮음 |
| research_memory_* | Knowledge | **KEEP** | 2 | 소규모 계열 — 현행 유지, 통합 이득 낮음 |
| security_* | System | **KEEP** | 2 | 소규모 계열 — 현행 유지, 통합 이득 낮음 |
| system_* | MIXED | **REVIEW** | 2 | 다중 카테고리 계열 — 책임 경계 재정의 후 결정 |

## 통합 로드맵

- 1. 로컬 런타임 단일 진입점 도입(P42) — 기존 boot()/status() 통합, 중복 스크립트 제거
- 2. 통합 네비게이션 정보구조 도입(P43) — 기존 페이지를 카테고리로 재배치, 신규 대시보드 생성 금지
- 3. 개인 연구 어시스턴트(P44) — 기존 원장 READ ONLY 요약, 신규 지능 계층 없음
- 4. 로컬 자동화(P45) — 반복 연구 작업 워크플로화, 거래/배포/배분 없음
- 통합 검토: autonomous_research_* 계열(Research, 3개) → 공용 파사드
- 통합 검토: execution_* 계열(Execution, 8개) → 공용 파사드
- 통합 검토: experiment_* 계열(Simulation, 3개) → 공용 파사드
- 통합 검토: knowledge_* 계열(Knowledge, 3개) → 공용 파사드
- 통합 검토: production_* 계열(System, 3개) → 공용 파사드
- 경계 재검토: data_* 계열(MIXED, 2개)
- 경계 재검토: governance_* 계열(MIXED, 4개)
- 경계 재검토: model_* 계열(MIXED, 2개)
- 경계 재검토: paper_* 계열(MIXED, 2개)
- 경계 재검토: research_* 계열(MIXED, 29개)
- 경계 재검토: system_* 계열(MIXED, 2개)

> 원칙: 기존 소유 경계 불변 · 기존 원장 READ ONLY · 추가만 · 마이그레이션/덮어쓰기 없음 · 기능이 이미 있으면 INTEGRATE(중복 금지).

