# Research Agent Architecture (P121)

> Integration only — an AI research organization of **analysis-only** agents composing existing engines.
> Not trading agents, not execution agents, not investment-decision agents. **Human approval mandatory.**

## Role hierarchy
`Research Director → Specialist Agents (Market / Company / Strategy) → Critic (Reviewer) → Report (Writer)`

Every agent is `RESEARCH_ONLY`, `is_advisory=True`, `is_decision=False`, `requires_human_review=True`.

## AgentCapabilityMap — `jarvis/research_workflow/agent_capability.py`
`capability_map()` documents each agent: **Agent · Purpose · Input · Output · Used Engines**.

| Agent | Role | Output | Used engines |
|---|---|---|---|
| ResearchDirector (P122) | director | Research Plan | hypothesis_generator, experiment_planner, research_prioritizer, session_manager |
| MarketAnalyst (P123) | specialist | Market Research Memo | market_cockpit, regime, event_stream, opportunity_discovery, news_pipeline |
| CompanyAnalyst (P124) | specialist | Company Research Memo | fundamental_pipeline, earnings_intelligence, news_pipeline, insider_flow |
| StrategyResearcher (P125) | specialist | Strategy Research Plan | hypothesis_generator, experiment_planner, backtest_bridge, paper_validation |
| ResearchReviewer (P126) | critic | Research Review | research_critic, quality_monitor, risk failure_reasoning, failure taxonomy |
| ResearchWriter (P127) | report | Research Report | recall, decision_support, explainability |

## Existing agent framework (audited, reused — not duplicated)
- `jarvis/agents` — permission-bounded principals (`RESEARCH_ONLY`…): `research.propose`, `critic.review`,
  `backtest.run`, `datagate.check`.
- `research_council.ResearchCouncilEngine` (cnl_ ledger) + `research_assistant.council` /
  `council_evolution.deliberate` (7-perspective memo).
- `research_workflow.ResearchCritic` (P75, 8 dimensions) — upgraded by P126.

## Governance
No new database/ledger/engine/memory. Agents write only through existing paths
(`session_manager`→rwf_, `record_advisory`→ras_). Analysis only; no execute/trade/broker.

## Consumer
`/console/agent-capability-map`, `/console/agent-workspace`.
