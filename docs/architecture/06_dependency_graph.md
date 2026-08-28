# Dependency Graph

Strictly acyclic, single-direction (newer layer -> older layer, READ ONLY).

- `autonomous_research` -> (no upstream jarvis deps)
- `experiment_orchestration` -> (no upstream jarvis deps)
- `meta_research_intelligence` -> (no upstream jarvis deps)
- `production_readiness` -> (no upstream jarvis deps)
- `research_agent_coordination` -> ['autonomous_research', 'research_automation', 'research_monitoring', 'research_reliability']
- `research_api_gateway` -> (no upstream jarvis deps)
- `research_automation` -> (no upstream jarvis deps)
- `research_dashboard_backend` -> (no upstream jarvis deps)
- `research_insight_intelligence` -> (no upstream jarvis deps)
- `research_memory_intelligence` -> ['autonomous_research', 'research_agent_coordination', 'research_automation', 'research_monitoring', 'research_reliability']
- `research_monitoring` -> ['production_readiness', 'research_automation']
- `research_reliability` -> ['production_readiness', 'research_automation', 'research_monitoring']
- `research_resource_manager` -> ['autonomous_research', 'experiment_orchestration', 'production_readiness', 'research_automation', 'research_strategy_generation']
- `research_strategy_generation` -> ['autonomous_research', 'research_insight_intelligence', 'research_memory_intelligence']
