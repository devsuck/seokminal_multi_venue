# 5. Duplicate / Overlap Analysis (중복·과중복 분석)

같은 이름 계열(family) ≥2 = 잠재 중복/책임 중첩 후보:

| Family | Category | Size | Members | Recommendation |
|---|---|---|---|---|
| agent_* | Agents | 2 | agent_governance, agent_runtime | 동일 카테고리 계열 — 통합 검토 권장 |
| autonomous_research_* | Research | 3 | autonomous_research_evaluation, autonomous_research_os, autonomous_research_pipeline | 동일 카테고리 계열 — 통합 검토 권장 |
| data_* | MIXED | 2 | data_governance, data_infrastructure | 다중 카테고리 계열 — 책임 경계 재검토 |
| execution_* | Execution | 8 | execution, execution_audit, execution_control, execution_cost, execution_readiness, execution_reconciliation, execution_risk, execution_simulation | 동일 카테고리 계열 — 통합 검토 권장 |
| experiment_* | Simulation | 3 | experiment_manager, experiment_orchestration, experiment_tracking | 동일 카테고리 계열 — 통합 검토 권장 |
| governance_* | MIXED | 4 | governance_evolution, governance_feedback, governance_memory, governance_orchestration | 다중 카테고리 계열 — 책임 경계 재검토 |
| knowledge_* | Knowledge | 3 | knowledge, knowledge_intelligence, knowledge_sharing | 동일 카테고리 계열 — 통합 검토 권장 |
| model_* | MIXED | 2 | model_governance, model_management | 다중 카테고리 계열 — 책임 경계 재검토 |
| operations_* | System | 2 | operations, operations_console | 동일 카테고리 계열 — 통합 검토 권장 |
| paper_* | MIXED | 2 | paper, paper_execution | 다중 카테고리 계열 — 책임 경계 재검토 |
| portfolio_* | Execution | 2 | portfolio, portfolio_research | 동일 카테고리 계열 — 통합 검토 권장 |
| production_* | System | 3 | production, production_readiness, production_review | 동일 카테고리 계열 — 통합 검토 권장 |
| research_* | MIXED | 29 | research_agents, research_api, research_automation, research_collaboration, research_compliance, research_control, research_coordinator, research_council, research_data, research_evolution, research_governance, research_improvement, research_kg, research_learning, research_lifecycle, research_literature, research_manager, research_memory, research_monitoring, research_observability, research_observatory, research_operations, research_orchestration, research_organization, research_os, research_planning, research_reliability, research_reviewer, research_validation | 다중 카테고리 계열 — 책임 경계 재검토 |
| research_agent_* | Agents | 2 | research_agent_coordination, research_agent_coordinator | 동일 카테고리 계열 — 통합 검토 권장 |
| research_memory_* | Knowledge | 2 | research_memory_intelligence, research_memory_system | 동일 카테고리 계열 — 통합 검토 권장 |
| security_* | System | 2 | security, security_audit | 동일 카테고리 계열 — 통합 검토 권장 |
| system_* | MIXED | 2 | system_health, system_integration | 다중 카테고리 계열 — 책임 경계 재검토 |
