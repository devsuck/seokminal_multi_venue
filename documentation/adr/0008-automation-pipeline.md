# ADR 0008 — Autonomous Research Pipeline

## Status

Accepted.

## Context

The system automates the research loop — scheduling experiments, coordinating agents, adapting,
evaluating, optimizing, and capturing lessons. Automation that could act on the world is
dangerous; automation must remain observational and reversible.

## Decision

The autonomous research pipeline is a chain of additive, event-sourced layers
(`autonomous_research_pipeline`, `autonomous_experiment_scheduler`, `research_agent_coordinator`,
`adaptive_research_loop`, `autonomous_research_evaluation`, `research_optimization_engine`,
`research_experience_memory`, `research_learning`), each of which only **observes, analyzes, and
records**. Improvement candidates are recorded, never auto-applied; alerts are record-only.
Everything is append-only and therefore fully reconstructable from history.

## Consequences

- **Reversibility:** because automation only appends records, any run can be reconstructed and
  audited; nothing is destructively changed.
- **Human/gated boundary:** the pipeline never crosses into execution; acting on a recorded
  recommendation is a separate, gated decision.
- **Composability:** each stage owns its ledgers and reads upstream stages read-only, so stages
  can evolve independently.
- **Cost:** the automation produces many records; diagnostics and large-ledger warnings help
  operators manage growth.
