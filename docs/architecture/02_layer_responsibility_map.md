# Layer Responsibility Map

| Phase | Package | Prefix | Responsibility |
|---|---|---|---|
| P21 | `production_readiness` | `pd_` | 배포 준비성·거버넌스 검토 기록 (VALIDATED != DEPLOYED) |
| P22 | `research_automation` | `ra_` | 연구 자동화 오케스트레이션 기록 (COMPLETED != VALIDATED) |
| P23 | `research_monitoring` | `rmon_` | 연구 생태계 건강·관측성 관찰 (OBSERVE != CONTROL) |
| P24 | `research_reliability` | `rel_` | 신뢰성 엔지니어링·복구 기록 (RECORD != REPAIR) |
| P25 | `autonomous_research` | `ar_` | 자율 연구 개선 루프·지식 생성 (KNOWLEDGE != TRADING) |
| P26 | `research_agent_coordination` | `racd_` | 연구 에이전트 협업 조정 (CONSENSUS != APPROVAL) |
| P27 | `research_memory_intelligence` | `rmi_` | 장기 연구 메모리 지능 (MEMORY DOES NOT DECIDE) |
| P28 | `research_insight_intelligence` | `rii_` | 연구 통찰·해석 (INSIGHT != DECISION) |
| P29 | `research_strategy_generation` | `rsg_` | 연구 전략 후보 생성 (GENERATED != SELECTED) |
| P30 | `meta_research_intelligence` | `mri_` | 연구 과정 메타 분석 (OBSERVATION != OPTIMIZATION) |
| P31 | `experiment_orchestration` | `exo_` | 실험 조정 기록 (ORCHESTRATION != EXECUTION) |
| P32 | `research_resource_manager` | `rrm_` | 연구 자원 추적 (RECORD != ALLOCATE) |
| P33 | `research_api_gateway` | `rgw_` | 통합 읽기 전용 API (GATEWAY != EXECUTION) |
| P34 | `research_dashboard_backend` | `rdb_` | 백엔드 집계 (AGGREGATION != DECISION) |
