# Module & Package Dependency Map

This document describes how packages depend on one another. The dependency graph is
**shallow and acyclic**: layers depend on a tiny shared core and read peers' data by file,
not by import.

## Shared core

Almost every layer depends only on:

- `jarvis.config` — provides `state_path(name)` (ledger location) and the autonomy gate
  (`live_execution_enabled()`, `AUTONOMY_LEVEL`, `MIN_LIVE_LEVEL`).
- The Python standard library (`json`, `hashlib`, `dataclasses`, `argparse`, `os`, `re`).

Within a layer, the internal import order is:

```text
models.py  →  ledger.py  →  engine.py  →  verify.py  →  __main__.py
```

`models.py` has no intra-layer dependencies; `engine.py` imports `models` and `ledger`;
`verify.py` imports `models` and `ledger`; `__main__.py` wires them for the CLI.

## Cross-layer dependencies

Cross-layer relationships are **data dependencies, not import dependencies**. A layer names
the ledgers it reads in a `SOURCE_LEDGERS` / `SOURCE_LAYERS` map and reads those files. It does
not import the producing layer's engine. This avoids import cycles and prevents accidental
writes across boundaries.

Exceptions (intentional, within a phase):

- P15 `sbom` reads `dependency`'s scan output; `security.report` composes `security.secrets`
  and `security.static`. These are same-phase, additive, read-only compositions.
- P16 `documentation` imports nothing from research layers except via **introspection**
  (`importlib` + `inspect`) to auto-generate the API reference.

## Dependency rules

1. No layer imports a higher layer (no upward imports).
2. No layer imports another layer to mutate it (cross-layer access is file-read-only).
3. No research layer imports the execution boundary
   (`jarvis.execution`, `jarvis.live_execution`, `jarvis.broker`, `jarvis.order`,
   `jarvis.portfolio`, `jarvis.permissions`, `jarvis.deployment`). This is enforced by
   forbidden-import AST scans in each layer's test suite.

## Verifying the graph

- `python -m jarvis.dependency` and `jarvis.dependency.dependency_graph(edges)` build and
  cycle-check a dependency graph for external packages.
- Per-layer tests assert the absence of forbidden imports.

See `documentation/diagrams/package-and-layers.md` for the visual hierarchy.
