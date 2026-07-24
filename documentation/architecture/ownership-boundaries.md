# Ownership Boundaries

Every layer **owns** a disjoint set of ledgers, identifier tags, and a package namespace.
Ownership is never transferred between layers. A later phase must claim a **free** namespace
(Phase 0 collision check) rather than extend or overwrite an existing one.

## What "ownership" means

A layer owns:

- **A package** under `jarvis/` (e.g. `jarvis/research_manager/`).
- **A physical ledger prefix** for its JSONL files (e.g. `rmgr_` for research_manager,
  `rctl_` for research_control, `aros_` for autonomous_research_os).
- **An identifier tag family** for deterministic record IDs (e.g. `RM*`, `CT*`, `AO*`).

No other layer writes to those ledgers or mints those IDs. This is what makes the system
safely composable: a layer's invariants cannot be violated by another layer.

## Phase 0 collision rule

Before implementing any new layer, a mandatory Phase 0 check verifies that the package name,
ledger filename prefix, and ID-tag family are all unused. If any collides, implementation
**stops** and a new namespace is chosen. Examples from history:

- Recovery hardening avoided the existing `recovery_control` package by naming itself
  `resilience`.
- The security/compliance phase avoided the existing `audit` package, folding audit
  functionality into `dependency` and `license`.
- The Research OS avoided the pre-existing `research_os` package and `ros_` prefix, choosing
  `autonomous_research_os` with the `aros_` prefix and `AO*` tags.

## Ownership examples (recent layers)

| Layer | Package | Ledger prefix | ID tags |
|---|---|---|---|
| research_manager (P12.9) | `jarvis/research_manager` | `rmgr_` | `RM*` |
| research_control (P12.10) | `jarvis/research_control` | `rctl_` | `CT*` |
| autonomous_research_os (P13) | `jarvis/autonomous_research_os` | `aros_` | `AO*` |
| benchmark (P14) | `jarvis/benchmark` | `bench_` (history only) | n/a |
| security/compliance (P15) | 7 packages | none (no persistence) | n/a |
| documentation (P16) | `jarvis/documentation` | none | n/a |

P14/P15/P16 tools are mostly **stateless** analysis tools: they read existing ledgers and
return dataclasses/reports without owning new persistent ledgers (except the benchmark
history file, which uses the isolated `bench_` prefix).

See `documentation/architecture/read-only-boundaries.md` for how layers safely read across
these boundaries, and `documentation/architecture/ledger-ownership-map.md` for the full map.
