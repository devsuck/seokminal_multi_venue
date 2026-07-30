# STEP3-A — Research Namespace Inventory & Dependency Audit

생성일: 2026-07-31
목적: `jarvis/research_*` + `jarvis/knowledge_intelligence` + `jarvis/research_queue.py` 전체(50개 유닛)를 이름이 아닌 실증거(import/runtime/API/dashboard/scheduler/state/data-flow/tests)로 재분류. **삭제는 이 문서 승인 후 STEP3-B에서만 실행.**

보호 대상(out of scope, 이번 감사에서 건드리지 않음): `research/autoresearch`(진짜 검증 엔진), `research_workflow`, `research_ingestion`, `research_memory_intelligence`, `research_assistant`, `research_navigation`, `research_risk_intelligence`, `research_queue.py`.

## Summary

| 분류 | 개수 | 의미 |
|---|---|---|
| KEEP | 4 | 실제 import/runtime/dashboard 의존 확인 — 손대지 않음 |
| ARCHIVE | 9 | 현재 미실행이나 미래 참조/마이그레이션 가치 있음 — deprecated 마커만, 삭제 안 함 |
| REMOVE_CANDIDATE | 37 | import 0 · runtime 0 · API 0 · dashboard 0 · scheduler 0 · state/ledger 0 · data-flow 0 · tests(자체 자가테스트만) — 8개 조건 전부 충족 |
| **합계** | **50** | jarvis/research_* 디렉토리 49개 + research_queue.py 1개(loose file, 최초 스윕 누락분) |

이번 STEP3-A 과정에서 원 6-agent 스윕이 놓친 **4개 감사 공백(AUDIT GAP)**을 발견해 KEEP으로 확정: `research_assistant`, `research_navigation`, `research_risk_intelligence`, `research_queue.py`. 전부 보호 대상 `research_workflow`/`research_ingestion`에서 직접 import되거나 그 자신이 protected 모듈의 핵심 상태(ledger)를 소유하는 load-bearing 코드였다.

## Mandatory Investigation Areas — 결론

### 1. Research OS Cluster (9개: research_os · research_os_core · research_api · research_api_gateway · research_kg · research_validation · research_manager · research_planning · research_reviewer)

**판정: "Research OS"라는 이름을 가진 실질 시스템은 존재하지 않는다.** 대시보드/`console_api.py`의 `/console/research-os` 엔드포인트가 실제로 집계하는 것은 `research_navigation`(P43) + `integration_audit`(P41) + `research_assistant`(P44) + `local_automation`(P45) — 즉 **보호 대상 4개 모듈**이다. `jarvis/research_os` 디렉토리 자체는 그 이름과 무관한 병렬 스캐폴드로, 자기 자신만 참조하는 고립된 트리다. `research_kg`도 동일 패턴: 실제 지식그래프 엔드포인트(`build_knowledge_graph`, `GET /research-os/graph`)는 `jarvis.research_workflow.knowledge_graph`(보호 대상)를 쓰고, `jarvis/research_kg`가 소유한다고 선언한 `kg_entities.jsonl`은 디스크 어디에도 존재하지 않는다 — 데이터 없는 껍데기. `research_planning`도 동일: `console_api.py`가 실제로 쓰는 건 `jarvis.research_workflow.research_planning`(보호 대상 서브모듈)이고, 최상위 `jarvis/research_planning`은 이름만 같은 별개 고립 모듈. → 9개 중 8개 REMOVE_CANDIDATE, `research_validation` 1개만 사용자 STEP3 지시로 ARCHIVE(증거만으로는 REMOVE 근거지만 마이그레이션 가능성 고려해 보존).

### 2. Discovery/Agent Cluster (6개: research_loop · research_agents · research_agent_coordination · research_agent_coordinator · research_strategy_generation · research_task_planner)

**"Agent"라는 이름이 있다고 자동 agent 시스템이 아니다 — 확인 결과 전부 미실행 스캐폴드.** 6개 전부 스케줄러/cron/tmux 등록 없음, CLI 진입점 미사용, 자동 가설생성 파이프라인에 연결 안 됨. `research_agent_coordination`/`research_strategy_generation`은 `security_audit`의 동적 `AUDIT_TARGETS` importlib 스캔에서만 소비되는데, 그 테스트 파일 자체가 `pyproject.toml` 기본 testpaths 바깥에 있어 평상시 전혀 실행되지 않는다(죽은 감사 도구 클러스터 — STEP5에서 함께 archive 예정). → `research_agent_coordination`/`research_agents`/`research_strategy_generation` 3개는 사용자 지시로 ARCHIVE, `research_loop`(레포 전체에서 가장 고립된 모듈 — import·선언적 참조·카탈로그 언급 전부 0건)도 ARCHIVE(override), `research_agent_coordinator`/`research_task_planner`는 REMOVE_CANDIDATE.

