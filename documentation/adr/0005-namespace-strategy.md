# ADR 0005 — Namespace Strategy (Phase 0 Collision Check)

## Status

Accepted.

## Context

With 100+ additive layers sharing one `_state/` directory and one `jarvis` package, name
collisions (package, ledger filename prefix, ID tag) would silently corrupt data or overwrite
code. We need a deterministic, mandatory procedure to guarantee disjoint namespaces.

## Decision

Every new layer begins with a **Phase 0 collision check** across: package name, ledger filename
prefix, ID-tag family, CLI name, and (for docs) documentation paths. If **any** collision
exists, implementation **stops**, the collision is reported, and a new, unused namespace is
chosen. Existing modules and files are never overwritten.

## Consequences

- **Disjoint ownership:** each layer's ledgers and IDs are provably unique (see
  `documentation/architecture/ownership-boundaries.md`).
- **Documented deviations:** when a preferred name was taken, the layer adopted an alternative —
  e.g. `resilience` instead of `recovery` (to avoid `recovery_control`), `autonomous_research_os`
  instead of `research_os`, and folding audit tooling into `dependency`/`license` instead of
  reusing the existing `audit` package.
- **Additive safety:** because names never collide, adding a layer cannot change the behavior of
  an existing one.
- **Overhead:** each phase spends effort up front scanning for collisions — an accepted cost for
  guaranteed isolation.
