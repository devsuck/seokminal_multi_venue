# Architecture Decision Records

Architecture Decision Records (ADRs) capture the significant, hard-to-reverse decisions that
shape the Autonomous Quant Research OS. Each ADR states the context, the decision, and its
consequences. All ADRs here are **Accepted** and reflect the system as built.

## Index

- `documentation/adr/0001-append-only-ledgers.md` — Append-only ledgers
- `documentation/adr/0002-hash-chain-integrity.md` — Hash-chain integrity
- `documentation/adr/0003-research-only-architecture.md` — Research-only architecture
- `documentation/adr/0004-no-live-execution.md` — No live execution
- `documentation/adr/0005-namespace-strategy.md` — Namespace strategy (Phase 0)
- `documentation/adr/0006-replay-system.md` — Deterministic replay system
- `documentation/adr/0007-knowledge-graph.md` — Knowledge graph & lineage
- `documentation/adr/0008-automation-pipeline.md` — Autonomous research pipeline
- `documentation/adr/0009-security-architecture.md` — Security architecture
- `documentation/adr/0010-decision-intelligence.md` — Decision intelligence
- `documentation/adr/0011-simulation-environment.md` — Simulation environment

## Format

Each ADR uses: **Status**, **Context**, **Decision**, **Consequences**. Because the system is
additive, superseded decisions would be recorded as new ADRs rather than by editing existing
ones — no ADR is ever rewritten to change history.
