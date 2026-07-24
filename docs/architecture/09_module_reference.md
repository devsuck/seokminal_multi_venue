# Module Reference

Every layer package exposes the same module surface:

- `models.py` — frozen dataclasses, deterministic IDs, hashing
- `ledger.py` — append-only JSONL readers/writers, READ ONLY source layers
- `engine.py` — record/observe/aggregate operations (no execution)
- `verify.py` — `verify_chain()` + `replay()` integrity
- `__main__.py` — read-only CLI

## Packages

- `jarvis.production_readiness` — `python -m jarvis.production_readiness`
- `jarvis.research_automation` — `python -m jarvis.research_automation`
- `jarvis.research_monitoring` — `python -m jarvis.research_monitoring`
- `jarvis.research_reliability` — `python -m jarvis.research_reliability`
- `jarvis.autonomous_research` — `python -m jarvis.autonomous_research`
- `jarvis.research_agent_coordination` — `python -m jarvis.research_agent_coordination`
- `jarvis.research_memory_intelligence` — `python -m jarvis.research_memory_intelligence`
- `jarvis.research_insight_intelligence` — `python -m jarvis.research_insight_intelligence`
- `jarvis.research_strategy_generation` — `python -m jarvis.research_strategy_generation`
- `jarvis.meta_research_intelligence` — `python -m jarvis.meta_research_intelligence`
- `jarvis.experiment_orchestration` — `python -m jarvis.experiment_orchestration`
- `jarvis.research_resource_manager` — `python -m jarvis.research_resource_manager`
- `jarvis.research_api_gateway` — `python -m jarvis.research_api_gateway`
- `jarvis.research_dashboard_backend` — `python -m jarvis.research_dashboard_backend`
