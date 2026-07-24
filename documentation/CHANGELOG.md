# Changelog & Architecture History

This changelog records the **architecture history** of the Autonomous Quant Research OS.
Every phase is **additive**: it introduces new packages without modifying existing
modules, ledger schemas, public APIs, or ownership boundaries. Backward compatibility is
mandatory across all phases.

## Compatibility policy

- No existing file is modified, renamed, or removed by a later phase.
- No ledger schema changes; no public API breaks; no ownership transfers.
- Every new layer is research / analysis / recording only. No execution capability is ever
  introduced. `live_execution_enabled()` remains `False` by default (`AUTONOMY_LEVEL=5 < MIN_LIVE_LEVEL=6`).

## Layer history (recent phases)

### P12 — Autonomous Research Infrastructure
- P12.1 `autonomous_research_pipeline` — research pipeline core
- P12.2 `autonomous_experiment_scheduler` — experiment scheduling
- P12.3 `research_agent_coordinator` — agent execution coordination
- P12.4 `adaptive_research_loop` — adaptive research loop
- P12.5 `autonomous_research_evaluation` — evaluation layer
- P12.6 `research_optimization_engine` — optimization engine
- P12.7 `research_experience_memory` — experience & memory
- P12.8 `research_learning` — learning loop
- P12.9 `research_manager` — research plan/task/dependency/progress manager
- P12.10 `research_control` — research control plane (observe/health/anomaly, record-only)

### P13 — Autonomous Research OS
- `autonomous_research_os` — top-level integration; READ-ONLY connects every layer; builds
  knowledge views and deterministic system snapshots; observation + analysis + recording only.

### P14 — Production Hardening
- `benchmark`, `cache`, `concurrency`, `resilience`, `profiling`, `diagnostics` — deterministic
  benchmarking, immutable read cache, safe concurrency, crash recovery (originals immutable),
  profiling, and diagnostics.

### P15 — Security & Compliance
- `security`, `compliance`, `integrity`, `sbom`, `dependency`, `license`, `threat_model` —
  secret scanning, static analysis, ledger/artifact integrity, SBOM, dependency & license
  audit, compliance checklists, and a full threat model.

### P16 — Documentation & Architecture
- `documentation` (this phase) — documentation validation + API auto-generation tooling, plus
  the complete `documentation/` tree (architecture, ADRs, API, diagrams, guides).

## Milestones

- Full regression grew additively to **8600+ passing tests** by P15.
- All layers share the append-only hash-chained ledger substrate and deterministic replay.
- Security posture: self-clean secret/static scans; SBOM + dependency + license audits.

## Notes

Earlier phases (P1–P11) established the execution-capable platform and the first research,
governance, and intelligence layers. Those layers are stable production code and are treated
as READ ONLY by all subsequent phases.