### 3. Knowledge Graph (research_kg · research_memory · knowledge_intelligence)

**실제 그래프 저장소/노드-엣지 데이터/런타임 쿼리 없음 — 전부 placeholder 확인.** `research_kg`는 위 1번 항목 참조(데이터 파일 자체가 디스크에 없음). `research_memory`는 real import 0건이며 `research_memory_system`·보호 대상 `research_memory_intelligence`와 이름 충돌 트랩까지 겹쳐 있었으나 실증거로 분리 완료 — 사용자 지시로 ARCHIVE. `knowledge_intelligence`는 대시보드 포함 레포 전체에서 자기 디렉토리 밖 참조 0건, 실제 리콜/쿼리 기능 없음 — REMOVE_CANDIDATE.

## Module Table

### KEEP (4)

| Module | Classification | Evidence | Action |
|---|---|---|---|
| `research_assistant` | KEEP | 보호 대상 `research_workflow/orchestrator.py` + `research_ingestion/models.py`가 직접 import, `console_api.py` P44 엔드포인트 10+ 호출 지점 | 유지 — 삭제/보관 없음 |
| `research_navigation` | KEEP | `console_api.py` P43 엔드포인트가 `NavigationEngine`/`section_for` import, 대시보드 `lib/research-os.ts`가 `navigation_manifest.json` 출력 직접 소비 | 유지 — 삭제/보관 없음 |
| `research_queue.py` | KEEP | 보호 대상 `research_workflow`(orchestrator/cockpit/hypothesis_generator/research_discovery 등 11+ 지점) + `research_assistant`가 import, `research_pending.jsonl`/`research_processed.jsonl` 상태 소유, 대시보드 `live-intelligence/page.tsx` 소비 | 유지 — 삭제/보관 없음 |
| `research_risk_intelligence` | KEEP | 보호 대상 `research_workflow/orchestrator.py` + `knowledge_graph.py`가 `StrategyRiskReasoner`/`_profile` 직접 import | 유지 — 삭제/보관 없음 |

### ARCHIVE (9) — deprecated 마커 + 문서화, 삭제 아님

| Module | Classification | Evidence | Action |
|---|---|---|---|
| `research_agent_coordination` | ARCHIVE | security_audit 동적 스캔에서만 소비(testpaths 밖, 평상시 미실행), static import 0 | deprecated 마커 + 문서화 |
| `research_agents` | ARCHIVE | 자기 디렉토리 밖 0건; 사용자 STEP3 override(마이그레이션 가능성) | deprecated 마커 + 문서화 |
| `research_loop` | ARCHIVE | 레포 전체 최고 고립도(0건); 사용자 STEP3 override | deprecated 마커 + 문서화 |
| `research_memory` | ARCHIVE | real import 0; `research_memory_system`/보호대상 `research_memory_intelligence`와 이름충돌 분리 완료; 사용자 STEP3 override | deprecated 마커 + 문서화 |
| `research_monitoring` | ARCHIVE | security_audit 동적 스캔 전용(testpaths 밖); LAYER_REGISTRY 등록만 존재 | deprecated 마커 + 문서화 |
| `research_reliability` | ARCHIVE | security_audit 동적 스캔 + system_integration 해시체크(둘 다 testpaths 밖) | deprecated 마커 + 문서화 |
| `research_resource_manager` | ARCHIVE | security_audit 동적 스캔 전용(testpaths 밖) | deprecated 마커 + 문서화 |
| `research_strategy_generation` | ARCHIVE | security_audit 동적 스캔 전용(testpaths 밖) | deprecated 마커 + 문서화 |
| `research_validation` | ARCHIVE | 증거상 REMOVE 근거지만 real `research/autoresearch`와 무관 확인 후 사용자 STEP3 override로 보존 | deprecated 마커 + 문서화 |

### REMOVE_CANDIDATE (37) — 8개 조건(import/runtime/API/dashboard/scheduler/state·ledger/data-flow/tests 전부 0) 충족, git rm 대상

