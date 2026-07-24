# API Overview

The public API is organized **one package per layer** under `jarvis/`. There are 110 public
subpackages. Each layer exposes a small, stable surface: a public `__init__.py` that re-exports
the layer's engine, record dataclasses, and helper functions.

## How the API is documented

- **Auto-generated reference:** `documentation/api/reference.md` is produced by introspecting
  every package (`importlib` + `inspect`) via `python -m jarvis.documentation gen`. It lists,
  per package: the module, its one-line docstring, public classes (with methods), public
  functions, and whether it ships a CLI. Regenerate it whenever a package's public surface
  changes — the docs validation checks that core packages are covered.
- **CLI catalog:** `documentation/api/cli.md` lists the `python -m jarvis.<layer>` commands.
- **Configuration:** `documentation/api/configuration.md` documents environment and the autonomy
  gate.

## Common shapes across layers

Most layers follow the same public contract:

```python
from jarvis.<layer> import <Engine>, <Record>...   # public exports

eng = <Engine>()
rec = eng.<verb>(..., now="2026-07-24T00:00:00Z", commit=False)  # dry-run by default
rec.to_dict()                                                    # frozen dataclass → dict
```

- **Engines** are deterministic and event-sourced. Mutating methods take `commit: bool` (default
  `False` = dry-run) and a `now` timestamp used only in record fields, never in IDs.
- **Records** are frozen dataclasses with `to_dict()`.
- **Verification** lives in each layer's `verify` module: `verify_chain()`, `replay(engine, now)`.
- **CLIs** mirror the engine (`python -m jarvis.<layer> <verb> [--commit]`).

## Stability

The public API is **append-only**: new phases add packages and symbols but never rename or
remove existing ones. Backward compatibility is mandatory. See
`documentation/api/reference.md` for the full generated surface.
