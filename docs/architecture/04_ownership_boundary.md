# Ownership Boundary Document

Each layer owns exactly one ledger prefix. Prefixes and packages are unique
(verified by P35). No layer may write to another layer's ledgers.

| Package | Owned prefix |
|---|---|
| `production_readiness` | `pd_` |
| `research_automation` | `ra_` |
| `research_monitoring` | `rmon_` |
| `research_reliability` | `rel_` |
| `autonomous_research` | `ar_` |
| `research_agent_coordination` | `racd_` |
| `research_memory_intelligence` | `rmi_` |
| `research_insight_intelligence` | `rii_` |
| `research_strategy_generation` | `rsg_` |
| `meta_research_intelligence` | `mri_` |
| `experiment_orchestration` | `exo_` |
| `research_resource_manager` | `rrm_` |
| `research_api_gateway` | `rgw_` |
| `research_dashboard_backend` | `rdb_` |

**Rule:** existing ownership boundaries are immutable. No migration, no overwrite.