| Module | Evidence |
|---|---|
| `knowledge_intelligence` | 자기 디렉토리 밖 0건(대시보드 포함) |
| `research_agent_coordinator` | 0건; 5개 sibling ledger 선언적 참조만; `research_agent_coordination`(별개 P26)과 구분 확인 |
| `research_api` | `api_server/main.py`의 `research_api` import는 무관한 형제 FastAPI 라우터(`api_server/research_api.py`, jarvis import 0) — 동명충돌 확인 |
| `research_api_gateway` | self-import만; 문서 카탈로그 문자열만 |
| `research_automation` | self-import만; `jarvis/__init__.py` status() 필드는 무관 문자열 |
| `research_collaboration` | self-import만; facades.models 메타데이터 튜플만 |
| `research_compliance` | self-import만; 9개 sibling ledger 선언적 키만 |
| `research_conflict_resolution` | self-import만; 6개 sibling ledger 선언적 키만 |
| `research_control` | self-import만; facades.models + autonomous_research_os ledger 선언적 키만 |
| `research_control_plane` | self-import만; `research_api`(별개) + integration_audit 카탈로그 문자열만 |
| `research_coordinator` | self-import만; 6개 sibling ledger + facades 선언적 키만 |
| `research_council` | self-import만; research_workflow 독스트링 한글 프로즈 언급뿐(실제 import 아님) |
| `research_dashboard_backend` | self-import만; console_api/lab_api/main.py 미import; 대시보드는 정적 nav 카탈로그에만 이름 존재 |
| `research_data` | self-import만(무관하지만 이름 유사한 `research/data/`와 구분 확인); 16개 sibling ledger 선언적 키만 |
| `research_event_bus` | self-import만; 4개 sibling ledger 선언적 키만; pub/sub 배선 없음 |
| `research_evolution` | 타 모듈 테스트의 negative-assertion fixture 문자열만; 11개 ledger 선언적 키만 |
| `research_experience_memory` | self-import만(보호대상 research_memory_intelligence와 구분 확인); 선언적 참조뿐 |
| `research_governance` | 레포 최다 문자열 참조(30+ ledger)지만 real import 0건 |
| `research_improvement` | self-import만; 5개 sibling ledger + facades 선언적 키만 |
| `research_insight_intelligence` | self-import만; architecture_docs 카탈로그 항목만 |
| `research_kg` | `kg_entities.jsonl` 디스크에 실존 안 함(33개 모듈이 선언만); 실제 그래프 엔드포인트는 보호대상 `research_workflow.knowledge_graph` 사용 |
| `research_learning` | self-import만; 3개 sibling ledger + facades 선언적 키만 |
| `research_lifecycle` | self-import만; 무관한 `research_api` 패키지가 자기 소유 동명 role 문자열 사용 중(이 패키지 import 아님) |
| `research_literature` | self-import만; 4개 sibling ledger 선언적 키만 |
| `research_manager` | self-import만; documentation 모듈의 범용 introspect_package 테스트는 기능적 호출자 아님 |
| `research_memory_system` | 0건; 2개 sibling ledger + agent_runtime 모델 튜플 선언적 참조만 |
| `research_observability` | 0건; ~7개 sibling ledger 선언적 참조만 |
| `research_observatory` | 0건; ~9개 sibling ledger + facades + integration_audit 카탈로그 선언적 참조만 |
| `research_operations` | 0건; 문자열 fixture 기본값 + 선언적 ledger 참조만 |
| `research_optimization_engine` | 0건; 2개 sibling ledger 선언적 참조만 |
| `research_orchestration` | 0건; ~9개 sibling ledger + facades 선언적 참조만 |
| `research_organization` | 0건; `console_api.py`의 `research_organization()` 엔드포인트는 `research_workflow.*`만 import(동명충돌 확인) |
| `research_os` | 0건; `console_api.py`의 `research_os()` 엔드포인트는 `research_navigation`/`integration_audit`/`research_workflow.*`만 import(동명충돌 확인) |
| `research_os_core` | 0건; integration_audit 카탈로그 셋 언급뿐(import 아님) |
| `research_planning` | 0건; `console_api.py`의 `research_planning` 필드는 보호대상 `research_workflow.research_planning`(별개 서브모듈)이 채움(동명충돌 확인); ~9개 sibling ledger 선언적 참조만 |
| `research_reviewer` | 0건; 5개 sibling ledger + facades 선언적 참조만 |
| `research_task_planner` | 0건; 4개 sibling ledger 선언적 참조만 |

## Dependency Report

