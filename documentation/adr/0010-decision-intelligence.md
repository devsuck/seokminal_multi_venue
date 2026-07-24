# ADR 0010 — Decision Intelligence

## Status

Accepted.

## Context

Research generates candidate strategies, hypotheses, and configurations. Choosing among them
must be structured, recorded, and reproducible — but a "decision" here must never become an
automatic action.

## Decision

Decision-making is modeled by `jarvis.decision_intelligence` (and related governance layers) as
**advisory, recorded decisions**. Candidates are scored using deterministic frameworks; decision
sessions and outcomes are written as hash-chained records. Decisions are non-binding
(`is_binding=False`) and are never executed by the research stack.

## Consequences

- **Traceable choices:** every decision has an auditable record of candidates, framework, and
  outcome; you can replay how a conclusion was reached.
- **No automatic action:** a recorded decision is an observation, not an instruction; acting on
  it is a separate, gated step (ADR 0004).
- **Reproducibility:** scoring is deterministic, so the same inputs yield the same ranking.
- **Consistency:** decision records share the ledger substrate, so integrity, lineage, and
  replay apply uniformly.
