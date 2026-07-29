# ADR 0007 — Knowledge Graph & Lineage

## Status

Accepted.

## Context

Research produces interrelated artifacts — plans, tasks, experiments, memories, episodes,
snapshots. To answer "where did this come from?" and "what depends on this?", relationships must
be first-class, queryable, and verifiable, without a heavyweight external graph database.

## Decision

Knowledge and provenance are modeled as **nodes and directed edges expressed in the ledgers
themselves**. Artifacts carry a `parent_artifact` link, forming lineage DAGs; knowledge layers
record nodes/edges as ordinary hash-chained records. Traversal (ancestors, topological order,
cycle detection) is implemented as **deterministic** pure functions.

## Consequences

- **No new infrastructure:** the graph lives in the same append-only, hash-chained ledgers as
  everything else; it inherits integrity and replay for free.
- **Verifiable lineage:** `jarvis.integrity` detects orphan/dangling parents and cycles;
  `jarvis.diagnostics` flags broken lineage.
- **Deterministic queries:** ancestor and topological traversals sort their frontier, so results
  are stable and reproducible.
- **Scale limits:** in-ledger graphs are ideal for research-scale provenance; very large graphs
  would need indexing, which is deferred until needed.
