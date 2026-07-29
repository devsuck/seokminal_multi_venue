# Autonomous Quant Research OS — Documentation

Production-grade documentation for the **Autonomous Quant Research OS**: an additive,
**research / analysis / recording–only** intelligence layer built on top of an
execution-capable multi-venue trading platform.

This documentation lets a new developer understand the entire architecture **without
reading source code first**.

## What this system is (and is not)

- **Is**: an append-only, hash-chained, deterministic, event-sourced set of research,
  governance, intelligence, hardening, and security layers under the `jarvis/` package.
- **Is not**: a trading system. The research layers never place orders, trade, deploy
  strategies, allocate capital, promote models, or mutate permissions. Reports are
  **non-binding** (`is_binding=False`) — *VALIDATED never means deployed*.

## Core invariants

- **Additive only.** New phases add packages; they never modify existing modules,
  ledger schemas, public APIs, or ownership boundaries. Backward compatibility is mandatory.
- **Append-only ledgers.** Every layer owns SHA256 hash-chained JSONL ledgers written via
  `jarvis.config.state_path(name)` into a shared `_state/` directory.
- **Deterministic.** Deterministic IDs and replay; identical inputs produce identical output.
- **Read-only upstream.** Higher layers read lower layers' ledgers by file; they never write them.

## Documentation map

| Area | Path |
|---|---|
| Navigation index | `documentation/INDEX.md` |
| Architecture | `documentation/architecture/` |
| Architecture Decision Records | `documentation/adr/` |
| API reference (auto-generated) | `documentation/api/` |
| Diagrams (mermaid) | `documentation/diagrams/` |
| Developer guide | `documentation/developer_guide/` |
| Operations guide | `documentation/operations/` |
| User guide | `documentation/user_guide/` |
| Change history | `documentation/CHANGELOG.md` |

## Validate & regenerate

```bash
# Validate the whole documentation tree (completeness, markdown, links, diagrams, API coverage)
python -m jarvis.documentation validate

# Regenerate the API reference from live introspection
python -m jarvis.documentation gen
```

Documentation tooling lives in the additive package `jarvis/documentation/`
(validation + API auto-generation). It executes nothing and modifies no ledgers.
