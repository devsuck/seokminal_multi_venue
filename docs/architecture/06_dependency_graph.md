# Dependency Graph

Strictly acyclic, single-direction (newer layer -> older layer, READ ONLY).

- `autonomous_research` -> ['production_readiness', 'research_automation', 'research_monitoring', 'research_reliability']
- `experiment_orchestration` -> ['autonomous_research', 'production_readiness', 'research_automation', 'research_reliability', 'research_strategy_generation']
- `meta_research_intelligence` -> ['autonomous_research', 'research_automation', 'research_insight_intelligence', 'research_memory_intelligence', 'research_monitoring', 'research_reliability', 'research_strategy_generation']
- `production_readiness` -> (no upstream jarvis deps)
- `research_agent_coordination` -> ['autonomous_research', 'research_automation', 'research_monitoring', 'research_reliability']
- `research_api_gateway` -> ['autonomous_research', 'experiment_orchestration', 'meta_research_intelligence', 'research_insight_intelligence', 'research_memory_intelligence', 'research_monitoring', 'research_reliability', 'research_resource_manager', 'research_strategy_generation']
- `research_automation` -> (no upstream jarvis deps)
- `research_dashboard_backend` -> ['autonomous_research', 'experiment_orchestration', 'meta_research_intelligence', 'research_agent_coordination', 'research_insight_intelligence', 'research_memory_intelligence', 'research_monitoring', 'research_reliability', 'research_resource_manager', 'research_strategy_generation']
- `research_insight_intelligence` -> ['autonomous_research', 'research_agent_coordination', 'research_memory_intelligence', 'research_monitoring', 'research_reliability']
- `research_memory_intelligence` -> ['autonomous_research', 'research_agent_coordination', 'research_automation', 'research_monitoring', 'research_reliability']
- `research_monitoring` -> ['production_readiness', 'research_automation']
- `research_reliability` -> ['production_readiness', 'research_automation', 'research_monitoring']
- `research_resource_manager` -> ['autonomous_research', 'experiment_orchestration', 'production_readiness', 'research_automation', 'research_strategy_generation']
- `research_strategy_generation` -> ['autonomous_research', 'research_insight_intelligence', 'research_memory_intelligence']
