# Layer-by-Layer Explanation

Each layer is an independent, additive package. This document explains the recent phases
(P12–P16) in depth and summarizes the foundations they build on.

## Foundations (P1–P11, pre-existing, READ ONLY)

- **Execution platform (P1–P8):** venue adapters, order lifecycle, execution controls,
  reconciliation, and the human-gated `live_execution` boundary. Disabled by default.
- **Research & governance (P9–P11):** research data, governance (access, model, policy,
  operational audit), memory, knowledge, and the first intelligence layers.

All subsequent phases treat these as stable production code and never modify them.

## P12 — Autonomous Research Infrastructure

| Layer | Package | Responsibility |
|---|---|---|
| P12.1 | `autonomous_research_pipeline` | Research cycle core (registry, objectives, cycles) |
| P12.2 | `autonomous_experiment_scheduler` | Experiment scheduling registry |
| P12.3 | `research_agent_coordinator` | Agent execution coordination (ownership events) |
| P12.4 | `adaptive_research_loop` | Adaptive research cycles |
| P12.5 | `autonomous_research_evaluation` | Evaluation registry |
| P12.6 | `research_optimization_engine` | Optimization studies |
| P12.7 | `research_experience_memory` | Experience, memories, episodes, lineage |
| P12.8 | `research_learning` | Learning loop (observe → lesson → improvement candidate) |
| P12.9 | `research_manager` | Plans, tasks, dependencies, progress, status reports |
| P12.10 | `research_control` | Control plane: state, health, metrics, anomaly alerts |

Each is event-sourced with its own lifecycle. Example lifecycles:

- `research_manager` plan: `CREATED → PLANNED → RUNNING → COMPLETED → REVIEWED → ARCHIVED`.
- `research_control` state: `INITIALIZED → OBSERVED → ANALYZED → REPORTED → ARCHIVED`. Anomaly
  alerts are **record-only** (`is_actionable=False`) — detection never triggers recovery.

## P13 — Autonomous Research OS

`autonomous_research_os` is the top-level integrator. It connects to every lower layer
**read-only**, records observation episodes, builds knowledge views (layer counts), and emits
**deterministic system snapshots**. Its lifecycle is
`INITIALIZED → CONNECTED → OBSERVING → ANALYZING → REPORTING → ARCHIVED`. It writes nothing to
source ledgers and holds no execution capability.

## P14 — Production Hardening

| Package | Responsibility |
|---|---|
| `benchmark` | Deterministic benchmarks (10 canonical ops), history, regression comparison |
| `cache` | Immutable, versioned read cache (copy-on-return, stats) |
| `concurrency` | Multi-reader / exclusive-append locks, atomic JSONL append, thread-safety checks |
| `resilience` | Crash recovery: scan, partial-replay, checkpoint validation, recover-to-new-file |
| `profiling` | CPU/memory/replay/graph/simulation profiling with injectable clocks |
| `diagnostics` | Dead/large ledger, slow replay, broken lineage, drift, perf-regression detection |

These are measurement/observation tools; they never modify original ledgers.

## P15 — Security & Compliance

| Package | Responsibility |
|---|---|
| `security` | Secret scanner + static security analysis (AST) + combined report |
| `compliance` | Security/repository/release/reproducibility checklists |
| `integrity` | Ledger integrity (chain/tamper/dup/timestamps/lineage/replay) + artifact validation |
| `sbom` | SBOM generation & verification (deterministic serial number) |
| `dependency` | Dependency scan, duplicate/unused/outdated, dependency graph |
| `license` | License inventory, distribution compatibility, third-party notice |
| `threat_model` | Assets, trust boundaries, attack surfaces, actors, risk matrix, residual risks |

## P16 — Documentation & Architecture

`documentation` provides doc validation (completeness, markdown, links, diagrams, API coverage)
and API auto-generation via introspection, plus this documentation tree. It executes nothing.

See `documentation/architecture/ledger-ownership-map.md` for the ledger inventory and
`documentation/architecture/dependency-map.md` for dependency relationships.