**실제 살아있는 import 그래프**(research 네임스페이스 내부, Phase1과 무관하게 항상 보존):
```
console_api.py ──P43──> research_navigation.engine.NavigationEngine
console_api.py ──P44──> research_assistant.engine.ResearchAssistantEngine
console_api.py ──P41──> integration_audit.scanner
console_api.py ──/research-os──> (P41+P43+P44+P45 집계, 자체 함수. jarvis.research_os 모듈 미사용)
console_api.py ──/research-os/graph──> research_workflow.knowledge_graph (jarvis.research_kg 미사용)
console_api.py ──research_planning 필드──> research_workflow.research_planning (jarvis.research_planning 미사용)
research_workflow.orchestrator ──> research_assistant, research_risk_intelligence, research_queue.py
research_workflow.knowledge_graph ──> research_risk_intelligence.failure_reasoning._profile
research_ingestion.models ──> research_assistant.models.classify_failure
research_workflow.__init__ ──> research_workflow.research_planning (내부 서브모듈, 최상위 research_planning과 별개)
```

**37개 REMOVE_CANDIDATE의 공통 패턴** (모두 확증된 false-positive/dead 신호):
1. **선언적 SOURCE_LEDGERS 딕셔너리 키** — 수십 개 sibling `ledger.py`가 `"research_governance": (...)` 같은 문자열 키로 자기 자신의 로컬 jsonl 파일명을 선언할 뿐, 실제 import 아님 (governance_memory와 동일 패턴, STEP2에서 이미 확인된 것과 동형)
2. **동명 로컬 함수/엔드포인트 충돌** — `research_os`/`research_organization`/`research_planning`/`research_api` 등, `console_api.py`나 sibling 패키지가 같은 이름을 갖되 내부적으로는 `research_workflow.*`(보호 대상)만 import (STEP1의 `autonomous_research`, STEP2의 `production_readiness`와 동일 충돌 패턴)
3. **negative anti-coupling 테스트 단언** — `assert "import jarvis.X" not in src` 형태로 "이 모듈을 안 쓴다"를 증명하는 테스트가 grep 상 유일한 히트로 잡히는 경우
4. **security_audit 동적 스캔 전용** — `pyproject.toml` testpaths 밖에 있어 평상시 전혀 실행되지 않는 감사 도구가 `AUDIT_TARGETS`로 importlib 스캔하는 경우만 존재(→ ARCHIVE, STEP5의 죽은 감사도구 클러스터와 함께 처리 예정)
5. **facades.models 메타데이터** — `jarvis/facades`(자체도 외부 호출자 0건, dynamic import 없음, 순수 읽기전용 레지스트리)가 "과분할 계열" 문서화 목적으로 이름만 나열

## Risk Report

**37개 REMOVE_CANDIDATE 전체 공통 리스크 프로필**: 낮음(LOW).
- **삭제 위험도**: 낮음 — 8개 검증 조건(import/runtime/API/dashboard/scheduler/state·ledger/data-flow/tests) 전부 0, 각 모듈 존재 확인은 자기 디렉토리 안의 자가 테스트(`tests/test_<module>.py`)뿐이며 그 테스트조차 그 모듈 자신만 검증
- **대체 기능 필요 여부**: 없음 — 실제 기능은 이미 보호 대상(`research_workflow`/`research_ingestion`/`research_assistant`/`research_navigation`/`research_risk_intelligence`/`research_queue.py`)이 수행 중이며 REMOVE_CANDIDATE들은 그 실제 구현과 병렬로 존재하는 미배선 스캐폴드
- **마이그레이션 필요성**: 없음 — 데이터(`_state/*.jsonl`) 자체가 존재하지 않는 모듈이 대부분(선언만 되고 한 번도 write된 적 없음)

**9개 ARCHIVE 공통 리스크 프로필**: 삭제하지 않으므로 리스크 없음. deprecated 마커 부착 + 문서화만 진행, export 제거 여부는 STEP3-B에서 개별 검토.

## Next Step

이 문서 승인 시 STEP3-B 실행:
1. **REMOVE_CANDIDATE 37개** → `git rm`, 그룹 단위 커밋(예: Research OS Cluster 8개 / Discovery-Agent Cluster 2개 / Knowledge Graph 2개 / 나머지 25개 순으로 분할 가능), 각 커밋 후 pytest + registry_hash + experiment_total_rows + governance validate_all() + protected-import 확인 + dashboard tsc 체크
2. **ARCHIVE 9개** → 삭제 없이 deprecated 마커 + 마이그레이션 노트 문서화만
3. STEP4(독립 유틸리티 제거) → STEP5(죽은 감사도구 archive, `research_agent_coordination`/`research_monitoring`/`research_reliability`/`research_resource_manager`/`research_strategy_generation`이 참조한 `security_audit` 클러스터 포함)로 계속
