# Jarvis Unified Navigation (P43)

기존 페이지/모듈을 단순 정보구조로 재배치(새 대시보드 없음, 기능 보존).

- 섹션 4 · 항목 10 · 모듈 142
- 커버리지 1.0 · 중복 페이지 계열 19
- digest `sha256:972006d2e34e9020`

```
Home
├─ Research (37)
│   ├ Alpha (32)
│   ├ Simulation (2)
│   ├ Experiments (3)
├─ Knowledge (14)
│   ├ Graph (1)
│   ├ Memory (6)
│   ├ Insights (7)
├─ Agents (11)
│   ├ Tasks (11)
│   ├ History (0)
├─ System (80)
│   ├ Monitoring (9)
│   ├ Configuration (71)
```

## 항목별 백킹 모듈

### Research
- **Alpha** (32): adaptive_research_loop, alpha_intelligence, autonomous_research, autonomous_research_evaluation, autonomous_research_os, autonomous_research_pipeline, causal_intelligence, decision_intelligence, fusion, meta_intelligence, meta_research_intelligence, planner, research_automation, research_data, research_event_bus, research_evolution, research_improvement, research_lifecycle, research_manager, research_navigation, research_optimization_engine, research_orchestration, research_organization, research_os, research_os_core, research_planning, research_reliability, research_risk_intelligence, research_strategy_generation, research_task_planner, research_validation, self_improvement_intelligence
- **Simulation** (2): paper, simulation_environment
- **Experiments** (3): experiment_manager, experiment_orchestration, experiment_tracking

### Knowledge
- **Graph** (1): research_kg
- **Memory** (6): governance_memory, memory, research_experience_memory, research_memory, research_memory_intelligence, research_memory_system
- **Insights** (7): continuous_learning, knowledge, knowledge_intelligence, knowledge_sharing, research_insight_intelligence, research_learning, research_literature

### Agents
- **Tasks** (11): agent_governance, agent_runtime, agents, research_agent_coordination, research_agent_coordinator, research_agents, research_collaboration, research_conflict_resolution, research_coordinator, research_council, research_reviewer
- **History** (0): —

### System
- **Monitoring** (9): benchmark, diagnostics, observability, profiling, research_monitoring, research_observability, research_observatory, resilience, system_health
- **Configuration** (71): access_governance, architecture_docs, audit, autonomous_experiment_scheduler, broker_readonly, cache, compliance, concurrency, data_governance, data_infrastructure, db, dependency, documentation, emergency, execution, execution_audit, execution_control, execution_cost, execution_readiness, execution_reconciliation, execution_risk, execution_simulation, fill_reconciliation, governance_evolution, governance_feedback, governance_orchestration, integration_audit, integrity, license, live_execution, live_market_data, local_runtime, market_data, model_governance, model_management, operational_audit, operations, operations_console, order_lifecycle, paper_execution, performance, permissions, policy_governance, portfolio, portfolio_research, post_trade_analytics, production, production_readiness, production_review, reconciliation, recovery_control, redteam, registry, release_candidate, research_api, research_api_gateway, research_compliance, research_control, research_control_plane, research_dashboard_backend, research_governance, research_operations, research_resource_manager, risk, sbom, security, security_audit, self_audit_intelligence, system_integration, threat_model, workflow_automation

## 중복·혼란 페이지 후보(같은 항목 동일 계열 ≥2)

- Agents/Tasks: agent_* → agent_governance, agent_runtime
- Agents/Tasks: research_* → research_agents, research_collaboration, research_coordinator, research_council, research_reviewer
- Agents/Tasks: research_agent_* → research_agent_coordination, research_agent_coordinator
- Knowledge/Insights: knowledge_* → knowledge, knowledge_intelligence, knowledge_sharing
- Knowledge/Insights: research_* → research_learning, research_literature
- Knowledge/Memory: research_memory_* → research_memory_intelligence, research_memory_system
- Research/Alpha: autonomous_research_* → autonomous_research_evaluation, autonomous_research_os, autonomous_research_pipeline
- Research/Alpha: research_* → research_automation, research_data, research_evolution, research_improvement, research_lifecycle, research_manager, research_navigation, research_orchestration, research_organization, research_os, research_planning, research_reliability, research_validation
- Research/Experiments: experiment_* → experiment_manager, experiment_orchestration, experiment_tracking
- System/Configuration: data_* → data_governance, data_infrastructure
- System/Configuration: execution_* → execution, execution_audit, execution_control, execution_cost, execution_readiness, execution_reconciliation, execution_risk, execution_simulation
- System/Configuration: governance_* → governance_evolution, governance_feedback, governance_orchestration
- System/Configuration: model_* → model_governance, model_management
- System/Configuration: operations_* → operations, operations_console
- System/Configuration: portfolio_* → portfolio, portfolio_research
- System/Configuration: production_* → production, production_readiness, production_review
- System/Configuration: research_* → research_api, research_compliance, research_control, research_governance, research_operations
- System/Configuration: security_* → security, security_audit
- System/Monitoring: research_* → research_monitoring, research_observability, research_observatory

## 기존 대시보드 패널 통합 매핑

- HEALTH → System
- KNOWLEDGE_SUMMARY → Knowledge
- MONITORING → System
- RESEARCH_PROGRESS → Research
- STATISTICS → Research
- TIMELINE → Research

> 기존 기능 보존 · 새 대시보드 생성 금지 · 재배치만 · 거래/집행/승인 없음.

