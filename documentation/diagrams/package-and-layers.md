# Diagram — Package Hierarchy & Layer Dependency

## Package hierarchy (inside a layer)

```mermaid
flowchart LR
  M["models.py<br/>dataclasses · IDs · hashing · transitions"] --> L["ledger.py<br/>append-only accessors"]
  M --> E["engine.py"]
  L --> E
  M --> V["verify.py"]
  L --> V
  E --> CLI["__main__.py<br/>python -m jarvis.&lt;layer&gt;"]
  V --> CLI
  E --> T["tests/ (_iso fixture)"]
  V --> T
```

## Layer dependency (across the stack)

```mermaid
flowchart TB
  CFG["jarvis.config<br/>state_path · autonomy gate"]
  P12["P12 research infra"] --> CFG
  P13["P13 autonomous_research_os"] --> CFG
  P14["P14 hardening"] --> CFG
  P15["P15 security & compliance"] --> CFG
  P16["P16 documentation"] --> CFG
  P13 -. reads .-> P12
  P14 -. reads .-> P13
  P15 -. reads .-> P13
  P16 -. introspects .-> P15
  P16 -. introspects .-> P14
```

## Notes

- All layers depend only on the shared `jarvis.config` core and the standard library.
- Cross-layer arrows are **data reads**, not import-level coupling — no upward imports, no
  cross-layer mutation. See `documentation/architecture/dependency-map.md`.
