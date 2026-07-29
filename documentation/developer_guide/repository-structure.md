# Repository Structure

The repository is organized as a single Python package root, `jarvis/`, containing
one subpackage per research layer. There are 111 such layers, spanning autonomous
research infrastructure, production hardening, and security & compliance. Every
layer is **additive and read-only** over the layers beneath it.

## Package-per-layer convention

Each layer lives in `jarvis/<layer_name>/` and follows a consistent internal shape.
Not every layer needs every file, but the typical set is:

- `__init__.py` — public surface of the layer; re-exports the stable API.
- `models.py` — frozen dataclasses (records, events, results) each with `to_dict()`.
- `ledger.py` — append-only, SHA256 hash-chained JSONL persistence for the layer.
- `engine.py` — deterministic analysis / recording logic; no side effects on trading.
- `verify.py` — verification and deterministic replay (`verify.replay(engine, now)`).
- `__main__.py` — argparse CLI, invoked as `python -m jarvis.<layer_name> <cmd>`.
- `tests/` — pytest suite for the layer, including forbidden-import and replay tests.

## The shared `_state/` directory

Ledgers are written into a shared `jarvis/_state/` directory. Each layer resolves
its own file path through `jarvis.config.state_path(name)`, which returns an
absolute path inside `_state/`. This directory holds the append-only JSONL ledgers
produced at runtime. Tests never write here: the `_iso` fixture monkeypatches each
layer's `ledger.state_path` to a `tmp_path`, keeping real state pristine.

## Notable layer groups

- **P12.x — Autonomous research infra:** `autonomous_research_pipeline`,
  `autonomous_experiment_scheduler`, `research_agent_coordinator`,
  `adaptive_research_loop`, `autonomous_research_evaluation`,
  `research_optimization_engine`, `research_experience_memory`,
  `research_learning`, `research_manager`, `research_control`.
- **P13 — `autonomous_research_os`:** top-level integration that composes the P12.x
  layers; strictly read-only over everything below it.
- **P14 — Production hardening:** `benchmark`, `cache`, `concurrency`, `resilience`,
  `profiling`, `diagnostics`.
- **P15 — Security & compliance:** `security`, `compliance`, `integrity`, `sbom`,
  `dependency`, `license`, `threat_model`.
- **P16 — Documentation:** `documentation`, which validates and generates docs.

## The `documentation/` tree

Human and generated documentation lives under `documentation/`:

- `documentation/developer_guide/` — guides like this one.
- `documentation/architecture/` — system architecture, e.g. `documentation/architecture/overview.md`.
- `documentation/api/` — generated API reference (`python -m jarvis.documentation gen`).
- `documentation/adr/` — architecture decision records.
- `documentation/operations/` and `documentation/user_guide/` — ops and user material.

The `jarvis.documentation` layer owns validation of everything in this tree.
